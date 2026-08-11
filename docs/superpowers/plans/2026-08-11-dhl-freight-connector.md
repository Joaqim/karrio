# DHL Freight Sweden connector implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Karrio `dhl_freight_sweden` connector for the DHL Freight Sweden API Farm that books transport instructions, returns a printed label in one `shipment/create` call, and surfaces a tracking id + tracking URL through the shipment `meta`.

**Architecture:** `shipment/create` chains two API Farm services behind one proxy method — book (`POST /transportinstruction/sendtransportinstruction`, returns `transportInstruction.id`) then print (Print API, op TBD, returns label bytes). Every request carries a single `client-key` header; there is no token exchange, no cache. Tracking is URL-only: `shipment/create` stamps `meta.tracking_url` built from a DHL Freight Sweden portal template; no tracking API call is possible against the API Farm. No rating, no cancel/returns in Phase 0. Hosts default to the API Farm with a per-connection `server_url` override.

**Tech Stack:** Python, `karrio.lib`, `attr`/`jstruct`, `unittest` (never pytest), Karrio SDK plugin entrypoints, `./bin/cli sdk add-extension` scaffolding + `./bin/run-generate-on` schema generation.

**Reference PRD:** `PRDs/PRD_DHL_FREIGHT_INTEGRATION.md`

**Precedent connectors to mirror (study before editing):**
- Static auth header on every request (no token exchange): `modules/connectors/seko/karrio/mappers/seko/proxy.py`
- `server_url` override + `ConnectionConfig`: `modules/connectors/postat/karrio/providers/postat/{units.py,utils.py}` + `karrio/plugins/postat/__init__.py`
- Single-body request Serializable + empty-label: `modules/connectors/gls/karrio/providers/gls/shipment/create.py`
- JSON create request/response, error, metadata, units, tests: `modules/connectors/mydhl/...`
- tracking_url property: `modules/connectors/dhl_express/karrio/providers/dhl_express/utils.py`

---

## File structure

```
modules/connectors/dhl_freight_sweden/
├── pyproject.toml                                   # scaffolded; entrypoint karrio.plugins.dhl_freight_sweden
├── generate                                         # scaffolded; edit CLI flags (camelCase API)
├── vendor/se-api-farm/                              # vendored SE API Farm OpenAPI 2.10.0 specs (git-tracked)
│   ├── transport-instruction-2.10.0.json
│   ├── print-api-2.10.0.json
│   ├── product-api-2.10.0.json
│   ├── pricequote-api-2.10.0.json
│   └── ... (servicepoint, home-delivery-locator, pallet, ...)
├── schemas/                                         # generation input (JSON samples)
│   ├── booking_request.json
│   ├── booking_response.json
│   ├── print_request.json
│   ├── print_response.json
│   └── error_response.json
├── karrio/
│   ├── plugins/dhl_freight_sweden/__init__.py              # METADATA (shipping only)
│   ├── mappers/dhl_freight_sweden/{__init__.py,mapper.py,proxy.py,settings.py}
│   ├── providers/dhl_freight_sweden/
│   │   ├── __init__.py                              # public exports
│   │   ├── utils.py                                 # Settings: client_key, server_url override, tracking_url, label_type, connection_config
│   │   ├── units.py                                 # ShippingService (full product set), ShippingOption, LabelLayout, ConnectionConfig
│   │   ├── error.py                                 # validationErrors[] + errorMessage
│   │   ├── tracking.py                              # deferred documented stub (not wired)
│   │   └── shipment/{__init__.py,create.py,cancel.py}   # create implemented; cancel a deferred stub
│   └── schemas/dhl_freight_sweden/                         # generated types (DO NOT EDIT)
└── tests/dhl_freight_sweden/
    ├── fixture.py
    └── test_shipment.py
```

Responsibility boundaries: `utils.py` owns settings + URL/credential resolution; `proxy.py` owns all HTTP + the book→print chain (with the `client-key` header); `shipment/create.py` owns unified↔carrier mapping and stamps `meta.tracking_url`; `error.py` owns the error shape; `units.py` owns all enums. `tracking.py` and `shipment/cancel.py` remain deferred documented stubs.

---

## Task 1: Scaffold the connector (done)

The connector is scaffolded and the SE API Farm specs are vendored under `vendor/se-api-farm/` (see git history: `scaffold connector`, `vendor SE API Farm 2.10.0 OpenAPI specs`).

- [x] **Step 1: Confirm branch + env**

```bash
git branch --show-current    # expect: dhl-sweden-connection
source ./bin/activate-env
```

- [x] **Step 2: Scaffold + vendor specs.** Already committed.

- [ ] **Step 3: Prune capabilities not in Phase 0**

Rating is deferred; delete any scaffolded `rate.py` + `test_rate.py` so no `rating` capability is exposed (capabilities are derived from proxy methods). Keep `tracking.py` and `shipment/cancel.py` as deferred documented stubs — leave a module docstring noting they are not wired in Phase 0.

