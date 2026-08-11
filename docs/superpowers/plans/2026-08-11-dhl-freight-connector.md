# DHL Freight Connector Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Karrio `dhl_freight` connector that books DHL Freight transport orders, returns a printed label in one `shipment/create` call, and exposes a tracking id + tracking URL.

**Architecture:** `shipment/create` chains three DHL Freight APIs behind one proxy method — authenticate (OAuth2 client-credentials over HTTP Basic → cached ~30-min Bearer token) → book (`POST /sendtransportinstruction`, returns a 13-char id) → print-by-id (`POST /print/printdocumentsbyid`, returns label bytes). Tracking is URL-only (no HTTP call): `get_tracking` echoes the number and the provider builds `carrier_tracking_link` from a template. No rating, no void/cancel (absent from the DHL Freight APIs). Hosts default to the DHL Group platform with a per-connection `server_url` override for the SE API Farm.

**Tech Stack:** Python, `karrio.lib`, `attr`/`jstruct`, `unittest` (never pytest), Karrio SDK plugin entrypoints, `./bin/cli sdk add-extension` scaffolding + `./bin/run-generate-on` schema generation.

**Reference PRD:** `PRDs/PRD_DHL_FREIGHT_INTEGRATION.md`

**Precedent connectors to mirror (study before editing):**
- Token cache + Bearer proxy: `modules/connectors/dhl_parcel_de/karrio/mappers/dhl_parcel_de/proxy.py`
- `server_url` override + `ConnectionConfig`: `modules/connectors/postat/karrio/providers/postat/{units.py,utils.py}` + `karrio/plugins/postat/__init__.py`
- Single-body request Serializable + empty-label: `modules/connectors/gls/karrio/providers/gls/shipment/create.py:55,156`
- JSON create request/response, tracking, error, metadata, units, tests: `modules/connectors/mydhl/...`
- tracking_url property: `modules/connectors/dhl_express/karrio/providers/dhl_express/utils.py:32-34`

---

## File Structure

```
modules/connectors/dhl_freight/
├── pyproject.toml                                   # scaffolded; entrypoint karrio.plugins.dhl_freight
├── generate                                         # scaffolded; edit CLI flags (camelCase API)
├── vendor/                                          # NEW: raw specs + guide (git-tracked)
│   ├── DHL Freight Authentication API YAML - 2026 R04.yaml
│   ├── DHL Freight Shipment Booking API YAML - 2026 R04.yaml
│   ├── DHL Freight Print API YAML - 2026 R04.yaml
│   ├── DHL Freight Shipment Tracking API YAML - 2026 R04.yaml
│   └── DHL Freight User Guide.md
├── schemas/                                         # generation input (JSON samples)
│   ├── auth_response.json
│   ├── booking_request.json
│   ├── booking_response.json
│   ├── print_request.json
│   ├── print_response.json
│   └── error_response.json
├── karrio/
│   ├── plugins/dhl_freight/__init__.py              # METADATA
│   ├── mappers/dhl_freight/{__init__.py,mapper.py,proxy.py,settings.py}
│   ├── providers/dhl_freight/
│   │   ├── __init__.py                              # public exports
│   │   ├── utils.py                                 # Settings: creds, server_url override, token_server_url, tracking_url, connection_config
│   │   ├── units.py                                 # ShippingService, ShippingOption, ConnectionConfig, TrackingStatus
│   │   ├── error.py                                 # booking validationErrors + auth {status,title,detail}
│   │   ├── tracking.py                              # URL-only build + parse
│   │   └── shipment/{__init__.py,create.py}         # book + print (no cancel)
│   └── schemas/dhl_freight/                         # generated types (DO NOT EDIT)
└── tests/dhl_freight/
    ├── fixture.py
    ├── test_shipment.py
    ├── test_tracking.py
    └── test_live_smoke.py                           # opt-in, env-gated (net-new)
```

Responsibility boundaries: `utils.py` owns settings + URL/credential resolution; `proxy.py` owns all HTTP + the token cache + the book→print chain; `shipment/create.py` owns unified↔carrier mapping; `tracking.py` owns URL-only tracking; `error.py` owns both error shapes; `units.py` owns all enums. Files that change together (a provider function + its schema types) stay together.

---

## Task 1: Scaffold the connector

**Files:**
- Create (via CLI): `modules/connectors/dhl_freight/` tree

- [ ] **Step 1: Confirm branch + env**

Run:
```bash
git branch --show-current    # expect: dhl-freight-connector
source ./bin/activate-env
```

- [ ] **Step 2: Scaffold with shipping + tracking only (no rating)**

Run:
```bash
./bin/cli sdk add-extension \
  --path modules/connectors \
  --carrier-slug dhl_freight \
  --display-name "DHL Freight" \
  --features "shipping,tracking" \
  --no-is-xml-api \
  --version 2026.4 \
  --confirm
```
Expected: creates `modules/connectors/dhl_freight/` with `schemas/`, `karrio/{plugins,mappers,providers,schemas}/dhl_freight/`, `tests/dhl_freight/`, `pyproject.toml`, `generate`.

- [ ] **Step 3: Verify structure + install editable**

