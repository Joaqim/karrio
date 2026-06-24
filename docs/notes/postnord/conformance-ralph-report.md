# PostNord connector — conformance ralph report

Iterative measure→fix→commit loop driving the PostNord carrier integration to a clean, upstream-conformant state (`karrioapi/karrio`).

## Methodology

- **Metric:** count of open conformance/correctness defects against (a) `.claude/rules/carrier-integration.md` definition-of-done, (b) the 4-method test pattern, (c) the `/lowy` volatility findings, and (d) upstream carrier conventions.
- **Measurement:** manual audit + `python -m unittest discover -f modules/connectors/postnord/tests` must stay green every cycle.
- **Scope:** `modules/connectors/postnord/` only. Nix/docker changes are explicitly excluded (not part of the carrier integration).
- **Constraints:** behavior changes allowed only to fix correctness defects; keep the suite green; commit one fix per cycle.

## Baseline (4 defects)

| # | Defect | Source | Severity |
|---|--------|--------|----------|
| D1 | Cancel reports false success — `success = not any(messages)` returns `success=True` on an empty/unrecognized body | lowy F2 | correctness |
| D2 | `return_shipment` is a scaffold stub (`request = {}`, `shipment = None`) yet wired through both `__init__` layers and the mapper — would POST an empty body | lowy F3 | correctness |
| D3 | Pickup volatility misplaced behind Manifest — no first-class Pickup API; degenerate SE→SE destination fallback | lowy F1 | structural |
| D4 | Rate feature lacks an error-handling test (DoD: "rate quote + error handling") | DoD | minor |

## Optimization log

| Cycle | Defect | Change | Defects after | Suite |
|-------|--------|--------|---------------|-------|
| baseline | — | — | 4 | 18 pass |
| 1 | D1 | `parse_shipment_cancel_response` returns `None` + explicit `cancellation_unsupported` message; never reports success on an empty body | 3 | 17 pass |
| 2 | D2 | `return_shipment` delegates to the `create` flow (PostNord returns are bookings with a return service code), replacing the `{}` stub | 2 | 17 pass |
