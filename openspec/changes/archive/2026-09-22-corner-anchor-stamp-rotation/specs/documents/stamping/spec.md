## MODIFIED Requirements

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

## ADDED Requirements

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
