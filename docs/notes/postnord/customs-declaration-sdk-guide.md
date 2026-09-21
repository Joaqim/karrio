# PostNord customs declaration — SDK supply guide

How a karrio caller supplies the unified fields that produce a CN22 for a
PostNord export letter, and where each value lands on the wire.
Covers the booking-time EDI declaration and the implicit standalone document;
the consumer-owned post-booking declaration methods are separate (see
`openspec/specs/postnord/customs-declaration/spec.md`).

Mapping code: `modules/connectors/postnord/karrio/providers/postnord/shipment/create.py`
(`_customs_declaration`, around line 280).

## Where each CN22 field comes from

| Unified input | CN22 member | Derivation |
|---|---|---|
| `customs.content_type` | `categoryOfItem.categoryType[0]` | normalized through the CN22 vocabulary (see below); unknown values pass through verbatim |
| `customs.commodities[]` | `detailedDescription[]` | see line mapping below |
| shipment packages | `totalGrossWeight` | total package weight, emitted in KGM |
| `customs.commodities[]` | `totalValue` | sum of `value_amount`; currency taken from the first commodity that sets one |
| `shipper.country_code` | `countryOfOrigin` | sender address country |
| `customs.options["eori_number"]` | `EORIorPersonalIdNumber` | omitted when empty |
| `customs.options["voec_number"]` | `voec` | omitted when empty |
| `customs.options["ioss_number"]` | `ioss` | omitted when empty |

Per commodity line: `title` (or `description`) becomes `content`, plus
`quantity`, `grossWeight` (unit converted, LB accepted), `value`,
`hsTariffNumber` from `hs_code`, `countryCode` from `origin_country`, and a
1-based `rowNo` assigned by position.

## content_type vocabulary

`customs.content_type` is normalized through the connector's CN22 vocabulary
(`units.py`, `CN22CategoryType`; wired into `_customs_declaration` in
`create.py`) before it is sent as the sole `categoryOfItem.categoryType`
entry.
Karrio's conventional values map onto PostNord's documented vocabulary
(`vendor/booking.swagger.json`, categoryOfItem description):

| `customs.content_type` | CN22 `categoryType` |
|---|---|
| `documents` | `DOCUMENT` |
| `gift` | `GIFT` |
| `sample` | `COMMERCIAL SAMPLE` |
| `merchandise` | `SALE OF GOODS` |
| `return_merchandise` | `RETURNED GOODS` |
| `other` | `OTHER` |

Lookup also accepts PostNord-native forms (`sale of goods` → `SALE OF
GOODS`), ignoring case and extra whitespace, so a caller already speaking
PostNord's vocabulary canonicalizes to the uppercase value.
Karrio's underscore keys keep their canonical spelling, so a space-spelled
karrio word such as `return merchandise` is outside both vocabularies and
passes through verbatim.
`SALE OF GOODS` was accepted by PostNord production on 2026-09-21
(re-declaration probe).
A value outside both vocabularies is sent verbatim: the swagger types
`categoryType` as a free string and PostNord validates server-side, so
exotic-but-accepted values keep flowing.
An absent `content_type` emits no `categoryOfItem` element at all.
Shipment `metadata` plays no part in the customs path; it is free-form and
unused by this mapping.

## Registration numbers

The three registration options ride `customs.options` as a plain dict and are
converted through the provider-level `CustomsOption` enum
(`units.py:206-208`: `eori_number`, `voec_number`, `ioss_number`).
The provider enum exists because the core karrio `CustomsOption` enum does not
carry `voec_number`/`ioss_number` members, so typing against the core enum
would silently drop those keys.
Empty-string and `None` option values emit no element at all — the request is
byte-identical to one without options.
PostNord's own completeness rule (SACUS-BR-24062502) rejects a CN22 carrying
none of EORI/VOEC/IOSS, so supply at least one for goods declarations.

## Limits and gating

- A declaration accepts at most 13 commodity lines (13 inclusive is sent in
  full); 14 or more rejects with a field error before any HTTP call
  (`enforce_customs_declaration_lines`).
- The CN22 branch is emitted only when `customs` is present with a non-empty
  `commodities` list; without customs data the booking request shape is
  unchanged.
- On the export-letter service the standalone CN22 document is fetched
  implicitly, keyed by the booking's `printId`, into `docs.extra_documents`.

## Worked example

Adapted from `CustomsShipmentPayload` in
`modules/connectors/postnord/tests/postnord/test_shipment.py`, with a
registration number added; the category is written in PostNord's own
vocabulary, though `merchandise` now maps to it automatically.

```python
import karrio
from karrio.core.models import ShipmentRequest, Customs, Commodity

shipment = ShipmentRequest(
    service="postnord_export_letter",       # export letter service
    reference="CANDY-0001",                 # becomes the searchable IL reference
    shipper=...,                            # address; country_code feeds countryOfOrigin
    recipient=...,
    parcels=[...],                          # package weights feed totalGrossWeight
    customs=Customs(
        content_type="SALE OF GOODS",       # or "merchandise" — maps automatically (see vocabulary above)
        commodities=[
            Commodity(
                title="Candy",
                quantity=1,
                weight=0.38,
                weight_unit="KG",
                value_amount=30.0,
                value_currency="EUR",
                hs_code="1704906500",
                origin_country="SE",
            ),
        ],
        options={"eori_number": "SE..."},   # or voec_number / ioss_number
    ),
    options={"language": "en"},             # shipment options, unrelated to customs
)

shipment, messages = karrio.Shipment.create(shipment).from_(gateway).parse()
```

Over plain REST the same shape applies: the `customs` object and its
`options` dict are fields of the `POST /v1/shipments` payload, and the mapped
result arrives as the `customsDeclarationCN22` branch of the booking EDI.
