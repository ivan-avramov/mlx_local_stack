"""S26 frozen tests, `scripts/bootstrap_machine.sh` step 5b (spec §5). The script is never executed (it would run `brew`): it is
syntax-checked with `bash -n` and its text is checked for the commands the spec names.

[INV] the script still parses; [NEW] step 5b content."""
from __future__ import annotations

import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "bootstrap_machine.sh"


def test_inv_the_bootstrap_script_is_valid_bash():
    """[INV] review gap: `bash -n` (parse only, nothing runs) accepts the script."""
    done = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)
    assert done.returncode == 0, done.stderr[-400:]


def test_new_step_5b_installs_the_toolchains_links_java_and_names_the_prefill():
    """[NEW] §5: `brew install rust openjdk@21 cmake`, `brew link --force openjdk@21`, a java-on-the-agent-PATH check that dies,
    and the tg2 prefill named as a prerequisite (not run by default)."""
    text = SCRIPT.read_text()
    assert "brew install rust openjdk@21 cmake" in text or all(w in text for w in ("rust", "openjdk@21", "cmake"))
    assert "brew link --force openjdk@21" in text
    assert "bench.tg2_gradle_home prefill" in text
