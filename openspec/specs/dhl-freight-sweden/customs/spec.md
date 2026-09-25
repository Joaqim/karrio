## Purpose

Defines how the DHL Freight Sweden connector carries customs documents, registration numbers, and customs services in the transport instruction, including the invoice-type meaning of `commercial_invoice` and the rule that priced customs services are only ever selected explicitly.

## Requirements

### Requirement: Customs documents are declared in the transport instruction

Shipment creation that includes unified customs data SHALL send a customs document in the transport instruction's customs information, carrying the invoice number from `customs.invoice`, the invoice date from `customs.invoice_date`, the invoice currency and amount from the customs duty, a transport movement of export when the recipient country differs from the shipper country, and the shipper EORI from `customs.options.eori_number` when present.

#### Scenario: Customs document fields are derived from the unified payload

- **WHEN** a shipment from Sweden to Norway is created with customs data carrying an invoice number, invoice date, declared value, currency, and EORI number
- **THEN** the transport instruction carries one customs document with those values, transport movement Export, and the EORI on the document

#### Scenario: Commodity lines carry quantity totals

- **WHEN** a commodity with quantity 2, a per-unit value of 30 EUR and a per-unit weight of 0.38 kg is declared
- **THEN** its customs commodity line carries customs value 60, net weight 0.76 kg, and 2 units, so that line values sum to the invoice amount

#### Scenario: Invoice number falls back to the shipment reference

- **WHEN** customs data carries no invoice number and the shipment carries a reference
- **THEN** the customs document identifier is the shipment reference

#### Scenario: Invoice date falls back to the shipping date

- **WHEN** customs data carries no invoice date
- **THEN** the customs document invoice date is the shipment's shipping date, or the booking date when no shipping date is given, so DHL never records a default date

#### Scenario: Missing invoice number and reference fails fast

- **WHEN** a customs document would be sent without an invoice number and without a shipment reference
- **THEN** the operation fails with a field error naming the invoice number and no request is sent to DHL

#### Scenario: Commodity net weight is sent in kilograms

- **WHEN** a customs commodity carries its weight in pounds or ounces
- **THEN** its customs commodity line carries the net weight converted to kilograms

#### Scenario: Missing EORI is sent as-is when no rule requires it

- **WHEN** customs data carries no EORI number and no selected customs service requires one
- **THEN** the customs document omits the EORI and DHL judges the declaration

#### Scenario: Bookings without customs data are unchanged

- **WHEN** a shipment is created without customs data
- **THEN** the transport instruction contains no customs information and matches the request shape produced before this change

### Requirement: `commercial_invoice` selects the customs document type

`customs.commercial_invoice` SHALL select the customs document type: true declares a commercial invoice and false a proforma invoice.
The connector SHALL apply the flag literally and SHALL NOT infer the type from `content_type` or other fields.

#### Scenario: Commercial flag declares a commercial invoice

- **WHEN** customs data carries `commercial_invoice` true
- **THEN** the customs document type is CommercialInvoice

#### Scenario: Unset commercial flag declares a proforma invoice

- **WHEN** customs data carries `commercial_invoice` false or omits it
- **THEN** the customs document type is ProformaInvoice, regardless of `content_type`

### Requirement: VOEC number is carried as the VOEC service

A `customs.options.voec_number` SHALL be sent as DHL's VOEC supply VAT service with that number as its VAT identifier.

#### Scenario: VOEC number becomes the VOEC service

- **WHEN** customs data carries a VOEC number
- **THEN** the transport instruction selects the VOEC supply VAT service with that number

### Requirement: Priced customs services are explicit opt-ins

The connector SHALL expose DHL's customs services (standard handling, full-service handling, customer's own declaration, joint declaration) as shipment options and SHALL select a customs service only when the caller sets its option, because each service carries a DHL fee.
Services that require an identifier SHALL fail fast when it is missing: standard customs handling requires the shipper EORI (`customs.options.eori_number`), customer's own declaration requires a customs identifier (MRN), and joint declaration requires a joint-declaration identifier.

#### Scenario: No customs service is selected implicitly

- **WHEN** a shipment to Norway is created with customs data and no customs service option
- **THEN** the transport instruction selects no customs service

#### Scenario: Selected customs service is sent

- **WHEN** the caller sets the standard customs handling option and customs data carries an EORI number
- **THEN** the transport instruction selects DHL's standard customs handling service

#### Scenario: Standard handling without EORI fails fast

- **WHEN** the caller sets the standard customs handling option and customs data carries no EORI number
- **THEN** the operation fails with a field error naming the EORI number and no request is sent to DHL

#### Scenario: Own declaration carries the customs identifier

- **WHEN** the caller selects customer's own declaration with a customs identifier
- **THEN** the transport instruction selects that service carrying the identifier

#### Scenario: Own declaration without identifier fails fast

- **WHEN** the caller selects customer's own declaration without a customs identifier
- **THEN** the operation fails with a field error naming the customs identifier and no request is sent to DHL

#### Scenario: Joint declaration without identifier fails fast

- **WHEN** the caller selects joint declaration without a joint-declaration identifier
- **THEN** the operation fails with a field error naming the identifier and no request is sent to DHL

### Requirement: Customs information is omitted within the EU VAT area

The connector SHALL omit customs information, customs services, and the VOEC service when both the shipper and the recipient are inside the EU VAT area, SHALL NOT apply the customs fail-fast checks to such shipments, and SHALL report the omission, naming any dropped customs services, as a warning message on the response when the caller supplied customs data or customs options.
Callers may supply customs data maximally; the connector owns the known criteria for when customs is not required.
The EU VAT area check SHALL treat Greece under its ISO code `GR` as a member state, and SHALL treat the following special fiscal territories as outside it even when their country code is an EU member state: Åland (`AX`, or `FI` with postal codes 22000–22999), the Canary Islands (`IC`, or `ES` with postal codes 35000–35999 and 38000–38999), Ceuta (`ES` 51000–51999), Melilla (`ES` 52000–52999), Büsingen (`DE` 78266), Heligoland (`DE` 27498), Livigno (`IT` 23041), Campione d'Italia (`IT` 22061), and the French overseas departments (`GP`, `GF`, `MQ`, `RE`, `YT`).

#### Scenario: Intra-EU shipment omits customs and warns

- **WHEN** a shipment from Sweden to Poland is created with customs data
- **THEN** the transport instruction contains no customs information and the response carries a warning message stating that customs data was not sent for an intra-EU shipment

#### Scenario: Greece is treated as EU

- **WHEN** a shipment from Sweden to Greece (`GR`) is created with customs data
- **THEN** the transport instruction contains no customs information

#### Scenario: Special fiscal territory keeps customs

- **WHEN** a shipment from Sweden to Åland (`FI`, postal code 22100) is created with customs data
- **THEN** the transport instruction carries customs information with transport movement Export

#### Scenario: Non-EU destination keeps customs

- **WHEN** a shipment from Sweden to Norway is created with customs data
- **THEN** the transport instruction carries customs information with transport movement Export

#### Scenario: Customs services are dropped within the EU without failing

- **WHEN** a shipment from Sweden to Poland is created with customs data, the standard customs handling option set, and no EORI number
- **THEN** the booking is sent without customs information or customs services, no field error is raised, and the warning message names the dropped standard customs handling service
