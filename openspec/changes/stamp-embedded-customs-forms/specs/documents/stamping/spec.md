# Spec Delta

## ADDED Requirements

### Requirement: Customs composition classification

The SDK SHALL expose a pure classification of a carrier document's customs composition, returning one of: a lone customs declaration, a shipping label composed with a customs declaration, or no customs declaration.
The result SHALL name the registry document type under which a stamp anchor resolves (`cn22` for a lone CN22, a distinct combined type for a label composed with a CN22, none otherwise), so a consumer can pass it to the stamp entry point without inspecting the document itself.
For PDF, the result SHALL also name the one-based index of the page carrying the customs declaration section.
Classification SHALL perform no I/O, SHALL NOT modify the document, and SHALL return the same result for the same input.

Classification SHALL be decided by carrier-declared section markers that distinguish the declaration section from the label section, declared per format: ZPL field comments for ZPL, and page text for PDF.
Classification SHALL NOT treat the declaration marker alone as proof that the document is a lone declaration, because a composed printout carries the declaration section and the label section together, in PostNord's case on a single ZPL format or a single PDF page.

#### Scenario: A lone PostNord ZPL CN22 is classified as cn22

- **WHEN** a consumer classifies a PostNord ZPL document carrying the CN22 section marker and no label section marker
- **THEN** the result is a lone customs declaration with document type `cn22`

#### Scenario: A combined PostNord ZPL label and CN22 is classified as combined

- **WHEN** a consumer classifies the live-captured PostNord ZPL document carrying both the CN22 section marker and the international letter label section marker in a single format
- **THEN** the result is a shipping label composed with a CN22
- **AND** the result names the combined document type, distinct from `cn22`

#### Scenario: A ZPL label without a customs section is not customs-bearing

- **WHEN** a consumer classifies a PostNord ZPL label carrying no CN22 section marker
- **THEN** the result is no customs declaration and names no stamp document type

#### Scenario: A combined PostNord PDF is classified with its CN22 page

- **WHEN** a consumer classifies the live-captured single-page PostNord PDF whose page text carries both the CN22 section and the international letter label section
- **THEN** the result is a shipping label composed with a CN22, names the combined document type, and names page 1 as the CN22 page

#### Scenario: A lone PostNord PDF CN22 is classified as cn22

- **WHEN** a consumer classifies the live-captured PostNord customs-only PDF whose page text carries the CN22 section and no label section
- **THEN** the result is a lone customs declaration with document type `cn22` and names page 1

#### Scenario: A PDF without extractable text is not customs-bearing

- **WHEN** a consumer classifies a PDF whose pages yield no text matching any declared marker
- **THEN** the result is no customs declaration rather than an error

#### Scenario: A carrier without declared sections is not customs-bearing

- **WHEN** a consumer classifies a document for a carrier that declares no customs sections for its format
- **THEN** the result is no customs declaration rather than an error

#### Scenario: Unsupported formats are rejected explicitly

- **WHEN** a consumer classifies a document that is neither ZPL nor PDF
- **THEN** classification fails with an explicit error naming the detected format

### Requirement: Registry seed for the combined label and CN22

The registry SHALL carry, per carrier that composes a label with a CN22, seeds for the combined document type in each format that carrier composes, resolving the stamp onto the CN22 section's signature region.
For ZPL, the combined seed SHALL resolve by the CN22 section's keyword.
For PDF, the combined seed SHALL carry its own coordinate placement measured on the combined printout's CN22 signature region, applied on the CN22 page named by classification.
The seed SHALL leave the label section of the combined document unchanged.
The existing lone `cn22` seeds for ZPL and PDF SHALL remain registered and SHALL resolve exactly as before this change.

#### Scenario: The combined PostNord ZPL document stamps on the CN22 signature region

- **WHEN** a consumer stamps the live-captured PostNord combined ZPL document under the combined document type, supplying neither placement nor keyword
- **THEN** the stamp composites at the placement derived from the CN22 section's signature keyword, identical to the placement derived for a lone CN22 with the same layout
- **AND** the label section of the document, including its barcode, is byte-identical to the input

#### Scenario: The combined PostNord PDF stamps on the CN22 page

- **WHEN** a consumer stamps a combined PostNord PDF under the combined document type with the CN22 page index from classification
- **THEN** the stamp composites on that page within the CN22 signature region measured on the combined printout
- **AND** the label section of the page carries no stamp content and the page count is unchanged

#### Scenario: The lone CN22 seeds are retained

- **WHEN** a consumer stamps a lone PostNord ZPL CN22 or a lone PostNord CN22 PDF under document type `cn22`
- **THEN** the placement resolves exactly as it did before this change

#### Scenario: Stamping a classified document end to end

- **WHEN** a consumer classifies a PostNord document and passes the returned document type (and, for PDF, page index) to the stamp entry point
- **THEN** the stamp resolves from the registry without the consumer naming an anchor of its own
