import os, sys
from huggingface_hub import HfApi
api = HfApi(token=os.environ["HF_TOKEN"])
mode, repo, folder = sys.argv[1], sys.argv[2], sys.argv[3]
api.create_repo(repo, repo_type="model", private=False, exist_ok=True)
if mode == "large":
    api.upload_large_folder(repo_id=repo, folder_path=folder, repo_type="model")
else:
    api.upload_folder(repo_id=repo, folder_path=folder, repo_type="model",
                      commit_message="mirror of mlx-community/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit (insurance clone)")
print("UPLOAD DONE", repo)
