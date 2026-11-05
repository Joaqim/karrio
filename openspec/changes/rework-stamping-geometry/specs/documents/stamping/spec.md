## MODIFIED Requirements

### Requirement: Consumer-supplied placement takes precedence

Placement anchors SHALL be expressed in the placement's unit from the top-left of a one-based page index, where the page is a PDF page or, for ZPL, a `^XA`...`^XZ` format.
A consumer-supplied placement without a keyword SHALL be the primary path and SHALL be used directly without consulting any keyword or registry of defaults.
A consumer-supplied keyword SHALL outrank the registry, and a placement supplied with it SHALL be its geometry, whose `x` and `y` are optional offsets from the located anchor, each defaulting to 0, in the placement's unit.
A registry seed SHALL be consulted for the anchor only when both the placement and the keyword are omitted, and for a keyword's geometry only when the placement is omitted.
Without a keyword, a placement carrying exactly one of `x` and `y`, or carrying neither, SHALL be rejected with an error naming the missing field or the missing keyword, and SHALL NOT fall back to the registry.

#### Scenario: A supplied placement is used as given

- **WHEN** a consumer supplies a placement carrying `x` and `y` together with the image and no keyword
- **THEN** the utility composites at the supplied anchor without performing a keyword or registry lookup

#### Scenario: A supplied keyword outranks the registry

- **WHEN** a consumer supplies a keyword without a placement for a carrier whose seed also carries a keyword
- **THEN** the utility resolves the anchor against the consumer's keyword, not the seed's

#### Scenario: A seed is consulted only on omission

- **WHEN** a consumer omits both the placement and the keyword and a registry seed exists for the document's key
- **THEN** the utility resolves the anchor from that seed and composites at it

#### Scenario: A half-anchored placement is rejected

- **WHEN** a consumer supplies a placement with `x` but no `y` and no keyword, for a document whose key has a registry seed
- **THEN** the utility raises an explicit error naming the missing `StampPlacement.y`
- **AND** no document is returned

#### Scenario: A geometry-only placement without a keyword is rejected

- **WHEN** a consumer supplies a placement without `x` and `y` and no keyword, for a document whose key has a registry seed
- **THEN** the utility raises an explicit error naming the missing keyword
- **AND** the registry seed is not used

#### Scenario: Placement offsets alongside a keyword

- **WHEN** a consumer supplies a keyword matching a ZPL field at `^FO160,240` and a placement with `x` 10 mm and `y` 5 mm at 203 dpi
- **THEN** the stamp field's origin is `^FO240,280`

#### Scenario: A single offset alongside a keyword

- **WHEN** a consumer supplies a keyword and a placement carrying `x` but no `y`
- **THEN** the utility offsets the located anchor by `x` along the label's x axis and by 0 along its y axis

#### Scenario: Pixel offsets alongside a keyword

- **WHEN** a consumer supplies a keyword matching a ZPL field at `^FO160,240` and a `px` placement with `x` 30 and `y` -40 at 203 dpi
- **THEN** the stamp field's origin is `^FO190,200`

### Requirement: Keyword-anchored placement resolution

