#!/bin/bash
# Sweep orphaned real-bash PersistentShell test processes off the box.
#
# 20th cold review round 20 (HIGH, box stability): 71 orphaned `/bin/bash --login` processes
# (ppid 1, no tty, 4-13h old, 15-43% CPU EACH, load average 92) were found accumulated on the live
# box -- real-bash PersistentShell test shells left behind whenever a pytest run was killed,
# alarmed, or a test raised before close(). `start_new_session=True` + killpg in
# PersistentShell.close()/kill()/__del__, a per-test autouse fixture, and a conftest
# pytest_sessionfinish hook (see benchmark/bench/agentbench_adapter.py,
# benchmark/bench/tests/test_agentbench_adapter.py, benchmark/bench/tests/conftest.py) are the
# in-process fixes; this script is the manual/periodic EXTERNAL backstop for whatever still slips
# through (e.g. the whole pytest process itself was `kill -9`'d from outside, so no Python
# cleanup code -- fixture teardown, session-finish hook, __del__ -- ever ran at all).
#
# DRY-RUN BY DEFAULT: lists matches only. Pass --kill to actually SIGKILL them.
#
# Scope is deliberately narrow: ppid == 1 (reparented to init -- a genuine orphan, never a live
# child of anything), tty == "??" (no controlling terminal -- never an interactive shell someone
# is using), command EXACTLY "/bin/bash --login" (never e.g. a live chain's own worktree
# process, which does not match this argv). This is the same match the coordinator verifies
# after a test run:
#   ps -axo pid,ppid,tty,command | awk '$2==1 && $3=="??" && $5=="--login"'
set -u

DRY_RUN=1
for arg in "$@"; do
  case "$arg" in
    --kill) DRY_RUN=0 ;;
    --help|-h)
      echo "usage: $0 [--kill]   (dry-run by default; --kill actually SIGKILLs matches)"
      exit 0
      ;;
  esac
done

matches="$(ps -axo pid,ppid,tty,command | awk '$2==1 && $3=="??" && $5=="--login"')"

if [ -z "$matches" ]; then
  echo "sweep_orphan_shells: no orphaned /bin/bash --login processes found"
  exit 0
fi

echo "sweep_orphan_shells: found orphaned /bin/bash --login process(es):"
echo "$matches"

if [ "$DRY_RUN" = "1" ]; then
  echo "sweep_orphan_shells: DRY RUN -- pass --kill to actually kill these"
  exit 0
fi

echo "$matches" | awk '{print $1}' | while read -r pid; do
  [ -z "$pid" ] && continue
  echo "sweep_orphan_shells: killing pid $pid"
  kill -KILL "$pid" 2>/dev/null
done
echo "sweep_orphan_shells: done"
