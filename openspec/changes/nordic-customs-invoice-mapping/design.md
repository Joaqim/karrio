# Design

## Context

See proposal.md for motivation and the spec deltas for required behaviour; source facts are in `docs/notes/customs/nordic-trade-documents-facts.md`.
PostNord builds CN22 lines in `_customs_line` and `_customs_declaration` (`modules/connectors/postnord/karrio/providers/postnord/shipment/create.py:242-342`), guarded by `enforce_customs_declaration_lines` and `enforce_customs_option_placement` (`.../postnord/units.py:262-310`), and attaches the result as `customsDeclarationCN22` (`create.py:546`).
The generated schema already has `CustomsInvoiceType`, `BuyerType`, `InvoiceType`, and `CustomsInvoiceDetailedDescriptionType` (`.../schemas/postnord/shipment_request.py:132-241, 364`).
The Export Letter customs document fetch (`.../mappers/postnord/proxy.py:157-252`) requests `definePrintout=onlyCustomsDeclarations`, which covers CN22, CN23, and customs invoices in both PDF and ZPL, and derives the document category from `printoutComposition` (`create.py:192-224`).
PostNord test-mode bookings never reach the print or declaration subsystems for by-id fetches (archived change `2026-09-21-postnord-customs-declaration`, task 5.2), but the sandbox gate on 2026-09-25 showed a parcel booking with `customsInvoice` returning composition `{label: 1, customsInvoice: 1}` and a two-page label printout whose second page is the invoice (`docs/notes/postnord/customs-invoice-live-verification.md`).
DHL Freight Sweden builds customs information in `_customs_information` (`.../dhl_freight_sweden/shipment/create.py:251-330`); `CustomsDocumentType.eori` exists in the generated schema, but `AdditionalServicesType` lacks all customs services, which the vendored `transport-instruction-2.10.0.json` `AdditionalServicesDTO` defines.

## Goals / Non-Goals

Goals: a single explicit product-group classification in the PostNord connector; reuse of the existing customs printout fetch; DHL customs services modelled like existing sub-field options; each fail-fast rule traceable to a carrier source.
Non-goals: CN22 versus CN23 selection and value thresholds; consumer advisories; any change to the SDK, server, or other connectors.

## Decisions

### PostNord product groups as a frozenset of letter codes

A `LETTER_SERVICES` frozenset (tracked, tracked letter, export letter, varubrev, expressbrev, registered variants RR/RK/RL/RE/RQ, VV, AF) and the International Parcel code live in `units.py` beside `CUSTOMS_DECLARATION_MAX_LINES`; every other service is a parcel product.
Alternative considered: an allow-list of parcel products. Rejected because new parcel services are more common than new letter services, and defaulting unknown services to the invoice path matches PostNord's rule that parcel products take an invoice.
VV (insured value) and AF (Danish delivery receipt) are classified as letters because both are letter-mail variants.

### Customs invoice built in its own function, CN22 builder unchanged

A `_customs_invoice` builder sits next to `_customs_declaration` and is selected by product group; the CN22 path keeps its current shape plus the registration-number check.
Field derivation:

| PostNord field | Source |
|---|---|
| `type` | `customs.commercial_invoice` true → COMMERCIAL, otherwise PROFORMA |
| `declarationType` | `invoiceExportDeclaration` |
| `seller` | shipper address; `vatNo` from shipper `tax_id` (required); `partyIdentification` from `settings.customer_number`; `eoriNo` from `customs.options.eori_number` |
| `buyer` | recipient address, recipient `tax_id` when present |
| `seller.contacts`, `buyer.contacts` | person name (or company name) and phone number of shipper and recipient; both required |
| `partyIdentification` | `partyId` from `settings.customer_number`, `partyIdType` `160` |
| `voec`, `ioss` | `customs.options.voec_number`, `customs.options.ioss_number` |
| `invoice.invoiceNo` | `customs.invoice`, else `payload.reference`, else field error |
| `invoice.shippingDate` | `customs.invoice_date` (the swagger describes `shippingDate` as the invoice date) |
| `invoice.reasonForExportation` | procedure code `1000` (permanent export) |
| `detailedDescription[]` | commodities: quantity, `hs_code`, description, origin country, value, commodity weight as net and gross weight |
| `invoiceTotal`, `totalGrossWeight` | sums over commodities, using the same rounding as the CN22 total |

