#!/usr/bin/env python3
"""Upload the three self-converted Qwen3.8-27B recipes to the hub (ruling 5, 2026-08-17).

Private repos under caslca/. Sequential, resumable (upload_folder skips already-uploaded
files by hash). Log lines go to stdout; drive with nohup.
"""
import os
import sys
import time

from huggingface_hub import HfApi

SRC = os.path.expanduser("~/ws/mlx_local_stack_workdir/optiq_out/Qwen3.8-27B-OptiQ-4bit")
RECIPES = [
    ("uniform_4bit", "caslca/Qwen3.8-27B-mlx-uniform-4bit"),
    ("static_mixed", "caslca/Qwen3.8-27B-static-mixed-4bit"),
    ("optiq_mixed", "caslca/Qwen3.8-27B-OptiQ-4.5bpw-mixed"),
]

api = HfApi()
for subdir, repo_id in RECIPES:
    folder = os.path.join(SRC, subdir)
    t0 = time.time()
    print(f"[{time.strftime('%F %T')}] START {repo_id} <- {folder}", flush=True)
    api.create_repo(repo_id, repo_type="model", private=True, exist_ok=True)
    api.upload_folder(
        folder_path=folder,
        repo_id=repo_id,
        repo_type="model",
        commit_message=f"Qwen3.8-27B self-converted recipe {subdir} (M5 Max, 2026-08-15)",
    )
    print(f"[{time.strftime('%F %T')}] DONE {repo_id} in {time.time()-t0:.0f}s", flush=True)
print("ALL UPLOADS COMPLETE", flush=True)
