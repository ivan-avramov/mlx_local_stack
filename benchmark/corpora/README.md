# benchmark/corpora

Committed prompt sets for benchmarks that don't load from Hugging Face at generation time.
`cjudge_v1.jsonl` (40 rows) is the role-C judge-panel corpus (M38, `docs/judge-panel-c.md`): 30 public prompts from `lmarena-ai/arena-hard-auto` v0.1 (apache-2.0) plus the 10 verbatim `dom-01..dom-10` domain prompts.
See `cjudge_v1.provenance.json` for the source revision, license, filter rules, pool size, seed and category counts.
`build_cjudge_v1.py` reproduces or rebuilds the jsonl deterministically.

`visionqa_v1.jsonl` (40 rows) is the vision-QA corpus (M39, `docs/vision-smoke-m39.md`): 15 ChartQA val (`HuggingFaceM4/ChartQA`, GPL-3.0, ids-only storage), 10 RICO ScreenQA-Short (`rootsautomation/RICO-ScreenQA-Short`, CC BY 4.0), 10 AI2D (`lmms-lab/ai2d`, CC BY-SA), 5 TextVQA val (`lmms-lab/textvqa` -- a parquet mirror of `facebook/textvqa`'s identical annotations, substituted to avoid `trust_remote_code=True` and a ~20GB image zip; see `visionqa_v1.provenance.json` for the rationale). Ids, questions and gold answers are committed; IMAGES ARE NEVER COPIED INTO THE REPO -- each row's `image_ref` is resolved against the local HF datasets cache at load time (`bench/benchmarks.py::_load_visionqa`). See `visionqa_v1.provenance.json` for source revisions, filters, seed and per-source counts.
`build_visionqa_v1.py` reproduces or rebuilds the jsonl deterministically.
