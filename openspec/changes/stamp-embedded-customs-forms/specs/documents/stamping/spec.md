# Spec Delta

## ADDED Requirements

### Requirement: Customs composition classification

The SDK SHALL expose a pure classification of a carrier document's customs composition, returning one of: a lone customs declaration, a shipping label composed with a customs declaration, or no customs declaration.
The result SHALL name the registry document type under which a stamp anchor resolves (`cn22` for a lone CN22, a distinct combined type for a label composed with a CN22, none otherwise), so a consumer can pass it to the stamp entry point without inspecting the document itself.
For PDF, the result SHALL also name the one-based index of the page carrying the customs declaration section.
Classification SHALL perform no I/O, SHALL NOT modify the document, and SHALL return the same result for the same input.

Classification SHALL be decided by carrier-declared section markers that distinguish the declaration section from the label section, declared per format: ZPL field comments for ZPL, and page text for PDF.
A carrier SHALL be able to declare alternative marker sets for one section kind, and the kind SHALL count as present when any one of its sets fully matches, so that differing carrier templates for the same section are recognized.
Classification SHALL NOT treat the declaration marker alone as proof that the document is a lone declaration, because a composed printout carries the declaration section and the label section together: in PostNord's case in a single ZPL format, and in PDF either on a single page or on separate pages of one document.

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

#### Scenario: A two-format PostNord International Parcel ZPL is classified as combined

- **WHEN** a consumer classifies the captured International Parcel ZPL whose first format carries the parcel label section marker and whose second format carries the upright CN22 section marker
- **THEN** the result is a shipping label composed with a CN22 and names the combined document type

#### Scenario: A two-page PostNord booking PDF is classified as combined

- **WHEN** a consumer classifies the captured PostNord booking PDF whose first page carries the tracked letter label section and whose second page carries the CN22 section
- **THEN** the result is a shipping label composed with a CN22, names the combined document type, and names page 2 as the CN22 page

#### Scenario: Alternative label templates are recognized

- **WHEN** a carrier declares two alternative marker sets for the label section and a document's page text fully matches only the second set
- **THEN** the label section is counted as present

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
For PDF, the combined seed SHALL resolve by the CN22 section's keyword located in the page text of the CN22 page named by classification, so that differing PDF layouts of the combined printout (the declaration rotated beside the label on one page, or upright on its own page) resolve without layout-specific coordinates.
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

#### Scenario: The two-format International Parcel ZPL stamps in its CN22 format

- **WHEN** a consumer stamps the captured International Parcel ZPL under the combined document type, supplying neither placement nor keyword
- **THEN** the stamp field is inserted into the format that contains the CN22 keyword, within that format's signature region and printable length, oriented along the upright signature line
- **AND** the parcel label format is byte-identical to the input

#### Scenario: The two-page PostNord booking PDF stamps on its upright CN22 page

- **WHEN** a consumer stamps the captured two-page PostNord booking PDF under the combined document type with the CN22 page index from classification
- **THEN** the stamp composites on page 2 within the CN22 signature region measured on that page, oriented along the upright signature line
- **AND** page 1 carries no stamp content and the page count is unchanged

#### Scenario: The lone CN22 seeds are retained

- **WHEN** a consumer stamps a lone PostNord ZPL CN22 or a lone PostNord CN22 PDF under document type `cn22`
- **THEN** the placement resolves exactly as it did before this change

#### Scenario: Stamping a classified document end to end

- **WHEN** a consumer classifies a PostNord document and passes the returned document type (and, for PDF, page index) to the stamp entry point
- **THEN** the stamp resolves from the registry without the consumer naming an anchor of its own

## MODIFIED Requirements

### Requirement: Keyword-anchored placement resolution

