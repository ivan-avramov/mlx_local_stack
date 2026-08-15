"""The aider BENCH settings carrier — the one aider config that DOES include candidates.

WHY THIS EXISTS. `benchmark/run_aider_docker.sh` mounts a settings file and passes it via
`--read-model-settings`; that file is what makes aider send our tuned sampling instead of
litellm's defaults. It defaulted to `aider_config/aider.model.settings.yml`, which is a CLIENT
config — and every client emitter filters on `role == "main"` so a `role: candidate` model is
deliberately absent (see test_candidate_role_is_accepted_and_never_emitted_to_clients).

The consequence was silent and measurement-invalidating: benchmarking a candidate through the
aider scaffold ran it at aider's default sampling, not at its registry `generation_defaults`,
while every other axis in the campaign runs the `deployed` profile. AGENTS.md requires production
params verbatim, so a candidate needs a settings file of its own.

This target is kept OUT of `TARGETS` on purpose. `TARGETS` is "configs advertised to clients",
and the invariant that a candidate never appears there is worth more than the convenience of one
combined list. This is a BENCH artifact under `benchmark/`, not a client config.
"""
import yaml

from configgen import targets
from configgen.emitters.aider import emit_aider, emit_aider_bench
from configgen.source import ModelSpec, Source
from configgen.transforms import sampling_extra


def _source_with_candidate() -> Source:
    """A registry shaped like the real one: one shipped model, one candidate, one task model.

    The candidate carries NO family, exactly as the real Nemotron entry does — configgen only
    accepts {qwen, gemma} and only REQUIRES a family for role=main, so inventing a family for a
    candidate is what previously broke `configgen check`.
    """
    return Source(
        models=[
            ModelSpec(name="Qwen-A", hf_path="ns/Qwen-A", role="main", family="qwen",
                      display_name="Qwen A", context=262144, output=102400,
                      capabilities=["tools"],
                      sampling={"temperature": 0.4, "top_p": 0.95, "top_k": 20, "min_p": 0.0,
                                "presence_penalty": 0.0, "max_tokens": 102400,
                                "thinking_budget": 81920, "enable_thinking": True},
                      edit_format="diff", port=None),
            ModelSpec(name="Cand-N", hf_path="ns/Cand-N", role="candidate", family=None,
                      display_name="Candidate N", context=262144, output=102400,
                      capabilities=["tools", "thinking"],
                      sampling={"temperature": 1.0, "top_p": 0.95, "presence_penalty": 0.0,
                                "max_tokens": 102400, "thinking_budget": 81920,
                                "enable_thinking": True},
                      edit_format="diff", port=None),
            ModelSpec(name="mlx-community/Task-C", hf_path="mlx-community/Task-C", role="task",
                      family=None, display_name="Task C", context=30000, output=2048,
                      capabilities=[], sampling={}, edit_format="whole", port=8092),
        ],
        agent_defaults={"aider": "Qwen-A"},
    )


def test_familyless_sampling_is_carried_not_dropped():
    """A family-less spec must still export its non-OpenAI sampling keys.

    `sampling_extra` used to `return {}` for any family outside {qwen, gemma}. For a candidate
    that silently dropped `presence_penalty`, `enable_thinking` and `thinking_budget` — and a
    NONZERO presence_penalty is what trips the suffix-decoding fallback, so a dropped 0.0 is not
    a cosmetic loss. mlx-serve would refill them from `generation_defaults` (FU-2), but relying on
    that makes the request's effective config invisible in the file we archive as provenance.
    """
    cand = next(m for m in _source_with_candidate().models if m.role == "candidate")
    extra = sampling_extra(cand)

    assert extra["presence_penalty"] == 0.0
    assert extra["thinking_budget"] == 81920
    assert extra["enable_thinking"] is True
    # Keys that belong in extra_params, not extra_body, must NOT be duplicated here.
    for k in ("temperature", "top_p", "max_tokens"):
        assert k not in extra
    # top_k / min_p are absent from this model's registry entry, so they must not be invented.
    assert "top_k" not in extra and "min_p" not in extra


def test_bench_settings_includes_the_candidate_at_its_tuned_sampling():
    settings = yaml.safe_load(emit_aider_bench(_source_with_candidate()))
    names = {e["name"] for e in settings}

    assert "openai/Cand-N" in names, "the candidate is the whole reason this file exists"
    assert "openai/Qwen-A" in names, "shipped models must still be present for paired runs"

    cand = next(e for e in settings if e["name"] == "openai/Cand-N")
    assert cand["edit_format"] == "diff"
    assert cand["extra_params"]["temperature"] == 1.0
    assert cand["extra_params"]["top_p"] == 0.95
    assert cand["extra_params"]["max_tokens"] == 102400
    assert cand["extra_params"]["extra_body"]["presence_penalty"] == 0.0
    assert cand["extra_params"]["extra_body"]["thinking_budget"] == 81920


def test_the_candidate_still_never_reaches_a_client_config():
    """The bench carrier must not weaken the client invariant it exists to work around."""
    src = _source_with_candidate()
    for name, emit, _dest in targets.TARGETS:
        out = emit(src)
        parts = out.values() if isinstance(out, dict) else [out]
        for text in parts:
            assert "Cand-N" not in text, f"candidate leaked into client target {name}"
    # ...and the client aider settings specifically, since it shares an emitter module.
    assert "Cand-N" not in emit_aider(src)["settings"]


def test_bench_target_is_registered_for_generate_and_check():
    """A file nobody regenerates drifts. It must be in BENCH_TARGETS and under benchmark/."""
    assert hasattr(targets, "BENCH_TARGETS"), "bench carrier must be a declared target"
    paths = [dest for _n, _e, dest in targets.BENCH_TARGETS]
    assert "benchmark/aider_bench.model.settings.yml" in paths
    # It must NOT be in TARGETS, or the client-invariant test above becomes unenforceable.
    client_paths = []
    for _n, _e, dest in targets.TARGETS:
        client_paths.extend(dest.values() if isinstance(dest, dict) else [dest])
    assert "benchmark/aider_bench.model.settings.yml" not in client_paths
