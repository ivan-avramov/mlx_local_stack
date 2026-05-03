# Getting started
```sh
./runserver
```

or to just initalize the local python env:
```sh
git submodule update --init --recursive
uv sync
```

# update forked deps with
```sh
git submodule update --init --recursive --remote
```

# updating locally-checked-out packages
```sh
uv lock --upgrade    # re-resolves everything, rewrites uv.lock
uv sync              # applies the new lock to your .venv
```

# HuggingFace cache management
## download a model
```sh
uv run hf download mlx-community/gemma-4-31b-it-6bit
```

## run script to update all downloaded models
```sh
uv run hf_sync.py
```

## clean cache from stale versions - the ones we have a more recent version downloaded
```sh
uv run hf cache prune
```
