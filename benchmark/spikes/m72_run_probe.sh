#!/bin/zsh
# M72 1.1 probe launcher: NAX on / off / on (ABA) with 10-minute idles, then spikes G/H at 4-bit in both NAX states.
# Usage: zsh benchmark/spikes/m72_run_probe.sh <out_dir>   (run detached; exit code = first failing step)
set -u
out=$1; mkdir -p "$out"
export PYTHONPATH=../mlx-vlm
run() {  # name, env-assignment-or-empty, command...
  local name=$1 arch=$2; shift 2
  echo "[$(date +%H:%M:%S)] BEGIN $name arch=${arch:-default} $(pmset -g batt | grep -o '[0-9]*%')" >>"$out/launcher.log"
  if [[ -n $arch ]]; then MLX_METAL_GPU_ARCH=$arch "$@" >"$out/$name.log" 2>&1; else "$@" >"$out/$name.log" 2>&1; fi
  local rc=$?
  echo "[$(date +%H:%M:%S)] END $name rc=$rc" >>"$out/launcher.log"
  return $rc
}
idle() { echo "[$(date +%H:%M:%S)] IDLE 600s" >>"$out/launcher.log"; sleep 600; }
run probe-nax-on-1 "" uv run python benchmark/spikes/m72_tq4_probe.py --out "$out/probe-nax-on-1.json" || exit 11
idle
run probe-nax-off "applegpu_g16s" uv run python benchmark/spikes/m72_tq4_probe.py --out "$out/probe-nax-off.json" || exit 12
idle
run probe-nax-on-2 "" uv run python benchmark/spikes/m72_tq4_probe.py --out "$out/probe-nax-on-2.json" || exit 13
idle
[[ -n ${SKIP_SPIKES:-} ]] && { echo "[$(date +%H:%M:%S)] ALL DONE (spikes skipped)" >>"$out/launcher.log"; exit 0; }
export SPIKE_BITS=4
run spike-g-4bit "" uv run python benchmark/spikes/spike_g_decode_compute.py || exit 14
run spike-h-4bit "" uv run python benchmark/spikes/spike_h_decode_opt.py || exit 15
run spike-h-4bit-nax-off "applegpu_g16s" uv run python benchmark/spikes/spike_h_decode_opt.py || exit 16
echo "[$(date +%H:%M:%S)] ALL DONE" >>"$out/launcher.log"
