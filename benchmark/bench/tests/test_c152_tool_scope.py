"""C152 (2026-10-11): the alloc injected positive needs no model cooperation.

The live model refused the 1 GiB `bytearray` addendum on every seed. The alloc kind now lowers a limit that applies
ONLY to tool processes: tracked processes whose tracked parent is model-role, i.e. anything below opencode's `serve`
(opencode 2.0.20 runs a simple shell command as a DIRECT child of `serve`; compound ones go through a shell). The
model's own test run (~40 MiB) trips it; `serve` (~180-380 MiB), the client and the worker keep campaign limits."""
import pytest

from bench import proc_guard as pg, tg1_runner as runner
from bench.tests.test_proc_guard import Process, guard
from bench.token_turn_gate import TransportAbort

MiB = 1024 ** 2
TOOL_LIMIT = 24 * MiB


def tree(tmp_path, **kw):
    client = Process(31001, created=110, argv=["opencode", "run"])
    serve = Process(31002, ppid=client.pid, created=111, rss=380 * MiB, argv=["opencode", "serve"])
    git = Process(31003, ppid=serve.pid, created=112, rss=3 * MiB, argv=["git", "rev-parse"])
    direct = Process(31004, ppid=serve.pid, created=113, rss=40 * MiB, argv=["python3", "-m", "pytest"])
    shell = Process(31005, ppid=serve.pid, created=114, rss=3 * MiB, argv=["/bin/zsh", "-c", "cd x && pytest"])
    nested = Process(31006, ppid=shell.pid, created=115, rss=40 * MiB, argv=["python3", "-m", "pytest"])
    g = guard(tmp_path, [client, serve, git, direct, shell, nested], **kw)
    g.started = 100
    g.register(client, "client")
    return g, dict(client=client, serve=serve, git=git, direct=direct, shell=shell, nested=nested)


def test_tool_limit_kills_tool_processes_and_spares_opencode_itself(tmp_path):
    g, p = tree(tmp_path, tool_per_process=TOOL_LIMIT)
    g.tick()
    assert p["direct"].dead and p["nested"].dead
    assert not any(p[k].dead for k in ("client", "serve", "git", "shell"))
    assert {k["pid"]: (k["scope"], k["role"]) for k in g.mem_kills} == {
        p["direct"].pid: ("tool", "model"), p["nested"].pid: ("tool", "model")}


def test_campaign_guard_has_no_tool_limit(tmp_path):
    g, p = tree(tmp_path)
    g.tick()
    assert g.mem_kills == [] and not any(x.dead for x in p.values())


def test_ordinary_per_process_kill_is_scoped_process(tmp_path):
    g, p = tree(tmp_path, per_process=100 * MiB, tool_per_process=TOOL_LIMIT)
    g.tick()
    scopes = {k["pid"]: k["scope"] for k in g.mem_kills}
    assert scopes == {p["serve"].pid: "process", p["direct"].pid: "tool", p["nested"].pid: "tool"}


def test_tool_membership_survives_reparenting(tmp_path):
    g, p = tree(tmp_path, tool_per_process=TOOL_LIMIT)
    p["direct"].rss = 1 * MiB
    g.tick()                                     # tracked as a tool process while under its parent
    p["direct"].parent = 1                       # detached: reparented to launchd
    p["direct"].rss = 40 * MiB
    g.tick()
    assert p["direct"].dead and any(k["pid"] == p["direct"].pid and k["scope"] == "tool" for k in g.mem_kills)


def test_run_item_passes_the_alloc_policy_into_the_guard(tmp_path, monkeypatch):
    seen = {}

    class Guard:
        client_resource = False

        def __init__(self, *args, **kwargs):
            seen.update(kwargs)
            raise TransportAbort("stop after construction")
    monkeypatch.setattr(pg, "ProcessGuard", Guard)
    gate, hygiene = runner.effective_policy("alloc")
    with pytest.raises(TransportAbort, match="stop after construction"):
        runner.run_item(None, model="fixture", work=tmp_path, prompt="fixture",
                        env={"TMPDIR": str(tmp_path / "itemtmp")}, binary="fixture",
                        evidence=tmp_path / "evidence/one", entry=dict(baseline_failing=1, leaves=[["a"]],
                                                                     lang="python"),
                        limit=262144, private=tmp_path, router={}, base="fixture", policy=(gate, hygiene))
    assert seen["tool_per_process"] == TOOL_LIMIT and seen["interval"] == 0.1
    assert seen["per_process"] == pg.POLICY["per_process"]



class Stream:
    def __init__(self, events):
        self.tool_events = events      # (request, part_id, tool, command)


def test_link_requires_an_argv_match_even_for_a_single_shell_call():
    # C152 review T1: the sole shell call of a request is no longer assigned without correlation
    stream = Stream([(1, "call_ls", "shell", "ls -la")])
    git = dict(argv=["git", "rev-parse", "--git-dir"], carrying_request=1)
    (linked,) = runner._link_mem_kills([git], stream)
    assert linked["tool_call_id"] is None
    stream = Stream([(1, "call_test", "shell", "python3 -m pytest -q bowling_test.py")])
    pyt = dict(argv=["/opt/homebrew/Cellar/python@3.15/Python.app/Contents/MacOS/Python", "-m", "pytest", "-q",
                     "bowling_test.py"], carrying_request=1)
    (linked,) = runner._link_mem_kills([pyt], stream)
    assert linked["tool_call_id"] == "call_test"
