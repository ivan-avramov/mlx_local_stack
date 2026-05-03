import sys
import os
import shutil
import tarfile
import subprocess
import json
from datetime import datetime, timezone
import yaml

if len(sys.argv) < 2:
    sys.exit(f"Usage: {sys.argv[0]} <compose-file> [folder1] [folder2] ...")

compose_file = sys.argv[1]
target_folders = sys.argv[2:]

if not os.path.isfile(compose_file):
    sys.exit(f"Error: Compose file '{compose_file}' not found.")

# Create backup directory with UTC timestamp
timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
backup_dir = os.path.join(".", "backup", timestamp)
os.makedirs(backup_dir, exist_ok=True)

# Define paths for the dual-artifact approach
original_backup_path = os.path.join(backup_dir, f"{os.path.basename(compose_file)}.original")
resolved_backup_path = os.path.join(backup_dir, os.path.basename(compose_file))

# Copy the original file strictly for human reference
shutil.copy2(compose_file, original_backup_path)

# Parse the YAML into an Abstract Syntax Tree
with open(compose_file, 'r') as f:
    try:
        compose_data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        sys.exit(f"Error parsing YAML: {e}")

# Interrogate Docker and mutate the AST
services = compose_data.get('services', {})
for service_name, service_config in services.items():
    if 'image' not in service_config:
        continue

    image = service_config['image']

    try:
        result = subprocess.run(
            ["docker", "image", "inspect", image],
            capture_output=True, text=True, check=True
        )
        inspect_data = json.loads(result.stdout)
        digests = inspect_data[0].get('RepoDigests', [])

        if digests:
            # Replace the mutable tag with the immutable digest
            service_config['image'] = digests[0]
        else:
            print(f"Warning: No RepoDigest for '{image}' (likely a local build). Leaving unmodified.")
    except (subprocess.CalledProcessError, json.JSONDecodeError, IndexError):
        print(f"Warning: Failed to inspect image '{image}'. Leaving unmodified.")

# Write the resolved YAML execution artifact
with open(resolved_backup_path, 'w') as f:
    yaml.dump(compose_data, f, default_flow_style=False, sort_keys=False)

# Archive target folders if provided
if target_folders:
    tar_path = os.path.join(backup_dir, "data.tar.gz")
    with tarfile.open(tar_path, "w:gz") as tar:
        for folder in target_folders:
            if os.path.isdir(folder):
                # Use normpath to prevent absolute path extraction issues
                tar.add(folder, arcname=os.path.normpath(folder))
            else:
                print(f"Warning: Directory '{folder}' does not exist, skipping.")

print(f"Backup complete: {backup_dir}")
