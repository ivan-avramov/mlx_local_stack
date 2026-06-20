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


class MemorySampler:
    """Captures absolute peak system-used and (optionally) one PID's peak RSS while active.
    Reports system_peak_gb (absolute high-water mark seen during the sampling window).
    Footprint relative to an idle baseline is the caller's responsibility:
      footprint_gb = sampler.system_peak_gb - idle_baseline_gb"""

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
