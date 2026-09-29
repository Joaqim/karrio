## Why

Upstream PR #1141 (`fix-state-code-normalization`) rewrites `state_code` inside `AugmentedAddressSerializer.validate`, so every address saved through the API is changed before any carrier sees it.
On the dev deployment this turned the stored Swedish shipper region "Västra Götaland" into `O`, the ISO 3166-2 code for SE-O, which the dashboard shows as free text because Sweden has no state picker.
An address is shared by every carrier a shipment may be quoted against, so shaping it for one carrier's field format is the wrong layer; the carrier connector that needs a code should derive it when it builds its request.
The PR's own motivating failure (FedEx rejecting a Swedish region) is already resolved by #1143, which makes FedEx omit the state outside US, CA, PR, MX, IN and AE, so the server-side rewrite and its Nordic table no longer have a consumer.
The PR has no reviews yet, so reshaping it now costs nothing on the upstream side.

## What Changes

- Remove the `normalize_state_code` call and its supporting code (fold helpers, suffix list, `NORMALIZATION_ONLY_STATES` for DK, FI, NO, SE, `STATE_INPUT_ALIASES`) from `modules/core/karrio/server/core/validators.py`; the server stores `state_code` exactly as submitted, which is the behaviour on `upstream/main`.
- Add an SDK resolver `lib.to_state_code(value, country)`, the inverse of the existing `lib.to_state_name`, that maps a subdivision name or an ISO `CC-` prefixed code to the subdivision code using only `units.CountryState` (AE, AU, CA, CN, IN, MX, US), and returns the input unchanged when nothing or more than one subdivision matches.
- FedEx `provider_utils.state_code` resolves the state through `lib.to_state_code` for countries in `STATE_CODE_COUNTRIES`, before the existing Canadian `QC` to `PQ` mapping, so a US or Canadian state entered by name reaches FedEx as a code.
- Keep the existing commit that routes FedEx pickup create and update through `provider_utils.state_code`.
- Rebase `fix-state-code-normalization` onto `fix-fedex-state-code-countries` (#1143), because both now change the body of `provider_utils.state_code`; rewrite the #1141 title and body to describe the connector-side fix.

## Capabilities

### New Capabilities

- `addresses/state-codes`: how the server stores a submitted address `state_code`, and the SDK resolver connectors use to derive a subdivision code from it.
- `fedex/state-codes`: which countries FedEx requests carry `stateOrProvinceCode` for, and how the value sent is derived from the stored address.

### Modified Capabilities

None.
Existing specs cover `dhl-freight-sweden`, `documents`, `plugins` and `postnord`, none of which state requirements on `state_code`.

## Impact

- Code on `fix-state-code-normalization`: `modules/core/karrio/server/core/validators.py` returns to its `upstream/main` content; `modules/sdk/karrio/core/utils/helpers.py` (`Location.as_state_code`) and `modules/sdk/karrio/lib.py` (`to_state_code`) are added; `modules/connectors/fedex/karrio/providers/fedex/utils.py` changes.
- Tests: the server normalization tests in `karrio.server.manager.tests.test_addresses` and `test_shipments` are replaced by a stored-as-entered test; SDK resolver tests and FedEx rate and shipment tests for a US state entered by name are added.
- API: `/v1/references` and the dashboard address form are unchanged; addresses submitted through REST or GraphQL keep the state as entered.
- Upstream: PR #1141 is force-pushed with a new base relationship to #1143 and a rewritten title and body; #1143 is unchanged.
- Fork: `BRANCHES` in `assemble-develop.sh` lists `fix-fedex-state-code-countries` before `fix-state-code-normalization`, and develop is reassembled.
- Data: addresses on the dev deployment already rewritten to a code (for example the "Hisingen" shipper holding `O`) are not migrated; they are corrected by editing them in the dashboard.
- Out of scope: the dashboard `object_type` error on `partial_shipment_update` (separate `fix(dashboard)` branch), and making the dashboard state picker optional per country.
