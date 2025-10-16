import os
from huggingface_hub import HfApi, snapshot_download

# Ask for the Hugging Face username
user = input("Enter the Hugging Face username: ").strip()

# Set base directory to the script's folder
base_dir = os.path.dirname(os.path.abspath(__file__))

api = HfApi()
models = list(api.list_models(author=user))  # convert generator to list

print(f"\nFound {len(models)} models for user '{user}'.\n")

for i, model in enumerate(models, start=1):
    model_name = model.modelId.split("/")[-1]
    target_dir = os.path.join(base_dir, model_name)

    if os.path.exists(target_dir):
        print(f"[{i}/{len(models)}] Skipping {model.modelId} (already exists)")
        continue

    print(f"[{i}/{len(models)}] Downloading {model.modelId} to {target_dir}")
    snapshot_download(repo_id=model.modelId, local_dir=target_dir)

print("\n✅ All downloads complete.")
