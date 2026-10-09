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
| `~/Documents/postnord_postpaket_utrikes_label_and_cn22.zpl` | live booking call and UX print (identical) | `postnord_postpaket_utrikes` (91) | ZPL | Two ZPL formats (two `^XZ`): parcel label (`^FX NORDIC_SHIPPING_LABEL^FS`, `^LL1520`) followed by an upright CN22 (`^FX CUSTOMS_CN22_V2^FS`, `^LL840`, `^FWN`); `printoutComposition` `cn22` + `label` |
| `~/Documents/postnord_postpaket_utrikes.pdf` | user capture (source not recorded) | `postnord_postpaket_utrikes` (91) | PDF | One PDF, two pages: page 1 an "International Parcel" label (`Item-ID`), page 2 an upright CN22; `printoutComposition` `cn22` + `label` |

## Findings

`printoutComposition` reported `cn22` + `label` in every booking capture, and the booking-call label carried both sections in both formats.
The PDF layout is not fixed: the by-id printout puts both sections on one rotated page, while the sandbox booking call put them on two pages with an upright CN22 and a different label template.
The earlier convention that PDF labels and declarations are separate documents while ZPL combines them was karrio's, not PostNord's.

Consequences implemented in the change (design D7): PDF label markers accept alternative templates (`lib.AnyOf`), and the combined PDF stamp anchors on the CN22 signature keyword rather than page coordinates, so both layouts resolve with one seed.

The 91 bookings were sent `customsDeclarationCN22`, as the connector does for every product, and PostNord printed that form back; this is not evidence that PostNord accepts a CN22 for 91, whose published requirement is a CN23 at any value (`docs/notes/customs/nordic-trade-documents-facts.md`, requirements by product).
The 91 printout uses different templates from the letter services: a parcel label marked `NORDIC_SHIPPING_LABEL` and an upright CN22 marked `CUSTOMS_CN22_V2`, in a second ZPL format rather than the same one.
Before group 7 the 91 ZPL classified as `none` and the 91 PDF as lone `cn22`, so the live booking on develop `8f6d9af93` emitted a false `postnord_unexpected_label_composition` warning.

Consequences implemented in the change (design D8): the ZPL and PDF markers accept the 91 templates as `lib.AnyOf` alternatives, and the combined ZPL seed anchors on the CN22 signature keyword in the field's reading frame and inserts the stamp into the format containing it.
One geometry fits both ZPL layouts: `^FO7,303` on the rotated letter CN22 (unchanged) and `^FO293,758` in the 91 CN22 V2 signature area.
The PDF keyword seed from D7 lands inside the 91 CN22 signature area on page 2 without change.
Both 91 captures are fixtures on `feat-postnord-cn22-stamping` (`postnord_label_cn22_international_parcel.{zpl,pdf}`), with booking verification tests on `feat-postnord-customs-invoice`; develop `6d7c37d7b` carries the fix.

## Open

Live PDF stamping is deferred to the consumer side (user decision 2026-09-28); ZPL stamping is the supported live path.
The sandbox two-page PDF has not been compared with a live PDF booking.
Opted-in standalone documents (`postnord_standalone_customs_documents`) are not captured (task 5.1.3 deferred 2026-09-28: the UX duplicate-shipment method used for iterative testing cannot change shipment metadata); issues will be raised as encountered.
A standalone 91 CN22 V2 from the opt-in fetch would still resolve the lone `cn22/ZPL/*` seed's label-axis offset (`PRDs/POSTNORD_CN22_STAMPING.md` D9), which is unverified against that layout.
Whether 91 should declare a CN23 rather than a CN22 is a separate connector question outside this change; if the connector switches, PostNord will presumably print a different form, which the D8 markers and seed would not recognise, so the booking check would warn again until a new capture adds its markers and geometry.
