## Purpose

Defines how the PostNord connector carries customs data at booking time, surfaces standalone customs documents (CN22, CN23, customs invoice) in the unified response's shipping-documents list, and exposes post-booking customs declaration as a consumer-owned capability against PostNord's customs declaration API.

## Requirements

### Requirement: Customs data is declared at booking time

Shipment creation that includes unified customs data SHALL send the customs declaration as part of the PostNord booking request, following PostNord's flow where EDI and customs information travel in the same request, with the declaration derived from the unified customs payload.
The customs structure SHALL be selected by the booked service's product group: parcel products send a customs invoice, while letter services (tracked, registered, export letter, varubrev, expressbrev, and their Danish siblings) and International Parcel (`postnord_postpaket_utrikes`, code 91) keep sending CN22 declaration lines until the CN22 versus CN23 selection rules are specified in a later change.
Parcel products are all PostNord services that are neither letter services nor International Parcel.

#### Scenario: Customs lines are derived from the unified payload

- **WHEN** a letter service or International Parcel is booked with customs data containing commodities
- **THEN** the booking request carries CN22 declaration lines with description, quantity, weight, value, currency, and country of origin derived from those commodities

#### Scenario: Line values and weights are totals over the quantity

- **WHEN** a commodity with quantity 3, a per-unit value of 10 and a per-unit weight of 0.2 kg is declared on a CN22 or a customs invoice
- **THEN** its declaration line carries value 30 and weight 0.6 kg, and the declaration's total value sums the line values, because unified commodity value and weight are per unit while PostNord's lines and totals are per line

#### Scenario: Total gross weight includes packaging

- **WHEN** a CN22 or customs invoice is sent for a shipment whose parcels carry weights
- **THEN** its total gross weight is the sum of the parcel weights, which include packaging, falling back to the sum of commodity line weights only when no parcel weight is given, and a customs invoice's total net weight is the sum of commodity line weights

#### Scenario: Parcel products carry a customs invoice instead of CN22

- **WHEN** a parcel product (for example `postnord_mypack_home`, `postnord_mypack_collect`, `postnord_parcel`, or `postnord_pallet`) is booked with customs data containing commodities
- **THEN** the booking request carries a customs invoice and no CN22 or CN23 declaration

#### Scenario: Customs invoice is built from unified data

- **WHEN** a customs invoice is sent
- **THEN** it names the shipper as seller (with the shipper tax identifier as VAT number, the PostNord customer number as party identification, and the EORI when present) and the recipient as buyer, carries the invoice number from `customs.invoice` (or the shipment reference when absent) and the date from `customs.invoice_date` as PostNord's invoice shipping date, lists the commodities as its detailed description with quantity, value, currency, net and gross weight, HS code, and country of origin, and states the invoice total and total gross weight derived from the commodities

#### Scenario: Seller VAT number is required

- **WHEN** a customs invoice would be sent and the shipper carries no tax identifier
- **THEN** the operation fails with a field error naming the shipper VAT number and no request is sent to PostNord

#### Scenario: Customs invoice required party and line fields fail fast

- **WHEN** a customs invoice would be sent and the shipper or recipient lacks a contact name or phone number, or a commodity lacks an HS code or country of origin
- **THEN** the operation fails with a field error naming each missing field and no request is sent to PostNord, because PostNord's booking schema requires seller and buyer contacts and per-line tariff number and origin

#### Scenario: Customs invoice declares permanent export by default

- **WHEN** a customs invoice is sent
- **THEN** its reason for exportation is PostNord's procedure code 1000 (permanent export, covering sale, gift, and sample)

#### Scenario: Customs invoice uses PostNord's invoice export declaration

- **WHEN** a customs invoice is sent without an explicit declaration type
- **THEN** its declaration type is PostNord's invoice export declaration

#### Scenario: Missing invoice number falls back to the shipment reference

- **WHEN** a parcel product is booked with customs data without `customs.invoice` but with a shipment reference
- **THEN** the customs invoice carries the shipment reference as its invoice number

