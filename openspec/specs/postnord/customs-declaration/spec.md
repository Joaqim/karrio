## Purpose

Defines how the PostNord connector carries customs data at booking time, surfaces standalone customs documents (CN22, CN23, customs invoice) in the unified response's shipping-documents list, and exposes post-booking customs declaration as a consumer-owned capability against PostNord's customs declaration API.

## Requirements

### Requirement: Customs data is declared at booking time

Shipment creation that includes unified customs data SHALL send the customs declaration as part of the PostNord booking request, following PostNord's flow where EDI and customs information travel in the same request, with the declaration lines derived from the unified customs payload.

#### Scenario: Customs lines are derived from the unified payload

- **WHEN** a shipment is created with customs data containing commodities
- **THEN** the booking request carries customs declaration lines with description, quantity, weight, value, currency, and country of origin derived from those commodities

#### Scenario: Sender registration numbers pass through customs options

- **WHEN** the customs payload carries `options.eori_number`, `options.voec_number`, or `options.ioss_number`
- **THEN** the booking's declaration carries them on the corresponding CN22 registration fields (`EORIorPersonalIdNumber`, `voec`, `ioss`), and a declaration carrying none of them is sent as-is for PostNord to judge

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