```bash
rm -f modules/connectors/dhl_freight_sweden/karrio/providers/dhl_freight_sweden/rate.py
rm -f modules/connectors/dhl_freight_sweden/tests/dhl_freight_sweden/test_rate.py
```
Then remove any `rate` import from `karrio/providers/dhl_freight_sweden/__init__.py`. The package will not fully import until schemas are generated (Task 3) and providers are rewritten (Tasks 4-9) — the normal Karrio scaffold state.

---

## Task 2: Vendor the raw specs (done)

The DHL Freight Sweden API Farm OpenAPI 2.10.0 specs are vendored, git-tracked, at `modules/connectors/dhl_freight_sweden/vendor/se-api-farm/`.

- [x] Committed as `vendor SE API Farm 2.10.0 OpenAPI specs`.

---

## Task 3: Schema samples + generation

DHL Freight is a **camelCase** JSON API (`productCode`, `payerCode`, `shipmentIds`, `pageOptions`), so generation uses `--no-nice-property-names`.

**Files:**
- Create: `modules/connectors/dhl_freight_sweden/schemas/*.json`
- Modify: `modules/connectors/dhl_freight_sweden/generate`

- [ ] **Step 1: Write the five JSON samples** (distilled from `vendor/se-api-farm/` schemas — real field shapes, minimal but complete)

`schemas/booking_request.json`:
```json
{
  "id": "",
  "productCode": "102",
  "pickupDate": "2026-08-12",
  "totalNumberOfPieces": 1,
  "totalWeight": 380,
  "references": [{ "qualifier": "CNR", "value": "REF123" }],
  "payerCode": { "code": "DAP", "location": "" },
  "parties": [
    { "type": "Consignor", "id": "ACCT1", "name": "Sender AB", "contactName": "A", "phone": "0700000000", "email": "a@x.se",
      "address": { "street": "Main 1", "cityName": "Stockholm", "postalCode": "11122", "countryCode": "SE" } },
    { "type": "Consignee", "name": "Receiver AB", "contactName": "B", "phone": "0700000001", "email": "b@x.se",
      "address": { "street": "Road 2", "cityName": "Gothenburg", "postalCode": "41111", "countryCode": "SE" } }
  ],
  "pieces": [
    { "id": [], "goodsType": "Machinery Parts", "packageType": "PAL", "numberOfPieces": 1, "weight": 380, "volume": 0.864, "width": 80, "height": 90, "length": 120, "stackable": true }
  ]
}
```

`schemas/booking_response.json`:
```json
{ "status": "OK", "transportInstruction": { "id": "1234567890123", "productCode": "102", "parties": [], "pieces": [] } }
```

`schemas/print_request.json`:
```json
{
  "shipmentIds": ["1234567890123"],
  "options": {
    "label": true, "waybill": false, "returnLabel": false,
    "pageOptions": { "pageType": "Label", "marginLeft": 0, "marginTop": 0, "padding": 0 }
  }
}
```

`schemas/print_response.json`:
```json
{ "reports": [ { "name": "label", "content": "base64bytes", "contentType": "application/pdf", "type": "PDF", "valid": true } ] }
```

`schemas/error_response.json`:
```json
{
  "status": "ERROR",
  "validationErrors": [ { "field": "productCode", "errorCode": 100, "message": "invalid", "incompatibleFields": [] } ],
  "errorMessage": "Bad Request"
}
```
(The error sample matches `TransportInstructionErrorResponse`: `status`, `validationErrors[]` of `IValidationError`, and `errorMessage`. There is no OAuth `{status,title,detail}` shape on the API Farm.)

- [ ] **Step 2: Configure `generate` for camelCase**

Edit `modules/connectors/dhl_freight_sweden/generate` so each schema is generated with `--no-nice-property-names`. Mirror the format of an existing camelCase connector's `generate` (e.g. `modules/connectors/mydhl/generate`). One line per JSON sample, e.g.:
```bash
quicktype ... schemas/booking_request.json ... karrio/schemas/dhl_freight_sweden/booking_request.py --no-nice-property-names
quicktype ... schemas/booking_response.json ... karrio/schemas/dhl_freight_sweden/booking_response.py --no-nice-property-names
quicktype ... schemas/print_request.json ... karrio/schemas/dhl_freight_sweden/print_request.py --no-nice-property-names
quicktype ... schemas/print_response.json ... karrio/schemas/dhl_freight_sweden/print_response.py --no-nice-property-names
quicktype ... schemas/error_response.json ... karrio/schemas/dhl_freight_sweden/error_response.py --no-nice-property-names
```

- [ ] **Step 3: Run generation + verify importable types**

```bash
chmod +x modules/connectors/dhl_freight_sweden/generate
./bin/run-generate-on modules/connectors/dhl_freight_sweden
python -c "import karrio.schemas.dhl_freight_sweden.booking_request as s; print([x for x in dir(s) if x[0].isupper()])"
python -c "import karrio.schemas.dhl_freight_sweden.print_request as s; print(dir(s))"
```
Note the exact class names emitted — later tasks import them (expect `Shipment`, `Party`, `Piece`, `PayerCode` for booking; `PrintOptionsById`/`ReportOptions`/`PageOptions` for print).

- [ ] **Step 4: Commit**

