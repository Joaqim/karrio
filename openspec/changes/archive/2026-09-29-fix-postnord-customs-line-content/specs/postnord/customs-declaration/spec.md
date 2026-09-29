## ADDED Requirements

### Requirement: Customs lines require a goods description

Every CN22 or customs invoice line sent to PostNord SHALL carry a goods description taken from the commodity's title, or from its description when the title is empty.
A booking or declaration in which any such commodity has neither SHALL fail with a field error before any request is submitted, naming the commodity by its position as `customs.commodities[<index>].title` and stating that PostNord requires a title or description for each customs line.
No other commodity field SHALL be used as the goods description.

#### Scenario: CN22 commodity without title or description is rejected

- **WHEN** a CN22 booking (for example service `34` from SE to CA) carries a commodity with HS code, quantity and value but no title and no description as its first commodity
- **THEN** the operation fails with a field error for `customs.commodities[0].title` and no request is sent to PostNord

#### Scenario: Customs invoice commodity without title or description is rejected

- **WHEN** a parcel booking outside the EU VAT area carries a customs invoice whose second commodity has no title and no description
- **THEN** the operation fails with a field error for `customs.commodities[1].title` and no request is sent to PostNord

#### Scenario: Description is used when the title is empty

- **WHEN** a customs commodity has no title and the description "Candy"
- **THEN** its customs line carries the goods description "Candy" and the booking is sent

#### Scenario: Customs omitted inside the EU VAT area is not checked

- **WHEN** a booking from SE to PL carries a commodity with no title and no description
- **THEN** customs is omitted as within the EU VAT area and no goods description error is raised
