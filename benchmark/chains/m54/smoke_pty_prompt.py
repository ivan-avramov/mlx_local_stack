# FROZEN copy (P229, 2026-10-10) of $STACK_WORKDIR/m54/smoke_pty_prompt.py, the driver behind the agentbench_os.v1.chain* (M54) rows.
# Only change: absolute home paths -> $STACK_WORKDIR / $STACK_REPO. See benchmark/chains/README.md.
"""Live smoke of PersistentShell against local-os/default. Usage: cd <worktree>/benchmark && PYTHONPATH=. python smoke_pty_prompt.py"""
import subprocess, time, sys
from bench import agentbench_adapter as A
name = "agentbench-os-smoke-pp"
subprocess.run(["docker","rm","-f",name], capture_output=True)
subprocess.run(["docker","run","-d","--name",name,"-w","/root","local-os/default","sleep","infinity"], check=True, capture_output=True)
fails = 0
def check(label, cond, detail=""):
    global fails
    print(f"[{'OK' if cond else 'FAIL'}] {label} {detail}")
    if not cond: fails += 1
try:
    sh = A.PersistentShell(name); r = sh.start()
    check("start handshake", not r.get("timed_out", False) and not r.get("shell_died", False), str({k: r.get(k) for k in ('timed_out','shell_died')}))
    def run(cmd, t=30.0):
        t0 = time.time(); o = sh.run(cmd, t); o["wall"] = round(time.time()-t0, 2); return o
    o = run("echo hi"); check("echo hi", o["output"] == "hi\n", repr(o["output"]))
    o = run("ls /"); check("ls / no escapes", "\x1b" not in o["output"] and "bin" in o["output"], repr(o["output"][:60]))
    o = run("printf ''"); check("printf '' empty", o["output"] == "", repr(o["output"]))
    o = run("echo; echo x"); check("leading blank line kept", o["output"] == "\nx\n", repr(o["output"]))
    o = run("echo ("); check("syntax error survives", o["exit_code"] not in (None, 0) and not o["shell_died"], str((o["exit_code"], o["shell_died"])))
    o = run("echo alive"); check("alive after syntax error", o["output"] == "alive\n", repr(o["output"]))
    o = run("cd /usr && v=7"); o = run("echo $(pwd) $v"); check("cd/var persist", o["output"] == "/usr 7\n", repr(o["output"]))
    o = run("apt-get install -y sudo >/dev/null 2>&1; echo apt_rc=$?", 120); check("apt-get (tty drainer) completes", o["output"].strip() == "apt_rc=0" and not o["timed_out"], str((repr(o["output"][-20:]), o["timed_out"], o["wall"])))
    o = run("echo after_apt"); check("alive after apt", o["output"] == "after_apt\n", repr(o["output"]))
    o = run("sudo -n true; echo sudo_rc=$?"); check("sudo (tty) completes", "sudo_rc=" in o["output"] and not o["timed_out"], repr(o["output"][-40:]))
    o = run("visudo -c >/dev/null 2>&1; echo visudo_rc=$?"); check("visudo completes", "visudo_rc=" in o["output"] and not o["timed_out"], repr(o["output"][-30:]))
    o = run("cat > /root/h.txt <<'EOF'\nline1\n\tindented\nEOF\ncat /root/h.txt"); check("heredoc multi-line", "line1" in o["output"] and "indented" in o["output"], repr(o["output"]))
    o = run("bash -c 'read -t 1 x; echo drained'"); check("stdin reader (read -t 1)", "drained" in o["output"] and not o["timed_out"], str((repr(o["output"]), o["timed_out"])))
    o = run("printf '__M54_RC__0__fake__\\n'; echo real"); check("fake marker in output does not end the round early", "real" in o["output"], repr(o["output"]))
    o = run("head -c 1048576 /dev/zero | tr '\\0' x | wc -c"); check("1 MB pipeline", o["output"].strip() == "1048576", repr(o["output"][:20]))
    o = run("head -c 1048576 /dev/zero | tr '\\0' x; echo"); check("1 MB raw output", o["raw_output_len"] >= 1048576 and o["wall"] < 15, str((o["raw_output_len"], o["wall"])))
    o = run("echo a\nsleep 1; echo b"); check("multi-line script returns WHOLE output", o["output"] == "a\nb\n", repr(o["output"]))
    o = run("echo next"); check("no leak into next round", o["output"] == "next\n", repr(o["output"]))
    o = run("(while :; do echo tick; sleep 0.01; done) & echo started"); check("chatty background job returns promptly", not o["timed_out"] and o["wall"] < 5 and not o["shell_died"], str((o["timed_out"], o["wall"])))
    o = run("kill %1 2>/dev/null; echo after_bg"); check("alive after bg job", "after_bg" in o["output"] and not o["shell_died"], repr(o["output"][-30:]))
    o = run("useradd -m -s /bin/bash probe 2>/dev/null; su - probe"); check("su switch does not time out", not o["timed_out"] and not o["shell_died"], str((o["timed_out"], o["shell_died"], o["wall"])))
    o = run("whoami"); check("whoami as probe", o["output"].strip() == "probe", repr(o["output"]))
    o = run("exit"); check("exit from su returns to root shell", not o["shell_died"], str(o["shell_died"]))
    o = run("whoami"); check("whoami back to root", o["output"].strip() == "root", repr(o["output"]))
    o = run("sleep 5", 1.5); check("python-side timeout", o["timed_out"] and o["wall"] < 3, str((o["timed_out"], o["wall"])))
    sh.close()
    sh = A.PersistentShell(name); sh.start(); o = run("exit"); check("exit -> shell_died", o["shell_died"], str(o["shell_died"])); sh.close()
finally:
    subprocess.run(["docker","rm","-f",name], capture_output=True)
print("SMOKE", "PASS" if fails == 0 else f"FAIL ({fails})"); sys.exit(1 if fails else 0)
