## Why

A PostNord booking from Göteborg (SE) to Montreal (CA) on service `34` failed with a message that names no line and no unified field:

```
code: CONTENT
message: content is a required field
details.references: CustomerOriginValidationError.type = MANDATORY_FIELDS_MISSING, CustomerOriginValidationError.subType = CONTENT
```

The request carried `customsDeclarationCN22.detailedDescription[0]` without `content`, because the connector fills `content` from `commodity.title or commodity.description` (`create.py:405`, and `:567` for customs invoice lines) and the commodity had neither.
PostNord's fault carries no row number or field path, and the parser discards the response's top-level `message` ("Invalid indata object EdiInstruction") whenever a fault has its own text.
The connector already fails fast on other customs input PostNord would reject (line limits, CN22 registration numbers, customs option placement), but not on a missing goods description.

## What Changes

- Reject a booking before it is sent when any CN22 or customs invoice line would lack a goods description, with a field error naming `customs.commodities[<index>].title` and stating that PostNord requires a title or description per customs line. No fallback to `sku` or other fields.
- Append a hint naming the unified field to fill to PostNord fault messages whose subType is known, keeping PostNord's text first and its references in `details`.
- Keep the response's top-level `message` in the message details when a fault carries its own text.
- Add `faultReferences` to the fault objects in `schemas/shipment_response.json` and regenerate, so parsing a fault no longer logs a jstruct "unknown arguments" warning.

## Capabilities

### New Capabilities

- `postnord/error-messages`: how PostNord fault responses become unified messages, including hints and retained response context.

### Modified Capabilities

- `postnord/customs-declaration`: adds a fail-fast requirement for customs lines without a goods description.

## Impact

- Code on a new branch `fix-postnord-customs-line-content` from `fix-postnord-eu-vat-territories`: `modules/connectors/postnord/karrio/providers/postnord/units.py`, `shipment/create.py`, `error.py`, `schemas/shipment_response.json` and the regenerated `karrio/schemas/postnord/shipment_response.py`, with connector tests.
- API: bookings with an untitled, undescribed customs commodity now fail locally with a field error instead of a PostNord fault; PostNord fault messages with a known subType gain a hint suffix.
- Fork: the branch is added to `BRANCHES` after `fix-postnord-eu-vat-territories`, and develop is rebuilt with `rebuild-develop.sh`.
- Out of scope: the dashboard allowing commodities and order line items without a title.
