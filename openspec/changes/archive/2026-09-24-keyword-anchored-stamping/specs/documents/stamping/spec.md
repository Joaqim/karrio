## ADDED Requirements

### Requirement: Keyword-anchored placement resolution

When the caller supplies a keyword, the utility SHALL locate the field in the carrier ZPL field stream whose rendered text contains the keyword and SHALL derive the stamp placement's position from the located field, combined with the keyword anchor's geometry.
The geometry SHALL come from the caller-supplied geometry or from the registry seed for the document's key, and when neither resolves the utility SHALL raise an explicit error naming what is missing.
A keyword-resolved placement SHALL flow through the same compositing path as a consumer-supplied placement, including rotation and bounds validation.
Keyword anchoring locates field origins in a ZPL stream; a keyword supplied for a PDF document SHALL be rejected with an explicit error rather than ignored.

#### Scenario: A consumer keyword anchors the stamp at the carrier's own field

- **WHEN** a consumer stamps a ZPL document supplying a keyword that matches a field in the carrier stream, together with the anchor geometry
- **THEN** the utility composites the stamp at a placement derived from the matched field's origin
- **AND** the matched field's own text remains present in the output
- **AND** the placement obeys the same bounds validation as a consumer-supplied placement

#### Scenario: A keyword that matches no field fails explicitly

- **WHEN** a supplied keyword matches no field text in the carrier ZPL stream
- **THEN** the utility raises an explicit error naming the keyword
- **AND** no document is returned

#### Scenario: A keyword with unresolvable geometry fails explicitly

- **WHEN** a consumer supplies a keyword without geometry and no registry seed for the document's key carries the geometry
- **THEN** the utility raises an explicit error naming the missing geometry source
- **AND** no document is returned

#### Scenario: A keyword supplied for a PDF document is rejected

- **WHEN** a consumer supplies a keyword together with a PDF document
- **THEN** the utility raises an explicit error identifying keyword anchoring as unsupported for the format
- **AND** no document is returned

### Requirement: Registry keyword seeds per carrier

A registry seed SHALL be able to carry a keyword alongside or instead of a coordinate placement, resolved per carrier and document type.
For a ZPL document whose caller supplied neither placement nor keyword, a seed carrying a keyword SHALL resolve the placement by locating the seed's keyword in the carrier stream, without the caller naming the keyword.
For a PDF document, the seed's coordinate placement SHALL resolve as before and the seed's keyword SHALL NOT be consulted.
A single seed SHALL be able to anchor both formats of the same carrier document: PDF by its coordinate placement, ZPL by its keyword.

#### Scenario: A seeded ZPL document resolves implicitly by keyword

- **WHEN** a consumer stamps a seeded carrier's ZPL document supplying neither placement nor keyword
- **THEN** the utility locates the seed's keyword in the carrier stream and composites at the derived placement

#### Scenario: One seed anchors both formats of a document

- **WHEN** a seed carries both a coordinate placement and a keyword for a carrier and document type
- **THEN** a PDF document of that carrier and document type resolves at the coordinate placement
- **AND** a ZPL document of the same carrier and document type resolves via the keyword
- **AND** the consumer supplies neither anchor in either case

## MODIFIED Requirements

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
