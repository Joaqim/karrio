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
| 3 | D3 | First-class Pickup API (`models.PickupRequest.address` → `/v3/pickups`, swagger-confirmed no-consignee courier-collection — no SE→SE fallback); manifest neutered to an explicit `not_supported` message. Removed orphaned manifest schema files. | 1 | 20 pass |
| 4 | D4 | Added `test_parse_rate_response_no_matching_zone` — a US recipient matches no SE service zone, yielding empty rates and no crash (DoD "rate quote + error handling"). | 0 | 21 pass |

## Status: complete (0 defects)

All four baseline defects are resolved and the suite is green at 21 tests, re-verified on a build machine with disk space:

```
nix develop .#default --command bash -c 'export PYTHONPATH=modules/connectors/postnord:$PYTHONPATH; python -m unittest discover -f modules/connectors/postnord/tests'
Ran 21 tests in 0.008s — OK
```

Cycle 3 (committed before the originating machine's disk filled) was confirmed at 20 pass on resume, and cycle 4 brings the suite to 21.

Out of scope for this conformance loop (follow-ups, not conformance defects):
- Live re-validation of the Pickup API under the `Pickup.schedule` entry point against the sandbox.
- Cancel remains blocked pending PostNord's v3 REST/EDI reference manual for the id-based delete endpoint (D8).
- The full `./bin/run-sdk-tests` no-regression sweep.