#### Scenario: Missing invoice number and reference fails fast

- **WHEN** a parcel product is booked with customs data without `customs.invoice` and without a shipment reference
- **THEN** the operation fails with a field error naming the invoice number and no request is sent to PostNord

#### Scenario: Sender registration numbers pass through customs options

- **WHEN** the customs payload carries `options.eori_number`, `options.voec_number`, or `options.ioss_number`
- **THEN** the booking's declaration carries them on the corresponding registration fields of the selected customs structure

#### Scenario: CN22 without any registration number fails fast

- **WHEN** a CN22 declaration would be sent and the customs payload carries none of `options.eori_number`, `options.voec_number`, or `options.ioss_number`
- **THEN** the operation fails with a field error naming the registration numbers and no request is sent to PostNord, matching PostNord's rejection `SACUS-BR-24062502` ("Customs CN22/CN23 should have either EORI, VOEC, IOSS")

#### Scenario: Customs invoice without registration numbers is sent as-is

- **WHEN** a customs invoice is sent and the customs payload carries no registration number
- **THEN** the customs invoice is sent as-is for PostNord to judge, until a sandbox verification establishes whether PostNord applies the same registration rule to customs invoices

#### Scenario: Bookings without customs data are unchanged

- **WHEN** a shipment is created without customs data
- **THEN** the booking request contains no customs structures and matches the request shape produced before this change

### Requirement: Implicit standalone customs document for export letter bookings

Booking the export letter service (`postnord_export_letter`, PostNord `UX`) with customs data SHALL attach a standalone customs document to the unified response's shipping documents, retrieved separately from the label printout so the consumer can handle it independently of the label.

#### Scenario: PDF label booking attaches a PDF customs document

- **WHEN** an export letter is booked with a PDF label and customs data
- **THEN** the response's shipping documents include the customs document in PDF format

#### Scenario: ZPL label booking follows the label format

- **WHEN** an export letter is booked with a ZPL label and customs data
- **THEN** the customs document is retrieved through PostNord's ZPL printout endpoint where supported, in the same format family as the label

#### Scenario: No customs data means no customs document

- **WHEN** an export letter is booked without customs data
- **THEN** no customs document is attached and the response matches the pre-change behavior

#### Scenario: Customs retrieval failure does not fail the booking

- **WHEN** the booking succeeds but retrieving the standalone customs document fails
- **THEN** the booking remains successful and the retrieval failure is reported as messages on the response

### Requirement: Document kinds reflect PostNord printout composition

Each customs document surfaced by these flows SHALL carry a document kind matching PostNord's printout composition kinds (cn22, cn23, customsInvoice, and siblings), taken from what PostNord composed for the booking rather than assumed from the service alone.

#### Scenario: Attached document is categorized by composed kind

- **WHEN** PostNord composes a CN22 for the booked item
- **THEN** the attached shipping document is categorized as kind `cn22`

### Requirement: Post-booking customs declaration is a consumer-owned capability

The connector SHALL expose an SDK-level operation that submits a customs declaration for an existing booking by its PostNord item identifier, through the digital declaration endpoint and its PDF variant, and returns the resulting documents in the unified documents structure.
The capability SHALL NOT reconcile, replace, or verify previously submitted declarations: correctness of post-booking declaration content is the caller's responsibility, and karrio performs no post-booking maintenance of customs documents.

#### Scenario: Digital declaration for an existing booking

- **WHEN** a customs declaration is submitted for an item identifier whose EDI booking was previously sent to PostNord
- **THEN** the declaration is submitted through the digital declaration endpoint and its acceptance is reported

#### Scenario: Declaration with rendered PDF

- **WHEN** a customs declaration is submitted through the PDF variant with rendering parameters
- **THEN** the response includes the rendered document (commercial or proforma invoice, CN22/CN23 as declared)

#### Scenario: Declaration without a prior booking is surfaced as an error

- **WHEN** a declaration is submitted for an item identifier with no prior EDI booking at PostNord
- **THEN** the upstream rejection is surfaced as unified error messages rather than a silent success

