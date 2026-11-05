---
title: PostNord NVIT customs facts
---

# PostNord NVIT customs facts

Provenance: extracted from `PRDs/POSTNORD_NVIT_CUSTOMS.md` on branch `backup-develop-2026-09-24` (last commit `144943753`, PRD dated 2026-09-22); the upstream-bound summary now lives in the Future Work section of `PRDs/PRD_POSTNORD_INTEGRATION.md`.
The "Current connector status" section was verified against `develop` at `ecb449c43` on 2026-09-28.

## Fact sheet

NVIT expands to norske varer i transitt, Norwegian goods in transit.
It covers goods moving from Norway to Norway routed via Sweden or Finland.
PostNord identifies the affected flows by postcode band: 0001–7999 to 8000–9999, and 8000–9499 to 9500–9999.
The legal basis is the Transit Convention; NCTS phase 5, live since 2025-01-21, makes a six-digit HS code mandatory for transit goods.
The temporary arrangement (collective code 54.02.53 plus a generic description) ended on 2026-03-31.
From 2026-04-01 the full requirement applies per goods line (varelinje): ordinary trade description, six-digit HS number, net weight, gross weight, and packaging (type, count, mark).
HS codes must have at least six digits and contain no spaces.
The carrier files the NCTS transit declaration; the merchant's obligation is complete data at booking.
Accepted channels are the TA system, EDI (IFTMIN), the API/Booking solution, and the Portal, and the data is never carried on the parcel itself.
PostNord's NVIT contact address is nvit@postnord.com.
VOEC is a separate regime (Norwegian import VAT, B2C under NOK 3,000, Skatteetaten registration) and rides the `voec` field that exists in all three declaration branches.

## Sources

| Source | Location | Statement | Grade |
|---|---|---|---|
| toll.no news, published 2026-02-10 | <https://www.toll.no/no/bedrift/nyheter-for-naeringslivet/midlertidig-ordning-for-nvit-opphorer> | Temporary NVIT arrangement ends 2026-03-31; six-digit HS required for transit goods | Fetched 2026-09-22 |
| toll.no NVIT page | <https://www.toll.no/no/bedrift/transport-og-tollager/norske-varer-i-transitt> | Per-varelinje data list; NCTS-5 since 2025-01-21 | Fetched 2026-09-22 |
| postnord.no NVIT article (EN) | <https://www.postnord.no/en/news/new-requirements-for-norwegian-goods-in-transit-nvit/> | Per varelinje, not per sending; HS at least six digits without spaces; channels; never on the parcel; postcode bands; nvit@postnord.com | Fetched 2026-09-22 |
| postnord.se customs-documents page | <https://www.postnord.se/en/business/import-export-customs/customs-documents-and-shipping-documents> | Commercial invoice requires net and gross weight per goods item and total gross; the invoice is a sufficient basis for PostNord to create the export declaration; CN23 thresholds (at most SEK 2,000 commercial) | Fetched 2026-09-22 |
| Vendored booking swagger v3.5.29.1 | `modules/connectors/postnord/vendor/booking.swagger.json` | Field names; `voec` "For import to norway"; `splitShipmentReference` "For export to Norway" (example `21100023_1111111`); endpoints `POST /v3/customs/declaration{,/pdf}` and `/v3/customs/consolidation` | Wire capture |
| Live verification 2026-09-21 | [customs-declaration-live-verification.md](customs-declaration-live-verification.md) | Booking-time CN22 and post-booking declarations accepted in sandbox and production | Live |
| Packrooster changelog (third party) | <https://approosters.com/pages/packrooster-changelog> | `reasonForExportation` codes 1000 (sale) and 1040 (return) | Third party |
| Developer portals | developer, atdeveloper, and guide.postnord.com | JavaScript single-page apps; official field descriptions are not fetchable without a portal application key | Limitation |

The PRD flagged one stale index entry: a quoted postnord.se sentence ("From 1 April 2026 ... split shipments, multi-parcel ...") was absent from the page as fetched on 2026-09-22, so the postnord.no article is the primary source for scope.
Which declaration branch PostNord expects for NVIT flows was never confirmed by PostNord; the PRD graded `customsInvoice` as an inference from branch structure and the postnord.se invoice guidance, and the confirmation mail to nvit@postnord.com was deferred by the user on 2026-09-22.

## Declaration branch capability matrix