Run:
```bash
ls modules/connectors/dhl_freight/karrio/providers/dhl_freight
pip install -e modules/connectors/dhl_freight
./bin/cli plugins show dhl_freight
```
Expected: providers dir lists `utils.py units.py error.py tracking.py shipment/`; plugin show prints `dhl_freight` metadata.

- [ ] **Step 4: Remove the scaffolded rate + cancel stubs we will not implement**

The scaffolder may emit `rate.py` and `shipment/cancel.py`/`return_shipment.py`. Delete any of these that exist so no unused capability is exposed (capabilities are derived from proxy methods; provider files left unused are dead code).

Run:
```bash
rm -f modules/connectors/dhl_freight/karrio/providers/dhl_freight/rate.py
rm -f modules/connectors/dhl_freight/karrio/providers/dhl_freight/shipment/cancel.py
rm -f modules/connectors/dhl_freight/karrio/providers/dhl_freight/shipment/return_shipment.py
rm -f modules/connectors/dhl_freight/tests/dhl_freight/test_rate.py
```
Then remove their imports from `karrio/providers/dhl_freight/__init__.py` and `karrio/providers/dhl_freight/shipment/__init__.py` (edit in Task 10/11).

- [ ] **Step 5: Commit the scaffold**

```bash
git add modules/connectors/dhl_freight
git commit -m "feat(dhl_freight): scaffold connector (shipping, tracking)"
```

---

## Task 2: Vendor the raw specs

**Files:**
- Create: `modules/connectors/dhl_freight/vendor/` (5 files moved from repo root)