```bash
git add modules/connectors/dhl_freight_sweden/schemas modules/connectors/dhl_freight_sweden/generate modules/connectors/dhl_freight_sweden/karrio/schemas/dhl_freight_sweden
git commit -m "feat(dhl_freight): add schema samples and generate carrier types"
```

---

## Task 4: `utils.py` — Settings, hosts, tracking URL, label type

**Files:**
- Modify: `modules/connectors/dhl_freight_sweden/karrio/providers/dhl_freight_sweden/utils.py`

- [ ] **Step 1: Write the Settings class** (replace scaffolded body)

```python
import karrio.lib as lib
import karrio.core as core


class Settings(core.Settings):
    """DHL Freight (SE API Farm) connection settings."""

    # credential field (API Farm client key)
    client_key: str = None
    account_number: str = None

    @property
    def carrier_name(self):
        return "dhl_freight_sweden"

    @property
    def server_url(self):
        # per-connection override else API Farm default (host root; per-API base paths appended in the proxy)
        return self.connection_config.server_url.state or (
            "https://test-api.freight-logistics.dhl.com"
            if self.test_mode
            else "https://api.freight-logistics.dhl.com"
        )

    @property
    def tracking_url(self):
        # DHL Freight Sweden portal template (confirm exact template, PRD Pending #2)
        return "https://www.dhl.com/se-en/home/tracking.html?tracking-id={}"

    @property
    def label_type(self):
        # account-aligned metadata (default PDF); the Print API 2.10.0 has no raster-format request field
        return self.connection_config.label_type.state or "PDF"

    @property
    def connection_config(self) -> lib.units.Options:
        from karrio.providers.dhl_freight_sweden.units import ConnectionConfig

        return lib.to_connection_config(
            self.config or {},
            option_type=ConnectionConfig,
        )
```

- [ ] **Step 2: Verify it imports**

```bash
python -c "import karrio.providers.dhl_freight_sweden.utils as u; print(u.Settings)"
```

- [ ] **Step 3: Commit**

```bash
git add modules/connectors/dhl_freight_sweden/karrio/providers/dhl_freight_sweden/utils.py
git commit -m "feat(dhl_freight): settings with client-key, server_url override, tracking url"
```

---

## Task 5: `units.py` — services, options, connection config

**Files:**
- Modify: `modules/connectors/dhl_freight_sweden/karrio/providers/dhl_freight_sweden/units.py`

- [ ] **Step 1: Write the enums** (full product set from the PRD product table)

```python
import karrio.lib as lib
import karrio.core.units as units


class PackagingType(lib.StrEnum):
    """DHL Freight package types (packageType)."""

    pallet = "PAL"
    package = "PK"

    """ Unified Packaging type mapping """
    envelope = pallet
    pak = pallet
    tube = pallet
    small_box = package
    medium_box = package
    large_box = package
    your_packaging = pallet


class ShippingService(lib.StrEnum):
    """DHL Freight product codes (productCode).

    Full domestic + international set for SE. The runtime source of truth is the
    Product API GET /products; the six fixture products (102/401/103, 232/202/109)
    are exercised by hermetic tests.
    """

    # Domestic (SE<->SE)
    dhl_freight_hemleverans_paket_b2c = "118"
    dhl_freight_home_delivery_b2c = "401"
    dhl_freight_home_delivery_c2b = "402"
    dhl_freight_home_delivery_c2b_alt = "502"
    dhl_freight_pall = "210"
    dhl_freight_paket = "102"
    dhl_freight_parti = "212"
    dhl_freight_service_point_b2c = "103"
    dhl_freight_service_point_c2b = "104"
    dhl_freight_special = "209"
    dhl_freight_stycke = "211"

    # International (to/from SE)
    dhl_freight_road_freight_standard = "202"
    dhl_freight_euroconnect_plus = "232"
    dhl_freight_road_freight_direct = "205"
    dhl_freight_road_freight_priority = "233"
    dhl_freight_home_delivery_international_b2c = "601"
    dhl_freight_parcel_connect_b2c = "109"
    dhl_freight_parcel_return_connect_c2b = "107"
    dhl_freight_parcel_connect_plus = "112"
    dhl_freight_standard_pallet_international = "SPI"


class LabelLayout(lib.StrEnum):
    """Print API pageType values (page layout/size; raster format is account-governed)."""

    label = "Label"
    label_2x_portrait_a4 = "Label2xPortraitA4"
    label_3x_landscape_a4 = "Label3xLandscapeA4"
    label_compact = "LabelCompact"
    label_compact_2x2_portrait_a4 = "LabelCompact2x2PortraitA4"


class PayerCode(lib.StrEnum):
    DAP = "DAP"
    DDP = "DDP"
    EXW = "EXW"
    CIP = "CIP"


class ShippingOption(lib.Enum):
    """DHL Freight shipment options."""

    dhl_freight_payer_code = lib.OptionEnum("dhl_freight_payer_code", str)
    dhl_freight_label_layout = lib.OptionEnum("dhl_freight_label_layout", str)
    dhl_freight_waybill = lib.OptionEnum("dhl_freight_waybill", bool)
    dhl_freight_return_label = lib.OptionEnum("dhl_freight_return_label", bool)


def shipping_options_initializer(
    options: dict,
    package_options: units.ShippingOptions = None,
) -> units.ShippingOptions:
    """Apply default values to the given options."""
    if package_options is not None:
        options.update(package_options.content)

    def items_filter(key: str) -> bool:
        return key in ShippingOption  # type: ignore

    return units.ShippingOptions(options, ShippingOption, items_filter=items_filter)


class ConnectionConfig(lib.Enum):
    """DHL Freight connection configuration options."""

    server_url = lib.OptionEnum("server_url", str)
    label_type = lib.OptionEnum("label_type", str)  # account-aligned label format tag; default PDF
```

