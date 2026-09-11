# benchmark/corpora

Committed prompt sets for benchmarks that don't load from Hugging Face at generation time.
`cjudge_v1.jsonl` (40 rows) is the role-C judge-panel corpus (M38, `docs/judge-panel-c.md`): 30 public prompts from `lmarena-ai/arena-hard-auto` v0.1 (apache-2.0) plus the 10 verbatim `dom-01..dom-10` domain prompts.
See `cjudge_v1.provenance.json` for the source revision, license, filter rules, pool size, seed and category counts.
`build_cjudge_v1.py` reproduces or rebuilds the jsonl deterministically.
