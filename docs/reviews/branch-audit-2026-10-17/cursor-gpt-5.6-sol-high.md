P1 — Branch audit

`origin/main = eb78b6ef84fa69af36e60168ddae01385cfd28e1`

| branch | status | evidence |
|---|---|---|
| `c152-alloc-tool-scope-wip` | KEEP — UNMERGED CONTENT | Ancestor: no. Unique `a1e9901e` (+ cherry): parked C152 tool-scope redesign/P273 variant, 12 files, +377/−89. No equivalent patch-id; P273 later landed separately. |
| `g1-fix` | SAFE TO DELETE | Ancestor: yes, tip `90eee058`. G1 `5f9fdbc4`, revert `2dd80916`, replacement `90eee058`, and merge `b9e0ad7b` are all in main. |
| `m63-mtp-tg1-arm` | SAFE TO DELETE | Ancestor: yes, tip `10ab9a61`. |
| `m64-plan-review` | SAFE TO DELETE | Ancestor: yes, tip `eee9d94d`. |
| `p290-docker-preflight` | SAFE TO DELETE | Ancestor: yes, tip `6586a6ca`. |
| `p297-uncertain-gone` | KEEP — UNMERGED CONTENT | Ancestor: no. Parked after review rejected the uncertain-cleanup restart approach. Three genuinely absent commits: `510ad800` implementation/fixture/tests (+622/−2), `4e3a107a` review prompt, `fe626427` rejection/parking record. |
| `p311-lite` | SAFE TO DELETE | Ancestor: yes, tip `dc86b86b`. |
| `p348-audit` | SAFE TO DELETE | Ancestor: yes, tip `04ad9a74`. |
| `p351-runner-universe` | SAFE TO DELETE | Ancestor: yes, tip `2c405034`. |
| `p357-power-sim` | SAFE TO DELETE | Ancestor: yes, tip `b8b44eb0`. |
| `p359-wash` | SAFE TO DELETE | Ancestor: yes, tip `f5e889e0`. |
| `p364-datefreeze` | SAFE TO DELETE | Ancestor: yes, tip `2613b350`. |
| `sync-upstream-1015` | SAFE TO DELETE | Ancestor: yes, tip `18a7ff0f`. Operator-parked, but fully present in main. |
| `tg2-build` | SAFE TO DELETE | Ancestor: yes, tip `8c273d3a`. |
| `tg2-step2` | KEEP — ACTIVE | Ancestor: no. Three unique (+ cherry) commits: `38c2b5c2` materializer, `9f4948f6` universe/draw tooling, `bcca06a3` dependency union/vendor/pids-limit. |
| `origin/evidence` | KEEP — UNMERGED CONTENT | Ancestor: no. Orphan/root commit `e219a345` (+ cherry), containing 5,318 irreproducible evidence files totaling 86,326,750 bytes. |
| `origin/m64-plan-review` | SAFE TO DELETE | Ancestor: yes, tip `eee9d94d`; identical to local branch. |
| `m64-build` | KEEP — ACTIVE | Ancestor: yes; clean worktree at `eb78b6ef`, exactly current main. |
| detached `/private/tmp/mlx_parent_8b016` | SAFE TO DELETE | HEAD `5a4167c9` is an ancestor. Its modified `answer_key.py` and untracked C158 test match commit `8b016f8c` byte-for-byte, so no unique content would be lost. |

For completeness, `git log origin/main..p297-uncertain-gone` also showed 18 older commits with equivalent patch-ids already in main:

```text
cc07e8e3→2d97d65b  3df7347c→d256255b  b4a346a8→f268a131
ecaaa662→c75ed590  6d9a442b→eaee63ca  fb394a74→fd46db12
58a0779a→99294f35  c7630dfb→7b90019a  264347c4→96f3f8c2
bacb9cd0→c892cd2b  68910f8c→cebb9a79  e2929c0c→9778c60e
92c63700→5f35c246  2407c82b→c7046143  9f5729f2→9ff6faf2
bc8bf936→154bb5a5  061f6f19→80bb4834  a5707783→993c3cf8
```

P2 — Uncommitted worktree files

| worktree | material status |
|---|---|
| main | None; only ignored-for-audit `.tg2-test-tmp/**` stubs. |
| detached `/private/tmp/mlx_parent_8b016` | `M benchmark/bench/answer_key.py`; `?? benchmark/bench/tests/test_c158_auditors.py`. Both exactly preserved by `8b016f8c`. |
| `g1-fix`, `m64-build`, `p311-lite`, `p348-audit`, `p357-power-sim`, `p359-wash`, `p364-datefreeze`, `tg2-step2` | Only `.venv-bench`; ignored per request. |
| `p351-runner-universe`, `m64-plan-review` | Clean. |

AUDIT COMPLETE