- [ ] **Step 2: Verify import**

```bash
python -c "import karrio.providers.dhl_freight_sweden.units as u; print(u.ShippingService.map('102').name, u.ConnectionConfig.server_url)"
```
Expected: `dhl_freight_paket <OptionEnum ...>`.

- [ ] **Step 3: Commit**

```bash
git add modules/connectors/dhl_freight_sweden/karrio/providers/dhl_freight_sweden/units.py
git commit -m "feat(dhl_freight): full product set, options, connection config"
```

---

## Task 6: `error.py` — validationErrors + errorMessage

**Files:**
- Modify: `modules/connectors/dhl_freight_sweden/karrio/providers/dhl_freight_sweden/error.py`

- [ ] **Step 1: Write the parser** (handles `validationErrors[]` and top-level `errorMessage`)

```python
import typing
import karrio.lib as lib
import karrio.core.models as models
import karrio.providers.dhl_freight_sweden.utils as provider_utils


def parse_error_response(
    response: dict,
    settings: provider_utils.Settings,
    **kwargs,
) -> typing.List[models.Message]:
    responses = response if isinstance(response, list) else [response]

    messages: typing.List[models.Message] = []
    for res in responses:
        # booking/print field validation errors (IValidationError)
        for err in res.get("validationErrors") or []:
            messages.append(
                models.Message(
                    carrier_id=settings.carrier_id,
                    carrier_name=settings.carrier_name,
                    code=str(err.get("errorCode")) if err.get("errorCode") is not None else None,
                    message=err.get("message") or "",
                    details=lib.to_dict(
                        {**kwargs, "field": err.get("field"), "incompatibleFields": err.get("incompatibleFields")}
                    ),
                )
            )
        # top-level error message with no field validation entries
        if res.get("errorMessage") and not (res.get("validationErrors") or []):
            messages.append(
                models.Message(
                    carrier_id=settings.carrier_id,
                    carrier_name=settings.carrier_name,
                    code=str(res.get("status")) if res.get("status") is not None else None,
                    message=res.get("errorMessage"),
                    details=lib.to_dict(kwargs),
                )
            )

    return messages
```

- [ ] **Step 2: Verify import**

```bash
python -c "import karrio.providers.dhl_freight_sweden.error as e; print(e.parse_error_response)"
```

- [ ] **Step 3: Commit**

```bash
git add modules/connectors/dhl_freight_sweden/karrio/providers/dhl_freight_sweden/error.py
git commit -m "feat(dhl_freight): error parser for validationErrors and errorMessage"
```

---

## Task 7: mapper `settings.py`

**Files:**
- Modify: `modules/connectors/dhl_freight_sweden/karrio/mappers/dhl_freight_sweden/settings.py`

- [ ] **Step 1: Write the mapper Settings**

```python
"""Karrio DHL Freight client settings."""

import attr
import karrio.core.models as models
import karrio.providers.dhl_freight_sweden.utils as provider_utils


@attr.s(auto_attribs=True)
class Settings(provider_utils.Settings):
    """DHL Freight connection settings."""

    # carrier specific properties
    client_key: str = None
    account_number: str = None

    # generic properties
    id: str = None
    test_mode: bool = False
    carrier_id: str = "dhl_freight_sweden"
    account_country_code: str = None
    metadata: dict = {}
    config: dict = {}
```

- [ ] **Step 2: Verify import**

```bash
python -c "import karrio.mappers.dhl_freight_sweden.settings as s; print(s.Settings)"
```

- [ ] **Step 3: Commit**

```bash
git add modules/connectors/dhl_freight_sweden/karrio/mappers/dhl_freight_sweden/settings.py
git commit -m "feat(dhl_freight): mapper settings"
```

---

## Task 8: `proxy.py` — client-key header + book→print chain

**Files:**
- Modify: `modules/connectors/dhl_freight_sweden/karrio/mappers/dhl_freight_sweden/proxy.py`

- [ ] **Step 1: Write the proxy**

