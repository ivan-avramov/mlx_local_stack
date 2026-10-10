import ast
import os
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import mock_open


class WatchTotalTest(unittest.TestCase):
    def test_watch_total_matches_generation_rows(self):
        path = Path(__file__).with_name("queue_chain3.py")
        tree = ast.parse(path.read_text())
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "run_generate")
        for limit, samples in [(50, 3), (5, 3), (164, 1)]:
            with self.subTest(limit=limit, samples=samples):
                calls = []
                class WatchCaptured(Exception):
                    pass
                def popen(cmd, **kwargs):
                    calls.append(cmd)
                    if len(calls) == 2:
                        raise WatchCaptured()
                    return SimpleNamespace(pid=1)
                ns = dict(os=os, time=time, PY="python", REPO="repo", OUT="queue",
                          log=lambda _: None, sha=lambda _: "hash", open=mock_open(),
                          subprocess=SimpleNamespace(Popen=popen, STDOUT=-2, DEVNULL=-3))
                exec(compile(ast.Module(body=[function], type_ignores=[]), str(path), "exec"), ns)
                with self.assertRaises(WatchCaptured):
                    ns["run_generate"]("example", "hep", "test", limit, "test", "overlay", samples=samples)
                driver, watch = calls
                self.assertEqual(driver[driver.index("--samples") + 1], str(samples))
                self.assertEqual(watch[watch.index("--total") + 1], str(limit * samples))


if __name__ == "__main__":
    unittest.main()
