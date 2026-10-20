# PostNord customs invoice — live verification findings

Record of the sandbox gate for the `nordic-customs-invoice-mapping` OpenSpec change (tasks 1.2 and 1.3), run on 2026-09-25.
Evidence comes from `openspec/changes/nordic-customs-invoice-mapping/verify_live.py` against the `atapi2.postnord.com` test host with test-mode bookings (`testIndicator=true`) on `POST /rest/shipment/v3/edi/labels/pdf`.
Credentials are referenced by environment variable name only (`POSTNORD_APIKEY`, `POSTNORD_CUSTOMER_NUMBER`, `POSTNORD_EORI`); no key, customer number, or EORI value appears in this note or in the script output, which was checked against the environment values after each run.
The script refuses to run when `POSTNORD_APIKEY` equals `POSTNORD_LIVE_APIKEY` or when the connector's server URL is not the sandbox host.

## Method

The connector (as installed on `develop`) serializes a `postnord_parcel` booking (basic service code 18) from Stockholm, SE to Oslo, NO without customs data.
The script then injects a hand-built `customsInvoice` into `shipment[0]`, the `shipmentCustomsv2` location defined by `vendor/booking.swagger.json`, and posts the body directly so the HTTP status is observable.

The invoice follows the design field table and the swagger's required fields:

| Field | Value sent |
|---|---|
| `type` | `COMMERCIAL` |
| `declarationType` | `invoiceExportDeclaration` |
| `seller` | shipper address and contact, `vatNo` (fixture value), `partyIdentification` `{partyId: <customer number>, partyIdType: "160"}`, `eoriNo` in variant A only |
| `buyer` | recipient address and contact, no `vatNo` |
| `invoice` | `invoiceNo`, `shippingDate` `2026-09-25`, `reasonForExportation` `"1000"` |
| `detailedDescription` | two lines with `quantity`, `hsTariffNumber`, `content`, `countryOfOrigin`, `netWeight`, `grossWeight`, `itemValue` (SEK) |
| `invoiceTotal`, `totalGrossWeight` | sums over the lines (SEK 500.00, 0.5 KGM) |

No `voec`, `ioss`, `shipTo`, `freightCost`, or `invoiceSubTotal` was sent in either variant.

## Variant A: EORI on the seller

Accepted on the first attempt: HTTP 200, no `compositeFault`, `idInformation[].status` `OK`, one item id with a `printId`.
`labelPrintout[].printoutComposition` reports `label: 1` and `customsInvoice: 1`, with `cn22` and `cn23` at 0.
The returned printout is a two-page PDF (about 21 450 base64 characters); page 2 contains the words "INVOICE" and "COMMERCIAL", and neither page contains "CN22" or "CN23".

## Variant B: no registration numbers

Accepted on the first attempt with the same response shape: HTTP 200, no fault, status `OK`, and the same composition `label: 1`, `customsInvoice: 1`.
The printout is again a two-page PDF with the invoice on page 2.
PostNord's CN22 rule `SACUS-BR-24062502` ("Customs CN22/CN23 should have either EORI, VOEC, IOSS") is not applied to a `customsInvoice` on a test-mode parcel booking.

## Composed customs invoice in test mode

Unlike the export-letter CN22 flow recorded in `customs-declaration-live-verification.md`, where composed documents could only be observed in production, a test-mode parcel booking with `customsInvoice` returns the composed invoice inline in the booking's label printout.
The by-id printout fetch (`/v3/labels/ids/pdf` with `onlyCustomsDeclarations`) was not exercised in this round.
The label printout composes label and invoice together, so a connector that surfaces the invoice as a separate document would duplicate it unless it splits or refetches, as design D2 of the archived customs change accepted for CN22.

## Residuals

Whether production applies `SACUS-BR-24062502` to customs invoices remains for the production probe (task 6.2); the sandbox has previously matched production on this rule for CN22.
A `PROFORMA` invoice, a buyer `vatNo`, and ZPL labels were not exercised.
The seller `vatNo` was a fixture value; the sandbox did not validate it against a register.

## Production probe 2026-09-25

Task 6.2 booked one parcel in production with explicit user approval, using `openspec/changes/nordic-customs-invoice-mapping/verify_prod_probe.py --production` against `api2.postnord.com`.
The script runs from the `feat-postnord-customs-invoice` worktree, and the connector module resolved into that worktree before the network call.
Unlike the sandbox gate, the booking goes through the karrio gateway and the branch connector, so the connector built the customs invoice and ran the by-id fetch itself.
Credentials were read by environment variable name only: `POSTNORD_LIVE_APIKEY`, `POSTNORD_LIVE_CUSTOMER_NUMBER`, and `POSTNORD_LIVE_APPLICATION_ID`, with `POSTNORD_EORI` held back for a fallback attempt that was not needed.
The script output was checked against every one of these values before recording; none appears in it or in this note.

The booking was `postnord_parcel` (basic service code 18) from Stockholm, SE to Karl Johans gate 1, 0154 Oslo, NO, 0.5 kg.
The shipper address and shipper VAT number were the sandbox fixture values (Sandhamnsgatan 61, 11528 Stockholm, and the fixture `vatNo`), not the account holder's real data.
The customs data was one commodity line (candy, HS 1704906500, origin SE, quantity 2, EUR 15.00 and 0.19 kg per unit), `commercial_invoice` true, and `customs.invoice` set.
The connector sent a `COMMERCIAL` `customsInvoice` with a line total of EUR 30.00 and 0.38 kg, `totalGrossWeight` 0.5 KGM, and no `eoriNo`, `voec`, or `ioss`.

### Attempt A: no registration numbers

Accepted on the first attempt: `idInformation[].status` `OK` with one item id and a printId, and no `compositeFault`.
The fallback attempt with the EORI was therefore not run, and exactly one booking was made.
The booking printout composition was `label: 1`, `customsInvoice: 1`, with `cn22` and `cn23` at 0, and the parsed shipment reports `meta.printout_composition` `["customsInvoice", "label"]`.
The label document is a PDF of 15,917 bytes (21,224 base64 characters) that combines the label and the invoice, as in the sandbox.

PostNord does not apply `SACUS-BR-24062502` to a customs invoice on a production parcel booking, which matches the sandbox result, so the connector's choice to leave the invoice path without a registration check holds.

### Composed customs invoice by printId

The connector's implicit by-id fetch (`POST /rest/shipment/v3/labels/ids/pdf` with `definePrintout=onlyCustomsDeclarations`, keyed by the booking's printId) returned member status `OK` and composition `customsInvoice: 1` with every other kind at 0.
The connector attached it as one `extra_documents` entry with category `customsInvoice`, format PDF, 2,711 bytes (3,616 base64 characters), `%PDF-` magic.
No message was raised.
The document contents were not saved to the repository.

### Booking left unshipped

PostNord offers no cancellation endpoint, so the booking was left unshipped rather than cancelled; the user confirmed that unshipped live-test bookings are not billed.

| Id | Value |
|---|---|
| item id (tracking number) | 00573132901949477786 |
| printId | 7879e5cd3edd4ed6bc8a36bd354e86cb |
| bookingId | ILPN001B0L6J8NTDEDBHZCGCOOHPTG |

The ZPL by-id fetch, a `PROFORMA` invoice, and a buyer `vatNo` were not exercised in production.