```python
"""Karrio DHL Freight client proxy."""

import karrio.lib as lib
import karrio.api.proxy as proxy
import karrio.mappers.dhl_freight_sweden.settings as provider_settings


class Proxy(proxy.Proxy):
    settings: provider_settings.Settings

    @property
    def headers(self) -> dict:
        return {
            "content-type": "application/json",
            "client-key": self.settings.client_key,
        }

    def create_shipment(self, request: lib.Serializable) -> lib.Deserializable[dict]:
        ctx = request.ctx or {}

        # 1) book
        booking = lib.request(
            url=f"{self.settings.server_url}/transportinstructionapi/v1/transportinstruction/sendtransportinstruction",
            data=lib.to_json(request.serialize()),
            trace=self.trace_as("json"),
            method="POST",
            headers=self.headers,
            decoder=lib.to_dict,
            on_error=lib.error_decoder,
        )
        shipment_id = ((booking or {}).get("transportInstruction") or {}).get("id")

        # 2) print-by-id (only if booking produced an id); op TBD (byid vs full payload)
        printed = None
        if shipment_id:
            print_body = {
                "shipmentIds": [shipment_id],
                "options": ctx.get("print_options") or {"label": True, "pageOptions": {"pageType": "Label"}},
            }
            printed = lib.request(
                url=f"{self.settings.server_url}/printapi/v1/print/printdocumentsbyid",
                data=lib.to_json(print_body),
                trace=self.trace_as("json"),
                method="POST",
                headers=self.headers,
                decoder=lib.to_dict,
                on_error=lib.error_decoder,
            )

        return lib.Deserializable({"booking": booking, "print": printed}, lib.to_dict)
```

No `get_rates`, `get_tracking`, or `cancel_shipment` is defined, keeping capabilities = shipping only.

- [ ] **Step 2: Verify import**

```bash
python -c "import karrio.mappers.dhl_freight_sweden.proxy as p; print(p.Proxy.create_shipment)"
```

- [ ] **Step 3: Commit**

```bash
git add modules/connectors/dhl_freight_sweden/karrio/mappers/dhl_freight_sweden/proxy.py
git commit -m "feat(dhl_freight): proxy client-key header, book+print chain"
```

---

## Task 9: `shipment/create.py` — request build + response parse

**Files:**
- Modify: `modules/connectors/dhl_freight_sweden/karrio/providers/dhl_freight_sweden/shipment/create.py`

> Use the exact generated class names printed in Task 3 Step 3. Below uses `dict` request bodies for robustness; swap to generated dataclasses if the team prefers typed construction.

- [ ] **Step 1: Write the provider**

```python
"""Karrio DHL Freight shipment create implementation."""

import typing
import karrio.lib as lib
import karrio.core.models as models
import karrio.providers.dhl_freight_sweden.error as error
import karrio.providers.dhl_freight_sweden.utils as provider_utils
import karrio.providers.dhl_freight_sweden.units as provider_units


def parse_shipment_response(
    _response: lib.Deserializable[dict],
    settings: provider_utils.Settings,
) -> typing.Tuple[typing.Optional[models.ShipmentDetails], typing.List[models.Message]]:
    response = _response.deserialize()
    booking = response.get("booking") or {}
    printed = response.get("print") or {}

    messages = [
        *error.parse_error_response(booking, settings),
        *error.parse_error_response(printed, settings),
    ]

    shipment_id = ((booking.get("transportInstruction") or {}).get("id"))
    details = (
        _extract_details(response, settings) if shipment_id and not any(messages) else None
    )
    return details, messages


def _extract_details(
    response: dict,
    settings: provider_utils.Settings,
) -> models.ShipmentDetails:
    shipment_id = ((response.get("booking") or {}).get("transportInstruction") or {}).get("id")
    reports = ((response.get("print") or {}).get("reports")) or []
    label = next(
        (r.get("content") for r in reports if (r.get("name") or "").lower() == "label"),
        next((r.get("content") for r in reports), None),
    )

    return models.ShipmentDetails(
        carrier_id=settings.carrier_id,
        carrier_name=settings.carrier_name,
        tracking_number=shipment_id,
        shipment_identifier=shipment_id,
        label_type=settings.label_type,
        docs=models.Documents(label=label or ""),
        meta=dict(tracking_url=settings.tracking_url.format(shipment_id)),
    )


def shipment_request(
    payload: models.ShipmentRequest,
    settings: provider_utils.Settings,
) -> lib.Serializable:
    shipper = lib.to_address(payload.shipper)
    recipient = lib.to_address(payload.recipient)
    packages = lib.to_packages(payload.parcels)
    options = lib.to_shipping_options(
        payload.options,
        package_options=packages.options,
        initializer=provider_units.shipping_options_initializer,
    )
    product_code = provider_units.ShippingService.map(payload.service).value_or_key
    payer_code = options.dhl_freight_payer_code.state or "DAP"
    layout = options.dhl_freight_label_layout.state or provider_units.LabelLayout.label.value

    def party(addr, party_type, account=None):
        return dict(
            type=party_type,
            id=account,
            name=addr.company_name or addr.person_name,
            contactName=addr.person_name,
            phone=addr.phone_number,
            email=addr.email,
            address=dict(
                street=lib.text(addr.address_line1, addr.address_line2, sep=" "),
                cityName=addr.city,
                postalCode=addr.postal_code,
                countryCode=addr.country_code,
            ),
        )

    request = dict(
        productCode=product_code,
        totalNumberOfPieces=len(packages),
        totalWeight=packages.weight.KG,
        payerCode=dict(code=payer_code, location=""),
        parties=[
            party(shipper, "Consignor", settings.account_number),
            party(recipient, "Consignee"),
        ],
        pieces=[
            dict(
                goodsType=lib.text(pkg.description, max=70),
                packageType=provider_units.PackagingType.map(pkg.packaging_type).value or "PAL",
                numberOfPieces=1,
                weight=pkg.weight.KG,
                width=pkg.width.CM,
                height=pkg.height.CM,
                length=pkg.length.CM,
            )
            for pkg in packages
        ],
    )

    print_options = {
        "label": True,
        "waybill": bool(options.dhl_freight_waybill.state),
        "returnLabel": bool(options.dhl_freight_return_label.state),
        "pageOptions": {"pageType": layout},
    }

    return lib.Serializable(
        request,
        lib.to_dict,
        dict(print_options=print_options),
    )
```

