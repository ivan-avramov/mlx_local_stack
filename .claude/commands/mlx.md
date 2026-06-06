---
description: Run the MLX local stack (start the runserver script)
argument-hint: start
allowed-tools: Bash(./runserver.sh)
---

Action: `$ARGUMENTS`

If the action is `start` (or empty), run the local stack with:

```
./runserver.sh
```

Run it in the foreground via Bash with a long timeout (600000ms) so the user sees the spinner output and can Ctrl+C to stop. Do not background it — the script traps SIGINT to tear down docker compose and the model processes.

For any other action, tell the user only `start` is supported right now.