When the caller supplies a keyword, the utility SHALL locate the keyword in the document and SHALL derive the stamp placement's position from the located text, combined with the keyword anchor's geometry.
For ZPL the keyword SHALL be located in the rendered text of the carrier ZPL field stream, the position SHALL derive from the matched field's origin and the orientation from the field's effective orientation (`^FW` default or the field's font orientation), and the stamp field SHALL be inserted into the `^XA`...`^XZ` format that contains the matched field, searched in the format the caller's page names when one is given, else in every format in order.
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

#### Scenario: A ZPL page restricts the keyword search to one format

- **WHEN** a consumer stamps a ZPL document of two formats that both carry the keyword, supplying the keyword, the anchor geometry and page 2
- **THEN** the stamp field is inserted into the second format at a placement derived from the keyword field in that format
- **AND** the first format is byte-identical to the input

### Requirement: Customs composition classification

The SDK SHALL expose a pure classification of a carrier document's customs composition, returning one of: a lone customs declaration, a shipping label composed with a customs declaration, or no customs declaration.
The SDK SHALL recognize two carrier-neutral declaration kinds, `cn22` and `cn23`.
The result SHALL name the registry document type under which a stamp anchor resolves (the declaration kind, `cn22` or `cn23`, for a lone declaration; the distinct combined type `label_cn22` or `label_cn23` for a label composed with that declaration; none otherwise), so a consumer can pass it to the stamp entry point without inspecting the document itself.
A document carrying the markers of both declaration kinds SHALL fail classification with an explicit error naming both kinds.
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

#### Scenario: A lone CN23 is classified as cn23

- **WHEN** a consumer classifies a document of a carrier declaring `cn23` and label markers, carrying the CN23 section marker and no label section marker
- **THEN** the result is a lone customs declaration with document type `cn23`

#### Scenario: A label composed with a CN23 is classified as label_cn23

- **WHEN** a consumer classifies a two-page PDF of a carrier declaring `cn23` and label markers, whose first page carries the label markers and whose second page carries the CN23 markers
- **THEN** the result is a shipping label composed with a CN23, names the combined document type `label_cn23`, and names page 2 as the declaration page

#### Scenario: Both declaration kinds fail explicitly

- **WHEN** a consumer classifies a document carrying both the CN22 and the CN23 section markers
- **THEN** classification fails with an explicit error naming `cn22` and `cn23`

## ADDED Requirements

### Requirement: Page and label bounds

The utility SHALL reject a placement whose anchor is negative or whose width or height is not positive, with an error naming the offending field, before any backend compositing work.
The ZPL backend SHALL reject a placement whose origin or extent operands resolve outside the ZPL operand range of 0 to 32000 dots.
The utility SHALL reject, with an error naming the crossed edge and the bounds, a placement whose final resolved rectangle, rotated extent included, falls outside the target: the page mediabox for PDF, at every rotation; for ZPL, the label length given by the latest `^LL` at or before the end of the selected format, and the label width given by the latest `^PW` there when present.
A ZPL stream without `^PW` SHALL be checked against its length only, and one without `^LL` against the operand range only.
The check SHALL apply to the final resolved rectangle only and SHALL NOT reject a keyword geometry whose offsets from the located keyword are negative.
The endpoint SHALL answer a bounds rejection with 400.

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

#### Scenario: An unrotated extent beyond the mediabox is rejected

- **WHEN** an unrotated PDF placement extends beyond the right or bottom edge of the mediabox
- **THEN** the utility raises an explicit error naming the crossed edge and the page bounds
- **AND** no document is returned

#### Scenario: A placement past the ZPL label length is rejected

- **WHEN** a ZPL placement's rectangle extends below the selected format's `^LL` length
- **THEN** the utility raises an explicit error naming the label length
- **AND** no raster is built

#### Scenario: A placement past the ZPL print width is rejected

- **WHEN** a ZPL placement's rectangle extends beyond the `^PW` width in effect for the selected format
- **THEN** the utility raises an explicit error naming the print width

#### Scenario: A ZPL stream without a print width checks the length only

- **WHEN** a ZPL placement inside the `^LL` length extends 2000 dots to the right of the label origin in a stream carrying `^LL` and no `^PW`
- **THEN** the utility composites it without a width rejection

#### Scenario: Negative keyword offsets are accepted

- **WHEN** a keyword geometry with a negative offset resolves to a rectangle inside the page or label
- **THEN** the utility composites at the resolved rectangle without a bounds rejection

#### Scenario: The endpoint answers a bounds rejection with 400

- **WHEN** a client posts a placement whose rectangle falls outside the page
- **THEN** the endpoint answers 400 with the error message naming the crossed edge

### Requirement: Placement units

A placement SHALL carry a unit, one of `mm` (the default), `pt` (1/72 inch) or `px`, applying to its `x`, `y`, `width` and `height`.
`px` SHALL mean printer dots at the placement's `dpi` for ZPL, and pixels of the PDF page rendered at the placement's `dpi` for PDF.
The utility SHALL normalize a placement to millimetres before resolution and compositing, so that registry seeds and registry results are expressed in millimetres, and SHALL reject an unknown unit with an error naming the `StampPlacement.unit` field.
A placement without a unit SHALL composite exactly as before units were available.

#### Scenario: Pixel placement on ZPL is in printer dots

- **WHEN** a consumer stamps a ZPL document with a `px` placement of x 40, y 60, width 400 and height 140 at 203 dpi
- **THEN** the stamp field's origin is `^FO40,60`
- **AND** the graphic is 400 dots wide and 140 dots high

#### Scenario: Pixel placement on PDF uses the render density

- **WHEN** a consumer stamps a PDF with a `px` placement of x 150, y 300, width 300 and height 75 at 150 dpi
- **THEN** the stamp composites at x 72 pt and 144 pt below the page top, 144 pt wide and 36 pt high

#### Scenario: Point placement

- **WHEN** a consumer stamps a PDF with a `pt` placement of x 72 and y 72
- **THEN** the stamp's top-left corner sits 1 inch from the page's left and top edges

#### Scenario: Millimetres stay the default

- **WHEN** a consumer supplies a placement without a unit
- **THEN** the result is identical to the same placement with unit `mm`

#### Scenario: An unknown unit is rejected

- **WHEN** a consumer supplies a placement with unit `in`
- **THEN** the utility raises an explicit error naming `StampPlacement.unit` and the accepted units

### Requirement: Aspect-preserving image fit

The utility SHALL scale the image uniformly to the largest size that fits inside its box, placing it against the box's leading edge along the primary axis and centred along the short axis, in the box's pre-rotation frame.
The box SHALL keep its size: the bounds check, the date strip and the ZPL raster extent SHALL use the whole box.
When a date strip is composited, the fit SHALL apply inside the signature's share of the box, and the date strip itself SHALL be drawn at its rendered size within its strip, without a fit.
These rules SHALL hold identically for the PDF and the ZPL backend.

#### Scenario: A wide image is not stretched into a tall box

- **WHEN** a 400 x 100 px image is stamped into a 40 x 20 mm box
- **THEN** the image is drawn 40 x 10 mm, with 5 mm of blank box above and below it

#### Scenario: A tall image is left-aligned

- **WHEN** a 100 x 100 px image is stamped into a 40 x 10 mm box
- **THEN** the image is drawn 10 x 10 mm against the box's left edge, and the rest of the box is blank

#### Scenario: The ZPL raster keeps the box size

- **WHEN** an image whose aspect differs from its box is stamped onto ZPL
- **THEN** the graphic's dot dimensions equal the box's dot dimensions
- **AND** the ink lies within the fitted region

#### Scenario: The fit applies inside the signature share

- **WHEN** a date and an image are stamped into one box
- **THEN** the date occupies its strip as before, and the image is fitted inside the remaining share

### Requirement: ZPL format selection by page

For ZPL, a placement's `page` SHALL select the Nth format, one-based, where the formats are the segments ending at each `^XZ` in order, plus a trailing segment after the last `^XZ` only when it contains `^XA`.
A page of 1, the default, SHALL select the first format.
A page beyond the format count SHALL raise an explicit error naming `StampPlacement.page` and the format count.
The stamp field SHALL be inserted before the selected format's `^XZ`, or appended and closed with `^XZ` for an unterminated format, and every other byte of the stream, header `^XA` commands and `^FX` text between or after formats included, SHALL be unchanged.
The stamp entry point's `page` argument SHALL select the format for ZPL as it selects the page for PDF.

#### Scenario: The default page stamps the first format

- **WHEN** a consumer stamps a two-format ZPL stream with a coordinate placement that names no page
- **THEN** the stamp field is inserted before the first format's `^XZ`
- **AND** the second format is byte-identical to the input

#### Scenario: Page 2 stamps the second format

- **WHEN** a consumer stamps a two-format ZPL stream whose second format opens with a nested header `^XA` and is preceded and followed by `^FX` text, with a placement on page 2
- **THEN** the stamp field is inserted before the second format's `^XZ`
- **AND** the nested `^XA` and both `^FX` texts are byte-identical to the input

#### Scenario: An unterminated last format is selectable

- **WHEN** a consumer stamps page 2 of a ZPL stream whose second format has no final `^XZ`
- **THEN** the stamp field is appended to the second format and closed with `^XZ`

#### Scenario: Trailing comment text is not a format

- **WHEN** a consumer stamps page 2 of a ZPL stream of one format followed by trailing `^FX` text
- **THEN** the utility raises an explicit error naming `StampPlacement.page` and a format count of 1

#### Scenario: The page argument selects a format for a seed

- **WHEN** a consumer stamps a two-format ZPL stream under a seed, passing page 2
- **THEN** the seed-resolved stamp is inserted into the second format

### Requirement: ZPL graphic compression

The ZPL backend SHALL emit an inline graphic as uncompressed uppercase hex by default, byte-identical to the output before compression was available.
When the caller requests `z64` compression, the backend SHALL emit `^GFA,<total>,<total>,<bytes per row>,:Z64:<data>:<crc>`, where `<total>` and `<bytes per row>` are the uncompressed values, `<data>` is the padded standard base64 of the zlib-compressed packed rows, and `<crc>` is the CRC-16/XMODEM of `<data>` as four uppercase hex digits.
With a graphic name, the `~DY` download SHALL carry the same Z64 data, with the uncompressed total and bytes per row.
The stamp entry point and the endpoint SHALL accept the compression choice, and SHALL reject any other value with an error naming the accepted values.

#### Scenario: Compression is off by default

- **WHEN** a consumer stamps a ZPL document without a compression choice
- **THEN** the emitted graphic is identical to the uncompressed hex emitted before compression was available

#### Scenario: Z64 round-trips to the same raster

- **WHEN** a consumer stamps a ZPL document with `z64` compression
- **THEN** decoding the base64 and inflating it yields exactly the packed rows of the uncompressed graphic for the same input
- **AND** the CRC field equals the CRC-16/XMODEM of the base64 text

#### Scenario: Z64 applies to the printer cache download

- **WHEN** a consumer stamps a ZPL document with `z64` compression and a graphic name
- **THEN** the `~DY` download carries `:Z64:` data whose inflated bytes equal the uncompressed packed rows, with the uncompressed total and bytes per row
- **AND** the stamp field recalls the graphic with `^XG` as without compression

#### Scenario: An unknown compression is rejected

- **WHEN** a consumer requests compression `gzip`
- **THEN** the utility raises an explicit error naming the accepted values

### Requirement: Stamping a PDF page leaves other pages unchanged

The PDF backend SHALL composite onto the stamped page without modifying any other page, including when the pages share one resources object.

#### Scenario: Shared resources do not leak the stamp

- **WHEN** a consumer stamps page 2 of a two-page PDF whose pages share one indirect `/Resources` object
- **THEN** page 2's resources carry the stamp image
- **AND** page 1's resources carry the same entries as in the input

### Requirement: Paper variant detected on the stamped page

The paper-variant segment of a PDF registry key SHALL be measured on the page the stamp lands on when that page is known before the key is composed: the entry point's `page` argument when given, else the first page containing a consumer keyword.
Otherwise the segment SHALL be measured on page 1.
A PDF `page` argument outside the document SHALL be rejected naming `StampPlacement.page` before the registry key is composed, so the page error is not masked by a registry miss.

#### Scenario: A letter page after an A4 page resolves the letter seed

- **WHEN** a consumer stamps page 2 of a PDF whose page 1 is A4 and page 2 is letter, under a carrier with seeds for both paper variants
- **THEN** the stamp resolves from the letter seed

#### Scenario: A keyword page decides the paper

- **WHEN** a consumer supplies a keyword that occurs only on the letter page 2 of a PDF whose page 1 is A4, without a page argument
- **THEN** the keyword geometry resolves from the letter seed

#### Scenario: An out-of-range page is reported before the key

- **WHEN** a consumer passes page 3 for a two-page PDF under a carrier whose only seed is for the A4 paper variant
- **THEN** the utility raises an explicit error naming `StampPlacement.page` and the page count, not a registry miss

### Requirement: Stamping endpoint placement fields

The stamping endpoint SHALL accept a placement unit, a keyword and a compression choice, and SHALL pass them to the stamp entry point.
A placement's `x` and `y` SHALL be optional, its `width` and `height` SHALL stay required, and without a keyword the endpoint SHALL answer 400 to a placement carrying only one of `x` and `y`, or neither.
With a keyword, a placement's `x` and `y` SHALL be passed through as offsets from the located keyword.

#### Scenario: Keyword stamping over REST

- **WHEN** a client posts a ZPL document with a keyword and a placement carrying only width, height and rotation
- **THEN** the endpoint answers 201 with the document stamped at the placement derived from the keyword

#### Scenario: Pixel units and compression over REST

- **WHEN** a client posts a ZPL document with a `px` placement and `z64` compression
- **THEN** the endpoint answers 201 with a document whose graphic is Z64-encoded at the pixel extent

#### Scenario: A geometry-only placement without a keyword is rejected

- **WHEN** a client posts a placement without `x` and `y` and no keyword
- **THEN** the endpoint answers 400 naming the missing keyword

#### Scenario: A half-anchored placement without a keyword is rejected

- **WHEN** a client posts a placement with `x` but no `y` and no keyword
- **THEN** the endpoint answers 400 naming the missing `y`

#### Scenario: Keyword offsets over REST

- **WHEN** a client posts a ZPL document with a keyword and a placement carrying `x` and `y`
- **THEN** the endpoint answers 201 with the stamp offset by `x` and `y` from the keyword's field origin

## REMOVED Requirements

### Requirement: Placement bounds

**Reason**: Its scenario "An unrotated placement keeps the permissive extent behavior" is reversed: every PDF placement, and every ZPL placement against `^LL`/`^PW`, is now checked against the page or label.
**Migration**: Superseded by "Page and label bounds", which keeps the anchor, operand-range and rotated-mediabox rules and their scenarios and adds the page and label checks.
