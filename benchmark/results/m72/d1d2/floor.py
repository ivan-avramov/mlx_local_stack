import time, statistics, mlx.core as mx
a = mx.ones((16,)); mx.eval(a)
ts=[]
for _ in range(200):
    t=time.perf_counter(); b=a+1; mx.eval(b); mx.synchronize(); ts.append((time.perf_counter()-t)*1e3)
print(f"tiny-op round trip: median {statistics.median(ts):.3f} ms, p10 {sorted(ts)[20]:.3f}, p90 {sorted(ts)[180]:.3f}")
