from configgen.transforms import input_limit, sampling_extra, sampling_openai, owui_meta
from configgen.source import ModelSpec

def test_input_limit_reserves_output(sample_source):
    q = sample_source.models[0]  # context 262144, output 102400
    assert input_limit(q) == 262144 - 102400

def test_qwen_extra_uses_presence_penalty_not_repetition(sample_source):
    extra = sampling_extra(sample_source.models[0])
    assert extra["presence_penalty"] == 0.0 and "repetition_penalty" not in extra
    assert extra["top_k"] == 20 and extra["min_p"] == 0.0

def test_gemma_extra_uses_repetition_penalty_not_presence(sample_source):
    extra = sampling_extra(sample_source.models[1])
    assert extra["repetition_penalty"] == 1.08 and "presence_penalty" not in extra

def test_owui_meta_default_features(sample_source):
    meta = owui_meta(sample_source.models[0])
    assert meta["capabilities"]["web_search"] is True
    assert "web_search" in meta["defaultFeatureIds"]

def test_sampling_openai_filters_to_openai_keys(sample_source):
    openai = sampling_openai(sample_source.models[0])
    assert openai == {"temperature": 0.4, "top_p": 0.95, "max_tokens": 102400}
    assert "top_k" not in openai
    assert "presence_penalty" not in openai

def test_sampling_extra_drops_wrong_family_keys():
    qwen = ModelSpec(name="x", hf_path="x", role="main", family="qwen",
                     display_name="x", context=1000, output=100, capabilities=[],
                     sampling={"top_k": 20, "presence_penalty": 0.0, "repetition_penalty": 1.08},
                     edit_format="diff", port=None)
    extra = sampling_extra(qwen)
    assert extra["presence_penalty"] == 0.0
    assert extra["top_k"] == 20
    assert "repetition_penalty" not in extra

    gemma = ModelSpec(name="x", hf_path="x", role="main", family="gemma",
                      display_name="x", context=1000, output=100, capabilities=[],
                      sampling={"top_k": 20, "presence_penalty": 0.0, "repetition_penalty": 1.08},
                      edit_format="diff", port=None)
    extra = sampling_extra(gemma)
    assert extra["repetition_penalty"] == 1.08
    assert "presence_penalty" not in extra

def test_owui_meta_omits_absent_features(sample_source):
    meta = owui_meta(sample_source.models[2])  # Task model with empty capabilities
    assert "web_search" not in meta["defaultFeatureIds"]
    # web_search is not in capabilities dict (or is False) since it's not in the model's capabilities
    assert not meta["capabilities"].get("web_search", False)
