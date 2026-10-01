#!/bin/bash
# M54: clone the pinned THUDM/AgentBench commit into $STACK_WORKDIR/agentbench and build the three
# os-std task images (local-os/default, local-os/packages, local-os/ubuntu) NATIVELY (aarch64) from
# its data/os_interaction/res/dockerfiles/*.
#
# MIRROR REWRITE (operator 2026-09-30): the upstream dockerfiles read
#   FROM docker.1ms.run/ubuntu
# -- a third-party mirror, unpinned tag. We do NOT pull from that mirror: each dockerfile is copied
# into the build dir and its FROM line is rewritten to a pinned Docker Hub base,
#   FROM ubuntu:22.04
# before `docker build` ever runs. The rewrite (and why) is recorded again in the images manifest
# this script writes, beside each image's `docker image inspect --format '{{.Id}}'`.
#
# Never run from this agent/session -- the operator runs this by hand when ready to build.
set -euo pipefail

AGENTBENCH_REPO="https://github.com/THUDM/AgentBench.git"
AGENTBENCH_SHA="d1e4a10db08c87075c78972e48ecc182be03e2d5"
MIRROR_FROM_LINE="FROM docker.1ms.run/ubuntu"
PINNED_FROM_LINE="FROM ubuntu:22.04"
IMAGE_NAMES=(default packages ubuntu)
BUILD_PLATFORM="linux/arm64"

# --------------------------------------------------------------------------- STACK_WORKDIR
# Same resolution order as bench/paths.py stack_workdir(): STACK_WORKDIR env wins; else parse
# (by sourcing, like runserver.sh does with .env) ${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/config.sh.
if [ -z "${STACK_WORKDIR:-}" ]; then
  CFG="${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/config.sh"
  if [ -f "$CFG" ]; then
    set -a
    # shellcheck disable=SC1090
    . "$CFG"
    set +a
  fi
fi
if [ -z "${STACK_WORKDIR:-}" ]; then
  echo "build_agentbench_images: STACK_WORKDIR is not set and config.sh does not declare it" \
       "(AGENTS.md: no filesystem pollution outside \$STACK_WORKDIR). Export STACK_WORKDIR or" \
       "source config.sh." >&2
  exit 1
fi

CLONE_DIR="$STACK_WORKDIR/agentbench"
BUILD_DIR="$STACK_WORKDIR/agentbench_build"
MANIFEST="$BUILD_DIR/images.manifest.json"

echo "build_agentbench_images: STACK_WORKDIR=$STACK_WORKDIR"

# --------------------------------------------------------------------------- clone + pin
if [ ! -d "$CLONE_DIR/.git" ]; then
  echo "build_agentbench_images: cloning $AGENTBENCH_REPO -> $CLONE_DIR"
  git clone --quiet "$AGENTBENCH_REPO" "$CLONE_DIR"
fi
echo "build_agentbench_images: fetching + checking out $AGENTBENCH_SHA"
git -C "$CLONE_DIR" fetch --quiet origin "$AGENTBENCH_SHA"
git -C "$CLONE_DIR" checkout --quiet "$AGENTBENCH_SHA"
ACTUAL_SHA="$(git -C "$CLONE_DIR" rev-parse HEAD)"
if [ "$ACTUAL_SHA" != "$AGENTBENCH_SHA" ]; then
  echo "build_agentbench_images: checked out $ACTUAL_SHA, expected $AGENTBENCH_SHA" >&2
  exit 1
fi

SRC_DOCKERFILES="$CLONE_DIR/data/os_interaction/res/dockerfiles"
mkdir -p "$BUILD_DIR"

# --------------------------------------------------------------------------- rewrite + build
RECORDS_TSV="$BUILD_DIR/.images.tsv"
: > "$RECORDS_TSV"
for name in "${IMAGE_NAMES[@]}"; do
  src="$SRC_DOCKERFILES/$name"
  if [ ! -f "$src" ]; then
    echo "build_agentbench_images: missing upstream dockerfile $src" >&2
    exit 1
  fi
  first_line="$(head -n 1 "$src")"
  if [ "$first_line" != "$MIRROR_FROM_LINE" ]; then
    echo "build_agentbench_images: $src's first line is $(printf '%q' "$first_line"), expected" \
         "$(printf '%q' "$MIRROR_FROM_LINE") -- upstream changed; update the rewrite before building." >&2
    exit 1
  fi

  dest_dir="$BUILD_DIR/$name"
  mkdir -p "$dest_dir"
  dest="$dest_dir/Dockerfile"
  {
    echo "# Rewritten by scripts/build_agentbench_images.sh (M54, 2026-09-30):"
    echo "# upstream base was '$MIRROR_FROM_LINE' (unpinned third-party mirror); pinned to"
    echo "# '$PINNED_FROM_LINE' (Docker Hub) instead. Never built against the mirror."
    echo "$PINNED_FROM_LINE"
    tail -n +2 "$src"
  } > "$dest"

  image="local-os/$name"
  echo "build_agentbench_images: building $image from $dest (--platform $BUILD_PLATFORM)"
  docker build --platform "$BUILD_PLATFORM" -t "$image" "$dest_dir"
  image_id="$(docker image inspect --format '{{.Id}}' "$image")"
  echo "build_agentbench_images: built $image -> $image_id"
  printf '%s\t%s\t%s\t%s\n' "$name" "$image" "$image_id" \
    "data/os_interaction/res/dockerfiles/$name" >> "$RECORDS_TSV"
done

# --------------------------------------------------------------------------- manifest
# Built with python3 (already a hard dependency of this repo) rather than hand-quoted bash JSON --
# the one-field-per-tab-separated-line form above has no bash string-interpolation/quoting hazard.
python3 - "$MANIFEST" "$AGENTBENCH_REPO" "$AGENTBENCH_SHA" "$BUILD_PLATFORM" \
  "$MIRROR_FROM_LINE" "$PINNED_FROM_LINE" "$RECORDS_TSV" <<'PYEOF'
import json
import sys

manifest_path, repo, sha, platform, mirror_line, pinned_line, tsv_path = sys.argv[1:]
images = []
with open(tsv_path, encoding="utf-8") as f:
    for line in f:
        line = line.rstrip("\n")
        if not line:
            continue
        name, image, image_id, dockerfile = line.split("\t")
        images.append({"name": name, "image": image, "image_id": image_id,
                       "dockerfile": dockerfile,
                       "from_rewrite": {"upstream": mirror_line, "pinned": pinned_line}})
doc = {
    "upstream_repo": repo,
    "upstream_commit": sha,
    "build_platform": platform,
    "from_rewrite_reason": ("upstream dockerfiles pull FROM a third-party mirror "
                            "(docker.1ms.run) with an unpinned tag; rewritten to the pinned "
                            "ubuntu:22.04 Docker Hub base before building, never pulled from "
                            "the mirror"),
    "images": images,
}
with open(manifest_path, "w", encoding="utf-8") as f:
    json.dump(doc, f, indent=2)
    f.write("\n")
PYEOF

echo "build_agentbench_images: wrote $MANIFEST"
echo "build_agentbench_images: done -- ${IMAGE_NAMES[*]} built as local-os/<name>"
