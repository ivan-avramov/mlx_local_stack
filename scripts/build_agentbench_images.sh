#!/bin/bash
# M54: clone the pinned THUDM/AgentBench commit into $STACK_WORKDIR/agentbench and build the three
# os-std task images (local-os/default, local-os/packages, local-os/ubuntu) NATIVELY (aarch64) from
# its data/os_interaction/res/dockerfiles/*.
#
# MIRROR REWRITE (operator 2026-02-08): the upstream dockerfiles read
#   FROM docker.1ms.run/ubuntu
# -- a third-party mirror, unpinned tag. We do NOT pull from that mirror: each dockerfile is copied
# into the build dir and its FROM line is rewritten to a DIGEST-PINNED Docker Hub base,
#   FROM ubuntu:24.04@sha256:<UBUNTU_DIGEST>
# before `docker build` ever runs. 24.04 matches upstream `ubuntu:latest` at the 2026-02-08 pin
# date; a bare tag (even "22.04"/"24.04") is still a MOVING target (Canonical republishes the same
# tag with security patches), so cold-review F9 requires a digest. Resolving that digest needs a
# registry query (`docker manifest inspect ubuntu:24.04` or the Docker Hub API) that this
# agent/session is not allowed to run -- UBUNTU_DIGEST below is an OPERATOR-FILLED variable; the
# script refuses outright while it is empty, rather than silently falling back to a moving tag.
# The resolved digest (and why) is recorded in the images manifest this script writes, beside each
# image's `docker image inspect --format '{{.Id}}'`.
#
# Never run from this agent/session -- the operator runs this by hand when ready to build.
set -euo pipefail

AGENTBENCH_REPO="https://github.com/THUDM/AgentBench.git"
AGENTBENCH_SHA="d1e4a10db08c87075c78972e48ecc182be03e2d5"
MIRROR_FROM_LINE="FROM docker.1ms.run/ubuntu"
# OPERATOR: fill this in with `docker manifest inspect ubuntu:24.04 | ...` (or the Docker Hub API)
# before running -- e.g. UBUNTU_DIGEST="sha256:aabbcc...". The script refuses while this is empty.
UBUNTU_DIGEST="${UBUNTU_DIGEST:-}"
if [ -z "$UBUNTU_DIGEST" ]; then
  echo "build_agentbench_images: UBUNTU_DIGEST is empty -- resolve the current ubuntu:24.04 digest" \
       "(docker manifest inspect ubuntu:24.04, or the Docker Hub API) and pass it as" \
       "UBUNTU_DIGEST=sha256:... in the environment. Refusing to build against a moving tag." >&2
  exit 1
fi
PINNED_FROM_LINE="FROM ubuntu:24.04@${UBUNTU_DIGEST}"
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
    echo "# Rewritten by scripts/build_agentbench_images.sh (M54, 2026-02-08):"
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
  "$MIRROR_FROM_LINE" "$PINNED_FROM_LINE" "$UBUNTU_DIGEST" "$RECORDS_TSV" <<'PYEOF'
import json
import sys

manifest_path, repo, sha, platform, mirror_line, pinned_line, ubuntu_digest, tsv_path = sys.argv[1:]
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
    "base_image": "ubuntu:24.04",
    "base_image_digest": ubuntu_digest,
    "from_rewrite_reason": ("upstream dockerfiles pull FROM a third-party mirror "
                            "(docker.1ms.run) with an unpinned tag; rewritten to a DIGEST-PINNED "
                            "ubuntu:24.04 Docker Hub base before building, never pulled from "
                            "the mirror -- a bare tag is still a moving target"),
    "images": images,
}
with open(manifest_path, "w", encoding="utf-8") as f:
    json.dump(doc, f, indent=2)
    f.write("\n")
PYEOF

echo "build_agentbench_images: wrote $MANIFEST"
echo "build_agentbench_images: done -- ${IMAGE_NAMES[*]} built as local-os/<name>"
