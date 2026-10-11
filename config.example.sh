# config.example.sh — machine-local settings kept OUT of the published repo.
#
# Preferred: `scripts/bootstrap_machine.sh --box <label>` generates this file with real paths and
# rebuilds the workdir + bench venv. Manual alternative: copy to
# ${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/config.sh and fill in your own paths/hosts. The orchestration + benchmark scripts source it so no absolute paths,
# usernames, or host aliases live in the repo. Each machine has its own copy.
#
#   mkdir -p ~/.config/mlx_local_stack
#   cp config.example.sh ~/.config/mlx_local_stack/config.sh
#   $EDITOR ~/.config/mlx_local_stack/config.sh

# Absolute path to THIS stack repo on this machine.
export STACK_REPO="${STACK_REPO:-$HOME/path/to/mlx_local_stack}"

# Out-of-repo artifacts (runs, transcripts, caches). Rebuild recipe: benchmark/README.md
# "Fresh machine"; raw evidence restores from the `evidence` branch.
export STACK_WORKDIR="${STACK_WORKDIR:-$HOME/path/to/mlx_local_stack_workdir}"
export POLYGLOT_DIR="${POLYGLOT_DIR:-$STACK_WORKDIR/polyglot-benchmark}"
export NLTK_DATA="${NLTK_DATA:-$STACK_WORKDIR/nltk_data}"

# Provenance label stamped into every manifest (bench/provenance.py). Rows from different boxes
# never pair; pick one label per machine and never reuse it.
export MLX_BOX="${MLX_BOX:-my-box-label}"

# The second benchmark box, reached over ssh (one model resident per machine).
export REMOTE_HOST="${REMOTE_HOST:-my-remote-host}"   # ssh alias (e.g. in ~/.ssh/config)
export REMOTE_USER="${REMOTE_USER:-remoteuser}"
export REMOTE_REPO="${REMOTE_REPO:-/home/remoteuser/path/to/mlx_local_stack}"
export REMOTE_HOME="${REMOTE_HOME:-/home/remoteuser}"

# Local model snapshot dirs that aren't resolvable from the HF hub (locally
# converted/distilled/quantized models). Leave empty if not present on this box.
export DISTILL_MODEL_PATH="${DISTILL_MODEL_PATH:-}"   # e.g. /path/to/models/<model>/<variant>