- [ ] **Step 2: Verify import**

```bash
python -c "import karrio.providers.dhl_freight_sweden.shipment.create as c; print(c.shipment_request, c.parse_shipment_response)"
```

- [ ] **Step 3: Commit**

```bash
git add modules/connectors/dhl_freight_sweden/karrio/providers/dhl_freight_sweden/shipment/create.py
git commit -m "feat(dhl_freight): shipment create request build and response parse"
```

---

## Task 10: Deferred stubs — `tracking.py` and `shipment/cancel.py`

**Files:**
- Modify: `modules/connectors/dhl_freight_sweden/karrio/providers/dhl_freight_sweden/tracking.py`
- Modify: `modules/connectors/dhl_freight_sweden/karrio/providers/dhl_freight_sweden/shipment/cancel.py`

- [ ] **Step 1: Leave both as documented deferred stubs**

Neither is wired in Phase 0. `tracking.py` carries a module docstring stating that tracking is surfaced as a URL through `shipment/create` `meta.tracking_url`, and that a full `TrackingRequest` to `TrackingDetails` feature is deferred (it would use the DHL Unified Shipment Tracking API on the DHL Group gateway — a different front door and credential, not the API Farm). `shipment/cancel.py` carries a docstring stating cancellation and returns are out of scope for Phase 0. Do not export `parse_tracking_response`/`tracking_request` or `cancel_shipment` from the provider `__init__` (Task 11), so no `tracking`/`cancel` capability is derived.

- [ ] **Step 2: Commit**

```bash
git add modules/connectors/dhl_freight_sweden/karrio/providers/dhl_freight_sweden/tracking.py modules/connectors/dhl_freight_sweden/karrio/providers/dhl_freight_sweden/shipment/cancel.py
git commit -m "docs(dhl_freight): document deferred tracking and cancel stubs"
```

---

## Task 11: Public exports + plugin METADATA (shipping only)

**Files:**
- Modify: `modules/connectors/dhl_freight_sweden/karrio/providers/dhl_freight_sweden/__init__.py`
- Modify: `modules/connectors/dhl_freight_sweden/karrio/providers/dhl_freight_sweden/shipment/__init__.py`
- Modify: `modules/connectors/dhl_freight_sweden/karrio/plugins/dhl_freight_sweden/__init__.py`

- [ ] **Step 1: providers `__init__.py`** — export only shipment create

```python
"""Karrio DHL Freight provider."""

from karrio.providers.dhl_freight_sweden.utils import Settings
from karrio.providers.dhl_freight_sweden.shipment import (
    parse_shipment_response,
    shipment_request,
)
```

- [ ] **Step 2: shipment `__init__.py`** — export create only (no cancel)

```python
from karrio.providers.dhl_freight_sweden.shipment.create import (
    parse_shipment_response,
    shipment_request,
)
```

- [ ] **Step 3: plugin `__init__.py`** — METADATA (shipping only)

```python
from karrio.core.metadata import PluginMetadata

from karrio.mappers.dhl_freight_sweden.mapper import Mapper
from karrio.mappers.dhl_freight_sweden.proxy import Proxy
from karrio.mappers.dhl_freight_sweden.settings import Settings
import karrio.providers.dhl_freight_sweden.units as units


METADATA = PluginMetadata(
    status="in-development",
    id="dhl_freight_sweden",
    label="DHL Freight Sweden",
    description="DHL Freight Sweden (API Farm) booking and label integration",
    # Integrations
    Mapper=Mapper,
    Proxy=Proxy,
    Settings=Settings,
    # Data Units
    is_hub=False,
    options=units.ShippingOption,
    services=units.ShippingService,
    connection_configs=units.ConnectionConfig,
    # Extra info
    website="https://www.dhl.com/se-en/home/our-divisions/freight.html",
    documentation="https://developer.dhl.com/api-reference",
)
```

- [ ] **Step 4: Confirm mapper.py wires create only (do NOT edit — it is generated)**

```bash
python -c "import karrio.mappers.dhl_freight_sweden.mapper as m; print([x for x in dir(m.Mapper) if not x.startswith('_')])"
```
Expected: includes `create_shipment_request`, `parse_shipment_response`. If `mapper.py` still references rate/tracking/cancel from scaffolding, re-run `./bin/run-generate-on` so it matches the provider functions present.

