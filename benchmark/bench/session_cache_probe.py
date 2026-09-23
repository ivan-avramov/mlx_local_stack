"""M45 — session-cache mechanics under opencode + eviction re-prefill cost (2026-09-23).

THE QUESTION (thread-1 review, B3): does OUR harness shape (opencode → mlx-serve → fork session
cache) reuse the prompt prefix turn after turn, or does a short follow-up re-prefill the whole
context ("full prompt processing for a three-word input")? And what does an evicted session cost
to resume at 8K/32K/64K at the shipped native16 full-cap floor?

INSTRUMENT. The worker logs one line per request:
  "Request completed: ... backend=<b> session=<id> cached_tokens=<n> prompt_tokens=<n> ..."
`cached_tokens` is the reused prefix length; `prompt_tokens - cached_tokens` is what was actually
prefilled. The same number rides the response as `usage.prompt_tokens_details.cached_tokens`.
Every leg is attributed to log lines by time window (offset taken before the leg).

LEGS.
  A  known-positive control: pinned chat id (`X-MLX-VLM-Chat-Id`), 10 appended turns → cached_tokens
     must grow each turn. Known-negative: the same conversation with an edited system prompt →
     cached_tokens must be 0. A probe that cannot show both is not looking.
  B  opencode: 10 `opencode run … --continue` turns in a scratch project (anonymous hash-chain
     routing, exactly what the daily driver does). Per-request reuse fraction, per-turn prefilled
     tokens, wall per turn.
  C  eviction: build a pinned session at N tokens (cold), resume it (warm), evict it with two fresh
     sessions (MLX_VLM_CACHE_SESSION_MAX=2, LRU), resume it again (cold-after-eviction). Records
     prefill seconds + cached_tokens per leg and the worker's `footprint` (Metal-inclusive
     phys_footprint) after each step.

`max_tokens` is capped: this measures PREFILL and reuse, not decode. Thinking stays ENABLED
(AGENTS.md) — it is cut short by the cap, never switched off.

  cd benchmark && PYTHONPATH=. ../.venv/bin/python -m bench.session_cache_probe \
      --model Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed --tag m45
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_LINE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2}) (?P<time>\d{2}:\d{2}:\d{2}),(?P<ms>\d{3}) .*Request completed: "
    r"endpoint=(?P<endpoint>\S+) model=(?P<model>\S+) stream=(?P<stream>\S+) backend=(?P<backend>\S+) "
    r"session=(?P<session>\S+) cached_tokens=(?P<cached>\d+) prompt_tokens=(?P<prompt>\d+) "
    r"generated_tokens=(?P<gen>\d+) elapsed=(?P<elapsed>[\d.]+)s prefill=(?P<prefill>[\d.]+) tok/s "
    r"decode=(?P<decode>[\d.]+) tok/s finish_reason=(?P<finish>\S+)")
_FILLER = "The quick brown fox jumps over the lazy dog near the riverbank at sunset. "
CPT = 4.61  # chars per token, same constant the APC probe used (measured on this filler)
CHAT_ID_HEADER = "X-MLX-VLM-Chat-Id"


# ----------------------------------------------------------------------------- pure helpers
def parse_completed_lines(text: str) -> list[dict]:
    rows = []
    for line in text.splitlines():
        m = _LINE.match(line)
        if not m:
            continue
        rows.append({
            "ts": f"{m['date']}T{m['time']}.{m['ms']}",
            "model": m["model"], "backend": m["backend"], "session": m["session"],
            "cached_tokens": int(m["cached"]), "prompt_tokens": int(m["prompt"]),
            "generated_tokens": int(m["gen"]), "elapsed_s": float(m["elapsed"]),
            "prefill_tps": float(m["prefill"]), "decode_tps": float(m["decode"]),
            "finish_reason": m["finish"],
        })
    return rows


def reuse_summary(rows: list[dict]) -> dict:
    prefilled = sum(r["prompt_tokens"] - r["cached_tokens"] for r in rows)
    fr = [round(r["cached_tokens"] / r["prompt_tokens"], 4) if r["prompt_tokens"] else 0.0 for r in rows]
    return {"requests": len(rows), "prefilled_tokens": prefilled,
            "prompt_tokens": sum(r["prompt_tokens"] for r in rows),
            "cached_tokens": sum(r["cached_tokens"] for r in rows),
            "reuse_fraction": fr, "elapsed_s": round(sum(r["elapsed_s"] for r in rows), 2)}


def parse_footprint(text: str) -> dict:
    out = {}
    for key, name in (("phys_footprint:", "footprint_gb"), ("phys_footprint_peak:", "peak_gb")):
        m = re.search(re.escape(key) + r"\s+(\d+)\s+KB", text)
        if m:
            out[name] = round(int(m.group(1)) / (1024 * 1024), 2)
    return out


def opencode_cmd(model: str, cwd: Path, prompt: str, *, first: bool) -> list[str]:
    cmd = ["opencode", "run", "--dir", str(cwd), "--model", f"mlx-local/{model}", "--pure"]
    if not first:
        cmd.append("--continue")
    cmd.append(prompt)
    return cmd


def filler(idx: int, approx_tokens: int) -> str:
    head = f"Session {idx} of the M45 probe, marker {idx * 7919}. "
    n = max(1, int(approx_tokens * CPT / len(_FILLER)))
    return head + _FILLER * n


# ----------------------------------------------------------------------------- live helpers
def _post(path: str, payload: dict, timeout: float, headers: dict | None = None) -> dict:
    import urllib.request
    base = os.environ.get("MLX_SERVE_BASE", "http://localhost:8000")
    h = {"Content-Type": "application/json", **(headers or {})}
    req = urllib.request.Request(base + path, data=json.dumps(payload).encode(), headers=h, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def chat(model: str, messages: list, *, max_tokens: int, timeout: float, chat_id: str | None) -> dict:
    body = {"model": model, "messages": messages, "stream": False, "max_tokens": max_tokens}
    t0 = time.perf_counter()
    r = _post("/v1/chat/completions", body, timeout, {CHAT_ID_HEADER: chat_id} if chat_id else None)
    wall = time.perf_counter() - t0
    us = r.get("usage") or {}
    msg = (r.get("choices") or [{}])[0].get("message", {})
    return {"wall_s": round(wall, 2), "prompt_tokens": us.get("prompt_tokens"),
            "cached_tokens": ((us.get("prompt_tokens_details") or {}).get("cached_tokens")),
            "completion_tokens": us.get("completion_tokens"),
            "finish_reason": (r.get("choices") or [{}])[0].get("finish_reason"),
            "content": msg.get("content") or "", "reasoning": msg.get("reasoning") or ""}


def worker_pid(model_hint: str) -> int | None:
    out = subprocess.run(["ps", "-eo", "pid,command"], capture_output=True, text=True).stdout
    for line in out.splitlines():
        if "mlx_vlm.server" in line and model_hint in line and "--port 8092" not in line:
            return int(line.split()[0])
    return None


def footprint(pid: int | None) -> dict:
    if not pid:
        return {}
    try:
        out = subprocess.run(["footprint", "-p", str(pid)], capture_output=True, text=True, timeout=60).stdout
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}
    return parse_footprint(out)


class LogTail:
    def __init__(self, path: Path):
        self.path = path
        self.offset = path.stat().st_size if path.exists() else 0

    def new_rows(self) -> list[dict]:
        with self.path.open("r", errors="replace") as f:
            f.seek(self.offset)
            text = f.read()
            self.offset = f.tell()
        return parse_completed_lines(text)


# ----------------------------------------------------------------------------- legs
def leg_a_control(model, log, pid, *, turns: int, timeout: float) -> dict:
    chat_id = f"m45-control-{int(time.time())}"
    system = "You are a terse assistant. Answer in at most one sentence."
    msgs = [{"role": "system", "content": system}]
    per_turn = []
    log.new_rows()
    for i in range(turns):
        msgs.append({"role": "user", "content": f"Turn {i + 1}: name one prime number greater than {i * 10}."})
        r = chat(model, msgs, max_tokens=48, timeout=timeout, chat_id=chat_id)
        msgs.append({"role": "assistant", "content": r["content"]})   # verbatim echo (hash is over content)
        rows = log.new_rows()
        per_turn.append({"turn": i + 1, **{k: r[k] for k in ("wall_s", "prompt_tokens", "cached_tokens", "completion_tokens", "finish_reason")},
                         "log": rows[-1] if rows else None})
        print(f"[A] turn {i + 1}: prompt={r['prompt_tokens']} cached={r['cached_tokens']} wall={r['wall_s']}s", flush=True)
    positive = all((t["cached_tokens"] or 0) > 0 for t in per_turn[1:])
    # known-negative: same messages, edited system prompt → no prefix to reuse
    neg_msgs = [{"role": "system", "content": system + " Be precise."}] + msgs[1:] + [{"role": "user", "content": "Turn X: say ok."}]
    log.new_rows()
    rn = chat(model, neg_msgs, max_tokens=16, timeout=timeout, chat_id=chat_id + "-neg")
    neg_rows = log.new_rows()
    negative = (rn["cached_tokens"] or 0) == 0
    print(f"[A] negative: prompt={rn['prompt_tokens']} cached={rn['cached_tokens']} → {'OK' if negative else 'UNEXPECTED REUSE'}", flush=True)
    return {"chat_id": chat_id, "turns": per_turn, "known_positive": positive,
            "negative": {**{k: rn[k] for k in ("wall_s", "prompt_tokens", "cached_tokens")}, "log": neg_rows[-1] if neg_rows else None},
            "known_negative": negative, "footprint_after": footprint(pid)}


OPENCODE_PROMPTS = [
    "In one sentence, what does utils.py do?",
    "Which function in utils.py has the most parameters? One line.",
    "Does main.py import anything from utils.py? Yes or no, one line.",
    "What would parse_args return for no arguments? One line.",
    "Is there a bug in slugify? One line.",
    "Name every file in this project. One line.",
    "What does README.md say the project is for? One line.",
    "Which function should have a docstring but does not? One line.",
    "Suggest one test for slugify, as a single sentence.",
    "Summarise this conversation in one sentence.",
]


def _scratch_project(root: Path) -> Path:
    proj = root / "proj"
    proj.mkdir(parents=True, exist_ok=True)
    (proj / "utils.py").write_text(
        "import re\n\n\ndef slugify(text, sep='-', lower=True, max_len=64):\n"
        "    s = re.sub(r'[^A-Za-z0-9]+', sep, text)\n    if lower:\n        s = s.lower()\n"
        "    return s.strip(sep)[:max_len]\n\n\ndef chunk(items, n):\n"
        "    \"\"\"Yield n-sized chunks.\"\"\"\n    for i in range(0, len(items), n):\n        yield items[i:i + n]\n")
    (proj / "main.py").write_text(
        "import argparse\nfrom utils import slugify\n\n\ndef parse_args(argv=None):\n"
        "    p = argparse.ArgumentParser()\n    p.add_argument('title', nargs='?', default='Hello World')\n"
        "    return p.parse_args(argv)\n\n\nif __name__ == '__main__':\n    print(slugify(parse_args().title))\n")
    (proj / "README.md").write_text("# slugger\n\nTiny CLI that turns a title into a URL slug.\n")
    return proj


def leg_b_opencode(model, log, pid, *, root: Path, turns: int, timeout: float) -> dict:
    proj = _scratch_project(root)
    env = dict(os.environ, XDG_DATA_HOME=str(root / "xdg"), XDG_CACHE_HOME=str(root / "xdg-cache"))
    per_turn = []
    log.new_rows()
    for i, prompt in enumerate(OPENCODE_PROMPTS[:turns]):
        cmd = opencode_cmd(model, proj, prompt, first=(i == 0))
        t0 = time.perf_counter()
        out_path = root / f"opencode_turn_{i + 1:02d}.txt"
        with out_path.open("w") as f:
            try:
                rc = subprocess.run(cmd, cwd=proj, env=env, stdout=f, stderr=subprocess.STDOUT, timeout=timeout).returncode
            except subprocess.TimeoutExpired:
                rc = "timeout"
        wall = round(time.perf_counter() - t0, 1)
        rows = log.new_rows()
        s = reuse_summary(rows)
        per_turn.append({"turn": i + 1, "prompt": prompt, "rc": rc, "wall_s": wall, "requests": rows, "summary": s})
        print(f"[B] turn {i + 1}: rc={rc} wall={wall}s requests={s['requests']} prefilled={s['prefilled_tokens']} "
              f"reuse={s['reuse_fraction']}", flush=True)
    all_rows = [r for t in per_turn for r in t["requests"]]
    return {"project": str(proj), "turns": per_turn, "overall": reuse_summary(all_rows),
            "sessions_seen": sorted({r["session"] for r in all_rows}), "footprint_after": footprint(pid)}


def leg_c_eviction(model, log, pid, *, sizes: list[int], timeout: float) -> dict:
    out = []
    for k, n in enumerate(sizes):
        chat_id = f"m45-evict-{n}-{int(time.time())}"
        # Anonymous hash-chain routing needs >= 2 matching turns (_MIN_HASH_PREFIX_MATCH) and hashes
        # the assistant turn over its CONTENT (reasoning excluded) — so carry a system turn and echo
        # the assistant content back VERBATIM (an empty string stays an empty string). First run
        # (2026-09-23) substituted "OK" for empty content and every warm resume became a new session.
        msgs = [{"role": "system", "content": "Reply with the single word OK."},
                {"role": "user", "content": filler(k + 1, n) + "\n\nReply OK."}]
        steps = {}
        log.new_rows()
        r = chat(model, msgs, max_tokens=8, timeout=timeout, chat_id=chat_id)
        steps["cold"] = {**r, "log": (log.new_rows() or [None])[-1], "footprint": footprint(pid)}
        msgs.append({"role": "assistant", "content": r["content"]})
        msgs.append({"role": "user", "content": "Again, reply OK."})
        r = chat(model, msgs, max_tokens=8, timeout=timeout, chat_id=chat_id)
        steps["warm"] = {**r, "log": (log.new_rows() or [None])[-1], "footprint": footprint(pid)}
        # evict: two fresh sessions (cap 2, LRU) — tiny prompts, each materialises its own floor
        for j in (1, 2):
            e = chat(model, [{"role": "user", "content": filler(100 + k * 10 + j, 200) + "\n\nReply OK."}],
                     max_tokens=8, timeout=timeout, chat_id=f"{chat_id}-evictor-{j}")
            steps[f"evictor_{j}"] = {**e, "log": (log.new_rows() or [None])[-1], "footprint": footprint(pid)}
        msgs.append({"role": "assistant", "content": r["content"]})
        msgs.append({"role": "user", "content": "Once more, reply OK."})
        r = chat(model, msgs, max_tokens=8, timeout=timeout, chat_id=chat_id)
        steps["cold_after_eviction"] = {**r, "log": (log.new_rows() or [None])[-1], "footprint": footprint(pid)}
        for s in steps.values():
            s.pop("content", None); s.pop("reasoning", None)
        row = {"target_tokens": n, "steps": steps,
               "prompt_tokens": steps["cold"]["prompt_tokens"],
               "cold_wall_s": steps["cold"]["wall_s"], "warm_wall_s": steps["warm"]["wall_s"],
               "warm_cached": steps["warm"]["cached_tokens"],
               "after_eviction_wall_s": steps["cold_after_eviction"]["wall_s"],
               "after_eviction_cached": steps["cold_after_eviction"]["cached_tokens"]}
        print(f"[C] {n}: prompt={row['prompt_tokens']} cold={row['cold_wall_s']}s warm={row['warm_wall_s']}s "
              f"(cached {row['warm_cached']}) after-eviction={row['after_eviction_wall_s']}s (cached {row['after_eviction_cached']})",
              flush=True)
        out.append(row)
    return {"sizes": out}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="M45 session-cache mechanics probe")
    ap.add_argument("--model", required=True)
    ap.add_argument("--tag", default="m45")
    ap.add_argument("--legs", default="A,B,C")
    ap.add_argument("--turns", type=int, default=10)
    ap.add_argument("--sizes", default="8000,32000,64000")
    ap.add_argument("--timeout", type=float, default=1200, help="derived: 64K prefill ≈141 s + queue; generous")
    ap.add_argument("--log", default=str(REPO / "logs/mlx_vlm.log"))
    ap.add_argument("--workdir", default=None, help="scratch root (default $STACK_WORKDIR/m45)")
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)

    wd = Path(a.workdir or os.path.join(os.environ.get("STACK_WORKDIR", "/tmp"), "m45"))
    wd.mkdir(parents=True, exist_ok=True)
    log = LogTail(Path(a.log))
    # preload through the router (server path; never a bare process)
    t0 = time.perf_counter()
    _post("/v1/models/load", {"model": a.model, "keep_alive": "240m"}, 900)
    print(f"[m45] loaded {a.model} in {time.perf_counter() - t0:.1f}s", flush=True)
    pid = worker_pid(a.model.split("/")[-1])
    result = {"model": a.model, "tag": a.tag, "started": datetime.now().isoformat(timespec="seconds"),
              "worker_pid": pid, "footprint_start": footprint(pid),
              "session_max_env": os.environ.get("MLX_VLM_CACHE_SESSION_MAX"), "legs": {}}
    legs = [x.strip().upper() for x in a.legs.split(",")]
    if "A" in legs:
        result["legs"]["A_control"] = leg_a_control(a.model, log, pid, turns=a.turns, timeout=a.timeout)
    if "B" in legs:
        result["legs"]["B_opencode"] = leg_b_opencode(a.model, log, pid, root=wd, turns=a.turns, timeout=a.timeout)
    if "C" in legs:
        result["legs"]["C_eviction"] = leg_c_eviction(a.model, log, pid, sizes=[int(x) for x in a.sizes.split(",")], timeout=a.timeout)
    result["finished"] = datetime.now().isoformat(timespec="seconds")
    result["footprint_end"] = footprint(pid)
    out = Path(a.out) if a.out else REPO / "benchmark/results" / a.model / f"session_cache.{a.tag}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=1))
    print(f"[m45] wrote {out}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
