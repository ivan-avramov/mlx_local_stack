// P364: freeze the date opencode shows the model. Structured session hooks only (never the wire):
// `context` (primary), `compaction`, `generate`, `title`. In the system text, "Today's date: <toDateString>" becomes
// the frozen date; any midnight update line "Today's date is now: ..." is removed from the messages. One receipt line
// per hook call goes to the per-item file named by BENCH_DATEFREEZE_RECEIPTS. Any malformed input throws before the
// request is built: never the real date.
import fs from "node:fs"
import crypto from "node:crypto"

const DATE_SHAPE = /^(Sun|Mon|Tue|Wed|Thu|Fri|Sat) (Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) (0[1-9]|[12][0-9]|3[01]) [0-9]{4}$/
const INITIAL = /Today's date: ([^\n]*)/g
const KINDS = { context: "primary", compaction: "compaction", generate: "generate", title: "title" }
const seq = new Map()

function fail(message) {
  throw new Error("P364_DATEFREEZE: " + message)
}

function config() {
  const frozen = process.env.BENCH_FROZEN_PROMPT_DATE
  if (typeof frozen !== "string" || !DATE_SHAPE.test(frozen)) fail("BENCH_FROZEN_PROMPT_DATE is unset or not 'Www Mmm DD YYYY'")
  const receipts = process.env.BENCH_DATEFREEZE_RECEIPTS
  if (typeof receipts !== "string" || !receipts.startsWith("/")) fail("BENCH_DATEFREEZE_RECEIPTS is unset or not absolute")
  return { frozen, receipts }
}

function freezeSystem(system, frozen) {
  let replaced = 0
  for (const entry of Array.isArray(system) ? system : []) {
    if (!entry || typeof entry.text !== "string") continue
    entry.text = entry.text.replace(INITIAL, (_all, shown) => {
      if (!DATE_SHAPE.test(shown)) fail("date instruction has an unexpected shape: " + JSON.stringify(shown.slice(0, 40)))
      replaced += 1
      return "Today's date: " + frozen
    })
  }
  return replaced
}

// The pinned binary's update is a `role:"system"` message whose text is the instruction line; only lines of exactly
// this shape, in system-role messages, are removed (user / synthetic / model text is never edited).
const UPDATE_EXACT = new RegExp("^Today's date is now: " + DATE_SHAPE.source.slice(1, -1) + "$")

function stripUpdates(text) {
  let removed = 0
  const kept = text.split("\n").filter((line) => {
    if (!UPDATE_EXACT.test(line)) return true
    removed += 1
    return false
  })
  return { text: kept.join("\n"), removed }
}

function cleanMessages(messages) {
  let total = 0
  if (!Array.isArray(messages)) return total
  for (let i = messages.length - 1; i >= 0; i--) {
    const message = messages[i]
    if (!message || message.role !== "system") continue
    let removed = 0
    if (typeof message.content === "string") {
      const r = stripUpdates(message.content)
      removed += r.removed
      message.content = r.text
    } else if (Array.isArray(message.content)) {
      for (let j = message.content.length - 1; j >= 0; j--) {
        const part = message.content[j]
        if (!part || typeof part.text !== "string") continue
        const r = stripUpdates(part.text)
        removed += r.removed
        part.text = r.text
        if (r.removed > 0 && r.text.trim() === "") message.content.splice(j, 1)
      }
    }
    if (typeof message.text === "string") {
      const r = stripUpdates(message.text)
      removed += r.removed
      message.text = r.text
    }
    total += removed
    if (removed === 0) continue
    const empty = (typeof message.content === "string" ? message.content.trim() === "" : !message.content || message.content.length === 0)
      && (typeof message.text !== "string" || message.text.trim() === "")
    if (empty) messages.splice(i, 1)
  }
  return total
}

function leftover(event) {
  const texts = (event.system || []).map((s) => (s && s.text) || "")
  for (const message of event.messages || []) {
    if (!message || message.role !== "system") continue
    texts.push(JSON.stringify(message.content ?? "") + JSON.stringify(message.text ?? ""))
  }
  return texts.some((t) => t.includes("Today's date is now: ") && t.match(/Today's date is now: [A-Z][a-z]{2} [A-Z][a-z]{2} [0-9]{2} [0-9]{4}/))
}

function receipt(path, record) {
  fs.appendFileSync(path, JSON.stringify(record) + "\n")
}

export default {
  id: "bench.datefreeze",
  setup(ctx) {
    config()
    for (const [hook, kind] of Object.entries(KINDS)) {
      ctx.session.hook(hook, (event) => {
        const { frozen, receipts } = config()
        const sessionID = String(event.sessionID ?? "")
        const key = sessionID + "|" + kind
        const n = (seq.get(key) ?? 0) + 1
        seq.set(key, n)
        const base = { sessionID, seq: n, kind, frozen }
        try {
          const replaced = freezeSystem(event.system, frozen)
          const removed = cleanMessages(event.messages)
          if (replaced === 0 && kind !== "title") fail("no date instruction found in the " + kind + " request")
          if (leftover(event)) fail("an instruction update message could not be removed")
          const texts = (event.system || []).map((s) => (s && s.text) || "")
          receipt(receipts, {
            ...base,
            n_initial_replaced: replaced,
            n_update_removed: removed,
            system_sha256: crypto.createHash("sha256").update(texts.join("\n")).digest("hex"),
          })
        } catch (error) {
          try {
            receipt(receipts, { ...base, error: String(error && error.message ? error.message : error) })
          } catch (_ignored) {}
          throw error
        }
      })
    }
  },
}