- [ ] **Step 5: Verify plugin loads with shipping-only capabilities**

```bash
python -c "import karrio.sdk as karrio; print(karrio.gateway['dhl_freight_sweden'].capabilities)"
```
Expected: `['shipping']` (no `rating`/`tracking`).

- [ ] **Step 6: Commit**

```bash
git add modules/connectors/dhl_freight_sweden/karrio
git commit -m "feat(dhl_freight): public exports and plugin metadata (shipping only)"
```

---

## Task 12: Shipment tests (4-method, mocks book + print)

**Files:**
- Modify: `modules/connectors/dhl_freight_sweden/tests/dhl_freight_sweden/fixture.py`
- Create: `modules/connectors/dhl_freight_sweden/tests/dhl_freight_sweden/test_shipment.py`

- [ ] **Step 1: fixture.py**

```python
"""DHL Freight carrier tests fixtures."""

import karrio.sdk as karrio


gateway = karrio.gateway["dhl_freight_sweden"].create(
    dict(
        id="123456789",
        test_mode=True,
        carrier_id="dhl_freight_sweden",
        client_key="TEST_CLIENT_KEY",
        account_number="ACCT1",
    )
)
```

- [ ] **Step 2: Write the four-method shipment test** (mocks both HTTP calls; no authenticate step exists)

`test_shipment.py`:
```python
"""DHL Freight shipment tests."""

import unittest
from unittest.mock import patch
from .fixture import gateway

import karrio.sdk as karrio
import karrio.lib as lib
import karrio.core.models as models


class TestDHLFreightShipment(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None
        self.ShipmentRequest = models.ShipmentRequest(**ShipmentPayload)

    def test_create_shipment_request(self):
        request = gateway.mapper.create_shipment_request(self.ShipmentRequest)
        self.assertEqual(lib.to_dict(request.serialize()), ShipmentRequest)

    def test_create_shipment(self):
        with patch("karrio.mappers.dhl_freight_sweden.proxy.lib.request") as mock:
            mock.side_effect = [BookingResponse, PrintResponse]
            karrio.Shipment.create(self.ShipmentRequest).from_(gateway)
            self.assertEqual(
                mock.call_args_list[0][1]["url"],
                f"{gateway.settings.server_url}/transportinstructionapi/v1/transportinstruction/sendtransportinstruction",
            )
            self.assertEqual(
                mock.call_args_list[0][1]["headers"]["client-key"],
                "TEST_CLIENT_KEY",
            )
            self.assertEqual(
                mock.call_args_list[1][1]["url"],
                f"{gateway.settings.server_url}/printapi/v1/print/printdocumentsbyid",
            )

    def test_parse_shipment_response(self):
        with patch("karrio.mappers.dhl_freight_sweden.proxy.lib.request") as mock:
            mock.side_effect = [BookingResponse, PrintResponse]
            parsed = karrio.Shipment.create(self.ShipmentRequest).from_(gateway).parse()
            self.assertListEqual(lib.to_dict(parsed), ParsedShipmentResponse)

    def test_parse_error_response(self):
        with patch("karrio.mappers.dhl_freight_sweden.proxy.lib.request") as mock:
            mock.side_effect = [ErrorResponse]
            parsed = karrio.Shipment.create(self.ShipmentRequest).from_(gateway).parse()
            self.assertListEqual(lib.to_dict(parsed), ParsedErrorResponse)


if __name__ == "__main__":
    unittest.main()


ShipmentPayload = {
    "service": "dhl_freight_paket",
    "shipper": {"company_name": "Sender AB", "person_name": "A", "phone_number": "0700000000",
                 "email": "a@x.se", "address_line1": "Main 1", "city": "Stockholm",
                 "postal_code": "11122", "country_code": "SE"},
    "recipient": {"company_name": "Receiver AB", "person_name": "B", "phone_number": "0700000001",
                   "email": "b@x.se", "address_line1": "Road 2", "city": "Gothenburg",
                   "postal_code": "41111", "country_code": "SE"},
    "parcels": [{"weight": 380.0, "weight_unit": "KG", "width": 80.0, "height": 90.0,
                  "length": 120.0, "dimension_unit": "CM", "packaging_type": "pallet",
                  "description": "Machinery Parts"}],
    "options": {"dhl_freight_payer_code": "DAP"},
}

ShipmentRequest = {
    "productCode": "102",
    "totalNumberOfPieces": 1,
    "totalWeight": 380.0,
    "payerCode": {"code": "DAP", "location": ""},
    "parties": [
        {"type": "Consignor", "id": "ACCT1", "name": "Sender AB", "contactName": "A",
         "phone": "0700000000", "email": "a@x.se",
         "address": {"street": "Main 1", "cityName": "Stockholm", "postalCode": "11122", "countryCode": "SE"}},
        {"type": "Consignee", "name": "Receiver AB", "contactName": "B",
         "phone": "0700000001", "email": "b@x.se",
         "address": {"street": "Road 2", "cityName": "Gothenburg", "postalCode": "41111", "countryCode": "SE"}},
    ],
    "pieces": [
        {"goodsType": "Machinery Parts", "packageType": "PAL", "numberOfPieces": 1,
         "weight": 380.0, "width": 80.0, "height": 90.0, "length": 120.0}
    ],
}

BookingResponse = {"status": "OK", "transportInstruction": {"id": "1234567890123"}}
PrintResponse = {"reports": [{"name": "label", "content": "SkVUTEFCRUw=", "contentType": "application/pdf", "type": "PDF", "valid": True}]}
ErrorResponse = {"status": "ERROR", "errorMessage": "Bad Request", "validationErrors": [
    {"field": "productCode", "errorCode": 100, "message": "invalid product", "incompatibleFields": []}]}

ParsedShipmentResponse = [
    {
        "carrier_id": "dhl_freight_sweden",
        "carrier_name": "dhl_freight_sweden",
        "tracking_number": "1234567890123",
        "shipment_identifier": "1234567890123",
        "label_type": "PDF",
        "docs": {"label": "SkVUTEFCRUw="},
        "meta": {"tracking_url": "https://www.dhl.com/se-en/home/tracking.html?tracking-id=1234567890123"},
    },
    [],
]

ParsedErrorResponse = [
    None,
    [
        {
            "carrier_id": "dhl_freight_sweden",
            "carrier_name": "dhl_freight_sweden",
            "code": "100",
            "message": "invalid product",
            "details": {"field": "productCode", "incompatibleFields": []},
        }
    ],
]
```

