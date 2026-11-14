"""M76 B5 erratum v1.5: the offline token counter counts token ids whatever `apply_chat_template(tokenize=True)` returns (a list
or a `BatchEncoding`-like mapping), refuses a non-positive count and a calibration outside 1 … 10 chars / token, names the
transformers version, and (v1.5a) a generated A5 prompt's frozen count lies within [−3 %, 0 %] of its rung target, never above
it, with the deviation per cell recorded. A real tokenizer from the
local HF cache where one is available offline; a stand-in otherwise. CPU only, no request."""
from __future__ import annotations

import math
from collections import UserDict

import pytest

from bench import m76_ids as M

ENTRY = "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed"
CPT = 3.6   # the stand-in's chars per token


class FakeBatchEncoding(UserDict):
    """transformers 5's `BatchEncoding` shape: a UserDict (not a dict) of input_ids / attention_mask."""


class StandIn:
    """A tokenizer whose chat template yields ceil(chars / CPT) ids (no template overhead), returned as `mode`."""

    chat_template = "{{ stand-in }}"

    def __init__(self, mode="batch", n=None, overhead=0):
        self.mode, self.n, self.overhead = mode, n, overhead

    def apply_chat_template(self, messages, add_generation_prompt=True, tokenize=True):
        assert tokenize and add_generation_prompt
        chars = sum(len(m["content"]) for m in messages)
        ids = list(range(self.n if self.n is not None else math.ceil(chars / CPT) + self.overhead))
        if self.mode == "list":
            return ids
        if self.mode == "batched":
            return FakeBatchEncoding(input_ids=[ids], attention_mask=[[1] * len(ids)])
        return FakeBatchEncoding(input_ids=ids, attention_mask=[1] * len(ids))


def _real_tokenizer():
    transformers = pytest.importorskip("transformers", reason="transformers is not installed in this venv")
    from bench.model_params import _registry_models

    hf = (_registry_models().get(ENTRY) or {}).get("hf_path") or ENTRY
    try:
        return transformers.AutoTokenizer.from_pretrained(hf, local_files_only=True)
    except Exception as exc:   # noqa: BLE001 — absent from the local HF cache
        pytest.skip(f"{hf} tokenizer is not in the local HF cache ({type(exc).__name__})")


@pytest.fixture(scope="module")
def real_tok():
    return _real_tokenizer()


# --- token_count -----------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("encoded", [[5, 6, 7], (5, 6, 7), FakeBatchEncoding(input_ids=[5, 6, 7], attention_mask=[1, 1, 1]),
                                     {"input_ids": [5, 6, 7], "attention_mask": [1, 1, 1]},
                                     FakeBatchEncoding(input_ids=[[5, 6, 7]], attention_mask=[[1, 1, 1]])])
def test_token_count_counts_ids_whatever_the_type(encoded):
    assert M.token_count(encoded) == 3


@pytest.mark.parametrize("encoded", [[], FakeBatchEncoding(input_ids=[], attention_mask=[]), FakeBatchEncoding(foo=[1, 2]),
                                     "abc", 3, [1.0, 2.0], [True], [[1, 2], [3, 4]]])
def test_token_count_refuses_non_positive_or_non_ids(encoded):
    with pytest.raises(M.IdsError):
        M.token_count(encoded)


# --- offline_counter (stand-in) --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("mode", ["batch", "list", "batched"])
def test_offline_counter_counts_input_ids_not_keys(mode):
    count, cpt, meta = M.offline_counter(tokenizer=StandIn(mode))
    assert count([{"role": "user", "content": "x" * 36}]) == 10
    assert cpt == pytest.approx(CPT, rel=1e-3)
    assert meta["chars_per_token"] == cpt


def test_offline_counter_refuses_insane_calibration():
    with pytest.raises(M.IdsError, match="calibration"):
        M.offline_counter(tokenizer=StandIn(n=2))          # the transformers-5 symptom: ≈ 7,400 chars / token
    with pytest.raises(M.IdsError, match="calibration"):
        M.offline_counter(tokenizer=StandIn(n=100_000))    # < 1 char / token


@pytest.mark.parametrize("cpt", [0.99, 10.01, float("nan"), None, True])
def test_check_calibration_range(cpt):
    with pytest.raises(M.IdsError):
        M.check_calibration(cpt)


@pytest.mark.parametrize("cpt", [1.0, 4.55, 10.0])
def test_check_calibration_accepts_sane(cpt):
    assert M.check_calibration(cpt) == cpt


def test_offline_counter_records_transformers_version():
    _count, _cpt, meta = M.offline_counter(tokenizer=StandIn())
    assert "transformers_version" in meta
    try:
        from importlib import metadata

        want = metadata.version("transformers")
    except Exception:   # noqa: BLE001
        want = None
    assert meta["transformers_version"] == want


@pytest.mark.parametrize("bad", [0, -3, 2.5, None, True])
def test_count_prompts_refuses_non_positive_counts(bad):
    item = dict(id="retrieval-131072-00", task="retrieval", rung=131072, task_seed=11, request_seed=12)
    with pytest.raises(M.IdsError):
        M.count_prompts([item], lambda _m: bad, CPT)


