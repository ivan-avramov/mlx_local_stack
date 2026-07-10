from configgen.__main__ import run


def test_generate_then_check_clean(tmp_path, sample_source, monkeypatch):
    # generate to a temp root, then check must report no drift
    root = tmp_path
    run(["generate"], source=sample_source, root=str(root))
    assert (root / "opencode_config/opencode.json").exists()
    assert run(["check"], source=sample_source, root=str(root)) == 0   # no drift


def test_check_detects_drift(tmp_path, sample_source):
    root = tmp_path
    run(["generate"], source=sample_source, root=str(root))
    (root / "opencode_config/opencode.json").write_text("{}\n")        # tamper
    assert run(["check"], source=sample_source, root=str(root)) == 1   # drift


def test_check_detects_drift_multifile(tmp_path, sample_source):
    # verify drift detection on multi-file aider target
    root = tmp_path
    run(["generate"], source=sample_source, root=str(root))
    # tamper one of aider's three dict-shaped output files
    (root / "aider_config/aider.model.metadata.json").write_text("{}\n")
    assert run(["check"], source=sample_source, root=str(root)) == 1
