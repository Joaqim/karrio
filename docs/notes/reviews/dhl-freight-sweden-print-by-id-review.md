# DHL Freight Sweden print by-id — review gate

Branch: dhl-freight-sweden-print-and-tracking. Scope: 597d570a4..HEAD (one feat, two docs commits) against PRD v1.4. Fresh-context review; the working tree was left clean (schema regeneration reproduced the committed files byte-for-byte).

## Review summary

### Status: PASS

### Verification performed

- Connector suite: 35/35 tests pass (`python -m unittest discover -v -f modules/connectors/dhl_freight_sweden/tests`).
- Regeneration check: `./bin/run-generate-on modules/connectors/dhl_freight_sweden` followed by `git status` produced no diff, proving the committed generated files are exact generator output.
- Serialization probe: `lib.to_dict(PrintRequestByIDType(...))` executed directly for the populated and empty-options cases.
- Spec cross-check: vendored `vendor/se-api-farm/print-api-2.10.0.json` `PrintOptionsById`, `ReportOptions`, `PrintDocumentReportOptions`, and `PageOptions` schemas compared field-by-field against the generated `OptionsType`/`PageOptionsType`.
- Capability check: `references.detect_proxy_methods` reads the proxy `__dict__`; `get_rates` maps to `rating` and `create_shipment` to `shipping`.

### Findings

1. [PASS] PRD compliance, decision #15. The proxy posts `{print_url}/print/printdocumentsbyid` (proxy.py:49) with the wire shape `{"shipmentIds": [id], "options": {...}}`, matching the decision text. The generated `PrintRequestByIDType` exists and is genuine generator output (regeneration is byte-clean). The PRD names the options schema `ReportOptions` after the vendored spec; the generated class is `OptionsType` per the sample-key naming convention, and its fields are the exact union of the spec's `oneOf` branches (`ReportOptions` plus `PrintDocumentReportOptions.itemStartSequence`), so no field is dropped and any emitted payload matches at least the `allOf` branch.
2. [PASS] PRD compliance, decision #16. The template's literal bytes (scheme, host, path, `submit=1&tracking-id=` query) match `utils.py:40` exactly; the PRD spells the placeholder `{id}` while the code uses the positional `{}` consumed by `tracking_url.format(...)`, which is the PRD's own documented convention. The residual (widget auto-submit not directly observed) is recorded inside the decision row rather than silently claimed as verified.
3. [PASS] Launch criteria honesty. The four checked boxes are backed by evidence: the suite passes, the parse tests assert tracking number, label bytes, and `carrier_tracking_link` (test_shipment.py:302-308, 354-366), and the capabilities claim (shipping plus rating, no tracking or pickup) matches what the proxy's public methods derive. The PRD's `meta.tracking_url` prose label for the `carrier_tracking_link` key is pre-existing wording unchanged in this range.
4. [PASS] No scope creep. Six files changed: the connector proxy, the new by-id sample plus its generated module, one `generate` wiring line, the shipment test, and the PRD. Version steps 1.2 to 1.3 to 1.4 land across the two docs commits, matching one version bump per decision-closing commit.
5. [PASS] Test coverage. `test_create_shipment` asserts the by-id URL, the `client-key` header on both calls, and the full serialized payload through `lib.to_dict(print_call.kwargs["data"]) == PrintByIdRequest`, which asserts the actual wire JSON rather than the construction path. The four-method pattern is intact and no pytest exists anywhere in the connector.
6. [PASS] Code quality and generated-file integrity. `mapper.py` is untouched in the range (diffstat), regeneration reproduces every schema module byte-for-byte, and the proxy keeps `karrio.lib` usage with no bare exceptions or mutable defaults.
7. [PASS] Security and hermeticity. The fixture uses the `TEST_CLIENT_KEY` placeholder, no real credentials or new hosts enter the range, and every proxy-touching test patches `lib.request`.
8. [WARN] Empty print options serialize as `"options": {}` rather than omitting the key. Verified by direct probe. This is unreachable through the standard create path, which always sets `label=True` (create.py:211-214), and the spec permits an options object with no properties set, so it is benign.
9. [WARN] Pre-existing, out of range: the plugin metadata comment still says "create_shipment only" (plugins/__init__.py:13-16) while the proxy exposes `get_rates` and the PRD now advertises shipping plus rating. Fixing the comment would be scope creep in this range; queue it for the next connector touch.
10. [WARN] Carry-over from the phase 0 review, out of scope: `client-key` is still absent from `SENSITIVE_HEADER_NAMES` in modules/sdk/karrio/core/utils/redaction.py, so traces persist it in plaintext. A shared-SDK fix belongs on its own change, not this connector branch.

### Adversarial probes

- Booking response without an id: the proxy's `lib.request(...) if shipment_id else "{}"` guard (proxy.py:66) means no print request is sent at all, so neither `None` nor an empty list ever reaches the wire. `parse_shipment_response` then returns `details=None` with the booking error surfaced, and `test_parse_error_response` exercises exactly this path.
- Wire shape: the direct serialization probe produced `{'options': {'label': True, 'pageOptions': {'pageType': 'Label'}}, 'shipmentIds': ['X1']}` — list-typed `shipmentIds`, no null fields — matching the live-verified shape from decision #15.
- Header and options flow: the shared `headers` dict (Content-Type plus `client-key`) is unchanged and asserted for both calls; the page-type chain (shipment option, connection config, default `Label`) is untouched in create.py; and the ctx re-typing through the by-id `OptionsType` is lossless because that class is field-identical to the full-payload `OptionsType`.
- Expected payload: the test's `PrintByIdRequest` composes the same `PrintOptions` constant asserted for the request ctx, and the suite passes against the actual serialized `data`, so the constant and the proxy output agree.

### Retired findings

The by-id switch retires two findings from the phase 0 review: the LOW-MEDIUM "print op deviates from PRD default" (this range implements its recommended fix, with live verification recorded) and the LOW "print-path productCode/postalCode not string-cast" (the print request no longer echoes the shipment, so the int-typed echo fields are gone from the wire entirely).

### Required actions

None. The three WARN items are informational, pre-existing, or unreachable, and none belong in this range.
