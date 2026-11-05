## Purpose

Composite a consumer-supplied raster image — a signature or letterhead — onto a carrier duty document that karrio returned, returning the document in the same format and shape it arrived in, so consumers never branch on document format themselves.

## Requirements

### Requirement: Format-preserving stamp entry point

The utility SHALL accept a returned carrier document, a base64-encoded PNG image, and a placement, and SHALL return a document of the same format whose content bytes carry the composited image.
The returned document SHALL preserve the input document's shape: only the encoded content is replaced, and the declared format is unchanged.

#### Scenario: Stamping a PDF preserves format and structure

- **WHEN** a consumer stamps a PDF duty document with an image and a valid placement
- **THEN** the returned document declares the same PDF format
- **AND** the returned document has the same page count as the input
- **AND** any fillable form fields present in the input remain fillable

#### Scenario: The carrier content layer is not rasterized

- **WHEN** a PDF document carrying a selectable text layer is stamped
- **THEN** the returned document's carrier text layer remains intact and is not converted to a raster image

### Requirement: Document format detection and dispatch

The utility SHALL detect the document format from its content by magic-byte inspection and route to the backend for that format.
Detection SHALL NOT depend on consumer-declared format hints alone.

#### Scenario: A PDF is detected and routed to the PDF backend

- **WHEN** the document content begins with the PDF magic bytes
- **THEN** the utility composites the image using the PDF backend regardless of any declared format field

### Requirement: Explicit rejection of unstampable formats

The utility SHALL reject, with an explicit error, any document whose format has no active compositing backend.
A raster image document (PNG) SHALL always be rejected rather than passed through unchanged.

#### Scenario: A PNG document is rejected

- **WHEN** a consumer submits a PNG document for stamping
- **THEN** the utility raises an explicit error identifying the unsupported format
- **AND** no document is returned

### Requirement: Consumer-supplied placement takes precedence

Placement anchors SHALL be expressed in millimetres from the top-left of a one-based page index.
A consumer-supplied placement SHALL be the primary path and SHALL be used directly without consulting any keyword or registry of defaults.
A consumer-supplied keyword SHALL be consulted only when the placement is omitted.
A registry seed SHALL be consulted only when both the placement and the keyword are omitted.

#### Scenario: A supplied placement is used as given

- **WHEN** a consumer supplies a placement together with the image
- **THEN** the utility composites at the supplied anchor without performing a keyword or registry lookup

#### Scenario: A supplied keyword outranks the registry

- **WHEN** a consumer supplies a keyword without a placement for a carrier whose seed also carries a keyword
- **THEN** the utility resolves the anchor against the consumer's keyword, not the seed's

#### Scenario: A seed is consulted only on omission

- **WHEN** a consumer omits both the placement and the keyword and a registry seed exists for the document's key
- **THEN** the utility resolves the anchor from that seed and composites at it

### Requirement: Registry miss fails explicitly

When a placement is omitted and no registry seed resolves for the document's key, the utility SHALL raise an explicit error naming the missing key and SHALL NOT fall back to a default or guessed anchor.

#### Scenario: No seed and no placement

- **WHEN** a consumer omits the placement and no registry seed matches the document's key
- **THEN** the utility raises an explicit error naming the missing key
- **AND** no document is returned

### Requirement: Layered compositing semantics

The utility SHALL support an overlay layer that draws the image over document content, for signatures.
The utility SHALL support an underlay layer that draws document content over the image, for letterheads, on the PDF backend.

#### Scenario: Overlay draws above content

- **WHEN** an image is composited with the overlay layer
- **THEN** the image appears above the carrier document content at the anchor

#### Scenario: Underlay draws beneath content

- **WHEN** a letterhead image is composited with the underlay layer onto a PDF
- **THEN** the carrier document content remains legible above the letterhead

### Requirement: No storage, verification, or validity assertion

The utility SHALL composite pixels only.
It SHALL NOT store the returned document, and SHALL NOT verify or assert the legal validity, authority, or signature semantics of the stamped content.

#### Scenario: Stamping retains nothing

- **WHEN** a document is stamped
- **THEN** the utility returns the stamped document to the caller and retains no copy of it
- **AND** the utility makes no assertion about whether the stamped image constitutes a valid signature

### Requirement: Placement rotation

The utility SHALL composite the image rotated clockwise by a caller-specified angle in degrees, and the placement's anchor SHALL locate the rotated extent's top-left corner: the rotated image's bounding box SHALL be placed so its top-left corner sits exactly at the placement's `(x, y)`.
The anchor SHALL carry the same meaning in the PDF and the ZPL backend, so a placement reads identically regardless of the document's format.
The rotation SHALL default to no rotation, and a zero rotation SHALL composite the image upright, byte-identical to the behavior before rotation was available.

#### Scenario: A rotation aligns the image with a sideways form

- **WHEN** a consumer supplies a placement with a 90-degree rotation onto a document whose target field runs sideways
- **THEN** the composited image is rotated 90 degrees clockwise with its rotated extent's top-left corner at the anchor, so it aligns with the sideways field

#### Scenario: A rotated strip starts at the page corner

- **WHEN** a consumer supplies a wide placement anchored at the page origin with a 90-degree rotation
- **THEN** the rotated extent's top-left corner sits exactly at the origin
- **AND** the emitted anchor operands are non-negative

#### Scenario: The default rotation composites upright

- **WHEN** a consumer supplies a placement without a rotation angle
- **THEN** the utility composites the image upright at the anchor
- **AND** the result is byte-identical to the behavior before rotation was available

### Requirement: Consumer-supplied date stamp