When the caller supplies a keyword, the utility SHALL locate the keyword in the document and SHALL derive the stamp placement's position from the located text, combined with the keyword anchor's geometry.
For ZPL the keyword SHALL be located in the rendered text of the carrier ZPL field stream, the position SHALL derive from the matched field's origin and the orientation from the field's effective orientation (`^FW` default or the field's font orientation), and the stamp field SHALL be inserted into the `^XA`...`^XZ` format that contains the matched field.
For PDF the keyword SHALL be located in the extracted page text of the target page (the requested page, or otherwise the first page containing the keyword), and the position and orientation SHALL derive from the matched text's origin and direction on that page.
The geometry SHALL come from the caller-supplied geometry or from the registry seed for the document's key, and when neither resolves the utility SHALL raise an explicit error naming what is missing.
A keyword-resolved placement SHALL flow through the same compositing path as a consumer-supplied placement, including rotation and bounds validation.

#### Scenario: A consumer keyword anchors the stamp at the carrier's own field

- **WHEN** a consumer stamps a ZPL document supplying a keyword that matches a field in the carrier stream, together with the anchor geometry
- **THEN** the utility composites the stamp at a placement derived from the matched field's origin
- **AND** the matched field's own text remains present in the output
- **AND** the placement obeys the same bounds validation as a consumer-supplied placement

#### Scenario: A ZPL keyword anchors along the field's orientation in its own format

- **WHEN** a consumer stamps a ZPL document of two formats whose keyword field sits upright in the second format, and another whose keyword field is rotated in a single format, supplying the anchor geometry
- **THEN** each stamp field is inserted into the format containing the keyword, at a placement derived from the field's origin and oriented along the field's orientation

#### Scenario: A keyword that matches no field fails explicitly

- **WHEN** a supplied keyword matches no field text in the carrier ZPL stream, or no text on the target PDF page
- **THEN** the utility raises an explicit error naming the keyword
- **AND** no document is returned

#### Scenario: A keyword with unresolvable geometry fails explicitly

- **WHEN** a consumer supplies a keyword without geometry and no registry seed for the document's key carries the geometry
- **THEN** the utility raises an explicit error naming the missing geometry source
- **AND** no document is returned

#### Scenario: A keyword supplied for a PDF document is rejected

- **WHEN** a consumer supplies a keyword for a PDF document whose target page yields no extractable text
- **THEN** the utility raises an explicit error stating that the keyword cannot be located without page text
- **AND** no document is returned

#### Scenario: A keyword anchors a PDF stamp along the text's direction

- **WHEN** a consumer stamps a PDF supplying a keyword that occurs in the page text, rotated 90 degrees on one fixture and upright on another, together with the anchor geometry
- **THEN** each stamp composites at a placement derived from the keyword's origin on its page, oriented along the keyword's text direction
- **AND** the placement obeys the same bounds validation as a consumer-supplied placement

### Requirement: Registry keyword seeds per carrier

A registry seed SHALL be able to carry a keyword alongside or instead of a coordinate placement, resolved per carrier and document type.
For a ZPL document whose caller supplied neither placement nor keyword, a seed carrying a keyword SHALL resolve the placement by locating the seed's keyword in the carrier stream, without the caller naming the keyword.
For a PDF document whose caller supplied neither placement nor keyword, a seed carrying PDF keyword geometry SHALL resolve the placement by locating the seed's keyword in the page text; a seed carrying only a coordinate placement for PDF SHALL resolve at that placement and SHALL NOT consult its keyword.
A single seed SHALL be able to anchor both formats of the same carrier document.

#### Scenario: A seeded ZPL document resolves implicitly by keyword

- **WHEN** a consumer stamps a seeded carrier's ZPL document supplying neither placement nor keyword
- **THEN** the utility locates the seed's keyword in the carrier stream and composites at the derived placement

#### Scenario: One seed anchors both formats of a document

- **WHEN** a seed carries both a coordinate placement and a ZPL keyword geometry, and no PDF keyword geometry, for a carrier and document type
- **THEN** a PDF document of that carrier and document type resolves at the coordinate placement
- **AND** a ZPL document of the same carrier and document type resolves via the keyword
- **AND** the consumer supplies neither anchor in either case

#### Scenario: A seeded PDF document resolves implicitly by keyword

- **WHEN** a consumer stamps a PDF under a seed carrying PDF keyword geometry, supplying neither placement nor keyword
- **THEN** the utility locates the seed's keyword in the page text of the target page and composites at the derived placement
