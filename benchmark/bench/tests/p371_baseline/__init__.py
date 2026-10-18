"""P371 phase 1b: the isolated pre-P371 baseline harness (A14). TEST-ONLY: production code never imports this package.

Layout: `bundle` (git archive of the baseline commit + manifest), `scenario` / `normalize` / `driver` (stdlib-only; copied
INTO the bundle and run there by a subprocess), `runner` (spawns the driver, loads scenarios and goldens, new-side stub),
`compare` (the plan's JSON-pointer table and the file-layout mapping), `scenarios/*.json`, `golden/*.json`."""
