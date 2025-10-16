import os
import json
import shutil
import tkinter as tk
from tkinter import ttk, messagebox
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
        self.root.geometry("700x500")

        self.config = load_config()
        self.hf_api = HfApi()
        self.models = []
        self.model_vars = {}

        # --- UI Elements ---
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

        # Frame for action buttons
        action_frame = ttk.Frame(root, padding="10")
        action_frame.pack(fill=tk.X)

        self.sync_button = ttk.Button(action_frame, text="Sync Models", command=self.sync_models)
        self.sync_button.pack(side=tk.RIGHT)

        self.status_label = ttk.Label(action_frame, text="Enter a username to begin.")
        self.status_label.pack(side=tk.LEFT)

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

        self.status_label.config(text=f"Loading models for {user}...")
        self.root.update_idletasks()

        try:
            self.models = list(self.hf_api.list_models(author=user))
        except Exception as e:
            messagebox.showerror("Error", f"Failed to fetch models: {e}")
            self.status_label.config(text="Failed to load models.")
            return

        self.display_models(user)

    def display_models(self, user):
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()

        self.model_vars = {}
        downloaded_models = self.config.get(user, [])

        for model in self.models:
            model_name = model.modelId
            var = tk.BooleanVar()
            var.set(model_name in downloaded_models)
            self.model_vars[model_name] = var

            cb = ttk.Checkbutton(self.scrollable_frame, text=model_name, variable=var)
            cb.pack(anchor=tk.W, padx=5, pady=2)

        self.status_label.config(text=f"Loaded {len(self.models)} models for {user}.")

    def sync_models(self):
        user = self.user_var.get().strip()
        if not user:
            messagebox.showerror("Error", "No user specified.")
            return

        self.status_label.config(text="Syncing models...")
        self.root.update_idletasks()

        currently_selected = {name for name, var in self.model_vars.items() if var.get()}
        previously_downloaded = set(self.config.get(user, []))

        to_download = currently_selected - previously_downloaded
        to_delete = previously_downloaded - currently_selected

        user_dir = os.path.join(BASE_DIR, user)
        os.makedirs(user_dir, exist_ok=True)

        # Download new models
        for i, model_name in enumerate(to_download, 1):
            target_dir = os.path.join(user_dir, model_name.replace("/", "__"))
            self.status_label.config(text=f"Downloading {model_name} ({i}/{len(to_download)})...")
            self.root.update_idletasks()
            try:
                snapshot_download(repo_id=model_name, local_dir=target_dir)
            except Exception as e:
                messagebox.showerror("Error", f"Failed to download {model_name}: {e}")

        # Delete unchecked models
        for i, model_name in enumerate(to_delete, 1):
            target_dir = os.path.join(user_dir, model_name.replace("/", "__"))
            self.status_label.config(text=f"Deleting {model_name} ({i}/{len(to_delete)})...")
            self.root.update_idletasks()
            if os.path.exists(target_dir):
                shutil.rmtree(target_dir)

        # Update config
        if user not in self.config:
            self.user_combobox['values'] = list(self.config.keys()) + [user]
        self.config[user] = list(currently_selected)
        save_config(self.config)

        self.status_label.config(text="Sync complete.")

if __name__ == '__main__':
    root = tk.Tk()
    app = App(root)
    root.mainloop()