- [ ] **Step 1: Move the four YAMLs + User Guide into vendor/**

Run:
```bash
mkdir -p modules/connectors/dhl_freight/vendor
git mv -k "DHL Freight Authentication API YAML - 2026 R04.yaml" modules/connectors/dhl_freight/vendor/ 2>/dev/null || mv "DHL Freight Authentication API YAML - 2026 R04.yaml" modules/connectors/dhl_freight/vendor/
mv "DHL Freight Shipment Booking API YAML - 2026 R04.yaml" modules/connectors/dhl_freight/vendor/
mv "DHL Freight Print API YAML - 2026 R04.yaml" modules/connectors/dhl_freight/vendor/
mv "DHL Freight Shipment Tracking API YAML - 2026 R04.yaml" modules/connectors/dhl_freight/vendor/
mv "DHL Freight User Guide.md" modules/connectors/dhl_freight/vendor/
```
(The root YAMLs are currently untracked, so plain `mv` is correct; `git mv` only applies if a file was already tracked.)

- [ ] **Step 2: Verify + commit**

Run:
```bash
ls modules/connectors/dhl_freight/vendor
git add modules/connectors/dhl_freight/vendor
git commit -m "docs(dhl_freight): vendor DHL Freight API specs and user guide"
```
Expected: five files listed; the repo root no longer holds the DHL YAMLs.

---

## Task 3: Schema samples + generation

DHL Freight is a **camelCase** JSON API (`productCode`, `payerCode`, `shipmentIds`, `pageOptions`), so generation uses `--no-nice-property-names`.

**Files:**
- Create: `modules/connectors/dhl_freight/schemas/*.json`
- Modify: `modules/connectors/dhl_freight/generate`

- [ ] **Step 1: Write the six JSON samples** (distilled from `vendor/` schemas — real field shapes, minimal but complete)

`schemas/auth_response.json`:
```json
{ "access_token": "opaque", "id_token": "jwt", "token_type": "Bearer", "expires_in": 1799 }
```

`schemas/booking_request.json`:
```json
{
  "id": "",
  "productCode": "ECI",
  "pickupDate": "2026-08-12",
  "totalNumberOfPieces": 1,
  "totalWeight": 380,
  "goodsDescription": "Machinery Parts",
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
{ "status": "OK", "shipment": { "id": "1234567890123", "productCode": "ECI", "parties": [], "pieces": [] } }
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
{ "reports": [ { "name": "label", "content": "base64bytes", "type": "PDF", "valid": true } ] }
```

`schemas/error_response.json`:
```json
{
  "status": "ERROR",
  "validationErrors": [ { "field": "productCode", "errorCode": 100, "message": "invalid", "incompatibleFields": [] } ],
  "title": "Bad Request",
  "detail": "Invalid response type."
}
```
(The single `error_response.json` merges the booking `validationErrors` shape and the auth `{status,title,detail}` shape so one generated `ErrorResponseType` covers both.)

- [ ] **Step 2: Configure `generate` for camelCase**

Edit `modules/connectors/dhl_freight/generate` so each schema is generated with `--no-nice-property-names`. Mirror the format of an existing camelCase connector's `generate` (e.g. `modules/connectors/mydhl/generate`). Each line maps a JSON sample to a module, e.g.:
```bash
quicktype ... schemas/booking_request.json ... karrio/schemas/dhl_freight/booking_request.py --no-nice-property-names
quicktype ... schemas/booking_response.json ... karrio/schemas/dhl_freight/booking_response.py --no-nice-property-names
quicktype ... schemas/print_request.json ... karrio/schemas/dhl_freight/print_request.py --no-nice-property-names
quicktype ... schemas/print_response.json ... karrio/schemas/dhl_freight/print_response.py --no-nice-property-names
quicktype ... schemas/auth_response.json ... karrio/schemas/dhl_freight/auth_response.py --no-nice-property-names
quicktype ... schemas/error_response.json ... karrio/schemas/dhl_freight/error_response.py --no-nice-property-names
```
Copy the exact quicktype invocation shape from `mydhl/generate` (same tool, flags, and header); only the file list and `--no-nice-property-names` flag differ.

- [ ] **Step 3: Run generation + verify importable types**

Run:
```bash
chmod +x modules/connectors/dhl_freight/generate
./bin/run-generate-on modules/connectors/dhl_freight
python -c "import karrio.schemas.dhl_freight.booking_request as s; print([x for x in dir(s) if x[0].isupper()])"
python -c "import karrio.schemas.dhl_freight.print_request as s; print(dir(s))"
```
Expected: prints generated classes (e.g. `Shipment`, `Party`, `Piece`, `PayerCode` for booking_request; `PrintOptionsById`/`ReportOptions`/`PageOptions` for print_request). Note the exact class names emitted — later tasks import them.

- [ ] **Step 4: Commit**

```bash
git add modules/connectors/dhl_freight/schemas modules/connectors/dhl_freight/generate modules/connectors/dhl_freight/karrio/schemas/dhl_freight
git commit -m "feat(dhl_freight): add schema samples and generate carrier types"
```

---

## Task 4: `utils.py` — Settings, hosts, token endpoint, tracking URL

**Files:**
- Modify: `modules/connectors/dhl_freight/karrio/providers/dhl_freight/utils.py`

- [ ] **Step 1: Write the Settings class** (replace scaffolded body)

```python
import karrio.lib as lib
import karrio.core as core


class Settings(core.Settings):
    """DHL Freight connection settings."""

    # credential fields (portal API Key / API Secret)
    consumer_key: str = None
    consumer_secret: str = None
    account_number: str = None

    @property
    def carrier_name(self):
        return "dhl_freight"

    @property
    def server_url(self):
        # per-connection override (SE API Farm) else DHL Group platform default
        return self.connection_config.server_url.state or (
            "https://api-sandbox.dhl.com"
            if self.test_mode
            else "https://api.dhl.com"
        )

    @property
    def tracking_url(self):
        return "https://www.dhl.com/global-en/home/tracking/tracking-freight.html?submit=1&tracking-id={}"

    @property
    def connection_config(self) -> lib.units.Options:
        from karrio.providers.dhl_freight.units import ConnectionConfig

        return lib.to_connection_config(
            self.config or {},
            option_type=ConnectionConfig,
        )
```

- [ ] **Step 2: Verify it imports**

Run:
```bash
python -c "import karrio.providers.dhl_freight.utils as u; print(u.Settings)"
```
Expected: prints the Settings class, no ImportError.

- [ ] **Step 3: Commit**

```bash
git add modules/connectors/dhl_freight/karrio/providers/dhl_freight/utils.py
git commit -m "feat(dhl_freight): settings with server_url override and tracking url"
```

---

## Task 5: `units.py` — services, options, connection config, statuses

**Files:**
- Modify: `modules/connectors/dhl_freight/karrio/providers/dhl_freight/units.py`

- [ ] **Step 1: Write the enums**

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

    Seed with the codes present in the specs/product manual; confirm the full
    set against GET /products during the live check (Task 13, Step 5).
    """

    dhl_freight_euroconnect = "ECI"
    dhl_road_freight_standard = "ERT"
    dhl_road_freight_priority = "ERP"


class LabelLayout(lib.StrEnum):
    """Print API pageType values (raster format PDF/ZPL is not selectable)."""

    label = "Label"
    label_2x_portrait_a4 = "Label2xPortraitA4"
    label_3x_landscape_a4 = "Label3xLandscapeA4"
    label_compact = "LabelCompact"


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
    id_token = lib.OptionEnum("id_token", bool)  # send id_token (JWT) as Bearer; default True


class TrackingStatus(lib.Enum):
    """UTAPI statusCode mapping (kept for a future events phase; URL-only for now)."""

    delivered = ["delivered"]
    in_transit = ["transit", "pre-transit"]
    delivery_failed = ["failure"]
    unknown = ["unknown"]
```

- [ ] **Step 2: Verify import**

Run:
```bash
python -c "import karrio.providers.dhl_freight.units as u; print(u.ShippingService.map('ECI').name, u.ConnectionConfig.server_url)"
```
Expected: `dhl_freight_euroconnect <OptionEnum ...>`.

- [ ] **Step 3: Commit**

```bash
git add modules/connectors/dhl_freight/karrio/providers/dhl_freight/units.py
git commit -m "feat(dhl_freight): services, options, connection config, statuses"
```

---

## Task 6: `error.py` — booking + auth error shapes

**Files:**
- Modify: `modules/connectors/dhl_freight/karrio/providers/dhl_freight/error.py`

- [ ] **Step 1: Write the parser** (handles `validationErrors[]` and `{status,title,detail}`)

```python
import typing
import karrio.lib as lib
import karrio.core.models as models
import karrio.providers.dhl_freight.utils as provider_utils


def parse_error_response(
    response: dict,
    settings: provider_utils.Settings,
    **kwargs,
) -> typing.List[models.Message]:
    responses = response if isinstance(response, list) else [response]

    messages: typing.List[models.Message] = []
    for res in responses:
        # booking/print validation errors
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
        # auth / problem-detail style errors ({status,title,detail})
        if res.get("detail") or res.get("title"):
            if (res.get("status") in (None, "OK")) and not res.get("detail") and not res.get("title"):
                continue
            messages.append(
                models.Message(
                    carrier_id=settings.carrier_id,
                    carrier_name=settings.carrier_name,
                    code=str(res.get("status")) if res.get("status") is not None else None,
                    message=res.get("detail") or res.get("title") or "",
                    details=lib.to_dict({**kwargs, "title": res.get("title")}),
                )
            )

    return messages
```

- [ ] **Step 2: Verify import**

Run:
```bash
python -c "import karrio.providers.dhl_freight.error as e; print(e.parse_error_response)"
```
Expected: prints the function, no ImportError.

- [ ] **Step 3: Commit**

```bash
git add modules/connectors/dhl_freight/karrio/providers/dhl_freight/error.py
git commit -m "feat(dhl_freight): error parser for booking and auth error shapes"
```

---

## Task 7: mapper `settings.py`

**Files:**
- Modify: `modules/connectors/dhl_freight/karrio/mappers/dhl_freight/settings.py`

- [ ] **Step 1: Write the mapper Settings**

```python
"""Karrio DHL Freight client settings."""

import attr
import typing
import karrio.core.models as models
import karrio.providers.dhl_freight.utils as provider_utils


@attr.s(auto_attribs=True)
class Settings(provider_utils.Settings):
    """DHL Freight connection settings."""

    # carrier specific properties
    consumer_key: str = None
    consumer_secret: str = None
    account_number: str = None

    # generic properties
    id: str = None
    test_mode: bool = False
    carrier_id: str = "dhl_freight"
    account_country_code: str = None
    metadata: dict = {}
    config: dict = {}
```

- [ ] **Step 2: Verify import + gateway creation**

Run:
```bash
python -c "import karrio.mappers.dhl_freight.settings as s; print(s.Settings)"
```
Expected: prints the Settings class.

- [ ] **Step 3: Commit**

```bash
git add modules/connectors/dhl_freight/karrio/mappers/dhl_freight/settings.py
git commit -m "feat(dhl_freight): mapper settings"
```

---

## Task 8: `proxy.py` — token cache + book→print chain + URL-only tracking

**Files:**
- Modify: `modules/connectors/dhl_freight/karrio/mappers/dhl_freight/proxy.py`

- [ ] **Step 1: Write the proxy**

```python
"""Karrio DHL Freight client proxy."""

import base64
import datetime
import karrio.lib as lib
import karrio.api.proxy as proxy
import karrio.core.errors as errors
import karrio.providers.dhl_freight.error as provider_error
import karrio.mappers.dhl_freight.settings as provider_settings


class Proxy(proxy.Proxy):
    settings: provider_settings.Settings

    def authenticate(self) -> str:
        """Return a cached ~30-min Bearer token, refreshing via client-credentials Basic auth."""
        cache_key = f"{self.settings.carrier_name}|{self.settings.consumer_key}"
        want_jwt = self.settings.connection_config.id_token.state
        want_jwt = True if want_jwt is None else want_jwt
        response_type = "id_token" if want_jwt else "access_token"

        def get_token():
            basic = base64.b64encode(
                f"{self.settings.consumer_key}:{self.settings.consumer_secret}".encode()
            ).decode()
            response = lib.request(
                url=f"{self.settings.server_url}/auth/v1/token"
                f"?response_type={response_type}&grant_type=client_credentials",
                trace=self.trace_as("json"),
                method="POST",
                headers={"Authorization": f"Basic {basic}"},
                decoder=lib.to_dict,
                on_error=lib.error_decoder,
                max_retries=2,
            )
            messages = provider_error.parse_error_response(response, self.settings)
            if any(messages):
                raise errors.ParsedMessagesError(messages=messages)

            expiry = datetime.datetime.now() + datetime.timedelta(
                seconds=int(response.get("expires_in", 0))
            )
            return {**response, "expiry": lib.fdatetime(expiry)}

        token = self.settings.connection_cache.thread_safe(
            refresh_func=get_token,
            cache_key=cache_key,
            buffer_minutes=5,
        )
        state = token.get_state()
        return state.get("id_token") if want_jwt else state.get("access_token")

    def create_shipment(self, request: lib.Serializable) -> lib.Deserializable[dict]:
        access_token = self.authenticate()
        headers = {
            "content-type": "application/json",
            "Authorization": f"Bearer {access_token}",
        }
        ctx = request.ctx or {}

        # 1) book
        booking = lib.request(
            url=f"{self.settings.server_url}/freight/shipping/orders/v1/sendtransportinstruction",
            data=lib.to_json(request.serialize()),
            trace=self.trace_as("json"),
            method="POST",
            headers=headers,
            decoder=lib.to_dict,
            on_error=lib.error_decoder,
        )
        shipment_id = ((booking or {}).get("shipment") or {}).get("id")

        # 2) print-by-id (only if booking produced an id)
        printed = None
        if shipment_id:
            print_body = {
                "shipmentIds": [shipment_id],
                "options": ctx.get("print_options") or {"label": True, "pageOptions": {"pageType": "Label"}},
            }
            printed = lib.request(
                url=f"{self.settings.server_url}/freight/shipping/labels/v1/print/printdocumentsbyid",
                data=lib.to_json(print_body),
                trace=self.trace_as("json"),
                method="POST",
                headers=headers,
                decoder=lib.to_dict,
                on_error=lib.error_decoder,
            )

        return lib.Deserializable({"booking": booking, "print": printed}, lib.to_dict)

    def get_tracking(self, request: lib.Serializable) -> lib.Deserializable[dict]:
        # URL-only: no HTTP call; echo the tracking numbers for the provider to format.
        return lib.Deserializable(
            {"tracking_numbers": request.serialize()}, lib.to_dict
        )
```

- [ ] **Step 2: Verify import**

Run:
```bash
python -c "import karrio.mappers.dhl_freight.proxy as p; print(p.Proxy.create_shipment, p.Proxy.get_tracking)"
```
Expected: prints both methods; no `get_rates`/`cancel_shipment` defined (keeps capabilities = shipping + tracking).

- [ ] **Step 3: Commit**

```bash
git add modules/connectors/dhl_freight/karrio/mappers/dhl_freight/proxy.py
git commit -m "feat(dhl_freight): proxy token cache, book+print chain, url-only tracking"
```

---

## Task 9: `shipment/create.py` — request build + response parse

**Files:**
- Modify: `modules/connectors/dhl_freight/karrio/providers/dhl_freight/shipment/create.py`

> Use the exact generated class names printed in Task 3 Step 3. Below assumes `booking_request.Shipment/Party/Piece/PayerCode/Address` and `print_response.PrintResult`; adjust names if generation emitted different ones.

- [ ] **Step 1: Write the provider**

```python
"""Karrio DHL Freight shipment create implementation."""

import typing
import karrio.lib as lib
import karrio.core.units as units
import karrio.core.models as models
import karrio.providers.dhl_freight.error as error
import karrio.providers.dhl_freight.utils as provider_utils
import karrio.providers.dhl_freight.units as provider_units


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

    shipment = booking.get("shipment") or {}
    shipment_id = shipment.get("id")
    details = (
        _extract_details(response, settings) if shipment_id and not any(messages) else None
    )
    return details, messages


def _extract_details(
    response: dict,
    settings: provider_utils.Settings,
) -> models.ShipmentDetails:
    shipment_id = ((response.get("booking") or {}).get("shipment") or {}).get("id")
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
        label_type="PDF",
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
        goodsDescription=lib.text(packages.description, max=70),
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

Run:
```bash
python -c "import karrio.providers.dhl_freight.shipment.create as c; print(c.shipment_request, c.parse_shipment_response)"
```
Expected: prints both functions.

- [ ] **Step 3: Commit**

```bash
git add modules/connectors/dhl_freight/karrio/providers/dhl_freight/shipment/create.py
git commit -m "feat(dhl_freight): shipment create request build and response parse"
```

---

## Task 10: `tracking.py` — URL-only

**Files:**
- Modify: `modules/connectors/dhl_freight/karrio/providers/dhl_freight/tracking.py`

- [ ] **Step 1: Write the provider**

```python
"""Karrio DHL Freight tracking (URL-only)."""

import typing
import karrio.lib as lib
import karrio.core.models as models
import karrio.providers.dhl_freight.utils as provider_utils


def parse_tracking_response(
    _response: lib.Deserializable[dict],
    settings: provider_utils.Settings,
) -> typing.Tuple[typing.List[models.TrackingDetails], typing.List[models.Message]]:
    numbers = (_response.deserialize() or {}).get("tracking_numbers") or []
    details = [_extract_details(str(number), settings) for number in numbers]
    return details, []


def _extract_details(number: str, settings: provider_utils.Settings) -> models.TrackingDetails:
    return models.TrackingDetails(
        carrier_id=settings.carrier_id,
        carrier_name=settings.carrier_name,
        tracking_number=number,
        events=[],
        delivered=False,
        info=models.TrackingInfo(
            carrier_tracking_link=settings.tracking_url.format(number),
        ),
    )


def tracking_request(
    payload: models.TrackingRequest,
    settings: provider_utils.Settings,
) -> lib.Serializable:
    return lib.Serializable(payload.tracking_numbers, lib.to_dict)
```

- [ ] **Step 2: Verify import**

Run:
```bash
python -c "import karrio.providers.dhl_freight.tracking as t; print(t.tracking_request, t.parse_tracking_response)"
```

- [ ] **Step 3: Commit**

```bash
git add modules/connectors/dhl_freight/karrio/providers/dhl_freight/tracking.py
git commit -m "feat(dhl_freight): url-only tracking provider"
```

---

## Task 11: Public exports + plugin METADATA

**Files:**
- Modify: `modules/connectors/dhl_freight/karrio/providers/dhl_freight/__init__.py`
- Modify: `modules/connectors/dhl_freight/karrio/providers/dhl_freight/shipment/__init__.py`
- Modify: `modules/connectors/dhl_freight/karrio/plugins/dhl_freight/__init__.py`

- [ ] **Step 1: providers `__init__.py`** — export only what exists (no rate)

```python
"""Karrio DHL Freight provider."""

from karrio.providers.dhl_freight.utils import Settings
from karrio.providers.dhl_freight.shipment import (
    parse_shipment_response,
    shipment_request,
)
from karrio.providers.dhl_freight.tracking import (
    parse_tracking_response,
    tracking_request,
)
```

- [ ] **Step 2: shipment `__init__.py`** — export create only (no cancel)

```python
from karrio.providers.dhl_freight.shipment.create import (
    parse_shipment_response,
    shipment_request,
)
```

- [ ] **Step 3: plugin `__init__.py`** — METADATA (no service_levels needed; keep minimal)

```python
from karrio.core.metadata import PluginMetadata

from karrio.mappers.dhl_freight.mapper import Mapper
from karrio.mappers.dhl_freight.proxy import Proxy
from karrio.mappers.dhl_freight.settings import Settings
import karrio.providers.dhl_freight.units as units


METADATA = PluginMetadata(
    status="in-development",
    id="dhl_freight",
    label="DHL Freight",
    description="DHL Freight palletized road-freight booking and label integration",
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
    website="https://www.dhl.com/freight",
    documentation="https://developer.dhl.com/api-reference/dhl-freight-shipment-booking",
)
```

- [ ] **Step 4: Confirm mapper.py wires create + tracking (do NOT edit — it is generated)**

Run:
```bash
python -c "import karrio.mappers.dhl_freight.mapper as m; print([x for x in dir(m.Mapper) if not x.startswith('_')])"
```
Expected: includes `create_shipment_request`, `parse_shipment_response`, `create_tracking_request`, `parse_tracking_response`. If `mapper.py` still references rate/cancel (from scaffolding), re-run `./bin/run-generate-on` or align it with the mydhl mapper (it is generated to match the provider functions present).

- [ ] **Step 5: Verify plugin loads with correct capabilities**

Run:
```bash
python -c "import karrio.sdk as karrio; print(karrio.gateway['dhl_freight'].capabilities)"
```
Expected: `['shipping', 'tracking']` (no `rating`).

- [ ] **Step 6: Commit**

```bash
git add modules/connectors/dhl_freight/karrio
git commit -m "feat(dhl_freight): public exports and plugin metadata"
```

---

## Task 12: Shipment tests (4-method, mocks book + print)

**Files:**
- Modify: `modules/connectors/dhl_freight/tests/dhl_freight/fixture.py`
- Create: `modules/connectors/dhl_freight/tests/dhl_freight/test_shipment.py`

- [ ] **Step 1: fixture.py**

```python
"""DHL Freight carrier tests fixtures."""

import karrio.sdk as karrio


gateway = karrio.gateway["dhl_freight"].create(
    dict(
        id="123456789",
        test_mode=True,
        carrier_id="dhl_freight",
        consumer_key="TEST_KEY",
        consumer_secret="TEST_SECRET",
        account_number="ACCT1",
    )
)
```

- [ ] **Step 2: Write the failing shipment test** (mocks `authenticate` + both HTTP calls)

`test_shipment.py`:
```python
"""DHL Freight shipment tests."""

import unittest
from unittest.mock import patch, ANY
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
        with patch("karrio.mappers.dhl_freight.proxy.Proxy.authenticate") as auth, \
             patch("karrio.mappers.dhl_freight.proxy.lib.request") as mock:
            auth.return_value = "TOKEN"
            mock.side_effect = [BookingResponse, PrintResponse]
            karrio.Shipment.create(self.ShipmentRequest).from_(gateway)
            self.assertEqual(
                mock.call_args_list[0][1]["url"],
                f"{gateway.settings.server_url}/freight/shipping/orders/v1/sendtransportinstruction",
            )
            self.assertEqual(
                mock.call_args_list[1][1]["url"],
                f"{gateway.settings.server_url}/freight/shipping/labels/v1/print/printdocumentsbyid",
            )

    def test_parse_shipment_response(self):
        with patch("karrio.mappers.dhl_freight.proxy.Proxy.authenticate") as auth, \
             patch("karrio.mappers.dhl_freight.proxy.lib.request") as mock:
            auth.return_value = "TOKEN"
            mock.side_effect = [BookingResponse, PrintResponse]
            parsed = karrio.Shipment.create(self.ShipmentRequest).from_(gateway).parse()
            self.assertListEqual(lib.to_dict(parsed), ParsedShipmentResponse)

    def test_parse_error_response(self):
        with patch("karrio.mappers.dhl_freight.proxy.Proxy.authenticate") as auth, \
             patch("karrio.mappers.dhl_freight.proxy.lib.request") as mock:
            auth.return_value = "TOKEN"
            mock.side_effect = [ErrorResponse]
            parsed = karrio.Shipment.create(self.ShipmentRequest).from_(gateway).parse()
            self.assertListEqual(lib.to_dict(parsed), ParsedErrorResponse)


if __name__ == "__main__":
    unittest.main()


ShipmentPayload = {
    "service": "dhl_freight_euroconnect",
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
    "productCode": "ECI",
    "totalNumberOfPieces": 1,
    "totalWeight": 380.0,
    "goodsDescription": "Machinery Parts",
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

BookingResponse = {"status": "OK", "shipment": {"id": "1234567890123"}}
PrintResponse = {"reports": [{"name": "label", "content": "SkVUTEFCRUw=", "type": "PDF", "valid": True}]}
ErrorResponse = {"status": "ERROR", "validationErrors": [
    {"field": "productCode", "errorCode": 100, "message": "invalid product", "incompatibleFields": []}]}

ParsedShipmentResponse = [
    {
        "carrier_id": "dhl_freight",
        "carrier_name": "dhl_freight",
        "tracking_number": "1234567890123",
        "shipment_identifier": "1234567890123",
        "label_type": "PDF",
        "docs": {"label": "SkVUTEFCRUw="},
        "meta": {"tracking_url": "https://www.dhl.com/global-en/home/tracking/tracking-freight.html?submit=1&tracking-id=1234567890123"},
    },
    [],
]

ParsedErrorResponse = [
    None,
    [
        {
            "carrier_id": "dhl_freight",
            "carrier_name": "dhl_freight",
            "code": "100",
            "message": "invalid product",
            "details": {"field": "productCode", "incompatibleFields": []},
        }
    ],
]
```

- [ ] **Step 3: Run to verify it fails first (before providers were correct), then passes**

Run:
```bash
python -m unittest -v modules.connectors.dhl_freight.tests.dhl_freight.test_shipment
```
Expected: PASS on all four. If a field differs, add `print(lib.to_dict(parsed))` above the assert, align the expected constant to the real output (recall `lib.to_dict` strips `None`/empty), then remove the print.

- [ ] **Step 4: Commit**

```bash
git add modules/connectors/dhl_freight/tests/dhl_freight/fixture.py modules/connectors/dhl_freight/tests/dhl_freight/test_shipment.py
git commit -m "test(dhl_freight): shipment create request, call, parse, error"
```

---

## Task 13: Tracking test + run suites

**Files:**
- Create: `modules/connectors/dhl_freight/tests/dhl_freight/test_tracking.py`

- [ ] **Step 1: Write the tracking test** (URL-only; no HTTP mock needed)

```python
"""DHL Freight tracking tests (URL-only)."""

import unittest
from .fixture import gateway

import karrio.sdk as karrio
import karrio.lib as lib
import karrio.core.models as models


class TestDHLFreightTracking(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None
        self.TrackingRequest = models.TrackingRequest(tracking_numbers=["1234567890123"])

    def test_parse_tracking_response(self):
        parsed = karrio.Tracking.fetch(self.TrackingRequest).from_(gateway).parse()
        self.assertListEqual(lib.to_dict(parsed), ParsedTrackingResponse)

    def test_tracking_url_construction(self):
        request = gateway.mapper.create_tracking_request(self.TrackingRequest)
        self.assertEqual(lib.to_dict(request.serialize()), ["1234567890123"])


if __name__ == "__main__":
    unittest.main()


ParsedTrackingResponse = [
    [
        {
            "carrier_id": "dhl_freight",
            "carrier_name": "dhl_freight",
            "tracking_number": "1234567890123",
            "delivered": False,
            "info": {
                "carrier_tracking_link": "https://www.dhl.com/global-en/home/tracking/tracking-freight.html?submit=1&tracking-id=1234567890123"
            },
        }
    ],
    [],
]
```

- [ ] **Step 2: Run the carrier suite**

Run:
```bash
python -m unittest discover -v -f modules/connectors/dhl_freight/tests
```
Expected: all shipment + tracking tests PASS. Adjust expected constants to real `lib.to_dict` output if needed (empty `events`/`None` fields are stripped).

- [ ] **Step 3: Run the full SDK suite (hermetic, offline)**

Run:
```bash
./bin/run-sdk-tests
```
Expected: green; `test_live_smoke.py` (Task 14) skips.

- [ ] **Step 4: Commit**

```bash
git add modules/connectors/dhl_freight/tests/dhl_freight/test_tracking.py
git commit -m "test(dhl_freight): url-only tracking"
```

- [ ] **Step 5 (deferred to live check): confirm productCodes + Bearer token key**

During Task 14, capture the real auth response and a booking response. Confirm: (a) whether Booking/Print accept `id_token` or `access_token` as Bearer (flip `ConnectionConfig.id_token` default if needed); (b) the full `productCode` set (extend `ShippingService`); (c) that `PrintReport.content` is base64. Update units/tests accordingly.

---

## Task 14: Opt-in live smoke test (net-new, env-gated)

**Files:**
- Create: `modules/connectors/dhl_freight/tests/dhl_freight/test_live_smoke.py`

- [ ] **Step 1: Write the gated smoke test**

```python
"""DHL Freight live smoke test — opt-in, hits test-api. Skipped by default.

Enable with:
  DHL_FREIGHT_LIVE_TEST=1 DHL_FREIGHT_CONSUMER_KEY=... DHL_FREIGHT_CONSUMER_SECRET=... \
  DHL_FREIGHT_ACCOUNT_NUMBER=... [DHL_FREIGHT_SERVER_URL=https://test-api.freight-logistics.dhl.com] \
  python -m unittest modules.connectors.dhl_freight.tests.dhl_freight.test_live_smoke
"""

import os
import unittest
import karrio.sdk as karrio
import karrio.lib as lib
import karrio.core.models as models

LIVE = bool(os.getenv("DHL_FREIGHT_CONSUMER_KEY") and os.getenv("DHL_FREIGHT_LIVE_TEST"))


@unittest.skipUnless(LIVE, "set DHL_FREIGHT_LIVE_TEST=1 + DHL_FREIGHT_CONSUMER_KEY/SECRET to run")
class TestDHLFreightLiveSmoke(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None
        config = {}
        if os.getenv("DHL_FREIGHT_SERVER_URL"):
            config["server_url"] = os.environ["DHL_FREIGHT_SERVER_URL"]
        self.gateway = karrio.gateway["dhl_freight"].create(
            dict(
                test_mode=True,
                carrier_id="dhl_freight",
                consumer_key=os.environ["DHL_FREIGHT_CONSUMER_KEY"],
                consumer_secret=os.environ["DHL_FREIGHT_CONSUMER_SECRET"],
                account_number=os.getenv("DHL_FREIGHT_ACCOUNT_NUMBER"),
                config=config,
            )
        )

    def test_auth_book_print(self):
        request = models.ShipmentRequest(**LiveShipmentPayload)
        details, messages = (
            karrio.Shipment.create(request).from_(self.gateway).parse()
        )
        print("messages:", lib.to_dict(messages))
        print("details:", lib.to_dict(details))
        self.assertFalse(messages, "expected no error messages from test-api")
        self.assertIsNotNone(details, "expected a booking + label")
        self.assertTrue(details.tracking_number)
        self.assertTrue(details.docs.label)


LiveShipmentPayload = {
    "service": "dhl_freight_euroconnect",
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
```

- [ ] **Step 2: Verify it SKIPS with no env**

Run:
```bash
python -m unittest -v modules.connectors.dhl_freight.tests.dhl_freight.test_live_smoke
```
Expected: `skipped` (not failed).

- [ ] **Step 3: Run it live (with real test-api creds) and capture responses**

Run (user supplies creds):
```bash
DHL_FREIGHT_LIVE_TEST=1 DHL_FREIGHT_CONSUMER_KEY=... DHL_FREIGHT_CONSUMER_SECRET=... \
DHL_FREIGHT_ACCOUNT_NUMBER=... \
python -m unittest modules.connectors.dhl_freight.tests.dhl_freight.test_live_smoke
```
Expected: PASS with a tracking number + non-empty label. If auth fails, retry with `DHL_FREIGHT_SERVER_URL=https://test-api.freight-logistics.dhl.com` and/or flip the `id_token` config. Feed the captured real payloads back into the hermetic fixtures (Task 12/13) and resolve Task 13 Step 5 items.

- [ ] **Step 4: Commit**

```bash
git add modules/connectors/dhl_freight/tests/dhl_freight/test_live_smoke.py
git commit -m "test(dhl_freight): opt-in env-gated live smoke test"
```

---

## Task 15: Final validation

- [ ] **Step 1: Full verification sweep**

Run:
```bash
python -m unittest discover -v -f modules/connectors/dhl_freight/tests
./bin/run-sdk-tests
./bin/cli plugins show dhl_freight
python -c "import karrio.sdk as k; print(k.gateway['dhl_freight'].capabilities)"
```
Expected: carrier + SDK suites green; plugin shows `dhl_freight`; capabilities `['shipping', 'tracking']`.

- [ ] **Step 2: Mark PRD launch criteria + update statuses**

Tick the PRD's Launch Criteria that now hold; update Implementation Plan phase statuses from `Pending`. Resolve the three parked Pending Questions with the live-check findings (or leave documented if test-api access is deferred).

- [ ] **Step 3: Final commit**

```bash
git add -A modules/connectors/dhl_freight PRDs/PRD_DHL_FREIGHT_INTEGRATION.md
git commit -m "chore(dhl_freight): finalize connector; resolve live-check items"
```

---

## Self-Review (completed by author)

- **Spec coverage:** book→print (Task 8/9), auth token cache (Task 8), URL-only tracking (Task 10/13), pageType layout option (Task 5/9), server_url override (Task 4/5/11), no rating/cancel (Task 1 Step 4 + Task 11), consumer_key/secret creds (Task 4/7), 30-min token cache buffer (Task 8), live smoke test (Task 14), vendoring (Task 2) — all mapped.
- **Placeholder scan:** service enum is seeded with concrete codes + a named live-check action (Task 13 Step 5), not a vague TODO. Generated class names are confirmed empirically in Task 3 Step 3 before use in Task 9.
- **Type consistency:** `consumer_key`/`consumer_secret`/`account_number` consistent across utils/settings/fixture/smoke test; `server_url` resolution identical in utils and used verbatim in test URL assertions; `tracking_url` template identical in utils, provider, and expected test constants; `ConnectionConfig.server_url`/`id_token` referenced consistently in units, utils, proxy, plugin.
- **Known adaptation point:** Task 9 uses `dict` request bodies (not generated dataclasses) for robustness against exact generated field names; if the team prefers `lib.to_object`-typed construction, the generated class names from Task 3 Step 3 substitute directly. Flagged in-task.
