"""C147 §3: the A4 gate for the tg1 scaffold; legacy/web gate paths stay byte-unchanged."""
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from bench.tests.test_session_pinning_a4_v2 import gate, FakeLogTail, row     # noqa: F401  (fixture reuse)

TG1 = "opencode-v2-web-tg1"


def sha(data):
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def fake(gate, tmp_path):         # noqa: F811
    module, binary, carrier = gate
    repo = module.REPO
    carrier_doc = json.loads(carrier.read_text())
    (repo / "benchmark/opencode_bench_v2_web.json").write_text(json.dumps(carrier_doc, sort_keys=True) + "\n")
    tg1_doc = {**carrier_doc, "marker": "tg1-carrier"}
    (repo / "benchmark/opencode_bench_v2_web_tg1.json").write_text(json.dumps(tg1_doc, sort_keys=True) + "\n")
    (repo / "benchmark/opencode_plugins/toolbounds.js").write_text("// fake toolbounds\n")
    return module, binary, repo


def run(module, binary, tmp_path, scaffold, **kw):
    log = FakeLogTail([row()], [row(cached=5500)])
    return module.a4_opencode("Test-Model", log, tmp_path / "unused", kw.pop("timeout", 10), str(binary),
                              opencode="v2", scaffold=scaffold, **kw)


def config_tree(result_root):
    cfg = Path(result_root) / "cfg/opencode"
    return {p.relative_to(cfg).as_posix(): sha(p.read_bytes()) for p in sorted(cfg.rglob("*")) if p.is_file()}


def run_root(tmp_path):
    (root,) = [p for p in (tmp_path / "session_gate").iterdir() if p.is_dir()]
    return root


def test_tg1_gate_selects_the_tg1_carrier_and_copies_both_plugins_by_sha(fake, tmp_path):
    module, binary, repo = fake
    result = run(module, binary, tmp_path, TG1)
    assert result["pass"] is True
    tree = config_tree(run_root(tmp_path))
    carrier = repo / "benchmark/opencode_bench_v2_web_tg1.json"
    assert tree == {
        "opencode.json": sha(carrier.read_bytes()),
        "plugins/noretry.js": sha((repo / "benchmark/opencode_plugins/noretry.js").read_bytes()),
        "plugins/toolbounds.js": sha((repo / "benchmark/opencode_plugins/toolbounds.js").read_bytes()),
    }
    from run_opencode_probe_v2 import _carrier_selection
    expected = _carrier_selection(TG1, None, repo=repo, source=carrier)["fields"]["opencode_bench_config_sha256"]
    assert result["carrier_sha256"] == expected == sha(carrier.read_bytes())


@pytest.mark.parametrize("scaffold,carrier_name", [("opencode-v2", "opencode_bench_v2.json"),
                                                   ("opencode-v2-web", "opencode_bench_v2_web.json")])
def test_legacy_and_web_gate_config_dirs_are_byte_unchanged_golden(fake, tmp_path, scaffold, carrier_name):
    module, binary, repo = fake
    result = run(module, binary, tmp_path, scaffold)
    assert result["pass"] is True
    assert config_tree(run_root(tmp_path)) == {
        "opencode.json": sha((repo / "benchmark" / carrier_name).read_bytes()),
        "plugins/noretry.js": sha((repo / "benchmark/opencode_plugins/noretry.js").read_bytes()),
    }
    assert result["carrier_sha256"] == sha((repo / "benchmark" / carrier_name).read_bytes())


def probe_receipt(tmp_path, receipt):
    path = tmp_path / "receipt.json"
    path.write_text(json.dumps(receipt))
    return path


def test_probe_accepts_the_tg1_receipt_with_limit_above_five_and_refuses_the_web_receipt(fake, tmp_path):
    import run_opencode_probe_v2 as p
    module, binary, repo = fake
    tg1 = run(module, binary, tmp_path, TG1)
    tg1_receipt = probe_receipt(tmp_path, tg1)
    router = {"pid": 4321, "config_sha256": "registry-sha"}
    exe = sha(binary.read_bytes())
    tg1_sha = p._carrier_selection(TG1, None, repo=repo,
                                   source=repo / "benchmark/opencode_bench_v2_web_tg1.json"
                                   )["fields"]["opencode_bench_config_sha256"]
    got = p._a4_receipt(str(tg1_receipt), router, 50, "Test-Model", exe, tg1_sha)
    assert got["pass"] is True and got["carrier_sha256"] == tg1_sha
    # a receipt produced by the web scaffold's gate is not valid for tg1
    for old in (tmp_path / "session_gate").iterdir():
        if old.is_dir():
            import shutil
            shutil.rmtree(old)
    web = run(module, binary, tmp_path, "opencode-v2-web")
    with pytest.raises(SystemExit, match="A4 v2 PASS"):
        p._a4_receipt(str(probe_receipt(tmp_path, web)), router, 50, "Test-Model", exe, tg1_sha)


def test_gate_timeout_signals_only_its_own_process_group(fake, tmp_path):
    module, binary, repo = fake
    outsider = subprocess.Popen(["sleep", "60"], start_new_session=True)
    try:
        slow = tmp_path / "slow-opencode"
        slow.write_text(binary.read_text().replace(
            "else:\n    print(", "else:\n    import time; time.sleep(60)\n    print(", 1))
        slow.chmod(0o755)
        started = time.time()
        result = run(module, slow, tmp_path, TG1, timeout=1)
        assert result["pass"] is False and result["turns"][0]["rc"] == "timeout"
        assert time.time() - started < 30
        assert outsider.poll() is None                  # same-uid process outside the group: never signalled
    finally:
        outsider.kill()
        outsider.wait()
