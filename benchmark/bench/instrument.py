"""Memory + perf instrumentation for a benchmark run on the box under test.
MemorySampler polls system memory (and optionally one process's RSS) in a thread.
It tracks absolute peaks only; footprint-vs-idle is computed by the caller
(subtract the pre-preload idle baseline from system_peak_gb).
Mirrors mem_decompose.py's psutil-with-resource-fallback approach."""
import threading
from dataclasses import dataclass

GB = 1e9


def system_used_gb() -> float:
    import psutil
    vm = psutil.virtual_memory()
    return (vm.total - vm.available) / GB


def rss_gb(pid: int) -> float:
    try:
        import psutil
        return psutil.Process(pid).memory_info().rss / GB
    except Exception:
        import resource
        m = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return (m if m > 1e9 else m * 1024) / GB


def find_model_server_pid(pattern: str = "mlx_vlm.server") -> int | None:
    """PID of the model-serving subprocess (the process that actually holds the
    weights + KV), matched by `pattern` in its command line. One model loads at a
    time, so at most one matches; if several do, return the highest-RSS one (the real
    model process, not a wrapper). Returns None if psutil is unavailable or no match."""
    try:
        import psutil
    except Exception:
        return None
    best = None
    for p in psutil.process_iter(["pid", "cmdline", "memory_info"]):
        try:
            cmd = " ".join(p.info.get("cmdline") or [])
            if pattern in cmd:
                mi = p.info.get("memory_info")
                rss = mi.rss if mi else 0
                if best is None or rss > best[0]:
                    best = (rss, p.info["pid"])
        except Exception:
            continue
    return best[1] if best else None


def await_model_pid(finder=find_model_server_pid, sleeper=None, attempts: int = 10):
    """Best-effort wait for the model-server PID: look, sleep 1s, repeat up to `attempts`.

    Returns the pid, or None if it never appears (memory sampling is then disabled — every
    caller treats that as a warning, never an error). `finder`/`sleeper` are injectable so a
    test doesn't spend 10 real seconds discovering there is no model server; a `finder` that
    raises is swallowed, since psutil can blow up mid-iteration and this is best-effort.
    """
    if sleeper is None:
        import time
        sleeper = time.sleep
    for _ in range(attempts):
        try:
            pid = finder()
        except Exception:  # noqa: BLE001 — best-effort probe; never fatal
            pid = None
        if pid is not None:
            return pid
        sleeper(1)
    return None


class MemorySampler:
    """Captures, while active: the model process's peak RSS (peak_rss_gb, when a pid is
    given) and absolute peak system-used (system_peak_gb). peak_rss_gb is the model's
    ACTUAL resident footprint and is the capacity-gate metric. system_peak_gb is a
    secondary cross-check; footprint-vs-idle is the caller's job:
      system_footprint_gb = sampler.system_peak_gb - idle_baseline_gb"""

    def __init__(self, pid: int | None = None, interval: float = 0.2):
        self.pid = pid
        self.interval = interval
        self._peak_sys = system_used_gb()
        self._peak_rss = 0.0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _loop(self):
        while not self._stop.is_set():
            try:
                self._peak_sys = max(self._peak_sys, system_used_gb())
                if self.pid is not None:
                    self._peak_rss = max(self._peak_rss, rss_gb(self.pid))
            except Exception:
                pass
            self._stop.wait(self.interval)

    def __enter__(self):
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    @property
    def system_peak_gb(self) -> float:
        return round(self._peak_sys, 2)

    @property
    def peak_rss_gb(self) -> float:
        return round(self._peak_rss, 2)


@dataclass
class PerfRecord:
    ctx: int
    peak_rss_gb: float = 0.0
    model_footprint_gb: float = 0.0
    system_peak_gb: float = 0.0
    server_peak_gb: float | None = None
    prefill_s: float | None = None
    prefill_tps: float | None = None
    decode_tps: float | None = None
    prompt_tokens: int | None = None
    bottleneck: str = "unknown"
