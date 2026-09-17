## Context

See `proposal.md` (Why) for the motivation. The capability landed on 2026-09-17 across commits `840d1a50d`..`5b27d4498`: a tri-state `address_validation` connection config, a unified `validate_address` proxy operation, and a config-gated booking pre-flight. All 69 connector tests pass against sandbox-captured fixtures; the runtime logic is not the defect.

The defect chain is confirmed by reproduction via `collect_references()`:

- `parse_type` in `modules/sdk/karrio/references.py:884-918` classifies a config option's type. It checks `if "Address" in str(_type)` before the enum check, because that check exists to recognize karrio's `Address` attrs model in capability request fields. `str(AddressValidationMode)` is `<enum 'AddressValidationMode'>`, which contains `Address`, so the option is emitted as `"type": "Address"`.
- The dashboard's generic config renderer, `renderConfigFields` in `packages/ui/components/carrier-connection-dialog.tsx:528-593`, branches only on `string`, `string`+`enum`, and `boolean`; anything else returns `null`, so the field is silently dropped.
- Deployment compounds this: `REFERENCE_MODELS` is built at import time (`modules/core/karrio/server/providers/dataunits.py:11-16`) and references are cached, so a server booted before this connector version serves stale connection configs until restart; the constance `DHL_FREIGHT_SWEDEN_ENABLED` gate also controls inclusion.

Config values are stored free-form on the connection; `OptionEnum` resolves an enum-typed option's state to the member name string, and unrecognized values pass through as the raw string, which today makes the booking pre-flight silently behave as `warn`.

## Goals / Non-Goals

**Goals:**

- Make `address_validation` render in the dashboard's Connection configuration with the connector's own code only.
- Lock the references payload shape in with a regression test that fails on the current code.
- Make unrecognized config values resolve to a defined mode instead of implicit `warn`.

**Non-Goals:**

- No SDK changes: `parse_type` and its Address heuristic stay untouched.
- No dashboard changes: no generic fallback renderer for unknown types carrying enums; revisitable later as defense-in-depth.
- No boolean toggle: the tri-state `off`/`warn`/`enforce` semantics are kept; a Select satisfies the operator need.
- No changes to the unified `validate_address` operation, URL building, error remapping, or verdict logic.
- No dashboard UI for the standalone address-validation endpoint.

## Decisions

### Fix at the connector: rename `AddressValidationMode` to `ServabilityMode`

The class name is the only input that misleads `parse_type`; renaming it lets the existing enum branch classify the option as `string` with the member names as `enum`, which the dashboard already renders as a Select. Member names (`off`, `warn`, `enforce`) and stored values are unchanged, so no data migration.

The name `ServabilityMode` reuses the connector's existing servability vocabulary (`PRODUCT_SERVICABILITY_FLAGS` in `providers/dhl_freight_sweden/address.py`). Any name containing `Address` would re-trigger the heuristic.

Alternatives considered:

- Reorder or tighten `parse_type` in the SDK (enum check before the Address check, or match on the attrs class rather than the substring): rejected. The heuristic serves every connector's capability schemas; changing its precedence is an SDK-wide blast radius for a one-connector defect, and a precise fix risks breaking Address field classification elsewhere.
- Add a dashboard fallback rendering unknown-type-with-enum as a Select: rejected for this change. It edits `packages/ui` for a defect fixable connector-locally, and the dashboard regression surface is not covered by connector tests.
- Convert the option to a boolean toggle: rejected. A boolean cannot express `enforce`, and collapsing the tri-state would lose the blocking mode the PRD designed.

### Regression-test the references payload, not just the enum

A connector test asserts that the generated references entry for `address_validation` is `{"type": "string", "enum": ["off", "warn", "enforce"]}` (via the SDK's `collect_references`, which is how the defect was reproduced). This is the severe verification: it fails on the current code and fails again if a future rename or SDK change reclassifies the option. Enum-member tests alone would not have caught this defect.

### Resolve mode values explicitly at the pre-flight call site

Replace the raw `state or "off"` read with a case-insensitive lookup against the mode members; values that still match no member resolve to `off`. Rationale: the feature is opt-in, and an explicit disabled state from a garbage value is more predictable than silently running warnings. Alternative rejected: keeping implicit `warn` behavior, which acts on a value the operator never chose. This changes behavior only for values outside the enum, which the UI cannot produce.

### Record the deployment recipe in the docs

The PRD and the PUDO guide's address-validation section get the corrected enum name where they reference it, plus the verification recipe: restart the API on `prime` (boot-cached reference models and references cache), confirm the constance `DHL_FREIGHT_SWEDEN_ENABLED` gate, then check that `/v1/references` lists the option with `type: string`.

## Risks / Trade-offs

- [Rename misses a reference site (tests, PRD, guide, mapper metadata comments)] → `rg AddressValidationMode` across the repo after the rename must return nothing; connector tests must pass.
- [A future connector names an enum `Address*` and hits the same heuristic] → documented here; the dashboard fallback renderer remains the systemic fix if this recurs.
- [Deployed servers keep serving stale references until restart] → deployment task includes the restart and `/v1/references` check before declaring the fix verified.
- [Clients that relied on unrecognized values behaving as `warn`] → the feature shipped today and was never visible in the UI, so exposure is unlikely; the change is called out in the change log.

## Migration Plan

Ship on `develop`, restart the API on `prime`, verify `/v1/references` shows `address_validation` with `type: string`, then set the mode from the dashboard. Rollback is reverting the commit; stored config values are unaffected because the value space is unchanged.

## Open Questions

None blocking. The optional dashboard fallback renderer is a deferrable follow-up that does not affect this change's specs or tasks.
