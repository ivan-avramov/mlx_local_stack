"""
Spike C — GQA tile-reuse decode prototype.

Today's decode launches one threadgroup per *query* head and maps bh = bqh / R,
so all R query heads of a kv-head independently re-read the same packed K/V from
DRAM (R=6x redundant traffic for Qwen). At long context the KV does not fit in
cache, so this is real DRAM bandwidth.

ONE flash-decode kernel, swept over G = query-heads-served-per-threadgroup:
  G=1  -> one tg per q-head, K/V re-read per head        == today's baseline
  G=2,3,6 -> one tg per (kv-head, head-group); dequant K[t]/V[t] ONCE and serve
            all G heads from it  -> G x less DRAM traffic.
SG=16 simdgroups (512 threads); SG-agnostic reduction via a tgmem partial buffer.
Both produce out[n_q, D]; checked vs an fp32 dequant reference.
Run: PYTHONPATH=../mlx-vlm uv run python benchmark/spikes/spike_c_gqa.py
"""
import time
import numpy as np
import mlx.core as mx

D = 256
BITS = 3
N_KV = 4
R = 6
N_Q = N_KV * R          # 24
EPT = D // 32           # 8 dims per lane
SG = 16                 # simdgroups per threadgroup -> 512 threads
TG = SG * 32


def bench(fn, iters=20, warmup=5):
    for _ in range(warmup):
        mx.eval(fn())
    mx.synchronize()
    t0 = time.perf_counter()
    for _ in range(iters):
        mx.eval(fn())
    mx.synchronize()
    return (time.perf_counter() - t0) / iters


def make_kv(T, seed=0):
    rng = np.random.default_rng(seed)
    cb = np.linspace(-1.0, 1.0, 1 << BITS).astype(np.float32)
    pw = (D * BITS + 31) // 32

    def pack(unit):
        idx = np.abs(unit[..., None] - cb).argmin(-1).astype(np.uint64)
        packed = np.zeros((N_KV, T, pw), dtype=np.uint64)
        for d in range(D):
            bit = d * BITS; w = bit // 32; off = bit % 32
            packed[:, :, w] |= idx[:, :, d] << off
            if off + BITS > 32:
                packed[:, :, w + 1] |= idx[:, :, d] >> (32 - off)
        return mx.array(packed.astype(np.uint32)), idx

    ku = rng.standard_normal((N_KV, T, D)).astype(np.float32); ku /= np.linalg.norm(ku, axis=-1, keepdims=True)
    vu = rng.standard_normal((N_KV, T, D)).astype(np.float32); vu /= np.linalg.norm(vu, axis=-1, keepdims=True)
    kpk, kidx = pack(ku); vpk, vidx = pack(vu)
    knm = mx.array((np.abs(rng.standard_normal((N_KV, T))) + 0.5).astype(np.float16))
    vnm = mx.array((np.abs(rng.standard_normal((N_KV, T))) + 0.5).astype(np.float16))
    q = mx.array(rng.standard_normal((N_Q, D)).astype(np.float16))
    out_ref = np.zeros((N_Q, D), dtype=np.float32)
    qn = np.array(q.astype(mx.float32)); knm_n = np.array(knm.astype(mx.float32)); vnm_n = np.array(vnm.astype(mx.float32))
    for qh in range(N_Q):
        kv = qh // R
        kdeq = cb[kidx[kv]] * knm_n[kv][:, None]; vdeq = cb[vidx[kv]] * vnm_n[kv][:, None]
        sc = qn[qh] @ kdeq.T; sc -= sc.max(); w = np.exp(sc); w /= w.sum()
        out_ref[qh] = w @ vdeq
    return kpk, knm, vpk, vnm, q, mx.array(cb), pw, mx.array(out_ref)


