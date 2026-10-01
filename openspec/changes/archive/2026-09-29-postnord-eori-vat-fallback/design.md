# Design

## Context

See proposal.md for motivation.
Current sourcing on develop (the authoritative base; the `feat-postnord-connector` worktree is already merged into it):

- CN22 EORI: `shipment/create.py:461` reads `options.eori_number.state or None` into `EORIorPersonalIdNumber`.
- Customs invoice EORI: `shipment/create.py:628` reads the same option into the seller `eoriNo`.
- Customs invoice VAT: `shipment/create.py:627` uses `shipper.tax_id` for seller `vatNo` and `recipient.tax_id` for buyer `vatNo`.
  `ComputedAddress.tax_id` (`modules/sdk/karrio/core/units.py:1604-1606`) folds to `federal_tax_id or state_tax_id`.
- VAT requirement: `shipment/create.py:517-520` fails when `not shipper.tax_id`, with the error keyed `shipper.federal_tax_id`.
- CN22 guard: `enforce_cn22_registration_numbers` (`units.py:424-441`) requires one of `eori_number`, `voec_number`, `ioss_number` from customs options only.
- Customs options enter via `lib.to_customs_info(payload.customs, option_type=provider_units.CustomsOption)` (`create.py:766-769`); the provider `CustomsOption` enum (`units.py:214`) is what keeps these keys alive through typed-options filtering.
- No existing test fixture sets `state_tax_id` anywhere in the postnord tests.

## Goals / Non-Goals

**Goals:**

- One EORI resolution rule shared by the CN22 branch, the customs invoice branch, and the CN22 registration guard: `customs.options.eori_number` first, then `shipper.state_tax_id`.
- Seller `vatNo` strictly from `shipper.federal_tax_id`, with the VAT requirement check tightened to match so the error key and the actual condition agree.
- Guard error text that tells the caller about the address fallback.

**Non-Goals:**

- Recipient-side changes: buyer `vatNo` keeps `recipient.tax_id`; the booking schema has no buyer EORI field.
- Address fallbacks for `voec_number` or `ioss_number`: no address field could carry them.
- Touching `enforce_customs_option_placement`, the EU VAT area omission, or any non-postnord connector (including `dhl_freight_sweden`'s own `eori_number` requirement).
- Server, dashboard, or schema/mapper changes: all PostNord request fields involved already exist in the generated schemas.

## Decisions

**Read the address fields directly, not `shipper.tax_id`.**
`tax_id`'s `federal_tax_id or state_tax_id` fold is precisely the ambiguity this change removes; routing EORI and VAT resolution through it would send a state-only value as both `eoriNo` and `vatNo`.
Alternative considered: keep `tax_id` for `vatNo` and add `state_tax_id` only for EORI (the double-duty option) — rejected by decision of record; a state-only shipper now fails the VAT requirement instead of having its EORI sent as a VAT number.

**Resolve the EORI once, next to the guard, in `units.py`.**
A small helper (colocated with `enforce_cn22_registration_numbers`) computes the resolved EORI from the customs options and the shipper, and the guard consumes it for its at-least-one check.
Both payload sites in `shipment/create.py` call the same helper, so precedence cannot drift between the CN22 branch, the invoice branch, and the guard.
Alternative considered: inline `options.eori_number.state or shipper.state_tax_id` at each site — three copies of one precedence rule is where the drift risk lives.

**Tighten the VAT check to `not shipper.federal_tax_id`.**
The error message already names `shipper.federal_tax_id`; only the condition widens to match the new source.
Seller `vatNo` becomes `shipper.federal_tax_id`; buyer `vatNo` stays `recipient.tax_id`.

**Test through the existing fixture pattern.**
Extend the module-level payloads in `tests/postnord/test_shipment.py` with `state_tax_id` variants rather than new fixture files, and assert on built requests (fallback present, precedence, guard satisfied) and on `SHIPPING_SDK_FIELD_ERROR` shapes (guard exhausted, state-only VAT failure), following the existing 4-method test style in `TestPostNordShipment` and `TestPostNordCustomsInvoice`.

## Risks / Trade-offs

- [State-only shippers booking parcel products with customs now fail instead of succeeding with a wrong VAT number] → deliberate breaking change recorded in the proposal; the field error names the fix (set `federal_tax_id`).
- [First connector in the codebase to source EORI from an address field] → deviation is documented in the proposal with the dpd option-then-address precedent; call it out again in the eventual upstream PR description.
- [A `state_tax_id` holding a non-EORI value reaches PostNord as an EORI] → caller data quality, same class of risk as any option value; PostNord validates at its end and rejects through the normal error path.
- [Existing tests asserting `eoriNo` from the option and the removed-federal VAT failure] → both keep passing: the fixtures carry the option (precedence) and no `state_tax_id` (guard and VAT conditions unaffected).

## Migration Plan

Code-only change, no data or API migration.
Rollback is a plain revert of the connector commits.
