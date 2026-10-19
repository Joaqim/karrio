# Proposal

## Why

The postnord connector sources every customs registration number exclusively from customs options.
The CN22 guard `enforce_cn22_registration_numbers` rejects a booking when none of `customs.options.eori_number`, `voec_number`, or `ioss_number` is set, even when the shipper address already carries the identifiers in `state_tax_id` (EORI) and `federal_tax_id` (VAT).
Orders that model tax identifiers on the party address therefore fail with a field error instead of using the data at hand.

## What Changes

- EORI resolution becomes customs option first, address second: `customs.options.eori_number`, falling back to `shipper.state_tax_id`.
- The fallback applies to both customs structures: the CN22 `EORIorPersonalIdNumber` field and the customs invoice `eoriNo` field.
- The CN22 registration-number guard is satisfied by `shipper.state_tax_id`, and its error message names the address fallback.
- **BREAKING** the customs invoice seller `vatNo` becomes strictly `shipper.federal_tax_id`.
  Today it uses `shipper.tax_id`, which resolves `federal_tax_id or state_tax_id`, so a state-only shipper's EORI is currently sent as a VAT number; under the new rule such a booking fails the VAT requirement with a field error instead.
- The recipient side is unchanged: buyer `vatNo` keeps coming from `recipient.tax_id`, and no buyer EORI field exists in the booking schema.
- The seller VAT requirement itself stays (PostNord's booking schema requires it for customs invoices); only its source tightens.

## Capabilities

### New Capabilities

### Modified Capabilities

- `postnord/customs-declaration`: the "Customs data is declared at booking time" requirement changes in three ways.
  Sender registration numbers resolve from customs options with a `shipper.state_tax_id` fallback instead of options only, the CN22 fail-fast accepts that fallback, and the customs invoice's seller VAT number source tightens from `federal_tax_id or state_tax_id` to `federal_tax_id` alone.

## Impact

- Code: `modules/connectors/postnord/karrio/providers/postnord/units.py` (guard, docstrings) and `modules/connectors/postnord/karrio/providers/postnord/shipment/create.py` (EORI resolution, seller `vatNo`, VAT requirement check).
- Tests: `modules/connectors/postnord/tests/postnord/test_shipment.py` — no existing fixture sets `state_tax_id`, so new fixtures and cases cover the fallback paths, the guard relaxation, and the tightened VAT check.
- No mapper or schema changes: `EORIorPersonalIdNumber`, `eoriNo`, and `vatNo` already exist in the generated request schemas.
- No server-side changes: customs options remain a free-form dict; the fallback is connector-side.
- Convention deviation, deliberate: no karrio connector currently reads EORI from an address field (all use `customs.options.eori_number`), and this is the first.
  The closest precedent is the dpd connector's option-first-then-address fallback for `vatNumber`.
  The deviation should be called out when this connector's customs work goes upstream.
