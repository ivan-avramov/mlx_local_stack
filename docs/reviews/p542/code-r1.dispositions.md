# P542 `qualify.py` for any registry entry — code review round 1 of 3: opinion + verify, dispositions

Material: `../mlx-vlm` `dev/p369_phase2/qualify.py` + `mlx_vlm/tests/test_p542_qualify_any.py` (the independent tests) and the amended
existing tests, spec `docs/specs/p542-qualify-any.md` v1.1 (opinion) / v1.3 (verify). Context: `briefed` (`change.diff`, `qualify.py`,
`registry_states.py` as `.txt`, `spec.md`; verify adds `repair.diff`, `tests-after.diff`). Budget: one opinion, one verify, both used.
Landed in fork `fd67082a`.

| Member | Runtime | Model (reported) | Session | Context | Opinion | Verify |
|---|---|---|---|---|---|---|
| sol | cursor-agent 2026.10.22 | `gpt-5.6-sol-high` (requested; not reported) | not reported | briefed, user instructions unconfirmed | 4 findings | fresh session: 8 / 9 resolved + 4 new |
| glm | cursor-agent 2026.10.22 | `glm-5.2-high` (requested; not reported) | not reported | briefed, user instructions unconfirmed | 4 findings + 1 scope request | fresh session: 2 minor, NOTHING OF SUBSTANCE |
| sonnet | claude CLI | `claude-sonnet-5-5` | `0fbc4d58-5458-49c5-8ef3-9fb5e726f63b` (resumed for verify) | briefed, user instructions suppressed; same vendor as the driver | 4 findings (did not read the last ~400 test lines) | 1 major (hypothesis) + 2 minor |

## Opinion ledger

| # | Finding | Raised by | Disposition |
|---|---|---|---|
| 1 | Registry TOCTOU: arms / gate from a pre-lock read, execution from a later read (MTP-ON without a gate) | sol (blocker), sonnet (minor) | Adopted (v1.2 / v1.3): one snapshot read right after the lock, used throughout; a differing later read or a moved stack HEAD refuses. |
| 2 | `served_on` MTP-ON not bound to the configuration P369 certified | sonnet (major) | Adopted, stronger (v1.2): the derived worker argv must equal the P369 run's `manifest.json` `picks[name].argv_on`; a difference refuses naming the first differing flag. |
| 3 | Production compared as a prefix, short vs full shas: a real full-sha summary refused on the default production; its test passed by construction | glm (major ×2) | Adopted (v1.2): both resolved to full shas in the fork and compared equal; realistic short / full tests. |
| 4 | Registry names used as filesystem paths (`/`, absolute, `..`) | sol (major) | Adopted (v1.2 / v1.3): safe id `<sanitized>-<sha8>`, every path under `--out`. |
| 5 | `mtp_off` removal regex too narrow (quoted keys, other indents); misleading refusal | sol (major), glm (minor) | Adopted (v1.2 / v1.3): YAML node marks; flow style refuses; failures name key + line. |
| 6 | "Served ON" by key presence, not by the drafter actually configured | sonnet (minor) | Adopted (v1.2): from `expected_config`'s drafter; partial / non-MTP blocks refuse. |
| 7 | `arm_for` restore without `name in registry_state` | glm (minor) | Adopted. |
| 8 | `rates` on a FAILED entry untested | sol (minor) | Adopted (test; behaviour already right). |
| 9 | Style slip `pre =orchestrate.preflight` | sonnet (minor) | Fixed in the repair. |
| S1 | Scope: pin `orchestrate.PRODUCTION`'s shape | glm | Dissolved by 3 (both sides resolved to full shas). |

## Verify ledger

All nine resolved (glm, sonnet; sol: 5 "not fully", see V4). New:

| # | Finding | Raised by | Disposition |
|---|---|---|---|
| V1 | Amended existing tests not updated for the repaired API (`resolve`, three-argument `_production_matches`, required `argv_on`) | sol (major) | Adopted: the existing tests and helpers updated; the fork gate at `fd67082a` PASS. |
| V2 | `--p369-summary name=path` cannot parse a name containing `/` | sol (major) | Adopted (v1.4): the text before the first `=` is a name when it is one of the `--entry` names. |
| V3 | An argv-certification mismatch became a per-entry FAILED, not a pre-run refusal; the test named "refuses" checked only that no job completed | sol (minor) | Adopted (v1.4): checked before the run (`SystemExit("refused: [...]")`); the test asserts the refusal and no report. |
| V4 | MTP keys inherited through a YAML merge key are missed (generic refusal) | sol (major) | Adopted (v1.4): refuse naming the key and its source line. |
| V5 | `argv_binding_problems` raises `TypeError` on a `None` certified argv; the manifest is read more than once | glm (minor ×2, hypothesis) | Adopted (v1.4): the certified argv is read once into the snapshot, used by the gate and the binding; missing → named refusal. |
| V6 | Real P369 manifests may not carry `picks[name].argv_on` in the tested shape | sonnet (major, hypothesis) | Resolved by measurement: C249 part (1) ran all three MTP-ON entries through the binding against their real P369 manifests (12 arms COMPLETED). |
| V7 | `expected_config` raises `TypeError` on a `null` integer key → traceback under the lock | sonnet (minor) | Adopted (v1.4): that entry refuses `<name>: <error>`. |
| V8 | Refusals now happen after the run lock is taken | sonnet (minor) | Accepted, spec-stated (v1.4): a second invocation fails at the lock with its existing message. |

Final: the fork gate PASS at `fd67082a` (receipt `mlx-vlm-fd67082a…-a54fac731bb1`); pushed at level full (C255).
