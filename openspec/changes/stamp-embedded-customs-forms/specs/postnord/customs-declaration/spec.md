# Spec Delta

## ADDED Requirements

### Requirement: Booking label carries the composed customs declaration

When a booking carries customs data for a letter service for which PostNord composes a CN22, the unified response's label SHALL be PostNord's complete printout for the item, containing both the CN22 and the shipping label, in the requested label format.
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

## RENAMED Requirements

- FROM: `### Requirement: Implicit standalone customs document for export letter bookings`
- TO: `### Requirement: Standalone customs document is opt-in for CN22 letter bookings`

## MODIFIED Requirements

### Requirement: Standalone customs document is opt-in for CN22 letter bookings

Booking a letter service for which PostNord composes a CN22 (including `postnord_export_letter`, PostNord `UX`, and service 91) with customs data SHALL attach a standalone customs document to the unified response's shipping documents only when the consumer opts in through a booking option; by default the CN22 is carried only within the label.
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
