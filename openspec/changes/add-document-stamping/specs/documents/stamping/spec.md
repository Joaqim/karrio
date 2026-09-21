## Purpose

Composite a consumer-supplied raster image — a signature or letterhead — onto a carrier duty document that karrio returned, returning the document in the same format and shape it arrived in, so consumers never branch on document format themselves.

## ADDED Requirements

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