- [ ] **Step 3: Run to verify it passes**

```bash
python -m unittest -v modules.connectors.dhl_freight_sweden.tests.dhl_freight_sweden.test_shipment
```
Expected: PASS on all four. If a field differs, add `print(lib.to_dict(parsed))` above the assert, align the expected constant (recall `lib.to_dict` strips `None`/empty), then remove the print. Confirm the exact `tracking_url` template value matches `utils.Settings.tracking_url` (PRD Pending #2).

- [ ] **Step 4: Extend fixtures to the remaining fixture products**

Add the other five fixture products (401, 103 domestic; 232, 202, 109 international) as additional payload/request/response constants or parametrized cases. At minimum, 102, 232, and 202 must pass end-to-end. If 103/401/109 require a service-point / home-delivery locator reference that cannot be caller-supplied, document that here and drop them from the fixture set (PRD Pending #3).

- [ ] **Step 5: Commit**

```bash
git add modules/connectors/dhl_freight_sweden/tests/dhl_freight_sweden/fixture.py modules/connectors/dhl_freight_sweden/tests/dhl_freight_sweden/test_shipment.py
git commit -m "test(dhl_freight): shipment create request, call, parse, error"
```

---

## Task 13: Final validation

- [ ] **Step 1: Full verification sweep**

```bash
python -m unittest discover -v -f modules/connectors/dhl_freight_sweden/tests
./bin/run-sdk-tests
./bin/cli plugins show dhl_freight_sweden
python -c "import karrio.sdk as k; print(k.gateway['dhl_freight_sweden'].capabilities)"
```
Expected: carrier + SDK suites green; plugin shows `dhl_freight_sweden`; capabilities `['shipping']`.

- [ ] **Step 2: Mark PRD launch criteria + update statuses**

Tick the PRD's Launch Criteria that now hold; update Implementation Plan phase statuses from `Pending`. Record the outcomes of the parked Pending questions (print op, tracking URL template, locator reference).

- [ ] **Step 3: Final commit**

```bash
git add -A modules/connectors/dhl_freight_sweden PRDs/PRD_DHL_FREIGHT_INTEGRATION.md
git commit -m "chore(dhl_freight): finalize Phase 0 connector"
```

---

## Self-Review (completed by author)

- **Spec coverage:** book→print (Task 8/9), `client-key` header (Task 4/8), URL-only tracking via shipment meta (Task 9), pageType layout option (Task 5/9), server_url override (Task 4/5/11), no rating/tracking/cancel capability (Task 8/10/11), `client_key`/`account_number` creds (Task 4/7), full product set with six fixtures (Task 5/12), deferred tracking/cancel stubs (Task 10) — all mapped.
- **Retarget consistency:** all endpoints, base paths, and the auth header are drawn from the vendored `vendor/se-api-farm/*.json` 2.10.0 specs; no OAuth token exchange, no cache, no DHL Group Portal host remains.
- **Type consistency:** `client_key`/`account_number` consistent across utils/settings/fixture; `server_url` resolution identical in utils and used verbatim in test URL assertions; `tracking_url` template identical in utils, provider, and expected test constants; `ConnectionConfig.server_url`/`label_type` referenced consistently in units, utils, plugin.
- **Known adaptation points:** the exact print operation (`printdocumentsbyid` vs `printdocuments`), the tracking URL template, and the service-point / home-delivery locator reference are open (PRD Pending #1/#2/#3) and flagged in-task. Task 9 uses `dict` request bodies for robustness; typed construction substitutes the generated class names from Task 3 Step 3.
