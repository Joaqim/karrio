# Proposal

## Why

Neither Nordic connector transmits the customs data its carrier expects for commercial exports, and `customs.commercial_invoice` is not honoured consistently.
PostNord sends a CN22 for every product whenever commodities are present, while PostNord requires a customs invoice instead of CN22/CN23 for parcel products and CN23 plus an invoice for letters and postal parcels above SEK 2 000 or sent for commercial purposes; a missing digital customs invoice or missing EDI is charged SEK 75 to SEK 250.
DHL Freight Sweden already maps the invoice type but omits the EORI that Standard customs handling requires, and exposes none of the customs services that DHL requires to be selected for Norway, Åland, Switzerland, Great Britain, and other non-EU destinations.
Facts and sources are collated in `docs/notes/customs/nordic-trade-documents-facts.md`.

## What Changes

- Fix the meaning of `customs.commercial_invoice` for both connectors as the invoice type selector: true declares a commercial invoice (goods sold), false a proforma invoice (goods not sold), matching the DHL Express and DHL Freight Sweden reading and PostNord's `customsInvoice.type`.
- PostNord: select the customs structure by product group instead of always sending CN22.
  Parcel products (MyPack Home, MyPack Collect, Parcel, Pallet, and siblings) send `customsInvoice`; letter services and International Parcel (91) keep sending CN22.
  The CN22 versus CN23 selection and value thresholds (PostNord SE's SEK 2 000) are deferred to a later change once more detailed guidance is gathered.
- PostNord: build `customsInvoice` from unified data (shipper as seller, recipient as buyer, `customs.invoice` and `invoice_date`, commodities as detailed description, declared totals and gross weight), with `declarationType` defaulting to PostNord's invoice export declaration.
- PostNord: surface the customs invoice PostNord composes for parcel bookings in the shipping documents, categorized by PostNord's printout composition, as already done for export letters.
- Verify in the PostNord sandbox, before implementation, that a booking accepts `customsInvoice` for parcel products and whether a single booking accepts CN23 together with `customsInvoice`.
- DHL Freight Sweden: map `customs.options.eori_number` to `CustomsDocument.eori` and `customs.options.voec_number` to the `voecSupplyVAT` service.
- DHL Freight Sweden: expose the customs services (`customsHandlingStandard`, `customsHandlingFullService`, `customsCustomersOwnDeclaration` with `customsId`, `customsJointDeclaration` with `sfid`) as explicit connector options that are never selected implicitly, because each carries a DHL fee.
- **BREAKING** for PostNord consumers booking parcel products with customs data: the booking carries `customsInvoice` instead of CN22, and the composed customs document kind changes accordingly.

Out of scope: CN22 versus CN23 selection and value thresholds; advisory warnings about consumer duties (printing, attaching, emailing invoices), which belong to the separate shipment-advisors change and the Nordic conventions plugin; karrio-rendered invoice templates; connectors other than PostNord and DHL Freight Sweden.

## Capabilities

### New Capabilities

- `dhl-freight-sweden/customs`: how the DHL Freight Sweden connector carries customs documents, registration numbers, and customs services in the transport instruction, including the invoice-type meaning of `commercial_invoice` and the explicit opt-in rule for priced customs services.

### Modified Capabilities

- `postnord/customs-declaration`: the booking-time requirement changes from "always CN22 lines" to a customs structure selected by product group, with a customs invoice built from unified data for parcel products and typed by `commercial_invoice`; composed customs invoices are surfaced for parcel bookings.

## Impact

- `modules/connectors/postnord/karrio/providers/postnord/shipment/create.py` (customs builder), `units.py` (product-group classification, options), and tests under `modules/connectors/postnord/tests/postnord/`; the generated schema already contains `customsInvoice` and `customsDeclarationCN23`, so no regeneration is expected.
- `modules/connectors/dhl_freight_sweden/karrio/providers/dhl_freight_sweden/shipment/create.py`, `units.py`, and tests; schema regeneration only if the generated transport-instruction types lack the customs service objects.
- Consumer-visible: PostNord booking payloads and returned document kinds for parcels with customs; new DHL Freight Sweden options.
- Delivered on a feature branch off `upstream/main` in the fork and assembled into `develop`; upstream submission follows the connectors' own upstream path.