def decode_kernel(G):
    groups = R // G
    return mx.fast.metal_kernel(
        name=f"dec_g{G}",
        input_names=["Q", "Kpacked", "Knorms", "Vpacked", "Vnorms", "cb"],
        output_names=["out"],
        source=f"""
    constexpr int EPT={EPT}; constexpr int BITS={BITS}; constexpr uint MASK={(1<<BITS)-1}u;
    constexpr int SG={SG}, G={G}, GROUPS={groups}, R={R}, DD={D};
    uint gid = threadgroup_position_in_grid.x;          // (kv-head, head-group)
    uint bh = gid / GROUPS; uint grp = gid % GROUPS; uint qbase = bh*R + grp*G;
    uint simd_gid = simdgroup_index_in_threadgroup;
    uint lane = thread_index_in_simdgroup;
    uint tid = thread_position_in_threadgroup.x;
    const device uint* kpk = Kpacked + bh*T*PW;
    const device half* knm = Knorms + bh*T;
    const device uint* vpk = Vpacked + bh*T*PW;
    const device half* vnm = Vnorms + bh*T;

    threadgroup float qsh[G*DD];
    for (uint i=tid; i<G*DD; i+=SG*32) qsh[i]=static_cast<float>(Q[qbase*DD + i]);
    threadgroup_barrier(mem_flags::mem_threadgroup);

    thread float o[G][EPT]={{}};
    float msc[G], sm[G];
    for(int r=0;r<G;r++){{msc[r]=-INFINITY; sm[r]=0;}}

    for (uint t=simd_gid; t<T; t+=SG) {{
        float kd[EPT];
        {{ const device uint* kp=kpk+t*PW;
           for(int i=0;i<EPT;i++){{uint d=lane*EPT+i;uint bit=d*BITS;uint w=bit>>5,off=bit&31;uint v=kp[w]>>off;if(off+BITS>32)v|=kp[w+1]<<(32-off);v&=MASK;kd[i]=cb[v];}} }}
        float kn=static_cast<float>(knm[t]);
        float vd[EPT];
        {{ const device uint* vp=vpk+t*PW;
           for(int i=0;i<EPT;i++){{uint d=lane*EPT+i;uint bit=d*BITS;uint w=bit>>5,off=bit&31;uint v=vp[w]>>off;if(off+BITS>32)v|=vp[w+1]<<(32-off);v&=MASK;vd[i]=cb[v];}} }}
        float vn=static_cast<float>(vnm[t]);
        for(int r=0;r<G;r++){{
            float sc=0; for(int i=0;i<EPT;i++) sc+=qsh[r*DD+lane*EPT+i]*kd[i];
            sc=simd_sum(sc)*kn;
            float nm=max(msc[r],sc); float corr=fast::exp(msc[r]-nm); float es=fast::exp(sc-nm);
            msc[r]=nm; sm[r]=sm[r]*corr+es;
            for(int i=0;i<EPT;i++) o[r][i]=o[r][i]*corr+es*vn*vd[i];
        }}
    }}
    // SG-agnostic reduction: each simdgroup holds a full [D] partial for its tokens
    threadgroup float ms[SG], ss[SG], red[SG*DD];
    for(int r=0;r<G;r++){{
        if(lane==0) ms[simd_gid]=msc[r];
        threadgroup_barrier(mem_flags::mem_threadgroup);
        float gmax=-INFINITY; for(int k=0;k<SG;k++) gmax=max(gmax, ms[k]);
        float corr=fast::exp(msc[r]-gmax);
        if(lane==0) ss[simd_gid]=sm[r]*corr;
        for(int i=0;i<EPT;i++) red[simd_gid*DD + lane*EPT + i]=o[r][i]*corr;
        threadgroup_barrier(mem_flags::mem_threadgroup);
        float gsum=0; for(int k=0;k<SG;k++) gsum+=ss[k];
        for(uint d=tid; d<DD; d+=SG*32){{
            float s=0; for(int k=0;k<SG;k++) s+=red[k*DD+d];
            out[(qbase+r)*DD + d] = gsum>0? s/gsum : 0;
        }}
        threadgroup_barrier(mem_flags::mem_threadgroup);
    }}
""")


KERN = {g: decode_kernel(g) for g in (1, 2, 3, 6)}


def run(T):
    kpk, knm, vpk, vnm, q, cb, pw, ref = make_kv(T)
    tmpl = [("T", T), ("PW", pw)]
    ins = [q, kpk, knm, vpk, vnm, cb]
    t_g1 = None
    for G in (1, 2, 3, 6):
        groups = R // G; kern = KERN[G]
        try:
            def call():
                return kern(inputs=ins, template=tmpl, grid=(N_KV*groups*TG, 1, 1), threadgroup=(TG, 1, 1),
                            output_shapes=[(N_Q, D)], output_dtypes=[mx.float32])[0]
            o = call(); mx.eval(o)
            diff = mx.max(mx.abs(o - ref)).item(); sec = bench(call)
            GB = (N_KV * groups * (T * pw * 4 * 2 + T * 2 * 2)) / 1e9   # packed K+V + norms read once per group
            if G == 1: t_g1 = sec
            sp = f"{t_g1/sec:.2f}x" if t_g1 else "-"
            tag = "baseline" if G == 1 else f"G={G}"
            print(f"  T={T:>7} {tag:9s} {sec*1e3:8.3f} ms  diff {diff:.4f}  {GB/sec:6.1f} GB/s  speedup {sp}")
        except Exception as e:  # noqa
            print(f"  T={T:>7} G={G}: {str(e)[:90]}")


if __name__ == "__main__":
    print("=" * 80)
    print(f"SPIKE C — GQA tile-reuse decode  ({mx.device_info()['device_name']})  "
          f"n_q={N_Q} n_kv={N_KV} R={R} D={D} bits={BITS} simdgroups={SG}")
    print("=" * 80)
    for T in (4096, 16384, 65536, 131072, 200000):
        run(T)
    print("\nDONE")
