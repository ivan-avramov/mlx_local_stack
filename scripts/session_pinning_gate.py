"""C102(a) live gate — do client session ids reach the worker and pin the prompt cache?

Pass/fail on the pre-registered criteria in docs/specs/c102a-session-headers.md:
  A4 opencode (--opencode v2; the 1.18 leg is frozen 2026-10-07):
     `opencode run` turn → worker log `session=ses_…` on every request (pinned). The
     resumed `--session` turn's prefix reuse is reported (`cross_process_reuse`), not gated.
  A5 OpenWebUI: a saved-chat completion → worker log `session=<chat id>`; a 2nd turn reuses.
  A6 no client id: a bare 3-request conversation still routes anonymously and reuses on request 3.

Instrument = the worker's `Request completed … session=… cached_tokens=…` line (M45 probe parser).
Run against a freshly started stack (router :8000 on the bumped submodules, OWUI :3000):

  cd $STACK_REPO && set -a; . ./.env; set +a; \
  uv run python scripts/session_pinning_gate.py --model Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "benchmark"))
sys.path.insert(0, str(REPO / "scripts" / "websearch"))
from bench.session_cache_probe import LogTail, chat, filler, opencode_v2_cmd  # noqa: E402
import owui_e2e_gate as owui  # noqa: E402


def wait_rows(log: LogTail, n: int, timeout: float) -> list[dict]:
    rows, t0 = [], time.time()
    while len(rows) < n and time.time() - t0 < timeout:
        rows += log.new_rows()
        if len(rows) < n:
            time.sleep(1)
    return rows


def a6_bare(model, log, timeout) -> dict:
    msgs = [{"role": "system", "content": "Reply with the single word OK."},
            {"role": "user", "content": filler(6, 3000) + "\n\nReply OK."}]
    out = []
    for i in range(3):
        log.new_rows()
        r = chat(model, msgs, max_tokens=8, timeout=timeout, chat_id=None)
        rows = wait_rows(log, 1, 30)
        out.append({"cached": r["cached_tokens"], "prompt": r["prompt_tokens"],
                    "session": rows[-1]["session"] if rows else None})
        msgs.append({"role": "assistant", "content": r["content"]})
        msgs.append({"role": "user", "content": f"Again {i}, reply OK."})
    ok = all(o["session"] and o["session"].startswith("anon:") for o in out) and (out[2]["cached"] or 0) >= 2500
    return {"pass": ok, "requests": out}


def a4_opencode(model, log, root: Path, timeout, oc_bin: str, *, opencode="v2", base=None) -> dict:
    if opencode == "1.18":
        raise SystemExit("REFUSED: the opencode 1.18 gate leg is frozen (M59, 2026-10-07); use --opencode v2")
    return _a4_opencode_v2(model, log, timeout, oc_bin,
                           base if base is not None else os.environ.get("MLX_SERVE_BASE", "http://localhost:8000/v1"))


def _a4_opencode_v2(model, log, timeout, oc_bin: str, base: str) -> dict:
    from bench import provenance

    router = provenance.assert_served_config(base, env={})
    workdir = os.environ.get("STACK_WORKDIR")
    if not workdir or not Path(workdir).is_dir():
        raise SystemExit("REFUSED: A4 v2 requires an existing STACK_WORKDIR")
    gate_dir = Path(workdir).resolve() / "session_gate"
    gate_dir.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="a4-v2-", dir=gate_dir))
    proj = root / "scratch"
    env = {
        "PATH": "/opt/homebrew/bin:/usr/bin:/bin", "HOME": str(root / "home"),
        "XDG_CONFIG_HOME": str(root / "cfg"), "XDG_DATA_HOME": str(root / "data"),
        "XDG_STATE_HOME": str(root / "state"), "XDG_CACHE_HOME": str(root / "cache"),
        "TMPDIR": str(root / "tmp") + "/", "OPENCODE_CONFIG_DIR": str(root / "cfg/opencode"),
        "OPENCODE_DISABLE_PROJECT_CONFIG": "1", "OPENCODE_DISABLE_MODELS_FETCH": "1",
        "OPENCODE_DISABLE_AUTOUPDATE": "1", "OPENCODE_DISABLE_FILEWATCHER": "1",
        "OPENCODE_CONFIG_CONTENT": json.dumps({"providers": {"mlx-local": {"models": {
            model: {"body": {"seed": 0}}}}}}, separators=(",", ":")),
        "PWD": str(proj), "TERM": "dumb", "NO_COLOR": "1",
    }
    for key in ("HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME",
                "TMPDIR", "OPENCODE_CONFIG_DIR", "PWD"):
        Path(env[key]).mkdir(parents=True, exist_ok=True)
    carrier = REPO / "benchmark/opencode_bench_v2.json"
    if not carrier.is_file():
        carrier = REPO / "opencode_config/opencode.json"
        print("[A4 v2] WARNING: benchmark/opencode_bench_v2.json absent; copying the daily-driver carrier verbatim (compaction ON)", flush=True)
    content = carrier.read_bytes()
    if json.loads(content)["providers"]["mlx-local"]["settings"]["baseURL"] != base:
        raise SystemExit("M50 tripwire: A4 v2 carrier destination differs from the verified router")
    (Path(env["OPENCODE_CONFIG_DIR"]) / "opencode.json").write_bytes(content)
    plugin = REPO / "benchmark/opencode_plugins/noretry.js"
    if plugin.is_file():
        target = Path(env["OPENCODE_CONFIG_DIR"]) / "plugins/noretry.js"
        target.parent.mkdir()
        target.write_bytes(plugin.read_bytes())
    else:
        print("[A4 v2] WARNING: noretry.js absent; A4 verifies session headers only", flush=True)
    # Seed the per-run cache; do not let opencode download a tool to a shared cache.
    rg = shutil.which("rg", path=env["PATH"])
    if rg:
        cache_bin = root / "cache/opencode/bin"
        cache_bin.mkdir(parents=True)
        shutil.copyfile(rg, cache_bin / "rg")
        (cache_bin / "rg").chmod(0o755)
    subprocess.run(["git", "init", "-q", str(proj)], cwd=proj, env=env,
                   stdin=subprocess.DEVNULL, capture_output=True, check=True, timeout=30)
    (proj / "hello.py").write_text("def hello(name):\n    return f'hello {name}'\n")
    binary = Path(oc_bin)
    if not binary.is_absolute():
        raise SystemExit("REFUSED: A4 v2 requires an absolute opencode binary")
    binary = binary.resolve(strict=True)
    version = subprocess.run([str(binary), "--version"], cwd=proj, env=env,
                             stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=30)
    version_text = version.stdout.strip().removeprefix("opencode v")
    if version.returncode or version_text != "2.0.20":
        raise SystemExit(f"REFUSED: A4 v2 requires opencode 2.0.20; got {version_text!r}")
    result = {"pass": False, "model": model, "opencode_version": version_text,
              "exe_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
              "run_id": root.name, "router": router, "router_pid": router["pid"],
              "carrier_sha256": hashlib.sha256(content).hexdigest()}
    turns, session_id = [], None
    log.new_rows()
    for i, prompt in enumerate(("In one sentence, what does hello.py do?", "One line: what does it return for 'x'?")):
        if i and not session_id:
            break
        cmd = opencode_v2_cmd(model, prompt, binary=str(binary), session_id=session_id)
        events_path = root / f"oc_turn_{i + 1}.jsonl"
        with events_path.open("w") as stdout, (root / f"oc_turn_{i + 1}.stderr").open("w") as stderr:
            with subprocess.Popen(cmd, cwd=proj, env=env, stdin=subprocess.DEVNULL,
                                  stdout=stdout, stderr=stderr, start_new_session=True) as proc:
                try:
                    rc = proc.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    # Kill only this invocation's group, including its standalone server.
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    proc.wait()
                    rc = "timeout"
        rows = wait_rows(log, 1, 30)
        # Include any trailing completions before starting the next process; never discard them.
        if i == 1:
            time.sleep(5)
        rows += log.new_rows()
        turns.append({"rc": rc, "requests": [
            {"session": r.get("session"), "cached": r["cached_tokens"], "prompt": r["prompt_tokens"]}
            for r in rows]})
        if i == 0:
            try:
                first = next(line for line in events_path.read_text().splitlines() if line.strip())
                session_id = json.loads(first).get("sessionID")
            except (StopIteration, ValueError, AttributeError):
                session_id = None
            if not isinstance(session_id, str) or not session_id.startswith("ses_"):
                session_id = None
        if rc != 0:
            break
    requests = [r for turn in turns for r in turn["requests"]]
    sessions = {r["session"] for r in requests if isinstance(r["session"], str)}
    result.update({
        "pass": bool(session_id) and len(turns) == 2
                and all(t["rc"] == 0 and t["requests"] for t in turns)
                and all(r["session"] == session_id for r in requests),
        "cross_process_reuse": len(turns) == 2 and any((r["cached"] or 0) >= 5000 for r in turns[1]["requests"]),
        "sessions": sorted(sessions), "session_id": session_id, "turns": turns,
    })
    try:
        provenance.assert_served_config_unchanged(router, base, env=env)
    except provenance.ServedConfigError:
        result["pass"] = False
        result["served_config_drift"] = True
    if result["pass"]:
        shutil.rmtree(root / "tmp")
    # Atomic publication prevents a probe reading a half-written PASS.
    pending = gate_dir / f".{root.name}.json"
    pending.write_text(json.dumps(result, indent=2) + "\n")
    pending.replace(gate_dir / "a4_v2_latest.json")
    return result


def a5_owui(model, log, base, email, password, timeout) -> dict:
    api = owui.login(base, email, password)
    q = "Reply with the single word OK."
    chat_doc, uid, aid = owui.chat_payload(model, q, "c102a session gate")
    chat_id = api.post("/api/v1/chats/new", {"chat": chat_doc})["id"]
    payload = owui.completion_payload(model, q, chat_id, aid, str(uuid.uuid4()))
    payload["features"] = {k: False for k in payload["features"]}
    log.new_rows()
    api.post("/api/chat/completions", payload, timeout=timeout)
    rows = wait_rows(log, 1, timeout)
    first = rows[-1] if rows else None
    # second turn in the same chat: the frontend shape re-sends the history with a new message id
    time.sleep(2)
    doc = api.get(f"/api/v1/chats/{chat_id}")
    asst = owui.assistant_message(doc, aid)
    content = (asst.get("content") or "").strip() or "OK"
    aid2 = str(uuid.uuid4())
    payload2 = owui.completion_payload(model, "Again, reply OK.", chat_id, aid2, str(uuid.uuid4()))
    payload2["features"] = {k: False for k in payload2["features"]}
    payload2["messages"] = [{"role": "user", "content": q}, {"role": "assistant", "content": content},
                            {"role": "user", "content": "Again, reply OK."}]
    log.new_rows()
    api.post("/api/chat/completions", payload2, timeout=timeout)
    rows2 = wait_rows(log, 1, timeout)
    second = rows2[-1] if rows2 else None
    pinned = bool(first) and first["session"] == chat_id and bool(second) and second["session"] == chat_id
    reused = bool(second) and (second["cached_tokens"] or 0) > 0
    return {"pass": pinned and reused, "chat_id": chat_id,
            "first": first and {k: first[k] for k in ("session", "cached_tokens", "prompt_tokens")},
            "second": second and {k: second[k] for k in ("session", "cached_tokens", "prompt_tokens")}}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--opencode", choices=("1.18", "v2"), default="v2",
                    help="A4 client (default v2; the 1.18 leg is frozen)")
    ap.add_argument("--model", required=True)
    ap.add_argument("--log", default=str(REPO / "logs/mlx_vlm.log"))
    ap.add_argument("--owui-url", default=os.environ.get("OWUI_URL", "http://localhost:3000"))
    ap.add_argument("--skip-owui", action="store_true")
    ap.add_argument("--timeout", type=float, default=600)
    ap.add_argument("--workdir", default=os.path.join(os.environ.get("STACK_WORKDIR", "/tmp"), "c102a"))
    a = ap.parse_args(argv)
    if a.opencode == "1.18":
        raise SystemExit("REFUSED: the opencode 1.18 gate leg is frozen (M59, 2026-10-07); use --opencode v2")
    try:
        from bench import provenance
        base = os.environ.get("MLX_SERVE_BASE", "http://localhost:8000/v1")
        provenance.assert_served_config(base)
        oc_bin, oc_version = os.environ.get("OPENCODE_PROBE_BIN", "/opt/homebrew/bin/opencode"), "2.0.20"
    except (SystemExit, OSError) as e:
        print(f"[gate] REFUSED: {getattr(e, 'code', None) or e}", file=sys.stderr, flush=True)
        return 2
    import run_opencode_probe as oc
    root = Path(a.workdir); root.mkdir(parents=True, exist_ok=True)
    log = LogTail(Path(a.log))
    res = {"model": a.model, "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "opencode_bin": oc._scrub_pii(oc._portable(Path(oc_bin))), "opencode_version": oc_version,
           "opencode_exe_sha256": oc._sha_of(Path(oc_bin))}
    # Validate the executable in its hermetic environment before any other gate requests.
    res["A4_opencode"] = a4_opencode(a.model, log, root, a.timeout, oc_bin, opencode="v2", base=base)
    res["opencode_version"] = res["A4_opencode"]["opencode_version"]
    res["opencode_exe_sha256"] = res["A4_opencode"]["exe_sha256"]
    res["A6_bare_anonymous"] = a6_bare(a.model, log, a.timeout); print("[A6]", res["A6_bare_anonymous"]["pass"], flush=True)
    print(f"[A4 opencode {a.opencode}]", res["A4_opencode"]["pass"], res["A4_opencode"]["sessions"], flush=True)
    if not a.skip_owui:
        res["A5_openwebui"] = a5_owui(a.model, log, a.owui_url, os.environ.get("OWUI_ADMIN_EMAIL", "admin@a.a"),
                                      os.environ.get("OWUI_ADMIN_PASSWORD", "admin"), a.timeout)
        print("[A5]", res["A5_openwebui"]["pass"], res["A5_openwebui"]["first"], res["A5_openwebui"]["second"], flush=True)
    out = root / "gate.json"
    text = json.dumps(res, indent=1)
    for real, ph in ((os.environ.get("STACK_WORKDIR"), "$STACK_WORKDIR"), (os.path.expanduser("~"), "$HOME")):
        if real and real != "~":
            text = text.replace(real, ph)
    out.write_text(text)
    verdict = all(v.get("pass") for k, v in res.items() if isinstance(v, dict))
    print(f"[gate] {'PASS' if verdict else 'FAIL'} -> {out}", flush=True)
    return 0 if verdict else 1


if __name__ == "__main__":
    sys.exit(main())