def test_main_refuses_on_calibration_error(monkeypatch, capsys):
    monkeypatch.setattr(M, "a5_sizes_from", lambda plan=None: ((72,), dict(source=M.PLAN_SOURCE, report_sha256="0" * 64)))
    monkeypatch.setattr(M, "deployed_budget", lambda: (65536, 32768))
    real = M.offline_counter
    monkeypatch.setattr(M, "offline_counter", lambda: real(tokenizer=StandIn(n=2)))   # the BatchEncoding-of-2 symptom
    monkeypatch.setattr(M, "read_universe", lambda path=None: pytest.fail("read past a refused counter"))
    assert M.main([]) == 2
    assert "calibration" in capsys.readouterr().err


# --- end to end: frozen count vs rung target -------------------------------------------------------------------------------


OVERHEAD = 52   # the real chat template's tokens around an empty user message (fix round 4)


def _one_per_cell():
    d = M.longctx_draw((72,))
    by = {}
    for it in d["items"] + d["smoke"]:
        by.setdefault((it["id"].startswith("smoke-"), it["task"], it["rung"]), it)
    return list(by.values())


def _e2e(count, cpt):
    items = _one_per_cell()
    counts = M.count_prompts(items, count, cpt)
    off = {it["id"]: (counts[it["id"]] - it["rung"]) / it["rung"] for it in items}
    assert all(-0.03 <= v <= 0.0 for v in off.values()), off      # v1.5a: [−3 %, 0 %], never above the rung
    assert M.prompt_band_problems(items, counts) == []
    return off


def test_e2e_stand_in_batch_encoding_within_band():
    count, cpt, _meta = M.offline_counter(tokenizer=StandIn("batch", overhead=OVERHEAD))
    off = _e2e(count, cpt)
    assert all(v < 0 for v in off.values())


def test_e2e_stand_in_without_template_overhead_lands_above_the_rung_and_is_refused():
    """No template overhead: the builders overshoot the rung slightly — above the band's 0 % ceiling, so refused."""
    count, cpt, _meta = M.offline_counter(tokenizer=StandIn("batch"))
    items = _one_per_cell()
    counts = M.count_prompts(items, count, cpt)
    assert any(c > it["rung"] for it, c in ((it, counts[it["id"]]) for it in items))
    assert M.prompt_band_problems(items, counts)
    with pytest.raises(M.IdsError, match="rung band"):
        M.check_prompt_band(items, counts)


_ITEM = dict(id="retrieval-131072-00", task="retrieval", rung=131072, task_seed=11, request_seed=12)


@pytest.mark.parametrize("n,ok", [(131072, True), (131073, False), (math.ceil(131072 * 0.97), True),
                                  (math.ceil(131072 * 0.97) - 1, False), (129_100, True), (100_000, False)])
def test_prompt_band_bounds(n, ok):
    assert (M.prompt_band_problems([_ITEM], {_ITEM["id"]: n}) == []) is ok


@pytest.mark.parametrize("counts", [{}, {"retrieval-131072-00": None}, {"retrieval-131072-00": 1.3e5},
                                    {"retrieval-131072-00": True}])
def test_prompt_band_refuses_missing_or_non_int(counts):
    assert M.prompt_band_problems([_ITEM], counts)


def test_longctx_records_deviation_per_cell():
    d = M.longctx_draw((72, 120))
    everything = d["items"] + d["smoke"]
    counts = {it["id"]: it["rung"] - 1000 - k for k, it in enumerate(everything)}
    rec = M.longctx((72, 120), 65536, 32768, prompt_tokens=counts)
    dev = rec["prompt_deviation"]
    assert dev["band"] == [-0.03, 0.0]
    cells = dev["cells"]
    want_keys = {f"{t}-{r}" for t in M.A5_TASKS for r in M.A5_RUNGS} | {f"smoke-{t}-{M.A5_SMOKE_RUNG}" for t in M.A5_TASKS}
    assert set(cells) == want_keys
    for key, cell in cells.items():
        members = [it for it in everything if M.cell_of(it) == key]
        devs = [(counts[it["id"]] - it["rung"]) / it["rung"] for it in members]
        assert cell["n"] == len(members) == (1 if key.startswith("smoke-") else 20)
        assert cell["min"] == min(devs) and cell["max"] == max(devs)
        assert cell["mean"] == pytest.approx(sum(devs) / len(devs))


def test_main_refuses_a_prompt_above_the_rung(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(M, "a5_sizes_from", lambda plan=None: ((72,), dict(source=M.PLAN_SOURCE, report_sha256="0" * 64)))
    monkeypatch.setattr(M, "deployed_budget", lambda: (65536, 32768))
    monkeypatch.setattr(M, "offline_counter", lambda: (lambda m: 200_000, 4.5, {}))   # above every rung
    monkeypatch.setattr(M, "longctx_draw", lambda sizes: dict(items=[_ITEM], smoke=[]))
    monkeypatch.setattr(M, "read_universe", lambda path=None: pytest.fail("read past a refused prompt size"))
    monkeypatch.setattr(M, "build", lambda *a, **k: pytest.fail("built past a refused prompt size"))
    assert M.main([]) == 2
    assert "rung band" in capsys.readouterr().err


def test_real_tokenizer_counts_input_ids(real_tok):
    count, cpt, meta = M.offline_counter(tokenizer=real_tok)
    assert 1.0 <= cpt <= 10.0
    n = count([{"role": "user", "content": "hello world " * 100}])
    assert n > 100
    assert meta["transformers_version"]


def test_e2e_real_tokenizer_within_band(real_tok):
    count, cpt, _meta = M.offline_counter(tokenizer=real_tok)
    _e2e(count, cpt)
