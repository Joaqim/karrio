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
- **THEN** it names the shipper as seller (with the shipper's federal tax identifier as VAT number, the PostNord customer number as party identification, and the EORI resolved from `customs.options.eori_number` falling back to the shipper's state tax identifier when present) and the recipient as buyer, carries the invoice number from `customs.invoice` (or the shipment reference when absent) and the date from `customs.invoice_date` as PostNord's invoice shipping date, lists the commodities as its detailed description with quantity, value, currency, net and gross weight, HS code, and country of origin, and states the invoice total and total gross weight derived from the commodities

#### Scenario: Seller VAT number is required

- **WHEN** a customs invoice would be sent and the shipper carries no federal tax identifier
- **THEN** the operation fails with a field error naming the shipper VAT number and no request is sent to PostNord

#### Scenario: State tax identifier alone does not satisfy the VAT requirement

- **WHEN** a customs invoice would be sent and the shipper carries a state tax identifier but no federal tax identifier
- **THEN** the operation fails with a field error naming the shipper VAT number and no request is sent to PostNord, because the state tax identifier is reserved for EORI resolution and is not sent as a VAT number

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

#### Scenario: CN22 EORI falls back to the shipper state tax identifier

- **WHEN** a CN22 declaration is sent whose customs payload carries no `options.eori_number` and whose shipper carries a `state_tax_id`
- **THEN** the CN22's EORI registration field carries the shipper's state tax identifier

#### Scenario: Customs invoice EORI falls back to the shipper state tax identifier

- **WHEN** a customs invoice is sent whose customs payload carries no `options.eori_number` and whose shipper carries a `state_tax_id`
- **THEN** the invoice seller's EORI field carries the shipper's state tax identifier

#### Scenario: Customs option EORI takes precedence over the address fallback

- **WHEN** both `customs.options.eori_number` and the shipper's `state_tax_id` are present
- **THEN** the declaration's EORI registration field carries the customs option value

#### Scenario: CN22 without any registration number fails fast

- **WHEN** a CN22 declaration would be sent whose customs payload carries none of `options.eori_number`, `options.voec_number`, or `options.ioss_number` and whose shipper carries no `state_tax_id`
- **THEN** the operation fails with a field error naming the registration numbers and the shipper state tax identifier fallback and no request is sent to PostNord, matching PostNord's rejection `SACUS-BR-24062502` ("Customs CN22/CN23 should have either EORI, VOEC, IOSS")

#### Scenario: CN22 registration guard is satisfied by the shipper state tax identifier

- **WHEN** a CN22 declaration would be sent whose customs payload carries no registration number option and whose shipper carries a `state_tax_id`
- **THEN** no registration field error is raised and the booking request is sent

#### Scenario: Customs invoice without registration numbers is sent as-is

- **WHEN** a customs invoice is sent and the customs payload carries no registration number option and the shipper carries no `state_tax_id`
- **THEN** the customs invoice is sent as-is for PostNord to judge, until a sandbox verification establishes whether PostNord applies the same registration rule to customs invoices

#### Scenario: Bookings without customs data are unchanged

- **WHEN** a shipment is created without customs data
- **THEN** the booking request contains no customs structures and matches the request shape produced before this change

### Requirement: Standalone customs document is opt-in for CN22 letter bookings

Booking a service for which PostNord composes a CN22 (the CN22-structured letter services, including `postnord_export_letter`, PostNord `UX`, and the International Parcel `postnord_postpaket_utrikes`, PostNord `91`) with customs data SHALL attach a standalone customs document to the unified response's shipping documents only when the consumer opts in through a booking option; by default the CN22 is carried only within the label.
When opted in, the standalone customs document SHALL be retrieved separately from the label printout, in the same format as the label, and categorized by its composed kind.
The opt-in SHALL behave identically for PDF and ZPL labels.

#### Scenario: PDF label booking attaches a PDF customs document

