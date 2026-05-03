from huggingface_hub import scan_cache_dir, snapshot_download
import sys

def sync_models():
    print("🔍 Scanning your local Hugging Face cache...")
    try:
        cache_info = scan_cache_dir()
    except Exception as e:
        print(f"❌ Error accessing cache: {e}")
        return

    repos = list(cache_info.repos)
    if not repos:
        print("📭 Your cache is empty. Try downloading Qwen 3.6 first!")
        return

    print(f"📦 Found {len(repos)} repositories. Checking for updates...\n")

    for i, repo in enumerate(repos, 1):
        # We strip the internal prefix and handle the repo type (model, dataset, etc.)
        repo_id = repo.repo_id
        repo_type = repo.repo_type

        print(f"[{i}/{len(repos)}] Checking {repo_type}: {repo_id}...")

        try:
            # snapshot_download is 'idempotent':
            # It pings HF, checks the latest commit hash, and ONLY downloads
            # new files if the model has been updated.
            snapshot_download(
                repo_id=repo_id,
                repo_type=repo_type,
                tqdm_class=None # Set to None for cleaner logs, or leave default for progress bars
            )
            print(f"   ✅ Up to date.")
        except Exception as e:
            print(f"   ⚠️  Could not sync {repo_id}: {e}")

    print("\n✨ Morning sync complete! Your models are at the latest published versions.")

if __name__ == "__main__":
    sync_models()