#### Scenario: Exactly one declaration type per request

- **WHEN** a declaration request is built
- **THEN** it carries exactly one of the CN22, CN23, or customs invoice declaration types, per PostNord's one-type-per-declaration constraint

### Requirement: Declaration line limits fail fast

Requests whose customs content exceeds PostNord's documented per-document line limit (13 lines per item identifier) SHALL fail with a field error before any request is submitted.

#### Scenario: Over-limit customs lines are rejected before submission

- **WHEN** a booking or declaration carries more than 13 customs lines for a single item identifier
- **THEN** the operation fails with a field error naming the limit and no request is sent to PostNord

### Requirement: `commercial_invoice` selects the customs invoice type

Whenever a customs invoice is sent, `customs.commercial_invoice` SHALL select its type: true declares a commercial invoice for goods sold, and false declares a proforma invoice, which PostNord accepts only for gifts and samples for which the recipient makes no payment.
The connector SHALL apply the flag literally and SHALL NOT infer the type from `content_type` or other fields; detecting a mismatch between the flag and the shipment is left to advisory tooling outside the connector.

#### Scenario: Commercial flag declares a commercial invoice

- **WHEN** a customs invoice is sent with `customs.commercial_invoice` true
- **THEN** the customs invoice type is COMMERCIAL

#### Scenario: Unset commercial flag declares a proforma invoice

- **WHEN** a customs invoice is sent with `customs.commercial_invoice` false or omitted
- **THEN** the customs invoice type is PROFORMA, regardless of `content_type`

### Requirement: Composed customs invoice is surfaced for parcel bookings

Booking a parcel product with customs data SHALL surface the customs document PostNord composes for the booking in the unified response's shipping documents, categorized by PostNord's printout composition, in the same format family as the label.

#### Scenario: Parcel booking returns the composed customs invoice

- **WHEN** a parcel product is booked with customs data and PostNord composes a customs invoice
- **THEN** the response's shipping documents include that document categorized as kind `customsInvoice`

#### Scenario: Customs invoice retrieval failure does not fail the booking

- **WHEN** the booking succeeds but retrieving the composed customs invoice fails
- **THEN** the booking remains successful and the retrieval failure is reported as messages on the response

### Requirement: Customs is omitted within the EU VAT area

The connector SHALL omit every customs structure (CN22, CN23, customs invoice) and the standalone customs document retrieval when both the shipper and the recipient are inside the EU VAT area, SHALL NOT apply the customs fail-fast checks to such shipments, and SHALL report the omission as a warning message on the response when the caller supplied customs data.
Callers may supply customs data maximally; the connector owns the known criteria for when customs is not required.
The EU VAT area check SHALL follow the DHL Freight Sweden connector's definition: Greece under its ISO code `GR` is a member state, and Åland (`AX`, or `FI` 22000–22999), the Canary Islands (`IC`, or `ES` 35000–35999 and 38000–38999), Ceuta (`ES` 51000–51999), Melilla (`ES` 52000–52999), Büsingen (`DE` 78266), Heligoland (`DE` 27498), Livigno (`IT` 23041), Campione d'Italia (`IT` 22061), and the French overseas departments (`GP`, `GF`, `MQ`, `RE`, `YT`) are outside it.

#### Scenario: Intra-EU booking omits customs and warns

- **WHEN** a parcel product is booked from Sweden to Poland with customs data
- **THEN** the booking request carries no customs structure, no customs document is retrieved, and the response carries a warning message stating that customs data was not sent for an intra-EU shipment

#### Scenario: Intra-EU booking skips customs fail-fast checks

- **WHEN** a letter service is booked from Sweden to Germany with customs data carrying no registration numbers
- **THEN** no field error is raised and the booking is sent without customs

#### Scenario: Special fiscal territory keeps customs

- **WHEN** a parcel product is booked from Sweden to Åland (`FI`, postal code 22100) with customs data
- **THEN** the booking request carries a customs invoice