Evidence is the generated schemas plus the vendored swagger; all three branches attach at the shipment element.
The last row reflects the connector as of 2026-09-22 and is superseded by the current status section below.

| Capability | CN22 | CN23 | customsInvoice |
|---|---|---|---|
| Line description | yes | yes | yes |
| Line HS code | yes | yes | yes, plus `returnHsTariffNumber` |
| Line net weight | no | no | yes |
| Line gross weight | yes | yes | yes |
| Per-parcel link | no | envelope `itemIds` | row `refItemIds` plus envelope `ids` |
| Split shipment | no | no | `splitShipmentId` (deprecated) or `splitShipmentReference` |
| Totals | `totalGrossWeight`, `totalValue` | same as CN22 | `totalNetWeight`, `totalGrossWeight`, `totalNumberOfPackages` |
| Mapped by connector (2026-09-22) | booking time | proxy only | proxy only |

## Field reference

NVIT requirement mapped to the PostNord invoice-branch field, as recorded in the PRD.

| NVIT requirement | Invoice-branch field |
|---|---|
| Trade description | `detailedDescription[].content` |
| HS code (at least six digits, no spaces) | `detailedDescription[].hsTariffNumber` |
| Net weight | `detailedDescription[].netWeight`, `totalNetWeight` |
| Gross weight | `detailedDescription[].grossWeight`, `totalGrossWeight` |
| Packaging type, count, mark | `marksAndNumbers`, `units`, `quantity`, `totalNumberOfPackages` |
| Per-parcel linkage | row `refItemIds`, envelope `ids` |
| Split shipment | `splitShipmentReference` |
| Returns | `invoice.reasonForExportation` (1040), `returnHsTariffNumber` |

Returns from Norway need `reasonForExportation` 1040 on the invoice and `returnHsTariffNumber` on the rows.
Two booking fields relevant to NVIT remain unmapped by the connector: the envelope `splitShipmentReference` and the goodsItem `goodsDescription`.

## Edge cases recorded in the PRD

| Scenario | Proposed handling |
|---|---|
| Same goods line in several parcels | One row whose `refItemIds` lists every containing parcel |
| Several lines in one parcel | Several rows referencing that parcel's item id |
| Net weight absent on some lines | Deterministic fallback (net equals gross, or reject), not silence |
| HS shorter than six digits or containing spaces | Validate and reject before sending |
| Row count above the branch limit | Extend the 13-line guard once the invoice limit is verified |
| Return from Norway | `reasonForExportation` 1040 and `returnHsTariffNumber` rows |
| Missing currency for line values | No silent currency guessing |

## Current connector status

Parcel products book the `customsInvoice` branch: `customs_structure` returns CN22 for the letter services and International Parcel (91) and `customsInvoice` for every other service (`modules/connectors/postnord/karrio/providers/postnord/units.py:271-293,389-397`), and the booking selects the builder accordingly (`modules/connectors/postnord/karrio/providers/postnord/shipment/create.py:752-782`).
The invoice builder `_customs_invoice` spans `create.py:582-650`.
Each invoice line sends `netWeight` equal to `grossWeight`, both taken from the single commodity line weight (`create.py:556-570`).
At the envelope, `totalNetWeight` is the sum of line weights and `totalGrossWeight` is the parcel weight, falling back to the line sum when no parcel weight is given (`create.py:605-606,639-648` and `create.py:358-371`).
`ExportReason` defines only `permanent_export = "1000"` (`units.py:383-386`), and the invoice always sends it (`create.py:634`); returns reuse the create flow unchanged (`modules/connectors/postnord/karrio/providers/postnord/shipment/return_shipment.py`), so a return sends 1000 rather than 1040.
No invoice row carries `returnHsTariffNumber`, `refItemIds`, or envelope `ids`, and `splitShipmentReference` and `goodsDescription` are not set anywhere in `create.py`.
Every goodsItem uses the constant `itemId="0"`, which asks PostNord to allocate the parcel id (`create.py:862-868`), so no per-parcel linkage is possible at booking time.
`Parcel.items` is not read by the booking mapping.

## Interim path

A consumer can build a `CustomsInvoiceType` declaration and submit it per parcel item id through `gateway.proxy.create_customs_declaration` or `create_customs_declaration_pdf`, one item id per declaration object, subject to the shared 13-line guard.
The recipe is in [../guides/postnord-customs-declaration-proxy.md](../guides/postnord-customs-declaration-proxy.md).
