"""Verbatim pre-P311 reference copies (HEAD 551890e4) for byte-equality tests. Do not edit; do not import in production."""
import hashlib
import re
from bench import answer_key
from bench.opencode_common import _stack_workdir

NET_SHELL = re.compile(
    r"\b(curl\b|wget\b|git\s+(clone|fetch|pull)\b|go\s+(get|install)\b|"
    r"pip3?\s+(download|install)\b|uv\s+(pip|add)\b|cargo\s+(add|install)\b|"
    r"npx\s|gh\s|brew\s|npm\s+(view|install)\b|https?://)"
)
NET_OUTPUT_FILE = re.compile(r"(?:^|\s)(?:-[oO](?:\s|$|[^\s]+)|--output(?:=|\s|$))|>|\btee\b")


def legacy_web_audit(export, item_dir, transcript_target, *, scaffold="opencode-v2-web"):
    """Audit failures exclude a row without interrupting generation or grading."""
    result = {"web_fetches": [], "net_shell": [], "web_denied": 0, "subagent_calls": 0,
              "web_audit_incomplete": False, "answer_key_contact": False, "answer_key_evidence": []}
    try:
        legacy_collect_web_audit(export, item_dir, transcript_target, scaffold, result)
    except Exception as exc:
        result["web_audit_error"] = f"{type(exc).__name__}: {exc}"
    return result


def legacy_collect_web_audit(export, item_dir, transcript_target, scaffold, result):
    """Audit native v2 tool parts; permission.rejected is pinned by real mock captures."""
    fetches, commands, texts = result["web_fetches"], result["net_shell"], []
    result["subagent_calls"] = sum(
        isinstance(part, dict) and part.get("type") == "tool" and part.get("name") == "subagent"
        for message in export["messages"] for part in (message.get("content") or []))
    result["web_audit_incomplete"] = (
        scaffold.startswith("opencode-v2-web") and result["subagent_calls"] > 0)
    for message in export["messages"]:
        for part in message.get("content") or []:
            if not isinstance(part, dict) or part.get("type") != "tool":
                continue
            name, state = part.get("name"), part.get("state", {})
            if name not in ("webfetch", "shell"):
                continue
            inputs = state.get("input", {})
            error = state.get("error", {})
            rejected = (state.get("status") == "error" and isinstance(error, dict)
                        and error.get("type") == "permission.rejected")
            source = inputs.get("url" if name == "webfetch" else "command", "")
            if name == "shell" and not NET_SHELL.search(source):
                continue
            result["web_denied"] += int(rejected)
            if name == "shell" and NET_OUTPUT_FILE.search(source):
                result["web_audit_incomplete"] = True
            content = state.get("content") or []
            chunks = ([content] if isinstance(content, str) else [
                c["text"] for c in content
                if isinstance(c, dict) and c.get("type") == "text" and isinstance(c.get("text"), str)
            ])
            # Preserve text blocks verbatim, without injecting separator bytes.
            text = "".join(chunks)
            status = "denied" if rejected else (
                "completed" if state.get("status") == "completed" else "error")
            if name == "webfetch":
                entry = {"url": source, "status": status}
                fetches.append(entry)
            else:
                entry = {"command": source, "status": status}
                commands.append(entry)
            if rejected:
                entry["error"] = {"message": error.get("message")}
            target = transcript_target.with_suffix(".web") / f"{len(fetches) + len(commands) - 1}.txt"
            root = _stack_workdir().resolve()
            relative = target.resolve().relative_to(root / "opencode_transcripts")
            target.parent.mkdir(parents=True, exist_ok=True)
            data = text.encode("utf-8", errors="surrogatepass")
            target.write_bytes(data)
            entry.update(path="$STACK_WORKDIR/opencode_transcripts/" + relative.as_posix(),
                         sha256=hashlib.sha256(data).hexdigest(), bytes=len(data))
            if text:
                texts.append({"source": source, "text": text})
    contact = answer_key.contact(item_dir, texts)
    result.update(answer_key_contact=contact["flag"], answer_key_evidence=contact["evidence"])


def legacy_shell_deny_patterns(patterns):
    """Match whole shell nodes; keep exact URLs bounded at token ends."""
    result = []
    boundaries = (' ', '\t', '\n', '"', "'", ';', '|', '&', ')', '>', '<', ',', '`', '$(', '@')
    for pattern in patterns:
        pattern = '*' + pattern.lstrip('*')
        result.append(pattern)
        if not pattern.endswith('*'):
            result.extend(pattern + boundary + '*' for boundary in boundaries)
        github = re.fullmatch(r'\*github\.com/([^/]+)/([^/*?#]+)', pattern)
        if github:
            project = '/'.join(github.groups())
            for command in (f'*gh repo clone {project}', f'*gh api repos/{project}'):
                result.append(command)
                result.extend(command + boundary + '*' for boundary in (*boundaries, '/'))
    return list(dict.fromkeys(result))
