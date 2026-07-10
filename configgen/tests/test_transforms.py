from configgen.transforms import input_limit, sampling_extra, owui_meta

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
