Reviewed the target content at `7133f310`; current HEAD only adds the round-4 prompt.

## 1. Round-3 disposition

- P22 — **Yes.** §5.1 now enumerates every carrier difference and explicitly retains the existing D1/headless denials.
- P23 — **Yes.** §11 defines the new per-judge gate, missing-verdict failure, and judge exclusion consequences.
- P24 — **Yes.** Length units/files, coverage denominator, bootstrap refitting, shift TOST, and zero-variance handling are specified.
- P25 — **Yes.** Admission-time sequencing plus a draining end fence closes late/disconnected receipts.
- P26 — **Yes.** Native cuts, transport incidents, precedence, auditing, and replacement attempts are distinguished.
- Watchdog test scope — **Yes.** The positive is limited to descendants observed before detachment; the pre-tick G2 escape is explicitly excluded.
- D1 propagation — **Yes.** Arms, inventory, carrier, treatment, and contract tests agree.
- D2 propagation — **Partly.** The ruling is propagated, but the shared service’s identity, lifecycle, evidence, availability, and determinism contracts remain incomplete.

## 2. v4 problems

P27 — **Stale normative status.** The header and §2.1 still say D1/D2 are “pending” although both are ruled. That leaves approval state internally contradictory.

P28 — **Effective SearXNG pinning is insufficient.** `docker-compose.yml` still uses `searxng/searxng:latest`; the spec promises a future digest but does not name an M64 overlay or require verification of the running container’s image identity. It records `settings.yml`, while Compose mounts generated `settings.generated.yml`, whose content can vary with a random secret and optional credential environment. The effective generated configuration, disabled BYOK inputs, MCP tarball integrity/lock, command, and tool schema need binding evidence.

P29 — **Shared-state fairness is undefined.** SearXNG fans each query to three external engines and maintains mutable suspension state. Existing qualification explicitly records shared upstream rate-limit budgets and 180-second engine suspension. Block permutations mitigate order bias but do not define whether SearXNG persists or restarts across blocks, arms, sessions, or recovery attempts.

P30 — **Availability has no state machine.** A preflight health check is inadequate for a long chain. The spec does not classify MCP-process failure, SearXNG-container failure, an unavailable engine pool, or zero-result upstream failure as infrastructure retry, transport DNF, or scored tool failure. A shared outage could therefore penalize whichever arm encounters it first.

P31 — **“Local search” does not remove third-party query egress.** It centralizes egress: queries still reach DuckDuckGo, Startpage, and Google. The disclosure should say this directly. P201 currently knows only `web_fetches` and `net_shell`; M64 must define a search-evidence schema containing exact query/parameters, raw response, engine errors/provenance, status/timestamps, and hashes, and register that schema with `answer_key.web_entries` and the auditor.

P32 — **The determinism claim is too strong.** §6 requires the search tool to answer “identically across arms,” but live web results cannot satisfy that contract. Offline tests should use a deterministic fixture/mock to prove identical schemas and request semantics; live smokes should prove pinned configuration, reachability, and evidence capture, not identical results. Common result-count, locale, category, safesearch, and timeout parameters also need pinning.

P33 — **The dsh exception is textually inconsistent.** “Every arm gets ONE” conflicts with the ruled no-MCP fallback. Preserve the ruling, but state the invariant as “one shared implementation wherever the client supports native MCP; otherwise dsh has no search,” and report that capability asymmetry.

## 3. BUILD go

No. The non-D2 design is now sufficiently specified, but D2 still admits materially different implementations and failure accounting. Those differences could alter arm opportunity and strict scores.

## 4. Minimum edits

1. Remove all “pending” D1/D2 language.
2. Bind and verify the running image digest, effective generated settings hash, credential-free environment, MCP package/lock/command/tool schema, and M64-owned container lifecycle.
3. Define service persistence/restart boundaries, health checks, outage classification, recovery, and restart evidence.
4. Define search request/result evidence and extend P201’s registered evidence schema; accurately disclose three-engine third-party egress.
5. Restrict identical-answer testing to deterministic offline fixtures and pin live request parameters.
6. Reconcile the dsh no-MCP exception with the “every arm” wording.

AGREE WITH CHANGES: D2 effective pinning; shared-service lifecycle and outage semantics; search egress/audit evidence; deterministic fixture contract; dsh exception wording; stale ruling status
