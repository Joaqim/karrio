## MODIFIED Requirements

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

## ADDED Requirements

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
