## Why

The address-validation capability added to the `dhl_freight_sweden` connector on 2026-09-17 never reaches operators.
The SDK references layer emits the `address_validation` connection-config option with `"type": "Address"` — the enum class name `AddressValidationMode` trips the `parse_type` heuristic in `modules/sdk/karrio/references.py` that exists to detect Address model fields — and the dashboard's generic config renderer (`packages/ui/components/carrier-connection-dialog.tsx`, `renderConfigFields`) only handles `string`, `string`+`enum`, and `boolean` types, so the field is silently dropped from the Connection configuration dialog.

The operator-visible symptom is a feature that is simultaneously "faulty" and absent: the booking pre-flight cannot be enabled from the UI, so deployed behavior does not reflect the feature that was built and tested.
The Python-side logic itself is sound — all 69 connector tests pass, verified against sandbox-captured fixtures — the defect is confined to type classification and reference-model staleness on deployment.

## What Changes

- Rename the connector's `AddressValidationMode` enum (to `ServabilityMode`) so the references payload classifies `address_validation` as `{"type": "string", "enum": ["off", "warn", "enforce"]}`, which the dashboard already renders as a Select dropdown. No SDK or dashboard code changes.
- Keep the tri-state `off`/`warn`/`enforce` semantics: member names and stored config values are unchanged, only the class name changes, so existing connection configs remain valid.
- Add a regression test asserting the generated references payload (type and enum values) for the connector's `connection_configs`; this test fails against the current code and would have caught the defect.
- Harden mode resolution at the booking pre-flight call site so config values that do not name a member resolve to a defined state (`off`) instead of silently behaving as `warn`.
- Refresh connector docs and the PRD where they name the enum, and record the deployment verification recipe: restart the API to rebuild the boot-cached reference models, confirm the constance `DHL_FREIGHT_SWEDEN_ENABLED` gate, and verify the option appears in `/v1/references`.

No changes to the unified `validate_address` capability, proxy URL building, error remapping, or verdict logic.

## Capabilities

### New Capabilities

- `dhl-freight-sweden/address-validation`: connection-config-driven destination address validation for the DHL Freight Sweden connector — visibility and semantics of the `address_validation` connection-config option, booking pre-flight behavior per mode, and failure handling.

### Modified Capabilities

None — `openspec/specs/` is empty; this is the first capability spec in this repository.

## Impact

- Code: `modules/connectors/dhl_freight_sweden/karrio/providers/dhl_freight_sweden/units.py` (enum rename), `proxy.py` (mode resolution hardening), and connector tests. No SDK (`modules/sdk`) or dashboard (`apps/dashboard`, `packages/ui`) changes.
- API surface: the `/v1/references` payload for `dhl_freight_sweden` changes `address_validation` from `"type": "Address"` to `"type": "string"` with an `enum` array; stored config values are unaffected.
- Deployment: the `prime` deployment must restart the API after shipping this change (boot-cached `REFERENCE_MODELS` and references cache serve stale connection configs until restart) before the option can appear in Connection configuration.
- Docs: `PRDs/DHL_FREIGHT_SWEDEN_ADDRESS_VALIDATION.md` and the PUDO guide's address-validation section where they reference the enum by name.
