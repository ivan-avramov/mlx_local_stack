# P581 — cold review (opinion, round 1 of 1; C264)

Member: `sol`, cursor-agent, `gpt-5.6-sol-high`, context `briefed` (the commit diff `24041878`, the existing argv tests, test-writer finding P33), user instructions unconfirmed; exit 0.

| # | Finding (sol) | Severity / evidence | Disposition |
|---|---|---|---|
| P1 | An explicitly injected interpreter identical to the shebang's (mlx-serve altered to exec `[python, script, …]`) is indistinguishable from the kernel-added token | major / confirmed (trace) | **Declined — no material consequence**: the identical interpreter running the same script with the same arguments is the same execution (nothing a leg measures can differ); the alteration it needs is in mlx-serve, which the receipt pins as a clean source tree at the frozen gitlink in both arms; every behaviour-changing token (`-X`, a wrapper, another interpreter) still fails. Residual recorded: identical-interpreter injection is undetectable from post-exec argv. |
