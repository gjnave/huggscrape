import os
import json
import shutil
import subprocess
import sys
import threading
import tkinter as tk
import webbrowser
from tkinter import ttk, messagebox, font
from huggingface_hub import HfApi, snapshot_download

CONFIG_FILE = 'config.json'
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def load_config():
    """Loads the configuration from config.json."""
    if not os.path.exists(CONFIG_FILE):
        return {}
    try:
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {}

def save_config(config):
    """Saves the configuration to config.json."""
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=4)

class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Hugging Face Model Downloader")
        self.root.geometry("900x760")  # a little taller and wider

        self.config = load_config()
        self.hf_api = HfApi()
        self.models = []
        self.model_vars = {}

        # Header
        self.setup_header(root)

        # Username input
        input_frame = ttk.Frame(root, padding="10")
        input_frame.pack(fill=tk.X)

        ttk.Label(input_frame, text="Hugging Face User:").pack(side=tk.LEFT, padx=(0, 5))

        self.user_var = tk.StringVar()
        self.user_combobox = ttk.Combobox(input_frame, textvariable=self.user_var, width=40)
        self.user_combobox['values'] = list(self.config.keys())
        self.user_combobox.pack(side=tk.LEFT, expand=True, fill=tk.X)
        self.user_combobox.bind("<<ComboboxSelected>>", self.on_user_select)

        self.load_button = ttk.Button(input_frame, text="Load Models", command=self.load_models)
        self.load_button.pack(side=tk.LEFT, padx=(5, 0))

        # Model list with scroll
        list_frame = ttk.Frame(root, padding="10")
        list_frame.pack(fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(list_frame)
        self.scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = ttk.Frame(self.canvas)

        self.scrollable_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        # Selection controls
        selection_frame = ttk.Frame(root, padding=(10, 0, 10, 10))
        selection_frame.pack(fill=tk.X)
        ttk.Button(selection_frame, text="Select All", command=self.select_all).pack(side=tk.LEFT)
        ttk.Button(selection_frame, text="Unselect All", command=self.unselect_all).pack(side=tk.LEFT, padx=5)
        ttk.Button(selection_frame, text="Reset", command=self.reset_selections).pack(side=tk.LEFT)

        # Search
        search_frame = ttk.Frame(root, padding=(10, 0, 10, 10))
        search_frame.pack(fill=tk.X)
        ttk.Label(search_frame, text="Search:").pack(side=tk.LEFT, padx=(0, 5))
        self.search_var = tk.StringVar()
        self.search_var.trace("w", lambda *args: self.filter_models())
        self.search_entry = ttk.Entry(search_frame, textvariable=self.search_var)
        self.search_entry.pack(fill=tk.X, expand=True)

        # Filters
        filter_frame = ttk.Frame(root, padding=(10, 0, 10, 10))
        filter_frame.pack(fill=tk.X)
        self.filter_var = tk.StringVar(value="All")
        ttk.Radiobutton(filter_frame, text="All", variable=self.filter_var, value="All", command=self.filter_models).pack(side=tk.LEFT)
        ttk.Radiobutton(filter_frame, text="Downloaded", variable=self.filter_var, value="Downloaded", command=self.filter_models).pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(filter_frame, text="Not Downloaded", variable=self.filter_var, value="Not Downloaded", command=self.filter_models).pack(side=tk.LEFT)

        # Actions
        action_frame = ttk.Frame(root, padding="10")
        action_frame.pack(fill=tk.X)

        self.sync_button = ttk.Button(action_frame, text="Sync Models", command=self.sync_models)
        self.sync_button.pack(side=tk.RIGHT)

        self.status_label = ttk.Label(action_frame, text="Enter a username to begin.")
        self.status_label.pack(side=tk.LEFT)

    def setup_header(self, root):
        header_frame = ttk.Frame(root, padding=(10, 10, 10, 0))
        header_frame.pack(fill=tk.X)

        bold_font = font.Font(weight="bold")
        small_font = font.Font(size=8)

        def open_url(url):
            webbrowser.open_new(url)

        get_going_fast_link = ttk.Label(header_frame, text="Get Going Fast", foreground="blue", cursor="hand2", font=bold_font)
        get_going_fast_link.pack()
        get_going_fast_link.bind("<Button-1>", lambda e: open_url("https://getgoingfast.pro"))

        ttk.Label(header_frame, text="Huggscraper", font=bold_font).pack()

        music_link = ttk.Label(header_frame, text="Listen to good music", foreground="blue", cursor="hand2", font=small_font)
        music_link.pack()
        music_link.bind("<Button-1>", lambda e: open_url("https://music.youtube.com/channel/UCGV4scbVcBqo2aVTy23JJeA"))

    # ---------- Helpers ----------
    def safe_dirname(self, model_id: str) -> str:
        """Convert repo id like user/repo into single folder name using __."""
        return model_id.replace('/', '__')

    def legacy_nested_path(self, user: str, model_id: str) -> str:
        """Legacy layout where repo parts became nested folders."""
        parts = model_id.split('/')
        return os.path.join(BASE_DIR, user, *parts)

    def resolve_model_path(self, user: str, model_id: str) -> str | None:
        """
        Resolve the on-disk folder for a model id.
        Order:
          1) Preferred: BASE_DIR/user/{user__repo}
          2) Case-insensitive match in BASE_DIR/user
          3) Legacy nested path BASE_DIR/user/user/repo
        Returns a path that exists, or None.
        """
        user_dir = os.path.join(BASE_DIR, user)
        safe_name = self.safe_dirname(model_id)

        # 1) Preferred
        p1 = os.path.join(user_dir, safe_name)
        if os.path.exists(p1):
            return p1

        # 2) Case-insensitive match in user_dir
        if os.path.isdir(user_dir):
            try:
                entries = os.listdir(user_dir)
                for entry in entries:
                    if entry.lower() == safe_name.lower():
                        p2 = os.path.join(user_dir, entry)
                        if os.path.exists(p2):
                            return p2
            except Exception:
                pass

        # 3) Legacy nested layout
        p3 = self.legacy_nested_path(user, model_id)
        if os.path.exists(p3):
            return p3

        return None

    # ---------- UI actions ----------
    def select_all(self):
        for var in self.model_vars.values():
            var.set(True)

    def unselect_all(self):
        for var in self.model_vars.values():
            var.set(False)

    def reset_selections(self):
        user = self.user_var.get().strip()
        if not user:
            return
        downloaded = self.config.get(user, [])
        for name, var in self.model_vars.items():
            var.set(name in downloaded)

    def on_user_select(self, event):
        self.load_models()

    def load_models(self):
        user = self.user_var.get().strip()
        if not user:
            messagebox.showerror("Error", "Please enter a Hugging Face username.")
            return

        self.load_button.config(state=tk.DISABLED)
        self.status_label.config(text=f"Loading models for {user}...")
        threading.Thread(target=self._load_models_thread, args=(user,)).start()

    def _load_models_thread(self, user):
        try:
            self.models = list(self.hf_api.list_models(author=user))
            self.model_vars = {}
            downloaded = self.config.get(user, [])
            for m in self.models:
                name = m.modelId
                var = tk.BooleanVar()
                var.set(name in downloaded)
                self.model_vars[name] = var
            self.root.after(0, self.filter_models)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to fetch models: {e}")
            self.status_label.config(text="Failed to load models.")
        finally:
            self.load_button.config(state=tk.NORMAL)

    def display_models(self, user, search_term="", filter_mode="All"):
        for w in self.scrollable_frame.winfo_children():
            w.destroy()

        downloaded = self.config.get(user, [])

        for m in self.models:
            name = m.modelId
            # Consider a model downloaded if either selected previously or folder exists
            has_folder = self.resolve_model_path(user, name) is not None
            is_downloaded = (name in downloaded) or has_folder

            if search_term.lower() not in name.lower():
                continue
            if filter_mode == "Downloaded" and not is_downloaded:
                continue
            if filter_mode == "Not Downloaded" and is_downloaded:
                continue

            container = ttk.Frame(self.scrollable_frame)
            container.pack(anchor=tk.W, fill=tk.X, expand=True)

            var = self.model_vars[name]
            ttk.Checkbutton(container, variable=var).pack(side=tk.LEFT)

            if is_downloaded:
                # Build link that resolves dynamically at click time
                link = ttk.Label(container, text=name, foreground="blue", cursor="hand2")
                link.pack(side=tk.LEFT, padx=5)
                link.bind("<Button-1>", lambda e, u=user, n=name: self.open_model_folder(u, n))
            else:
                ttk.Label(container, text=name).pack(side=tk.LEFT, padx=5)

        self.status_label.config(text=f"Loaded {len(self.models)} models for {user}.")

    def open_model_folder(self, user: str, model_id: str):
        path = self.resolve_model_path(user, model_id)
        if not path:
            # Helpful diagnostics if something is off
            user_dir = os.path.join(BASE_DIR, user)
            safe_name = self.safe_dirname(model_id)
            legacy = self.legacy_nested_path(user, model_id)
            messagebox.showerror(
                "Error",
                "Folder not found for this model.\n\n"
                f"Tried:\n"
                f"1) {os.path.join(user_dir, safe_name)}\n"
                f"2) Case-insensitive match in {user_dir}\n"
                f"3) {legacy}\n\n"
                "If you downloaded with an older version, try re-syncing."
            )
            return

        self.open_folder(path)

    def open_folder(self, path):
        if os.path.exists(path):
            if sys.platform == "win32":
                os.startfile(path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        else:
            messagebox.showerror("Error", f"Folder not found:\n{path}")

    def filter_models(self):
        user = self.user_var.get().strip()
        if not user:
            return
        search = self.search_var.get().strip()
        mode = self.filter_var.get()
        self.display_models(user, search, mode)

    def sync_models(self):
        user = self.user_var.get().strip()
        if not user:
            messagebox.showerror("Error", "No user specified.")
            return

        self.sync_button.config(state=tk.DISABLED)
        self.status_label.config(text="Syncing models...")
        threading.Thread(target=self._sync_models_thread, args=(user,)).start()

    def _sync_models_thread(self, user):
        try:
            selected = {n for n, v in self.model_vars.items() if v.get()}
            prev = set(self.config.get(user, []))
            to_download = selected - prev
            to_delete = prev - selected

            user_dir = os.path.join(BASE_DIR, user)
            os.makedirs(user_dir, exist_ok=True)

            # Download models into preferred layout user_dir/{user__repo}
            for i, name in enumerate(to_download, 1):
                safe_name = self.safe_dirname(name)
                target_dir = os.path.join(user_dir, safe_name)
                self.root.after(0, self.status_label.config, {'text': f"Downloading {name} ({i}/{len(to_download)})..."})
                try:
                    snapshot_download(
                        repo_id=name,
                        local_dir=target_dir,
                        local_dir_use_symlinks=False
                    )
                except Exception as e:
                    messagebox.showerror("Error", f"Failed to download {name}: {e}")

            # Delete unchecked models in both possible layouts
            for i, name in enumerate(to_delete, 1):
                self.root.after(0, self.status_label.config, {'text': f"Deleting {name} ({i}/{len(to_delete)})..."})

                # Preferred layout
                safe_name = self.safe_dirname(name)
                preferred_dir = os.path.join(user_dir, safe_name)
                if os.path.exists(preferred_dir):
                    shutil.rmtree(preferred_dir, ignore_errors=True)

                # Legacy layout
                legacy_dir = self.legacy_nested_path(user, name)
                if os.path.exists(legacy_dir):
                    shutil.rmtree(legacy_dir, ignore_errors=True)

            # Update config
            self.config[user] = list(selected)
            save_config(self.config)

            self.root.after(0, self.status_label.config, {'text': "Sync complete."})
            self.root.after(0, self.filter_models)
        finally:
            self.root.after(0, self.sync_button.config, {'state': tk.NORMAL})

if __name__ == '__main__':
    root = tk.Tk()
    app = App(root)
    root.mainloop()
