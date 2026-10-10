- **P5 / S1:** Added turn-1 rc=0, turn-2 rc=1 regression: leg FAILS.
- **P6 / S2:** Added mismatched-carrier test: `M50 tripwire: A4 v2 carrier destination differs from the verified router`.
- **P7 / S3:** Added wrong-version test: `REFUSED: A4 v2 requires opencode 2.0.20; got '2.0.19'`.

S1–S3: **3 failed with guards disabled → 3 passed restored**; enforcement already existed.

- **P8 / S4:** Destination row now requires exact CONTENT-overlay equality and exact file path.
- **P9 / S5:** Documented both disabled skill directories, re-enabling compatibility, and personal-config sampling migration.
- **P10 / N1:** Documented superpowers loading and first-use GitHub clone; retained entry.
- **P11 / N3:** Added process sessions, timeout group kill, and full-command-line survivor assertion. **2 mutation failures → green**; real-binary validation passed.
- **P12 / N4:** Added five-second settle, model metadata, validated URL forwarding, and PASS-only tmp cleanup. **5 pre-fix failures → green**; FAIL artifacts remain.

```text
configgen:       73 passed in 1.41s
gate/session:    45 passed in 4.85s
configgen check: exit 0
git diff --check: clean
```

Five allowed files modified; nothing staged or committed. HEAD remains `d2cd345`.