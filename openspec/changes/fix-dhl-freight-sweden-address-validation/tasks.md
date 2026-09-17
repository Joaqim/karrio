## 1. Connector regression test and rename

- [x] 1.1 Add a references-payload regression test asserting the `address_validation` connection-config entry is classified as `{"type": "string", "enum": ["off", "warn", "enforce"]}` (built on the SDK's `collect_references`, mirroring how the defect was reproduced), and verify the test fails against current `develop`
- [x] 1.2 Rename `AddressValidationMode` to `ServabilityMode` in `modules/connectors/dhl_freight_sweden/karrio/providers/dhl_freight_sweden/units.py` and every reference site (`proxy.py`, tests, metadata comments), and verify the 1.1 regression test passes and `rg -n 'AddressValidationMode' modules/ PRDs/ docs/` returns no remaining hits
- [ ] 1.3 Harden mode resolution at the pre-flight call site in `proxy.py` (`_destination_route_messages`): resolve the stored value case-insensitively against the mode members, with unresolved values resolving to `off`, and verify new unit tests for `Warn` → warn and `strict`/`true` → off pass

## 2. Documentation

- [x] 2.1 Update `PRDs/DHL_FREIGHT_SWEDEN_ADDRESS_VALIDATION.md` and the PUDO guide's address-validation section with the renamed enum, the unrecognized-value semantics (resolve to `off`), and the deployment verification recipe (API restart, constance `DHL_FREIGHT_SWEDEN_ENABLED`, `/v1/references` check), and verify the updated sections read correctly

## 3. Verification

- [x] 3.1 Run the full dhl_freight_sweden connector suite with `source bin/activate-env && python -m unittest discover -v -f modules/connectors/dhl_freight_sweden/tests` and confirm all tests pass
- [x] 3.2 After deployment: restart the API on `prime`, confirm the constance `DHL_FREIGHT_SWEDEN_ENABLED` gate, and verify `/v1/references` lists `address_validation` with `type: string` and the dashboard Connection configuration renders the mode dropdown
