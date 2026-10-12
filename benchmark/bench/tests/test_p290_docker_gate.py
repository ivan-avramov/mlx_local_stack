"""P290 (2026-10-12): the chain checks docker before a schedule with Go legs, and again before each Go leg.

The C154 smoke rehearsal's first Go leg aborted ("container cleanup uncertain") because OrbStack had not restarted
after a reboot; nothing checked docker before the router, the model load and a Python pilot had already run."""
from bench.tests.test_c147_chain_runner import CHAIN, PILOT, env, log_has, run   # noqa: F401  (fixture)


def test_docker_down_aborts_before_the_router_when_go_legs_are_scheduled(env):
    env["ops"].docker = False
    assert run(env, CHAIN) == 2
    assert log_has(env, "docker gate FAIL")
    names = [c[0] for c in env["ops"].calls]
    assert "docker_ok" in names and "start_router" not in names and "load" not in names


def test_python_only_pilot_does_not_need_docker(env):
    env["ops"].docker = False
    assert run(env, PILOT) == 0
    assert "docker_ok" not in [c[0] for c in env["ops"].calls]


def test_docker_lost_mid_chain_aborts_before_launching_the_go_leg(env):
    env["ops"].docker = [True, False]           # start gate ok, then down before the first Go leg
    assert run(env, CHAIN) == 2
    assert log_has(env, "docker gate FAIL before launch")
    inv = (env["ops"].state / "invocations.jsonl").read_text()
    assert '"--lang", "go"' not in inv and "opencode_go" not in inv


def test_docker_up_chain_checks_once_at_start_and_before_each_go_leg(env):
    assert run(env, CHAIN) == 0
    calls = [c[0] for c in env["ops"].calls]
    assert calls.index("docker_ok") < calls.index("start_router")
    assert calls.count("docker_ok") == 1 + 2      # chain s1: one Go leg per pick


def test_go_launches_are_visible_in_the_invocation_log_when_docker_is_up(env):
    # guards the negative assertion above against passing vacuously
    assert run(env, CHAIN) == 0
    assert "opencode_go" in (env["ops"].state / "invocations.jsonl").read_text()
