---
title: Booking printout composition verification
---

# Booking printout composition verification

Evidence for the openspec change `stamp-embedded-customs-forms`, recorded 2026-09-28.

## Captures

| Capture | Source | Service | Format | Result |
|---|---|---|---|---|
| `~/Documents/postnord_cn22_and_shipment_label.zpl` | live booking call | `postnord_export_letter` (UX) | ZPL | One ZPL format (single `^XZ`): CN22 section (`^FX CUSTOMS_CN22_ROTATED^FS`) followed by the letter label (`^FX SE_INTERNATIONAL_LETTER_LABEL^FS`); `printoutComposition` `cn22` + `label` |
| `~/Documents/postnord_cn22_and_label_two_pages.pdf` | sandbox booking call | `postnord_export_letter` (UX) | PDF | One PDF, two A4 pages: page 1 a "PostNord Tracked Letter" label (`Item-ID`, no `Brev utrikes`/`Parcel ID`), page 2 an upright CN22; `printoutComposition` `cn22` + `label` |
| `agent-logs/karrio/postnord-customs-probe/probe1b_printid_unrestricted.pdf` | sandbox by-id, unrestricted | UX | PDF | One A4 page: CN22 rotated 90 degrees beside the letter label |
| `agent-logs/karrio/postnord-customs-probe/probe2c_printid_zpl.zpl` | sandbox by-id, unrestricted | UX | ZPL | Same layout as the live booking ZPL |
| `agent-logs/karrio/postnord-customs-probe/probe2b_printid_onlyCustomsDeclarations.pdf` | sandbox by-id, customs only | UX | PDF | Lone CN22, one A4 page, rotated; byte-identical to the `postnord_cn22.pdf` fixture |

## Findings

`printoutComposition` reported `cn22` + `label` in every booking capture, and the booking-call label carried both sections in both formats.
The PDF layout is not fixed: the by-id printout puts both sections on one rotated page, while the sandbox booking call put them on two pages with an upright CN22 and a different label template.
The earlier convention that PDF labels and declarations are separate documents while ZPL combines them was karrio's, not PostNord's.

Consequences implemented in the change (design D7): PDF label markers accept alternative templates (`lib.AnyOf`), and the combined PDF stamp anchors on the CN22 signature keyword rather than page coordinates, so both layouts resolve with one seed.

## Open

Live PDF stamping is deferred to the consumer side (user decision 2026-09-28); ZPL stamping is the supported live path.
The sandbox two-page PDF has not been compared with a live PDF booking.
Opted-in standalone documents (`postnord_standalone_customs_documents`) and service 91 are not yet captured; service 91 may print a different label template, which would be added as another marker alternative.
