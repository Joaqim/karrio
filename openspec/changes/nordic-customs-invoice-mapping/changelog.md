# Changelog entry (draft for the next release)

CHANGELOG.md is compiled by release commits from the git log, so this draft stages the entry here for the release step rather than inserting an unreleased section into a file whose sections are all releases.
Commits are on `feat-postnord-customs-invoice` (base `feat-postnord-connector` 01262fbb4) and `feat-dhl-freight-se-customs` (base `feat-dhl-freight-se-connector` 817d97abf).

## Features

- feat(postnord): classify services into customs product groups.
  Letter services (`LETTER_SERVICES`) and International Parcel keep the CN22 declaration; every other service is a parcel product.
- feat(postnord): send `customsInvoice` for parcel products with customs data.
  The invoice is built from unified data: shipper as seller, recipient as buyer, `customs.invoice` (falling back to the shipment reference) and `customs.invoice_date`, commodities as detailed description, and PostNord's invoice export declaration type.
  `customs.commercial_invoice` true selects COMMERCIAL, false or omitted selects PROFORMA.
- feat(postnord): reject CN22 declarations without registration numbers before any request is sent.
- feat(postnord): attach the customs invoice PostNord composes for parcel bookings to the shipping documents (`docs.extra_documents`), fetched by printId as for export letters and categorized by the printout composition; retrieval failure does not fail the booking.
- docs(postnord): document the customs invoice selection for parcel products in the connector README.
- feat(dhl_freight_sweden): add the customs additional services to the transport instruction schema.
- feat(dhl_freight_sweden): send `customs.options.eori_number` as `CustomsDocument.eori` and apply `customs.commercial_invoice` literally as the document type.
- feat(dhl_freight_sweden): add opt-in customs service options that are never selected implicitly: `dhl_freight_sweden_customs_handling_standard`, `dhl_freight_sweden_customs_handling_full_service`, `dhl_freight_sweden_customs_own_declaration` with `dhl_freight_sweden_customs_own_declaration_id`, and `dhl_freight_sweden_customs_joint_declaration` with `dhl_freight_sweden_customs_joint_declaration_id`.
  `customs.options.voec_number` is sent as the `voecSupplyVAT` service.
- feat(dhl_freight_sweden): fail fast on standard customs handling without EORI, own declaration without customs identifier, and joint declaration without SFID.
- feat(dhl_freight_sweden): fall back the customs invoice number to the shipment reference and the invoice date to the shipping date, then the booking date.
- feat(dhl_freight_sweden): omit customs information, customs services, and VOEC within the EU VAT area with a warning, treating special fiscal territories (Åland, Canary Islands, Ceuta, Melilla, Büsingen, Heligoland, Livigno, Campione d'Italia) as outside it.

## Fixes

- fix(postnord): type customs invoice party postal codes as strings, so leading zeros such as Norwegian `0154` survive serialization.
- fix(postnord): declare customs line values and weights as quantity totals on CN22 and customs invoice lines.
- fix(postnord): declare the CN22 total gross weight from parcel weights, falling back to the sum of line weights.
- fix(dhl_freight_sweden): send customs commodity net weight in kilograms regardless of the commodity weight unit.
- fix(dhl_freight_sweden): declare customs commodity value and net weight as quantity totals.

## Breaking changes

- PostNord parcel products with customs data send `customsInvoice` instead of `customsDeclarationCN22`, and the composed customs document is categorized as a customs invoice.
  Migration: consumers reading a CN22 from parcel bookings read the customs invoice document instead, and consumers needing a CN22 book a letter service or International Parcel.
- PostNord CN22 declarations (letter services and International Parcel) without any of EORI, VOEC, or IOSS fail with a field error on `customs.options` instead of being rejected by PostNord with `SACUS-BR-24062502`.
  Migration: send `customs.options.eori_number`, `voec_number`, or `ioss_number`.
- PostNord parcel customs invoices require the shipper tax id, contact name and phone number for both shipper and recipient, and `hs_code` and `origin_country` on every commodity, and fail with field errors naming each missing field.
  Migration: set shipper `federal_tax_id` (or `state_tax_id`), `person_name` (or `company_name`) and `phone_number` on shipper and recipient, and `hs_code` and `origin_country` on each commodity.
- PostNord and DHL Freight Sweden customs line values and weights are now per-unit value and weight multiplied by quantity, so declared line and total values for quantities above one were previously understated.
  Migration: send per-unit `value_amount` and `weight` on commodities; consumers that pre-multiplied by quantity to compensate stop doing so.
- PostNord CN22 total gross weight is the sum of parcel weights, including packaging, rather than the sum of commodity weights.
  Migration: set parcel weights to the shipped gross weight.
- DHL Freight Sweden customs documents with an invoice number and `commercial_invoice` false are typed ProformaInvoice instead of CommercialInvoice.
  Migration: set `customs.commercial_invoice` true for goods sold.
- DHL Freight Sweden omits customs information, customs services, and VOEC when shipper and recipient are both inside the EU VAT area, returning the warning `customs_omitted_intra_eu`.
  Migration: none required to book; consumers that relied on customs data being sent within the EU VAT area handle the warning.
- DHL Freight Sweden customs documents take the shipment reference when `customs.invoice` is absent and the shipping date or booking date when `customs.invoice_date` is absent, and fail with a field error on `customs.invoice` when neither invoice number nor reference exists.
  Migration: send `customs.invoice` and `customs.invoice_date`, or a shipment reference.
- DHL Freight Sweden customs services are selected only through the new options, and each selector without its required identifier fails fast.
  Migration: set `dhl_freight_sweden_customs_handling_standard` together with `customs.options.eori_number`, `dhl_freight_sweden_customs_own_declaration` together with `dhl_freight_sweden_customs_own_declaration_id`, or `dhl_freight_sweden_customs_joint_declaration` together with `dhl_freight_sweden_customs_joint_declaration_id`.