- **WHEN** a CN22-bearing letter service is booked with a PDF label and customs data, opting in to standalone customs documents
- **THEN** the response's shipping documents include the CN22 as a separate PDF document of kind `cn22`, in addition to the combined label

#### Scenario: ZPL label booking follows the label format

- **WHEN** a CN22-bearing letter service is booked with a ZPL label and customs data, opting in to standalone customs documents
- **THEN** the customs document is retrieved through PostNord's ZPL printout endpoint where supported, in the same format family as the label, and attached as kind `cn22` in addition to the combined label

#### Scenario: Not opting in attaches no standalone customs document

- **WHEN** a CN22-bearing letter service is booked with customs data in either format without opting in
- **THEN** the response's shipping documents contain no standalone customs document and the CN22 is carried only within the label

#### Scenario: No customs data means no customs document

- **WHEN** an export letter is booked without customs data
- **THEN** no customs document is attached and the response matches the pre-change behavior

#### Scenario: Customs retrieval failure does not fail the booking

- **WHEN** the booking succeeds but retrieving the standalone customs document fails
- **THEN** the booking remains successful and the retrieval failure is reported as messages on the response

### Requirement: Document kinds reflect PostNord printout composition

Each customs document surfaced by these flows SHALL carry a document kind matching PostNord's printout composition kinds (cn22, cn23, customsInvoice, and siblings), taken from what PostNord composed for the booking rather than assumed from the service alone.
A label whose printout PostNord composed with a customs kind SHALL report that composition alongside the label.

#### Scenario: Attached document is categorized by composed kind

- **WHEN** PostNord composes a CN22 for the booked item
- **THEN** the attached shipping document is categorized as kind `cn22`

#### Scenario: Combined label reports its composition

- **WHEN** PostNord composes a label together with a CN22, in either format
- **THEN** the response reports the label's composition as label plus `cn22`, consistent with the SDK's classification of the same label

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
The EU VAT area check SHALL follow the DHL Freight Sweden connector's definition: Greece under its ISO code `GR` and Monaco (`MC`) are treated as EU, Northern Ireland (`GB` with a postal code beginning `BT`) is treated as EU because the connector decides customs handling for goods movements and Northern Ireland is inside the EU VAT area for goods, and Åland (`AX`, or `FI` 22000–22999), the Canary Islands (`IC`, or `ES` 35000–35999 and 38000–38999), Ceuta (`ES` 51000–51999), Melilla (`ES` 52000–52999), Büsingen (`DE` 78266), Heligoland (`DE` 27498), Livigno (`IT` 23041), Campione d'Italia (`IT` 22061), Mount Athos (`GR` 63086), and the French overseas departments (`GP`, `GF`, `MQ`, `RE`, `YT`) are outside it.

#### Scenario: Intra-EU booking omits customs and warns

- **WHEN** a parcel product is booked from Sweden to Poland with customs data
- **THEN** the booking request carries no customs structure, no customs document is retrieved, and the response carries a warning message stating that customs data was not sent for an intra-EU shipment

#### Scenario: Intra-EU booking skips customs fail-fast checks

- **WHEN** a letter service is booked from Sweden to Germany with customs data carrying no registration numbers
- **THEN** no field error is raised and the booking is sent without customs

#### Scenario: Special fiscal territory keeps customs

- **WHEN** a parcel product is booked from Sweden to Åland (`FI`, postal code 22100) with customs data
- **THEN** the booking request carries a customs invoice

#### Scenario: Northern Ireland is treated as EU

- **WHEN** a parcel product is booked from Sweden to the United Kingdom (`GB`, postal code BT1 1AA) with customs data
- **THEN** the booking request carries no customs structure

#### Scenario: Monaco is treated as EU

- **WHEN** a parcel product is booked from Sweden to Monaco (`MC`) with customs data
- **THEN** the booking request carries no customs structure

#### Scenario: Mount Athos keeps customs

