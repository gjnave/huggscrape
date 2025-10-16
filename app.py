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
        self.root.geometry("700x700")

        self.config = load_config()
        self.hf_api = HfApi()
        self.models = []
        self.model_vars = {}

        # --- UI Elements ---
        self.setup_header(root)
        # Frame for user input
        input_frame = ttk.Frame(root, padding="10")
        input_frame.pack(fill=tk.X)

        ttk.Label(input_frame, text="Hugging Face User:").pack(side=tk.LEFT, padx=(0, 5))

        self.user_var = tk.StringVar()
        self.user_combobox = ttk.Combobox(input_frame, textvariable=self.user_var, width=30)
        self.user_combobox['values'] = list(self.config.keys())
        self.user_combobox.pack(side=tk.LEFT, expand=True, fill=tk.X)
        self.user_combobox.bind("<<ComboboxSelected>>", self.on_user_select)

        self.load_button = ttk.Button(input_frame, text="Load Models", command=self.load_models)
        self.load_button.pack(side=tk.LEFT, padx=(5, 0))

        # Frame for the model list
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

        # Frame for selection buttons
        selection_frame = ttk.Frame(root, padding=(10, 0, 10, 10))
        selection_frame.pack(fill=tk.X)

        self.select_all_button = ttk.Button(selection_frame, text="Select All", command=self.select_all)
        self.select_all_button.pack(side=tk.LEFT)

        self.unselect_all_button = ttk.Button(selection_frame, text="Unselect All", command=self.unselect_all)
        self.unselect_all_button.pack(side=tk.LEFT, padx=5)

        self.reset_button = ttk.Button(selection_frame, text="Reset", command=self.reset_selections)
        self.reset_button.pack(side=tk.LEFT)

        # Search bar
        search_frame = ttk.Frame(root, padding=(10, 0, 10, 10))
        search_frame.pack(fill=tk.X)
        ttk.Label(search_frame, text="Search:").pack(side=tk.LEFT, padx=(0, 5))
        self.search_var = tk.StringVar()
        self.search_var.trace("w", lambda name, index, mode: self.filter_models())
        self.search_entry = ttk.Entry(search_frame, textvariable=self.search_var)
        self.search_entry.pack(fill=tk.X, expand=True)

        # Filter radio buttons
        filter_frame = ttk.Frame(root, padding=(10, 0, 10, 10))
        filter_frame.pack(fill=tk.X)
        self.filter_var = tk.StringVar(value="All")
        ttk.Radiobutton(filter_frame, text="All", variable=self.filter_var, value="All", command=self.filter_models).pack(side=tk.LEFT)
        ttk.Radiobutton(filter_frame, text="Downloaded", variable=self.filter_var, value="Downloaded", command=self.filter_models).pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(filter_frame, text="Not Downloaded", variable=self.filter_var, value="Not Downloaded", command=self.filter_models).pack(side=tk.LEFT)

        # Frame for action buttons
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
        downloaded_models = self.config.get(user, [])
        for model_name, var in self.model_vars.items():
            var.set(model_name in downloaded_models)

    def on_user_select(self, event):
        self.load_models()

    def load_models(self):
        user = self.user_var.get().strip()
        if not user:
            messagebox.showerror("Error", "Please enter a Hugging Face username.")
            return

        self.load_button.config(state=tk.DISABLED)
        self.status_label.config(text=f"Loading models for {user}...")

        thread = threading.Thread(target=self._load_models_thread, args=(user,))
        thread.start()

    def _load_models_thread(self, user):
        try:
            self.models = list(self.hf_api.list_models(author=user))
            self.model_vars = {}
            downloaded_models = self.config.get(user, [])
            for model in self.models:
                model_name = model.modelId
                var = tk.BooleanVar()
                var.set(model_name in downloaded_models)
                self.model_vars[model_name] = var
            self.root.after(0, self.filter_models)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to fetch models: {e}")
            self.status_label.config(text="Failed to load models.")
        finally:
            self.load_button.config(state=tk.NORMAL)

    def display_models(self, user, search_term="", filter_mode="All"):
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()

        downloaded_models = self.config.get(user, [])

        for model in self.models:
            model_name = model.modelId
            is_downloaded = model_name in downloaded_models

            if search_term.lower() not in model_name.lower():
                continue

            if filter_mode == "Downloaded" and not is_downloaded:
                continue
            elif filter_mode == "Not Downloaded" and is_downloaded:
                continue

            container = ttk.Frame(self.scrollable_frame)
            container.pack(anchor=tk.W, fill=tk.X, expand=True)

            var = self.model_vars[model_name]
            cb = ttk.Checkbutton(container, variable=var)
            cb.pack(side=tk.LEFT)

            if is_downloaded:
                model_path = os.path.join(BASE_DIR, user, *model_name.split('/'))
                link = ttk.Label(container, text=model_name, foreground="blue", cursor="hand2")
                link.pack(side=tk.LEFT, padx=5)
                link.bind("<Button-1>", lambda e, path=model_path: self.open_folder(path))
            else:
                ttk.Label(container, text=model_name).pack(side=tk.LEFT, padx=5)

        self.status_label.config(text=f"Loaded {len(self.models)} models for {user}.")

    def open_folder(self, path):
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])

    def filter_models(self):
        user = self.user_var.get().strip()
        search_term = self.search_var.get().strip()
        filter_mode = self.filter_var.get()
        self.display_models(user, search_term, filter_mode)

    def sync_models(self):
        user = self.user_var.get().strip()
        if not user:
            messagebox.showerror("Error", "No user specified.")
            return

        self.sync_button.config(state=tk.DISABLED)
        self.status_label.config(text="Syncing models...")

        thread = threading.Thread(target=self._sync_models_thread, args=(user,))
        thread.start()

    def _sync_models_thread(self, user):
        try:
            currently_selected = {name for name, var in self.model_vars.items() if var.get()}
            previously_downloaded = set(self.config.get(user, []))

            to_download = currently_selected - previously_downloaded
            to_delete = previously_downloaded - currently_selected

            user_dir = os.path.join(BASE_DIR, user)
            os.makedirs(user_dir, exist_ok=True)

            # Download new models
            for i, model_name in enumerate(to_download, 1):
                target_dir = os.path.join(user_dir, *model_name.split('/'))
                self.root.after(0, self.status_label.config, {'text': f"Downloading {model_name} ({i}/{len(to_download)})..."})
                try:
                    snapshot_download(repo_id=model_name, local_dir=target_dir)
                except Exception as e:
                    messagebox.showerror("Error", f"Failed to download {model_name}: {e}")

            # Delete unchecked models
            for i, model_name in enumerate(to_delete, 1):
                target_dir = os.path.join(user_dir, *model_name.split('/'))
                self.root.after(0, self.status_label.config, {'text': f"Deleting {model_name} ({i}/{len(to_delete)})..."})
                if os.path.exists(target_dir):
                    shutil.rmtree(target_dir)

            # Update config
            if user not in self.config:
                self.root.after(0, self.user_combobox.config, {'values': list(self.config.keys()) + [user]})
            self.config[user] = list(currently_selected)
            save_config(self.config)

            self.root.after(0, self.status_label.config, {'text': "Sync complete."})
            self.root.after(0, self.filter_models)
        finally:
            self.root.after(0, self.sync_button.config, {'state': tk.NORMAL})

if __name__ == '__main__':
    root = tk.Tk()
    app = App(root)
    root.mainloop()