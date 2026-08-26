# Cuda / APEX — Project Brief for Claude Code

## What this is
An autonomous crypto-futures trading system (signal → brain → execution intent →
durable ledger → execution coordinator → exchange adapter). This is a financial
execution system — safety and correctness take priority over speed of delivery.

## How to work in this repo
- This repo should be under real git version control. If `.git` is missing, run
  `git init` and make an initial commit before touching anything.
- Work in **stages**, one at a time. After each stage:
  1. Run the full test suite (`pytest -q`).
  2. Run `python -m compileall -q brain market config`.
  3. Show me a summary of what changed and why, plus the diff.
  4. Wait for me to say "continue" before starting the next stage.
- Do not batch multiple stages into one uninterrupted run. I want to review
  real diffs and real test output at each checkpoint — not a final summary
  claiming everything is done.
- Never mark something "complete," "production ready," or "certified" unless
  the tests you just ran actually prove it. If you can't verify something
  (e.g. no real exchange connectivity available), say so explicitly instead
  of asserting it works.
- If you hit a genuine blocker (missing dependency, ambiguous requirement,
  architecture conflict), stop and ask rather than guessing.

## Non-negotiable safety priorities (in order)
1. Capital protection — never risk creating duplicate/phantom orders.
2. Fail-closed behavior — unknown state = do not trade, do not resubmit.
3. Deterministic state — no ambiguous lifecycle transitions.
4. Durable persistence — nothing execution-relevant lives only in memory.
5. Idempotency — safe under retries, duplicate events, out-of-order events.
6. Single authoritative execution path — no component bypasses the
   ExecutionCoordinator.
7. Correctness, then observability, then performance, then convenience.

## Architecture (target state)
```
EngineSupervisor (owns lifecycle: STARTING → RECOVERING → READY → RUNNING →
                   DEGRADED → STOPPING → STOPPED)
  ├─ MarketDataManager   (feed lifecycle, stale/disconnect detection)
  ├─ Context Provider
  ├─ BrainLoop           (signal generation — no lookahead, no repainting)
  ├─ ExecutionConsumer   (durable intent claim, no double-processing)
  ├─ ExecutionCoordinator (risk gates, reconciliation, protection checks)
  ├─ Recovery / Reconciliation
  ├─ Dashboard           (observation/control-plane only — cannot bypass
  │                        the coordinator)
  └─ Shutdown
```

## Code style
- Small, cohesive modules with explicit interfaces — not one giant file.
  Each concern (ledger, coordinator, risk, market data) stays separable so
  it can be tested and reasoned about in isolation.
- Typed models, deterministic state machines, dependency injection.
- No hidden global state, no silent exception swallowing, no unbounded
  queues/lists/caches, no arbitrary sleeps, no duplicated execution paths.
- If a review of *many files* feels unwieldy, solve that with a single
  consolidated architecture/diff summary per stage — not by merging modules
  together.

## PAPER vs LIVE
- PAPER is always the default.
- LIVE must require explicit, valid configuration. Missing credentials,
  malformed config, unknown mode, failed startup validation, stale data, or
  failed reconciliation must never result in LIVE activation — fail closed
  to PAPER/DEGRADED instead.
- Never log or persist API keys, secrets, or credentials in any form.

## Suggested stage order (adjust as the audit reveals the real state)
1. **Audit** — map what currently exists against this architecture. Report
   gaps with file/line references. No code changes yet.
2. **Execution intent durability** — persistent ledger, lifecycle states
   (CREATED → QUEUED → PROCESSING → SUBMITTED → ACKNOWLEDGED → FILLED /
   REJECTED / CANCELLED / FAILED / RECOVERY_REQUIRED), idempotency keys,
   crash-safe recovery of pending intents.
3. **Concurrency safety** — atomic intent claims, no double submission
   (test: N simultaneous identical intents → exactly one submission).
4. **Reconciliation & protective orders** — startup reconciliation against
   exchange state; every open position has verified stop/target protection;
   unresolved/unknown state → DEGRADED, never RUNNING.
5. **Risk engine verification** — confirm CONSERVATIVE/AGGRESSIVE profile
   values against config; drawdown kill switch; exposure/notional limits.
6. **Market data lifecycle** — feed state machine, stale/disconnect
   detection, reconnect/backoff, brain never trades on stale data.
7. **Shutdown correctness** — deterministic order, no abandoned pending
   execution, ledger closed last.
8. **Dashboard isolation** — read-only/control-plane only, cannot bypass
   the coordinator, auth verified.
9. **Observability & bounded resources** — structured logging without
   credentials, bounded queues/history/caches.
10. **Acceptance & failure-injection tests** — crash-point tests across the
    intent lifecycle, duplicate/out-of-order event handling, restart
    recovery.
11. **Deployment review** — Dockerfile/compose, health checks, safe
    defaults, secret injection.

## Definition of "done" for this project
Not "tests pass." Done means: every stage above has real, currently-passing
tests behind it, the gaps found in the audit are either fixed or explicitly
and honestly listed as open, and nothing is claimed to work that hasn't
actually been run and verified in this repo.
