// A4 (P371): tool start / end receipts for the M64 shell watchdog. opencode 2.0.20 reports a tool only when it
// COMPLETES; these two hooks make a tool visible while it runs. `execute.before` / `execute.after` append one JSON line
// {attempt_id, session_id, call_id, tool, phase, seq, ms} to the per-item file named by BENCH_TOOLWINDOW_RECEIPTS
// (absolute, outside the config dir). `call_id` is the tool call id the client's own `tool_use` event carries. A write
// failure THROWS: the tool call fails and the item is never silently unwatched. Unset env refuses at setup.
import fs from "node:fs"

let seq = 0

function fail(message) {
  throw new Error("P371_TOOLWINDOWS: " + message)
}

function config() {
  const file = process.env.BENCH_TOOLWINDOW_RECEIPTS
  if (typeof file !== "string" || !file.startsWith("/")) fail("BENCH_TOOLWINDOW_RECEIPTS is unset or not absolute")
  const attempt = process.env.BENCH_ATTEMPT_ID
  if (typeof attempt !== "string" || attempt === "") fail("BENCH_ATTEMPT_ID is unset or empty")
  return { file, attempt }
}

function text(event, key) {
  const value = event && event[key]
  if (typeof value !== "string" || value === "") fail("the tool hook event carries no " + key)
  return value
}

function receipt(phase, event) {
  const { file, attempt } = config()
  const line = JSON.stringify({
    attempt_id: attempt,
    session_id: text(event, "sessionID"),
    call_id: text(event, "id"),
    tool: text(event, "tool"),
    phase,
    seq: seq + 1,
    ms: Date.now(),
  })
  try {
    fs.appendFileSync(file, line + "\n")
  } catch (error) {
    fail("cannot write the " + phase + " receipt: " + String(error && error.message ? error.message : error))
  }
  seq += 1
}

export default {
  id: "bench.toolwindows",
  setup(ctx) {
    config()
    ctx.tool.hook("execute.before", (event) => receipt("start", event))
    ctx.tool.hook("execute.after", (event) => receipt("end", event))
  },
}
