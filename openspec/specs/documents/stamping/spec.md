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
A consumer-supplied placement SHALL be the primary path and SHALL be used directly without consulting any registry of defaults.
A registry seed SHALL be resolved only when the consumer omits the placement.

#### Scenario: A supplied placement is used as given

- **WHEN** a consumer supplies a placement together with the image
- **THEN** the utility composites at the supplied anchor without performing a registry lookup

#### Scenario: A seed is consulted only on omission

- **WHEN** a consumer omits the placement and a registry seed exists for the document's key
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

#### Scenario: A supplied date is composited preceding the signature

- **WHEN** a consumer supplies a date value together with the signature image and a placement
- **THEN** both the rendered date text and the signature appear on the page at the anchor
- **AND** the date precedes the signature
- **AND** the date text shares the signature's rotation

#### Scenario: An omitted date composites the signature alone

- **WHEN** a consumer omits the date value
- **THEN** the utility composites only the signature image at the anchor
- **AND** the result is unchanged from the behavior before the date stamp was available

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
