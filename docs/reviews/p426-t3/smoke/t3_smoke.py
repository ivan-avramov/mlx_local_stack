"""T3 acceptance 6 smoke: one arm per invocation. Lean router from the arm's worktree serving its committed registry, 3 requests,
draft counters checked from the worker log, teardown verified. Usage: t3_smoke.py <off|on> <worktree> <out-dir>"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ENTRY = "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed"
BUSY = ("mlx_vlm.server", "mlx_vlm/server", "mlx-serve start", "session_cache_probe", "opencode run", "run.py generate",
        "run_opencode_probe", "run_tg1_probe", "run_oc_probe", "run_agentbench_os", "runserver.sh")
PROMPTS = ["Write a Python function that returns the n-th Fibonacci number iteratively, with a docstring.",
           "Explain in three sentences what a hash map is.",
           "Reply with exactly the word: ok"]


def sh(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=kw.pop("timeout", 120), **kw)


def listeners():
    out = sh(["lsof", "-nP", "-iTCP:8000", "-sTCP:LISTEN", "-Fp"]).stdout
    return sorted({int(x[1:]) for x in out.splitlines() if x.startswith("p") and x[1:].isdigit()})


def busy():
    me = os.getpid()
    return [ln.strip() for ln in sh(["ps", "-axo", "pid=,command="]).stdout.splitlines()
            if any(b in ln for b in BUSY) and not ln.split(None, 1)[0] == str(me)]


def ancestors(pid):
    out, p = [], pid
    while p > 1:
        out.append(p)
        r = sh(["ps", "-o", "ppid=", "-p", str(p)]).stdout.strip()
        if not r.isdigit():
            break
        p = int(r)
    return out


def log(out, msg):
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} {msg}"
    print(line, flush=True)
    with open(out / "smoke.log", "a") as f:
        f.write(line + "\n")


def main(arm, wt, out):
    wt, out = Path(wt).resolve(), Path(out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    tmp = out / "tmp"
    tmp.mkdir()
    reg = wt / "main_models.yaml"
    res = dict(arm=arm, worktree_head=sh(["git", "-C", str(wt), "rev-parse", "HEAD"]).stdout.strip(),
               registry_sha256=sh(["shasum", "-a", "256", str(reg)]).stdout.split()[0],
               clean=sh(["git", "-C", str(wt), "status", "--porcelain", "--untracked-files=no"]).stdout == "",
               power=sh(["pmset", "-g", "ac"]).stdout + sh(["pmset", "-g", "batt"]).stdout)
    if listeners() or busy():
        log(out, f"REFUSED: listeners={listeners()} busy={busy()}")
        return 2
    env = {k: v for k, v in os.environ.items() if k != "APC_ENABLED"}
    env.update(MLX_SERVE_CONFIG=str(reg), MLX_VLM_CACHE_SESSION_MAX="1", MLX_VLM_LOG_FILE="logs/mlx_vlm.log",
               MLX_VLM_LOG_LEVEL="INFO", TMPDIR=str(tmp))
    (wt / "logs").mkdir(exist_ok=True)
    slog = wt / "logs/mlx_vlm.log"
    off0 = slog.stat().st_size if slog.exists() else 0
    lf = open(wt / "logs/main_model.log", "a")
    proc = subprocess.Popen(["uv", "run", "--frozen", "--no-sync", "mlx-serve", "start"], cwd=str(wt), env=env, stdout=lf,
                            stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
    log(out, f"router spawned pid={proc.pid} cwd={wt} MLX_SERVE_CONFIG={reg}")
    rc = 1
    try:
        for _ in range(120):
            if listeners():
                break
            time.sleep(2)
        ls = listeners()
        assert len(ls) == 1, f"listeners {ls}"
        pid = ls[0]
        assert proc.pid in ancestors(pid), f"listener {pid} is not the spawned router's descendant"
        e = sh(["ps", "-o", "command=", "-E", "-p", str(pid)]).stdout
        cwd = sh(["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"]).stdout
        envp = [p for p, ok in [("mlx-serve", "mlx-serve" in e), (f"MLX_SERVE_CONFIG={reg}", f"MLX_SERVE_CONFIG={reg}" in e),
                                ("MLX_VLM_CACHE_SESSION_MAX=1", "MLX_VLM_CACHE_SESSION_MAX=1" in e),
                                ("no APC_ENABLED", "APC_ENABLED" not in e), ("cwd", str(wt) in cwd)] if not ok]
        res["router"] = dict(pid=pid, problems=envp)
        log(out, f"router pid={pid} owns :8000; problems={envp or 'none'}")
        assert not envp, envp
        reqs = []
        for i, p in enumerate(PROMPTS):
            body = json.dumps(dict(model=ENTRY, messages=[{"role": "user", "content": p}], max_tokens=512, seed=1000 + i,
                                   stream=False)).encode()
            rq = urllib.request.Request("http://127.0.0.1:8000/v1/chat/completions", data=body,
                                        headers={"Content-Type": "application/json"})
            t0 = time.time()
            with urllib.request.urlopen(rq, timeout=1800) as r:
                doc = json.loads(r.read())
            u = doc.get("usage", {})
            reqs.append(dict(i=i, wall_s=round(time.time() - t0, 1), finish=doc["choices"][0].get("finish_reason"),
                             completion_tokens=u.get("completion_tokens"), prompt_tokens=u.get("prompt_tokens")))
            log(out, f"request {i}: {reqs[-1]}")
        res["requests"] = reqs
        workers = [ln.strip() for ln in sh(["ps", "-axo", "pid=,command="]).stdout.splitlines()
                   if "mlx_vlm.server" in ln or "mlx_vlm/server" in ln]
        res["worker_cmdline"] = workers
        log(out, f"worker: {workers}")
        time.sleep(3)
        with open(slog, "rb") as f:
            f.seek(off0)
            text = f.read().decode("utf-8", errors="replace")
        wlogs = [slog] + sorted((tmp / "mlx-manager-logs").glob("*.log"))
        done = [ln for ln in text.splitlines() if "Request completed" in ln]
        res["completed_lines"] = done
        res["worker_logs"] = [str(f) for f in wlogs]
        log(out, f"{len(done)} Request completed lines")
        for ln in done:
            log(out, "  " + ln[-400:])
        drafted = [ln for ln in done if "draft_" in ln]
        wargv = " ".join(workers)
        if arm == "on":
            ok = (len(done) == 3 and len(drafted) == 3 and "--draft-kind mtp" in wargv
                  and all(int(m.group(1)) > 0 for m in (re.search(r"draft_n=(\d+)", ln) for ln in drafted) if m))
        else:
            ok = len(done) == 3 and not drafted and "--draft-kind" not in wargv and "--draft-model" not in wargv
        res["verdict"] = "PASS" if ok else "FAIL"
        log(out, f"VERDICT {arm}: {res['verdict']}")
        rc = 0 if ok else 1
    except Exception as exc:  # noqa: BLE001
        log(out, f"ERROR: {exc!r}")
        res["error"] = repr(exc)
    finally:
        st = sh([str(wt / "scripts/stack_stop.sh")], timeout=180)
        survivors = busy()
        res["teardown"] = dict(stack_stop_rc=st.returncode, stack_stop=st.stdout.strip() + st.stderr.strip(),
                               listeners=listeners(), survivors=survivors)
        log(out, f"teardown: {res['teardown']}")
        if st.returncode != 0 or listeners() or survivors:
            rc = 3
        (out / "result.json").write_text(json.dumps(res, indent=1) + "\n")
    return rc


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:4]))
