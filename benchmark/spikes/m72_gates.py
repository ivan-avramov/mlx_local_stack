"""M72 probe idle-GPU gate (S20-P1, C313). No MLX import: the probe passes its own tiny-op callable.

Refuse a measured pass unless idle device utilization <= MAX_UTIL_PCT and a tiny MLX op's round trip <= MAX_FLOOR_MS.
Unreadable or unmeasured values refuse. Normal on the M5 Max: 0 % / 0.17-0.19 ms; the stuck-busy state read 100 % / ~1 ms.
"""

import re
import statistics
import subprocess
import time

MAX_UTIL_PCT = 5
MAX_FLOOR_MS = 0.5
_UTIL = re.compile(r'"Device Utilization %"=(\d+)')


def gpu_utilization():
    try:
        out = subprocess.run(["ioreg", "-r", "-c", "IOAccelerator", "-d", "1", "-k", "PerformanceStatistics"],
                             capture_output=True, text=True, timeout=10).stdout
    except Exception:
        return None
    vals = [int(v) for v in _UTIL.findall(out)]
    return max(vals) if vals else None


def tiny_op_floor_ms(op, n=200, clock=time.perf_counter):
    ts = []
    for _ in range(n):
        t0 = clock()
        op()
        ts.append((clock() - t0) * 1e3)
    return statistics.median(ts)


def gpu_idle_ok(state):
    util, floor = state.get("device_utilization_pct"), state.get("tiny_op_floor_ms")
    return util is not None and floor is not None and util <= MAX_UTIL_PCT and floor <= MAX_FLOOR_MS
