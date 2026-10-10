import json
from configgen.emitters import opencode
from configgen import targets
from configgen.tests.test_opencode_bench import _source_with_candidate


def test_tg1_web_plus_subagent_only_and_daily_untouched():
    source = _source_with_candidate()
    web = json.loads(opencode.emit_opencode_bench_v2_web(source))
    tg = json.loads(opencode.emit_opencode_bench_v2_web_tg1(source))
    deny = dict(action="subagent", resource="*", effect="deny")
    assert tg["permissions"] == web["permissions"] + [deny]
    tg["permissions"].pop()
    assert tg == web
    assert dict(action="execute", resource="*", effect="deny") in tg["permissions"]
    assert (
        tg["compaction"] == {"auto": False}
        and tg["agents"]["title"]["disabled"] is True
    )
    assert "toolbounds" not in opencode.emit_opencode(source)
    assert any(
        n == "opencode-bench-v2-web-tg1"
        and p == "benchmark/opencode_bench_v2_web_tg1.json"
        for n, _, p in targets.BENCH_TARGETS
    )
