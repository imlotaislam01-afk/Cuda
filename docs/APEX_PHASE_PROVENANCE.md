# APEX Phase Provenance

This document records how the transferred APEX implementation and subsequent closure work map to the new repository history. The historical source baseline is `69550c080d0870a0bf8e5942138cf9c9ede82b65`, preserved in `apex1-main.zip`. The new repository does not contain that historical commit object.

| Phase | Historical source | New repository commit | Provenance | Verification |
| --- | --- | --- | --- | --- |
| P2.27 | Transferred historical baseline | `2dd0fd9` | TRANSFERRED FROM HISTORICAL BASELINE | Baseline feed continuity and quality suites |
| P2.28 | Historical baseline, then replay closure | `649a72b` | INDEPENDENTLY COMMITTED | Replay suite, cutoff immunity, duplicate and out-of-order proofs |
| P2.29 | Transferred baseline plus canonical backtest closure | `db8d9b3` | TRANSFERRED + INDEPENDENT CLOSURE | Backtest suite and canonical replay adapter |
| P2.30 | Transferred baseline plus canonical backtest closure | `db8d9b3` | TRANSFERRED + INDEPENDENT CLOSURE | Backtest adversarial suite |
| P2.31 | Transferred baseline plus observability closure | `e1d045a` | TRANSFERRED + INDEPENDENT CLOSURE | Observability non-interference suite |
| P2.32 | Raw-feed/dashboard acceptance closure | `c4356b9` | INDEPENDENTLY COMMITTED | Raw feed to paper execution, HTTP, WebSocket, and observability proof |
| P2.33 | Transferred baseline acceptance matrix | `2dd0fd9` | TRANSFERRED FROM HISTORICAL BASELINE | Original 32-case matrix |
| P2.34 | Final acceptance and extended adversarial closure | `34216f6`, `fd9d51a` | INDEPENDENTLY COMMITTED | Final acceptance contract and extended matrix |

## Current closure commits

- `8ee4780` closes historical feed-wide quality validation.
- `e1d045a` proves full-state observability non-interference.
- `fd9d51a` adds the independently enumerated extended adversarial matrix.
- `34216f6` is the final acceptance-matrix commit from the prior closure stage.

Each listed commit was pushed to `origin/main`. No historical commit was recreated, rewritten, or represented as an authored phase commit where the work was transferred.
