## ADDED Requirements

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
