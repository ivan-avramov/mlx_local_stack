"""Run a scenario on the isolated bundle (old side), load scenarios / goldens, and the new-side stub.

CLI (from `benchmark/`): `../.venv-bench/bin/python -m bench.tests.p371_baseline.runner regen [name ...]` rewrites the
golden outputs from a freshly built bundle (deterministic; the test asserts regenerated == stored)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from . import bundle as bundle_mod
from . import scenario as scn

HERE = Path(__file__).resolve().parent
SCENARIO_DIR = HERE / "scenarios"
GOLDEN_DIR = HERE / "golden"
DRIVER_COPIES = {"driver.py": "p371_driver_run.py", "scenario.py": "p371_scenario.py", "normalize.py": "p371_normalize.py",
                 "../hermetic_scan.py": "p371_hermetic_scan.py"}


class DriverError(RuntimeError):
    """The isolated driver run failed (isolation violation, scenario failure or timeout)."""


def scenario_names():
    return sorted(p.stem for p in SCENARIO_DIR.glob("*.json"))


def load_scenario(name):
    return scn.load(SCENARIO_DIR / f"{name}.json")


def scenario_kind(name):
    return load_scenario(name)["kind"]


def load_golden(name):
    return json.loads((GOLDEN_DIR / f"{name}.json").read_text())


def write_golden(name, result):
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    (GOLDEN_DIR / f"{name}.json").write_text(json.dumps(result, indent=1, sort_keys=True) + "\n")


def install_driver(bundle):
    tests = Path(bundle) / "benchmark/bench/tests"
    for src, dst in DRIVER_COPIES.items():
        data = (HERE / src).read_bytes()
        target = tests / dst
        if not target.exists() or target.read_bytes() != data:
            target.write_bytes(data)
    # The archived grader code hard-wires `<repo>/.venv-bench/bin/python`; the bundle has no venv, so it gets a symlink
    # to the interpreter environment that runs this harness (never a copy of the current source tree).
    venv = Path(bundle) / ".venv-bench"
    if not venv.is_symlink():
        venv.symlink_to(Path(sys.prefix).resolve(), target_is_directory=True)
    return tests / DRIVER_COPIES["driver.py"]


def run_old_side(bundle, scenario, *, plant=None, timeout=150):
    """Execute `scenario` on the BUNDLE's own code in a subprocess (`python -I -B`, cwd = bundle) and return the
    normalized result dict (with the driver's `_audit`)."""
    bundle = Path(bundle).resolve()
    driver = install_driver(bundle)
    with tempfile.TemporaryDirectory(prefix="p371-run-") as scratch:
        sfile, rfile = Path(scratch) / "scenario.json", Path(scratch) / "result.json"
        sfile.write_text(json.dumps(scenario))
        cmd = [sys.executable, "-I", "-B", str(driver), "--bundle", str(bundle), "--scenario", str(sfile),
               "--out", str(rfile)]
        if plant:
            cmd += ["--plant", str(plant)]
        env = {k: v for k, v in os.environ.items() if not k.startswith(("PYTHON", "VIRTUAL_ENV", "PYTEST"))}
        try:
            got = subprocess.run(cmd, cwd=str(bundle), env=env, capture_output=True, text=True, timeout=timeout,
                                 stdin=subprocess.DEVNULL)
        except subprocess.TimeoutExpired as exc:
            raise DriverError("driver timed out after %ss: %s" % (timeout, (exc.stderr or "")[-400:])) from None
        if got.returncode:
            raise DriverError("driver rc %d (%s)\n--- stderr\n%s\n--- stdout tail\n%s" % (
                got.returncode, "isolation violation" if "isolation violation" in got.stderr else "scenario failure",
                got.stderr[-1500:], got.stdout[-2500:]))
        return json.loads(rfile.read_text())


def run_new_side(scenario):
    """Run the SAME scenario on the new shared core with the current tree's equivalent fakes and return a result of the
    same schema (ITEM: plus `_raw` / `_expected`, see `new_side`). CHAIN scenarios run the current chain entry."""
    from . import new_side
    if scenario["kind"] == "chain":
        return new_side.run_chain_new_side(scenario)
    return new_side.run_item_new_side(scenario)


def _regen(names):
    with tempfile.TemporaryDirectory(prefix="p371-regen-") as tmp:
        bundle = Path(tmp) / "bundle"
        bundle_mod.check_history()
        bundle_mod.make_bundle(bundle)
        for name in names or scenario_names():
            result = run_old_side(bundle, load_scenario(name))
            write_golden(name, {k: v for k, v in result.items() if not k.startswith("_")})
            print("golden", name, flush=True)


if __name__ == "__main__":
    if sys.argv[1:2] != ["regen"]:
        sys.exit("usage: python -m bench.tests.p371_baseline.runner regen [scenario ...]")
    _regen(sys.argv[2:])
