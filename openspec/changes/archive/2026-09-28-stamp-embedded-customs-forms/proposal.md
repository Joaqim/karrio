## Why

Consumers stamp PostNord customs declarations after booking, but the SDK only knows a document is a CN22 when the caller says so, and it cannot tell a lone CN22 from the combined CN22 + shipping label that PostNord actually returns at booking.
A live capture confirms the combined ZPL form: one format (single `^XZ`) whose first part is the CN22 layout (marked `^FX CUSTOMS_CN22_ROTATED^FS`) and whose second part is the letter label (marked `^FX SE_INTERNATIONAL_LETTER_LABEL^FS`); PDF bookings likewise compose label and CN22 onto a single A4 page, so neither format separates them by structure alone.
The existing stamping design assumed PDF labels and declarations are always separate while ZPL combines them; that split was a karrio convention, not PostNord API behavior, and it left the two formats non-interchangeable (the export letter additionally receives a duplicate standalone CN22 by default, and service 91 none).

## What Changes

- Add a pure SDK customs-composition classifier returning lone `cn22`, combined label + `cn22`, or no customs, with the registry document type to stamp under: decided by carrier-declared section markers in both formats (ZPL field comments, PDF page text), never by the CN22 marker alone.
- Add registry seeds for the combined form in ZPL (keyword) and PDF (placement measured on the combined page); the existing `cn22/ZPL/*` and `cn22/PDF/A4` seeds are kept unchanged.
- Specify that PostNord bookings for CN22-bearing letter services return the complete composed printout (label + CN22) as `docs.label` in both formats, with PDF and ZPL following one interchangeable flow.
- Verify the returned label at booking with the classifier in both formats; an unexpected composition is a warning message, never a booking failure, since the label remains valid and post-booking customs verification is the consumer's responsibility.
- Make standalone customs documents opt-in through a booking option for both formats, extended to every CN22-structured service: the letter services and the International Parcel (`91`). This changes the default for export letters, which currently receive a standalone CN22 in `extra_documents`; the feature has not been merged upstream, so the fork is its only consumer.
- Out of scope, recorded as follow-ups: a second `declarationOnly` call as an opt-out, CN23 for service 91, and parcel customs-invoice composition.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `documents/stamping`: adds customs-composition classification for ZPL and PDF and registry seeds for the combined label + CN22 form, alongside the retained lone-CN22 seeds.
- `postnord/customs-declaration`: bookings return the composed label + CN22 in both formats, verified with a warning on mismatch; standalone customs documents become opt-in for both formats; renames and revises "Implicit standalone customs document for export letter bookings" and "Document kinds reflect PostNord printout composition".

## Impact

- SDK: `modules/sdk/karrio/core/utils/stamping.py` (classifier, combined-form resolution), `modules/sdk/karrio/core/metadata.py` (declared sections), and stamping tests.
- PostNord connector: `providers/postnord/shipment/create.py`, `mappers/postnord/proxy.py` (opt-in standalone declaration for all CN22-structured services, both formats), `providers/postnord/stamping.py` (new seed), plugin metadata, and fixtures including the live combined ZPL capture (no personal data) and the earlier by-id PDF/ZPL probe captures; a live booking capture for service 91 is still to be taken.
- Branches: SDK work on `feat-document-stamping`; PostNord work on `feat-postnord-cn22-stamping` and `feat-postnord-customs-invoice`.
- Consumers: `docs.label` is unchanged in both formats; export letter consumers stop receiving the standalone CN22 unless they opt in, and may see a composition warning message.
