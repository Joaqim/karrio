---
title: PostNord customs data at booking
---

# PostNord customs data at booking

Consumer-facing summary of how the PostNord connector turns unified `customs` data into the booking request, as implemented for the `nordic-customs-invoice-mapping` OpenSpec change on branch `feat-postnord-customs-invoice`.
Sandbox evidence for the customs invoice path is in `customs-invoice-live-verification.md`; CN22 evidence is in `customs-declaration-live-verification.md`.

## Product groups

A shipment carrying `customs` with at least one commodity sends exactly one customs structure, selected by the booked service.
Letter services and International Parcel send a CN22 declaration (`customsDeclarationCN22`).
Every other service is a parcel product and sends a customs invoice (`customsInvoice`), with no CN22 or CN23.

| Group | Services (basicServiceCode) | Customs structure |
|---|---|---|
| Letters | `postnord_tracked` (04), `postnord_tracked_letter` (34), `postnord_export_letter` (UX), `postnord_varubrev_first_class` (86), `postnord_expressbrev` (LX), `postnord_rek` (RR), `postnord_rek_retur` (RK), `postnord_rek_extra` (RL), `postnord_rekommanderet_brev` (RE), `postnord_rekommanderet_quickbrev` (RQ), `postnord_varde` (VV), `postnord_afleveringsattest` (AF) | CN22 |
| International Parcel | `postnord_postpaket_utrikes` (91) | CN22 |
| Parcel products | all other services, for example `postnord_mypack_home`, `postnord_mypack_collect`, `postnord_parcel`, `postnord_pallet`, and any service code the connector does not list | customs invoice |

The letter set is `LETTER_SERVICES` in `karrio/providers/postnord/units.py`, so a service added later is a parcel product unless it is added there.
Selecting CN23 and applying value thresholds such as PostNord Sweden's SEK 2 000 are not implemented.

## Customs invoice field sources

| PostNord field | Unified source |
|---|---|
| `type` | `customs.commercial_invoice`: true sends `COMMERCIAL`, false or omitted sends `PROFORMA`, regardless of `content_type` |
| `declarationType` | always `invoiceExportDeclaration` |
| `seller` | shipper: `company_name` (else `person_name`) as `name`, address lines as `streets`, `city`, `postal_code`, `country_code` |
| `seller.vatNo` | shipper `federal_tax_id` (else `state_tax_id`) |
| `seller.partyIdentification` | connection `customer_number` with `partyIdType` `160` |
| `seller.eoriNo` | `customs.options.eori_number` |
| `buyer` | recipient, mapped like the seller; `vatNo` from the recipient tax id when present |
| `seller.contacts`, `buyer.contacts` | `person_name` (else `company_name`) as `name`, `phone_number` as `phoneNo`, `email` as `emailAddress` |
| `voec`, `ioss` | `customs.options.voec_number`, `customs.options.ioss_number` |
| `invoice.invoiceNo` | `customs.invoice`, else the shipment `reference` |
| `invoice.shippingDate` | `customs.invoice_date`, passed through unchanged (PostNord expects `YYYY-MM-DD`) |
| `invoice.reasonForExportation` | always `1000` (permanent export, covering sale, gift, and sample) |
| `detailedDescription[]` | per commodity: `quantity`, `hs_code` as `hsTariffNumber`, `title` (else `description`) as `content`, `origin_country` as `countryOfOrigin`, `weight` × `quantity` in KGM as both `netWeight` and `grossWeight`, `value_amount` × `quantity` and `value_currency` as `itemValue` |
| `totalGrossWeight` | sum of the line weights in KGM |
| `invoiceTotal` | sum of the line values, rounded to two decimals, in the currency of the first commodity that sets one |

Commodity `value_amount` and `weight` are per unit, so each line carries them multiplied by `quantity` and the totals sum the lines; the CN22 lines and totals are built the same way.
Postal codes are sent as strings, so a Norwegian `0154` keeps its leading zero.

## Fail-fast errors

These checks run before any request is sent, and each failure returns a `SHIPPING_SDK_FIELD_ERROR` message whose details name every missing field at once.

| Condition | Details key | Message |
|---|---|---|
| Customs invoice without shipper tax id | `shipper.federal_tax_id` | shipper VAT number is required for a PostNord customs invoice |
| Customs invoice without `customs.invoice` and without `reference` | `customs.invoice` | invoice number is required for a PostNord customs invoice; send customs.invoice or a shipment reference |
| Shipper or recipient without person and company name | `shipper.person_name` / `recipient.person_name` | contact name is required for a PostNord customs invoice |
| Shipper or recipient without phone number | `shipper.phone_number` / `recipient.phone_number` | contact phone number is required for a PostNord customs invoice |
| Commodity without HS code | `customs.commodities[<i>].hs_code` | HS tariff number is required for a PostNord customs invoice line |
| Commodity without origin country | `customs.commodities[<i>].origin_country` | country of origin is required for a PostNord customs invoice line |
| CN22 without any of EORI, VOEC, or IOSS | `customs.options` | a CN22 declaration requires at least one of eori_number, voec_number, or ioss_number |
| CN22 with more than 13 commodities | `customs.commodities` | customs.commodities exceeds the 13-line customs declaration limit |
| Registration numbers under shipment `options` | `options.<key>` | customs registration number; send it under customs.options |

