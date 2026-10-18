"""Entry for `new_side.run_item_new_side`: run as `pytest new_side_driver.py -k test_run_scenario` in a subprocess with
P371_SCENARIO / P371_RESULT in the environment. Not collected by the normal suite (the name does not match test_*.py)."""
import json
import os
from pathlib import Path

from bench.tests.p371_baseline import new_side, scenario as scn


def test_run_scenario(tmp_path, monkeypatch):
    sc = scn.load(os.environ["P371_SCENARIO"])
    result = new_side.run_in_pytest(tmp_path, monkeypatch, sc)
    Path(os.environ["P371_RESULT"]).write_text(json.dumps(result, sort_keys=True))
