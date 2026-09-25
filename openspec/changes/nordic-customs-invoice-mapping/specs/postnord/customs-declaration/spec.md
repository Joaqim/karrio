# Spec Delta

## MODIFIED Requirements

### Requirement: Customs data is declared at booking time

Shipment creation that includes unified customs data SHALL send the customs declaration as part of the PostNord booking request, following PostNord's flow where EDI and customs information travel in the same request, with the declaration derived from the unified customs payload.
The customs structure SHALL be selected by the booked service's product group: parcel products send a customs invoice, while letter services (tracked, registered, export letter, varubrev, expressbrev, and their Danish siblings) and International Parcel (`postnord_postpaket_utrikes`, code 91) keep sending CN22 declaration lines until the CN22 versus CN23 selection rules are specified in a later change.
Parcel products are all PostNord services that are neither letter services nor International Parcel.

#### Scenario: Customs lines are derived from the unified payload

- **WHEN** a letter service or International Parcel is booked with customs data containing commodities
- **THEN** the booking request carries CN22 declaration lines with description, quantity, weight, value, currency, and country of origin derived from those commodities

#### Scenario: Line values and weights are totals over the quantity

- **WHEN** a commodity with quantity 3, a per-unit value of 10 and a per-unit weight of 0.2 kg is declared on a CN22 or a customs invoice
- **THEN** its declaration line carries value 30 and weight 0.6 kg, and the declaration totals sum these line totals, because unified commodity value and weight are per unit while PostNord's lines and totals are per line

#### Scenario: Parcel products carry a customs invoice instead of CN22

- **WHEN** a parcel product (for example `postnord_mypack_home`, `postnord_mypack_collect`, `postnord_parcel`, or `postnord_pallet`) is booked with customs data containing commodities
- **THEN** the booking request carries a customs invoice and no CN22 or CN23 declaration

#### Scenario: Customs invoice is built from unified data

- **WHEN** a customs invoice is sent
- **THEN** it names the shipper as seller (with the shipper tax identifier as VAT number, the PostNord customer number as party identification, and the EORI when present) and the recipient as buyer, carries the invoice number from `customs.invoice` (or the shipment reference when absent) and the date from `customs.invoice_date` as PostNord's invoice shipping date, lists the commodities as its detailed description with quantity, value, currency, net and gross weight, HS code, and country of origin, and states the invoice total and total gross weight derived from the commodities

#### Scenario: Seller VAT number is required

- **WHEN** a customs invoice would be sent and the shipper carries no tax identifier
- **THEN** the operation fails with a field error naming the shipper VAT number and no request is sent to PostNord

#### Scenario: Customs invoice required party and line fields fail fast

- **WHEN** a customs invoice would be sent and the shipper or recipient lacks a contact name or phone number, or a commodity lacks an HS code or country of origin
- **THEN** the operation fails with a field error naming each missing field and no request is sent to PostNord, because PostNord's booking schema requires seller and buyer contacts and per-line tariff number and origin

#### Scenario: Customs invoice declares permanent export by default

- **WHEN** a customs invoice is sent
- **THEN** its reason for exportation is PostNord's procedure code 1000 (permanent export, covering sale, gift, and sample)

#### Scenario: Customs invoice uses PostNord's invoice export declaration

- **WHEN** a customs invoice is sent without an explicit declaration type
- **THEN** its declaration type is PostNord's invoice export declaration

#### Scenario: Missing invoice number falls back to the shipment reference

- **WHEN** a parcel product is booked with customs data without `customs.invoice` but with a shipment reference
- **THEN** the customs invoice carries the shipment reference as its invoice number

#### Scenario: Missing invoice number and reference fails fast

- **WHEN** a parcel product is booked with customs data without `customs.invoice` and without a shipment reference
- **THEN** the operation fails with a field error naming the invoice number and no request is sent to PostNord

#### Scenario: Sender registration numbers pass through customs options

- **WHEN** the customs payload carries `options.eori_number`, `options.voec_number`, or `options.ioss_number`
- **THEN** the booking's declaration carries them on the corresponding registration fields of the selected customs structure

#### Scenario: CN22 without any registration number fails fast

- **WHEN** a CN22 declaration would be sent and the customs payload carries none of `options.eori_number`, `options.voec_number`, or `options.ioss_number`
- **THEN** the operation fails with a field error naming the registration numbers and no request is sent to PostNord, matching PostNord's rejection `SACUS-BR-24062502` ("Customs CN22/CN23 should have either EORI, VOEC, IOSS")

#### Scenario: Customs invoice without registration numbers is sent as-is

- **WHEN** a customs invoice is sent and the customs payload carries no registration number
- **THEN** the customs invoice is sent as-is for PostNord to judge, until a sandbox verification establishes whether PostNord applies the same registration rule to customs invoices

#### Scenario: Bookings without customs data are unchanged

- **WHEN** a shipment is created without customs data
- **THEN** the booking request contains no customs structures and matches the request shape produced before this change

## ADDED Requirements

### Requirement: `commercial_invoice` selects the customs invoice type

Whenever a customs invoice is sent, `customs.commercial_invoice` SHALL select its type: true declares a commercial invoice for goods sold, and false declares a proforma invoice, which PostNord accepts only for gifts and samples for which the recipient makes no payment.
The connector SHALL apply the flag literally and SHALL NOT infer the type from `content_type` or other fields; detecting a mismatch between the flag and the shipment is left to advisory tooling outside the connector.

#### Scenario: Commercial flag declares a commercial invoice

- **WHEN** a customs invoice is sent with `customs.commercial_invoice` true
- **THEN** the customs invoice type is COMMERCIAL

#### Scenario: Unset commercial flag declares a proforma invoice

- **WHEN** a customs invoice is sent with `customs.commercial_invoice` false or omitted
- **THEN** the customs invoice type is PROFORMA, regardless of `content_type`

### Requirement: Composed customs invoice is surfaced for parcel bookings

Booking a parcel product with customs data SHALL surface the customs document PostNord composes for the booking in the unified response's shipping documents, categorized by PostNord's printout composition, in the same format family as the label.

#### Scenario: Parcel booking returns the composed customs invoice

- **WHEN** a parcel product is booked with customs data and PostNord composes a customs invoice
- **THEN** the response's shipping documents include that document categorized as kind `customsInvoice`

#### Scenario: Customs invoice retrieval failure does not fail the booking

- **WHEN** the booking succeeds but retrieving the composed customs invoice fails
- **THEN** the booking remains successful and the retrieval failure is reported as messages on the response