The CN22 registration rule mirrors PostNord's rejection `SACUS-BR-24062502`.
It is not applied to customs invoices, because the sandbox accepted a parcel customs invoice without registration numbers; whether production applies the rule is open until the production probe.

## Composed customs invoice document

PostNord composes the customs invoice into the booking's label printout (`printoutComposition` `{label: 1, customsInvoice: 1}`), and `meta.printout_composition` lists the composed kinds.
For parcel-product and Export Letter bookings with customs data, the connector also fetches the standalone customs document with `POST /rest/shipment/v3/labels/ids/{pdf,zpl}` and `definePrintout=onlyCustomsDeclarations`, keyed by the booking's `printId` (else the item id), in the label's format.
The document is attached to `docs.extra_documents` with the category PostNord reports, `customsInvoice` for parcel products.
Because the invoice is also page 2 of the label printout, the standalone document duplicates it.
A failed fetch never fails the booking; it is reported as messages next to the shipment details.
Other letter services and International Parcel do not fetch the standalone document.

## Example

This payload is the `CustomsInvoiceShipmentPayload` fixture in `modules/connectors/postnord/tests/postnord/test_shipment.py`, whose expected booking body is asserted by `test_create_shipment_customs_invoice_request`.

```python
{
    "shipper": {
        "address_line1": "Sandhamnsgatan 61",
        "city": "Stockholm",
        "postal_code": "11528",
        "country_code": "SE",
        "state_code": "Stockholm",
        "person_name": "John Sender",
        "company_name": "ACME Sender AB",
        "phone_number": "+46701234567",
        "email": "sender@example.com",
        "federal_tax_id": "SE556123471101",
    },
    "recipient": {
        "address_line1": "Karl Johans gate 22",
        "city": "Oslo",
        "postal_code": "0154",
        "country_code": "NO",
        "person_name": "Kari Receiver",
        "company_name": "Receiver AS",
        "phone_number": "+4791234567",
        "email": "receiver@example.com",
    },
    "parcels": [
        {
            "weight": 1.5,
            "width": 20.0,
            "height": 10.0,
            "length": 30.0,
            "weight_unit": "KG",
            "dimension_unit": "CM",
            "packaging_type": "small_box",
        }
    ],
    "service": "postnord_parcel",
    "options": {"insurance": 500.0},
    "reference": "ORDER-7788",
    "customs": {
        "content_type": "merchandise",
        "commercial_invoice": True,
        "invoice": "INV-2026-001",
        "invoice_date": "2026-09-25",
        "commodities": [
            {
                "title": "Wool socks",
                "quantity": 2,
                "weight": 0.2,
                "weight_unit": "KG",
                "value_amount": 150.0,
                "value_currency": "SEK",
                "hs_code": "6115950000",
                "origin_country": "SE",
            },
            {
                "description": "Knitted cap",
                "quantity": 1,
                "weight": 0.1,
                "weight_unit": "KG",
                "value_amount": 200.0,
                "value_currency": "SEK",
                "hs_code": "6505003000",
                "origin_country": "SE",
            },
        ],
        "options": {"eori_number": "SE556000123401"},
    },
}
```

The resulting `customsInvoice` element, with the fixture's connection `customer_number` `00000000`:

```json
{
  "declarationType": "invoiceExportDeclaration",
  "type": "COMMERCIAL",
  "seller": {
    "partyIdentification": {"partyId": "00000000", "partyIdType": "160"},
    "vatNo": "SE556123471101",
    "name": "ACME Sender AB",
    "streets": ["Sandhamnsgatan 61"],
    "city": "Stockholm",
    "postalCode": "11528",
    "countryCode": "SE",
    "contacts": {"name": "John Sender", "phoneNo": "+46701234567", "emailAddress": "sender@example.com"},
    "eoriNo": "SE556000123401"
  },
  "buyer": {
    "name": "Receiver AS",
    "streets": ["Karl Johans gate 22"],
    "city": "Oslo",
    "postalCode": "0154",
    "countryCode": "NO",
    "contacts": {"name": "Kari Receiver", "phoneNo": "+4791234567", "emailAddress": "receiver@example.com"}
  },
  "invoice": {"invoiceNo": "INV-2026-001", "shippingDate": "2026-09-25", "reasonForExportation": "1000"},
  "detailedDescription": [
    {
      "quantity": 2,
      "hsTariffNumber": "6115950000",
      "content": "Wool socks",
      "countryOfOrigin": "SE",
      "netWeight": {"value": 0.4, "unit": "KGM"},
      "grossWeight": {"value": 0.4, "unit": "KGM"},
      "itemValue": {"amount": 300.0, "currency": "SEK"}
    },
    {
      "quantity": 1,
      "hsTariffNumber": "6505003000",
      "content": "Knitted cap",
      "countryOfOrigin": "SE",
      "netWeight": {"value": 0.1, "unit": "KGM"},
      "grossWeight": {"value": 0.1, "unit": "KGM"},
      "itemValue": {"amount": 200.0, "currency": "SEK"}
    }
  ],
  "totalGrossWeight": {"value": 0.5, "unit": "KGM"},
  "invoiceTotal": {"amount": 500.0, "currency": "SEK"}
}
```
