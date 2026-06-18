"""
Spike C v2 — GQA tile-reuse with a token-block split to PRESERVE occupancy.

v1 lesson: collapsing R heads into one threadgroup cut the threadgroup count and
regressed (occupancy-bound, ~46 GB/s). Real flash-decode keeps occupancy via many
token blocks. Here: 1 simdgroup per (head-group, block); huge block count -> full
occupancy regardless of G. Pass-1 writes per-(head,block) flash partials; the
cross-block online-softmax merge is done in mx. We compare, at equal occupancy:
  G=1  -> per-q-head reads K/V  (R x redundant)        == today's structure
  G=2,3,6 -> read K/V ONCE per (kv-head,block), serve G heads.
Run: PYTHONPATH=../mlx-vlm uv run python benchmark/spikes/spike_c2_blocksplit.py
"""
import time
import numpy as np
import mlx.core as mx

D = 256; BITS = 3; N_KV = 4; R = 6; N_Q = N_KV * R; EPT = D // 32
NB = 512  # token blocks -> occupancy


def bench(fn, iters=20, warmup=6):
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
    qn = np.array(q.astype(mx.float32)); kn = np.array(knm.astype(mx.float32)); vn = np.array(vnm.astype(mx.float32))
    for qh in range(N_Q):
        kv = qh // R
        kd = cb[kidx[kv]] * kn[kv][:, None]; vd = cb[vidx[kv]] * vn[kv][:, None]
        sc = qn[qh] @ kd.T; sc -= sc.max(); w = np.exp(sc); w /= w.sum()
        out_ref[qh] = w @ vd
    return kpk, knm, vpk, vnm, q, mx.array(cb), pw, mx.array(out_ref)


def pass1_kernel(G):
    groups = R // G
    return mx.fast.metal_kernel(
        name=f"p1_g{G}",
        input_names=["Q", "Kpacked", "Knorms", "Vpacked", "Vnorms", "cb"],
        output_names=["po", "lmax", "lsum"],
        source=f"""
    constexpr int EPT={EPT}, BITS={BITS}, G={G}, GROUPS={groups}, R={R}, DD={D}, NB={NB};
    uint gid = threadgroup_position_in_grid.x;
    uint block = gid % NB; uint ug = gid / NB;
    uint bh = ug / GROUPS; uint grp = ug % GROUPS; uint qbase = bh*R + grp*G;
    uint lane = thread_index_in_simdgroup;
    const device uint* kpk = Kpacked + bh*T*PW;
    const device half* knm = Knorms + bh*T;
    const device uint* vpk = Vpacked + bh*T*PW;
    const device half* vnm = Vnorms + bh*T;

    float qreg[G][EPT];
    for(int r=0;r<G;r++) for(int i=0;i<EPT;i++) qreg[r][i]=static_cast<float>(Q[(qbase+r)*DD+lane*EPT+i]);
    float o[G][EPT]; float msc[G], sm[G];
    for(int r=0;r<G;r++){{ msc[r]=-INFINITY; sm[r]=0; for(int i=0;i<EPT;i++) o[r][i]=0; }}

    uint tpb = (T + NB - 1) / NB;
    uint t0 = block*tpb; uint t1 = min(t0+tpb, (uint)T);
    for (uint t=t0; t<t1; t++) {{
        float kd[EPT];
        {{ const device uint* kp=kpk+t*PW;
           for(int i=0;i<EPT;i++){{uint d=lane*EPT+i;uint bit=d*BITS;uint w=bit>>5,off=bit&31;uint v=kp[w]>>off;if(off+BITS>32)v|=kp[w+1]<<(32-off);v&={(1<<BITS)-1}u;kd[i]=cb[v];}} }}
        float kn=static_cast<float>(knm[t]);
        float vd[EPT];
        {{ const device uint* vp=vpk+t*PW;
           for(int i=0;i<EPT;i++){{uint d=lane*EPT+i;uint bit=d*BITS;uint w=bit>>5,off=bit&31;uint v=vp[w]>>off;if(off+BITS>32)v|=vp[w+1]<<(32-off);v&={(1<<BITS)-1}u;vd[i]=cb[v];}} }}
        float vnn=static_cast<float>(vnm[t]);
        for(int r=0;r<G;r++){{
            float sc=0; for(int i=0;i<EPT;i++) sc+=qreg[r][i]*kd[i];
            sc=simd_sum(sc)*kn;
            float nm=max(msc[r],sc); float corr=fast::exp(msc[r]-nm); float es=fast::exp(sc-nm);
            msc[r]=nm; sm[r]=sm[r]*corr+es;
            for(int i=0;i<EPT;i++) o[r][i]=o[r][i]*corr+es*vnn*vd[i];
        }}
    }}
    for(int r=0;r<G;r++){{
        uint h=qbase+r;
        for(int i=0;i<EPT;i++) po[(h*NB+block)*DD + lane*EPT + i]=o[r][i];
        if(lane==0){{ lmax[h*NB+block]= (t1>t0)? msc[r] : -1e30f; lsum[h*NB+block]=sm[r]; }}
    }}
""")


KERN = {g: pass1_kernel(g) for g in (1, 2, 3, 6)}


def merge(po, lmax, lsum):
    gmax = mx.max(lmax, axis=1, keepdims=True)          # [N_Q,1]
    corr = mx.exp(lmax - gmax)                          # [N_Q,NB]
    gsum = mx.sum(lsum * corr, axis=1, keepdims=True)   # [N_Q,1]
    num = mx.sum(po * corr[:, :, None], axis=1)         # [N_Q,D]
    return num / gsum


def run(T):
    kpk, knm, vpk, vnm, q, cb, pw, ref = make_kv(T)
    tmpl = [("T", T), ("PW", pw)]; ins = [q, kpk, knm, vpk, vnm, cb]
    t_g1 = None
    for G in (1, 2, 3, 6):
        groups = R // G; kern = KERN[G]
        try:
            def call():
                po, lmax, lsum = kern(inputs=ins, template=tmpl,
                                      grid=(N_KV*groups*NB*32, 1, 1), threadgroup=(32, 1, 1),
                                      output_shapes=[(N_Q, NB, D), (N_Q, NB), (N_Q, NB)],
                                      output_dtypes=[mx.float32, mx.float32, mx.float32])
                return merge(po, lmax, lsum)
            o = call(); mx.eval(o)
            diff = mx.max(mx.abs(o - ref)).item(); sec = bench(call)
            GB = (N_KV * groups * (T * pw * 4 * 2 + T * 2 * 2)) / 1e9
            if G == 1: t_g1 = sec
            sp = f"{t_g1/sec:.2f}x" if t_g1 else "-"
            tag = "baseline(Rx)" if G == 1 else f"G={G} read-once"
            print(f"  T={T:>7} {tag:16s} {sec*1e3:8.3f} ms  diff {diff:.4f}  {GB/sec:6.1f} GB/s  speedup {sp}")
        except Exception as e:  # noqa
            print(f"  T={T:>7} G={G}: {str(e)[:90]}")


if __name__ == "__main__":
    print("=" * 82)
    print(f"SPIKE C v2 — block-split GQA tile-reuse  ({mx.device_info()['device_name']})  "
          f"R={R} D={D} bits={BITS} NB={NB} (peak~310GB/s)")
    print("=" * 82)
    for T in (16384, 65536, 131072, 200000):
        run(T)
    print("\nNote: GB/s counts K+V packed read once per (kv-head,block). For G=1 the same"
          "\nkv-head is read R=6x across its q-heads; speedup ~ read-traffic reduction.")
    print("DONE")