When the caller supplies a date value, the utility SHALL render it as text and composite it preceding the signature image within the placement, at the same rotation as the signature.
The caller SHALL supply the date as a pre-formatted string; the utility SHALL NOT format the date or impose a locale.
The rendered date SHALL NOT be stretched to fill its portion of the placement: its glyph height SHALL be proportional to the placement's short axis, its natural glyph aspect SHALL be preserved, and it SHALL be centered within its portion.
When the rendered text would overflow its portion along the placement's primary axis, the utility SHALL reduce the glyph height to fit rather than distort or overflow.
These rendering rules SHALL hold identically for the PDF and the ZPL backend.

#### Scenario: A supplied date is composited preceding the signature

- **WHEN** a consumer supplies a date value together with the signature image and a placement
- **THEN** both the rendered date text and the signature appear on the page at the anchor
- **AND** the date precedes the signature
- **AND** the date text shares the signature's rotation

#### Scenario: An omitted date composites the signature alone

- **WHEN** a consumer omits the date value
- **THEN** the utility composites only the signature image at the anchor
- **AND** the result is unchanged from the behavior before the date stamp was available

#### Scenario: The date renders at a proportional glyph height

- **WHEN** a date is rendered into its portion of a placement
- **THEN** the date's ink band height is at most the proportional bound of the portion's short axis, not the full short axis
- **AND** the ink band touches neither edge of the portion's short axis

#### Scenario: A long date shrinks to fit its portion

- **WHEN** the rendered date text at the proportional height is wider than its portion along the placement's primary axis
- **THEN** the utility reduces the glyph height until the text fits within the portion
- **AND** the text's natural aspect is preserved

#### Scenario: The PDF date overlay scales uniformly

- **WHEN** a date is composited into a PDF placement
- **THEN** the overlay image's horizontal and vertical scale factors into the placement rectangle are equal, so the rendered text carries no aspect distortion

### Requirement: Placement bounds

The utility SHALL reject a placement whose anchor is negative or whose width or height is not positive, with an error naming the offending field, before any backend compositing work.
The ZPL backend SHALL reject a placement whose origin or extent operands resolve outside the ZPL operand range of 0 to 32000 dots.
The PDF backend SHALL reject a rotated placement whose rotated extent crosses the page mediabox, with an error naming the crossed edge.
The PDF backend SHALL NOT reject an unrotated placement for extending beyond the mediabox.

#### Scenario: A negative anchor is rejected naming the field

- **WHEN** a consumer supplies a placement with a negative x or y in either backend
- **THEN** the utility raises an explicit error naming the offending `StampPlacement` field
- **AND** no document is returned

#### Scenario: A ZPL operand beyond the valid range is rejected

- **WHEN** a ZPL placement's origin or extent resolves to more than 32000 dots
- **THEN** the utility raises an explicit error naming the operand range
- **AND** no out-of-spec operands are emitted

#### Scenario: A rotated extent beyond the mediabox is rejected

- **WHEN** a rotated PDF placement's bounding box crosses the page mediabox
- **THEN** the utility raises an explicit error naming the crossed edge and the page bounds
- **AND** no document is returned

#### Scenario: An unrotated placement keeps the permissive extent behavior

- **WHEN** an unrotated PDF placement extends beyond the mediabox
- **THEN** the utility composites it as before, without a containment rejection

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

### Requirement: Seeded placements land on the measured target region

A registry seed's coordinate placement SHALL composite the stamp within the carrier form's measured target region for that carrier, document type, and format, at the orientation the form's own content reads.
A seed's measured values SHALL be superseded only by a re-measurement that bumps the seed's revision.
Oracles asserting a seeded placement SHALL derive their expected values from the measurement, not from the seed under test.

#### Scenario: The PostNord CN22 PDF seed composites on the signature strip

- **WHEN** a consumer stamps the PostNord CN22 PDF supplying neither placement nor keyword
- **THEN** the stamp composites within the vertical signature strip at page x 53.34-60.96 mm, y 91.44-140.55 mm of the A4 page
- **AND** the stamp's glyphs read along the form's sideways signature line, matching the ZPL form's rotated field stream
- **AND** the seed carries revision 3, superseding the axis-swapped revision 2

#### Scenario: A seeded extent leaving the form's target region is a defect

- **WHEN** a shipped seed's rendered extent falls outside the carrier form's measured target region while remaining inside the page
- **THEN** the seed is wrong regardless of page-level bounds validation, and is corrected by a re-measurement with a bumped revision rather than by adjusting the oracles

### Requirement: Threshold binarization of the ZPL stamp raster

The ZPL backend SHALL binarize the composited stamp raster with a fixed ink threshold rather than error-diffusion dithering, so anti-aliased text edges render as solid ink and the raster carries no scattered dither speckle.
Signature resampling SHALL preserve stroke connectivity, and faint signature strokes SHALL survive binarization as connected ink.

#### Scenario: The date region carries no isolated speckle pixels

- **WHEN** a date is composited into a ZPL stamp raster
- **THEN** the date's portion of the raster contains no isolated single-pixel ink dots isolated from the glyph strokes

#### Scenario: A faint signature stroke survives as connected ink

- **WHEN** a signature image whose strokes flatten to a light gray is composited into a ZPL stamp raster
- **THEN** the stroke's ink survives binarization as a connected run spanning the stroke's length

#### Scenario: Solid black input stays fully black

- **WHEN** an opaque solid-black signature image is composited into a ZPL stamp raster
- **THEN** at least one row of the raster is black across its entire width

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

#### Scenario: A two-page PostNord International Parcel PDF is classified as combined

- **WHEN** a consumer classifies the captured International Parcel PDF whose first page carries the parcel label and whose second page carries the CN22 section
- **THEN** the result is a shipping label composed with a CN22 and names page 2 as the CN22 page

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
