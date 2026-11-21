Findings, none above minor. I read the diff, test, and layout only and ran nothing, so everything below is hypothesis, not reproduction.

**1. Everything under `run/` is exempt, not only the records**
- Location: `benchmark/bench/modelnames.py`, `_M76_TG2_POSITIVES`.
- Severity: minor. Evidence: hypothesis, from the regex alone. The pattern is a prefix `.match` with nothing after `/run/`.
- Problem: the request says "exactly those `run/` records", but the boundary is the directory, not the record shape. Any file placed under `run/` is skipped: a `README.md`, a `NOTES.md`, a `.py` or `.sh` helper.
- Failure scenario: someone adds `positives-20261119-fail/run/NOTES.md` or `run/rust/summarize.py` containing `optiq` shorthand, and the pre-push check lets it through. <!-- allow-shorthand: quotes the flagged path segment -->
- Proposed change: anchor the tail to the real record shape, for example `run/[a-z0-9_+-]+/[^/]+\.manifest\.json$`. If other harvested file types such as logs or receipts live there, list their suffixes explicitly. If directory-level exemption is deliberate to match `_M76_WAVE2`'s `run|pairs`, say so in the comment and pin it with a test.

**2. The label charset is narrower than the sibling patterns**
- Location: `(-[a-z0-9]+)?` in the same regex.
- Severity: minor. Evidence: hypothesis. The layout shows only `-fail`.
- Problem: `_M76_WAVE2` and `_P426_WAVE2` accept `[a-z0-9][a-z0-9.-]*` for their labels, but this pattern does not. A label with a hyphen or dot, such as `positives-20261119-fail-rerun` or `positives-20261120-r2.1`, falls through to checked. The request writes the label as `[-<label>]` with no restriction.
- Failure scenario: a rerun directory with a hyphenated label is harvested, and its `optiq/metadata.json` inventory blocks the push again, the same failure this change fixes. <!-- allow-shorthand: quotes the flagged path segment -->
- Proposed change: use `(-[a-z0-9][a-z0-9.-]*)?`. The `\d{8}` before it still keeps the date strict.

**3. The test does not show the boundary the request describes**
- Location: the new test file.
- Severity: minor. Evidence: confirmed by reading.
- Problem:
  - Every parametrized case checks the same two sibling files, `README.md` and `positives.json`, at the positives root. Nothing checks prose or a script inside `run/`, so finding 1 passes silently and the test cannot say whether that is intended.
  - Nothing covers a multi-part label (finding 2).
  - The negative cases cover a wrong directory name, a bad date and a path outside `run/`, but not a crafted near-miss such as `positives-20261119-fail/run` as a file or `…/runs/…`.
- Proposed change:
  - Add a case for a non-record file under `run/` that asserts the intended outcome.
  - Add a hyphenated or dotted label case.
  - Add a `…/runs/x.manifest.json` negative.
  - Parametrize the sibling files once instead of repeating them per record.

Path traversal (`..`) is not a concern: git diff paths are normalized, and the `^` anchor pins the prefix.