- **WHEN** a parcel product is booked from Sweden to Greece (`GR`, postal code 630 86) with customs data
- **THEN** the booking request carries a customs invoice

### Requirement: Booking label carries the composed customs declaration

When a booking carries customs data for a service for which PostNord composes a CN22 (CN22-structured letter services and the International Parcel `91`), the unified response's label SHALL be PostNord's complete printout for the item, containing both the CN22 and the shipping label, in the requested label format.
PDF and ZPL bookings SHALL follow the same flow and yield the same document set, differing only in format.
The connector SHALL NOT split, reorder, or strip the customs declaration from the label.
The response SHALL report the label's composition so a consumer can tell the label carries a CN22 without parsing it.

#### Scenario: ZPL booking returns the combined printout as the label

- **WHEN** an export letter is booked with a ZPL label and customs data, and PostNord composes a CN22
- **THEN** the response's label is the single ZPL format containing the CN22 section and the shipping label section
- **AND** the response reports the label composition as label plus `cn22`

#### Scenario: PDF booking returns the combined printout as the label

- **WHEN** an export letter is booked with a PDF label and customs data, and PostNord composes a CN22
- **THEN** the response's label is one PDF carrying both the CN22 section and the shipping label section, on one page or on separate pages
- **AND** the response reports the label composition as label plus `cn22`
- **AND** no composition warning is emitted when the label and CN22 sections are on separate pages

#### Scenario: International Parcel ZPL booking returns the label and CN22 as two formats

- **WHEN** an International Parcel (`91`) is booked with a ZPL label and customs data, and PostNord composes a CN22
- **THEN** the response's label is the single ZPL document containing the parcel label format followed by the upright CN22 format
- **AND** the response reports the label composition as label plus `cn22` and carries no composition warning

#### Scenario: Formats are interchangeable

- **WHEN** the same customs-bearing letter booking is made once with a PDF label and once with a ZPL label
- **THEN** both responses carry the same composition, the same set of shipping documents by kind, and the same messages

#### Scenario: Booking without customs returns a plain label

- **WHEN** a letter is booked within the EU VAT area or without customs data, in either format
- **THEN** the response's label contains no CN22 and the composition reports no customs kind

### Requirement: Combined label is verified at booking

For a booking expected to carry a CN22 under "Booking label carries the composed customs declaration", the connector SHALL verify the returned label with the SDK's customs composition classification, in either format.
A label that does not classify as a shipping label composed with a CN22 SHALL NOT fail the booking: the label SHALL be returned unchanged and the response SHALL carry a warning message naming the expected and the classified composition.
Verification SHALL NOT fetch, generate, or repair customs documents; customs verification after booking remains the consumer's responsibility.

#### Scenario: A combined label passes verification silently

- **WHEN** a booking expected to carry a CN22 returns a label classified as a shipping label composed with a CN22
- **THEN** the response carries no composition warning

#### Scenario: A ZPL label without the CN22 section yields a warning

- **WHEN** a ZPL booking expected to carry a CN22 returns a label classified as having no customs declaration
- **THEN** the booking succeeds with the label returned unchanged
- **AND** the response carries a warning message stating the label was expected to be combined with a CN22 and was classified as having none

#### Scenario: A lone CN22 returned as the label yields a warning

- **WHEN** a ZPL booking expected to carry a CN22 returns a label classified as a lone CN22
- **THEN** the booking succeeds with the label returned unchanged
- **AND** the response carries a warning message naming the unexpected composition

#### Scenario: A PDF label without the CN22 section yields a warning

- **WHEN** a PDF booking expected to carry a CN22 returns a label whose text carries no CN22 section
- **THEN** the booking succeeds with the label returned unchanged
- **AND** the response carries a warning message naming the expected and the classified composition

#### Scenario: Bookings not expected to carry a CN22 are not verified

- **WHEN** a booking carries no customs data or is within the EU VAT area
- **THEN** no composition verification runs and no composition warning is emitted