The existence check for `payload.reference` reads the payload field, not `shipmentId`, because `shipmentId` falls back to a generated UUID (`create.py:410`).
Postal codes and the procedure code are sent as strings: the generated schema types `BuyerType.postalCode` and `reasonForExportation` as `int`, which would drop leading zeros (Norwegian `0154`), so the schema sample is corrected to strings and regenerated, as the swagger declares.
Alternative considered: letting PostNord reject missing required fields. Rejected for `vatNo`, `invoiceNo`, contact name and phone, and per-line HS code and origin because the swagger marks them required and the user chose to fail fast where a requirement is established.

### Registration-number check on the CN22 path only

A CN22 with none of EORI, VOEC, or IOSS fails fast with `lib.exceptions.FieldError`, as the line-limit guard already does, citing `SACUS-BR-24062502` observed live.
The customs invoice path does not apply the check until the production probe establishes PostNord's behaviour.

### Reuse the Export Letter printout fetch for parcels

The proxy trigger widens from "Export Letter with customs" to "Export Letter or parcel product with customs", keeping `onlyCustomsDeclarations`, the printId-then-item-id lookup, and the fail-open behaviour.
Alternative considered: `onlyCustomsInvoice`. Rejected because PostNord documents it for PDF only, and the category is already derived from `printoutComposition`, so the broader mode loses nothing.

### DHL Freight Sweden customs services as sub-field options

The schema sample `dhl_freight_sweden/schemas/transport_instruction_request.json` gains the five services from `AdditionalServicesDTO` and the types are regenerated.
Options follow the `doorstepDelivery{accessCode}` pattern: boolean options select each of the four services (standard handling, full-service handling, own declaration, joint declaration), and separate string options carry the own-declaration `customsId` and the joint-declaration `sfid`, so that selecting a service without its identifier is expressible and fails fast (a single string option doubling as selector would let a boolean `true` pass through as the identifier `"True"`), and `voecSupplyVAT{vatId}` fed from `customs.options.voec_number` rather than a new option.
Fail-fast checks raise the connector's existing `ShippingSDKDetailedError` subclass with `SHIPPING_SDK_FIELD_ERROR` (`create.py:18-27`): standard handling without EORI, own declaration without customs identifier, joint declaration without SFID.
The document type applies `commercial_invoice` literally, replacing `commercial_invoice or invoice` (`create.py:294-298`), and `transportMovement` compares recipient country with shipper country rather than `settings.account_country_code`; both are equal for Swedish accounts.

### Callers may declare customs maximally

Callers may attach customs data and customs options to every shipment; the connectors own the known criteria for when customs is not required and drop it with a warning rather than failing (user decision 2026-09-25).
Both connectors apply this within the EU VAT area with the same definition, implemented connector-locally in each; a shared SDK helper is a candidate for the shipment-advisors follow-up or an upstream `EUCountry` fix.

## Risks / Trade-offs

- [PostNord rejects `customsInvoice` on parcel bookings] → the first task is a sandbox booking; if validation rejects it, stop and revise the specs toward CN22 at booking plus a post-booking customs invoice declaration.
- [The by-id customs fetch cannot be observed in sandbox, and the invoice is also embedded as page 2 of the label printout, so the standalone document duplicates it, as already accepted for export letters] → one production booking with `customsInvoice` on a parcel product, approved by the user and left unshipped (PostNord's booking API offers no cancellation; the user confirmed on 2026-09-25 that unshipped live-test bookings are not billed), following `verify_prod_probe.py` from the archived customs change; no production key or EORI value is printed or committed.
- [Consumers without shipper `tax_id` start failing on parcel customs bookings] → recorded as breaking in the proposal; the error names the missing field.
- [Unknown future services default to parcel] → the classification is a single frozenset with a test asserting every `ShippingService` member is either in it or deliberately a parcel product.
- [Procedure code 1000 is wrong for returns or temporary exports] → accepted for now; returns and temporary exports are not in scope, and PostNord's codes are recorded in the facts note.

## Migration Plan

Work lands on branches off `feat-postnord-connector` and `feat-dhl-freight-se-connector`, and `develop` is regenerated with the assembly script.
Rollback is reverting the feature-branch merges and regenerating `develop`; no data migration is involved.
Existing tests that book `postnord_parcel` with customs (about 12 in `tests/postnord/test_shipment.py`) move to the customs invoice expectation, CN22 tests move to a letter service, and export-letter fixtures gain an EORI.

## Open Questions

- Whether PostNord applies `SACUS-BR-24062502` to customs invoices; the spec already defines behaviour for both outcomes, and the production probe answers it.
