"""Live verification of the PostNord customs-declaration change (task 5.2).

Run from the repository root with the repo environment active:

    source bin/activate-env
    POSTNORD_APIKEY=... POSTNORD_CUSTOMER_NUMBER=... \
        python openspec/changes/postnord-customs-declaration/verify_live.py

Environment:
    POSTNORD_APIKEY            required; sandbox apikey (atapi2 host is used)
    POSTNORD_CUSTOMER_NUMBER   optional; real party id for the booking parties
    POSTNORD_ISSUER_CODE       optional; defaults to Z12 (Sweden)
    POSTNORD_PROBE_SERVER_LIMIT  set to 1 to additionally POST a hand-built
                                 14-line declaration directly, bypassing the
                                 connector guard, to observe PostNord's own
                                 server-side limit behavior

Scenarios:
    A  book UX (postnord_export_letter) with customs, PDF label — expects a
       standalone customs document in docs.extra_documents and cn22 in
       meta.printout_composition
    B  same booking with a ZPL label — expects the by-id ZPL customs printout
    C  14-line customs payload — expects the local field error and no booking
    D  optional server-limit probe (see env above)

Each scenario prints a FINDINGS block; paste the full output back into the
session so results can be recorded under docs/notes/.
"""

import base64
import json
import os
import sys

import karrio.sdk as karrio
import karrio.lib as lib

RECIPIENT = {
    "address_line1": "350 Fifth Avenue",
    "city": "New York",
    "postal_code": "10118",
    "country_code": "US",
    "state_code": "NY",
    "person_name": "Jane Receiver",
    "company_name": "Receiver Co",
    "phone_number": "+12125550123",
    "email": "receiver@example.com",
}

SHIPPER = {
    "address_line1": "Sandhamnsgatan 61",
    "city": "Stockholm",
    "postal_code": "11528",
    "country_code": "SE",
    "state_code": "Stockholm",
    "person_name": "John Sender",
    "company_name": "ACME Sender AB",
    "phone_number": "+46701234567",
    "email": "sender@example.com",
}

COMMODITY = {
    "title": "Wool socks",
    "quantity": 2,
    "weight": 0.4,
    "weight_unit": "KG",
    "value_amount": 2.5,
    "value_currency": "USD",
    "hs_code": "6115950000",
    "origin_country": "SE",
}


def _commodities(count):
    return [dict(COMMODITY, title=f"Wool socks batch {n}") for n in range(count)]


def _payload(label_type=None, commodities=None):
    payload = {
        "shipper": SHIPPER,
        "recipient": RECIPIENT,
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
        "service": "postnord_export_letter",
        "reference": f"CUSTOMS-VERIFY-{os.getpid()}",
        "customs": {
            "content_type": "merchandise",
            "commodities": commodities or _commodities(2),
        },
        "options": {"currency": "USD"},
    }
    if label_type:
        payload["label_type"] = label_type
    return payload


def _gateway():
    settings = dict(
        apikey=os.environ["POSTNORD_APIKEY"],
        issuer_code=os.environ.get("POSTNORD_ISSUER_CODE", "Z12"),
        test_mode=True,
        services=[
            dict(
                service_name="PostNord Export Letter",
                service_code="postnord_export_letter",
                carrier_service_code="UX",
                currency="USD",
                transit_days=5,
                domicile=False,
                international=True,
                zones=[dict(label="International", rate=79.0)],
            )
        ],
    )
    if os.environ.get("POSTNORD_CUSTOMER_NUMBER"):
        settings["customer_number"] = os.environ["POSTNORD_CUSTOMER_NUMBER"]
    return karrio.gateway["postnord"].create(settings)


def _decoded_prefix(document):
    raw = base64.b64decode(document.base64 or "")
    return raw[:8]


def _book(gateway, label_type=None, commodities=None):
    request = karrio.Shipment.create(_payload(label_type, commodities))
    return request.from_(gateway).parse()


def scenario_0(gateway):
    """Auth probe: a light GET that only needs the apikey.

    Discriminates a key/environment problem (probe also fails) from a booking
    entitlement problem (probe passes, booking 403s).
    """
    print("\n=== Scenario 0: apikey probe (service points byaddress) ===")
    settings = gateway.settings
    response = lib.request(
        url=(
            f"{settings.server_url}/rest/businesslocation/v5/servicepoints"
            f"/nearest/byaddress?apikey={settings.apikey}"
            "&returnType=json&countryCode=SE&postalCode=11528"
        ),
        method="GET",
    )
    body = str(response)
    print(f"[probe] {body[:300]}")
    ok = "Forbidden" not in body and "Missing API Key" not in body
    print(f"[check] {'PASS' if ok else 'FAIL'}: apikey accepted by host ({'accepted' if ok else 'rejected — key/environment problem, not the customs change'})")
    return ok


def scenario_a(gateway):
    print("\n=== Scenario A: UX booking with customs, PDF label ===")
    shipment, messages = _book(gateway)
    for message in messages:
        print(f"[message] {message.code}: {message.message} details={getattr(message, 'details', None)}")

    checks = []
    if shipment is None:
        checks.append(("shipment created", False, "shipment is None"))
        _report(checks)
        return None

    print(f"[booking] tracking_number={shipment.tracking_number}")
    print(f"[booking] meta.printout_composition={shipment.meta.get('printout_composition')}")
    documents = shipment.docs.extra_documents or []
    for doc in documents:
        prefix = _decoded_prefix(doc)
        print(f"[document] category={doc.category} format={doc.format} magic={prefix!r}")

    checks.append(("shipment created", shipment.tracking_number is not None, shipment.tracking_number))
    composition = shipment.meta.get("printout_composition") or []
    checks.append(("cn22 in printout_composition", "cn22" in composition, composition))
    checks.append(("extra_documents present", len(documents) >= 1, len(documents)))
    if documents:
        doc = documents[0]
        checks.append(("document format PDF", doc.format == "PDF", doc.format))
        checks.append(
            ("document is PDF magic", _decoded_prefix(doc).startswith(b"%PDF-"), _decoded_prefix(doc))
        )
        checks.append(("category names cn22 or fallback", "cn22" in doc.category or "customs" in doc.category, doc.category))
    _report(checks)
    return shipment


def scenario_b(gateway):
    print("\n=== Scenario B: UX booking with customs, ZPL label ===")
    shipment, messages = _book(gateway, label_type="ZPL")
    for message in messages:
        print(f"[message] {message.code}: {message.message}")

    checks = []
    if shipment is None:
        checks.append(("shipment created", False, "shipment is None"))
        _report(checks)
        return

    documents = shipment.docs.extra_documents or []
    for doc in documents:
        prefix = _decoded_prefix(doc)
        print(f"[document] category={doc.category} format={doc.format} magic={prefix!r}")

    checks.append(("shipment created", shipment.tracking_number is not None, shipment.tracking_number))
    checks.append(("extra_documents present", len(documents) >= 1, len(documents)))
    if documents:
        doc = documents[0]
        prefix = _decoded_prefix(doc)
        checks.append(("document format ZPL", doc.format == "ZPL", doc.format))
        checks.append(
            ("document is ZPL magic", prefix.startswith(b"^XA") or not prefix.startswith(b"%PDF-"), prefix)
        )
    _report(checks)


def scenario_c(gateway):
    print("\n=== Scenario C: 14-line customs payload (local guard) ===")
    shipment, messages = _book(gateway, commodities=_commodities(14))
    for message in messages:
        print(f"[message] {message.code}: {message.message} details={getattr(message, 'details', None)}")

    guard_fired = any(
        message.code == "SHIPPING_SDK_FIELD_ERROR"
        and "13-line" in str(getattr(message, "details", None))
        for message in messages
    )
    checks = [
        ("shipment rejected", shipment is None, shipment is not None),
        ("field error names the limit", guard_fired, [m.message for m in messages]),
    ]
    _report(checks)


def scenario_d(gateway, item_id):
    print("\n=== Scenario D: server-side 14-line limit probe (opt-in) ===")
    if not item_id:
        print("[skipped] no item id from scenario A")
        return

    lines = [
        {
            "content": f"Probe line {n}",
            "quantity": {"value": 1},
            "grossWeight": {"value": 0.1, "unit": "KGM"},
            "value": {"amount": 0.1, "currency": "USD"},
            "countryCode": "SE",
            "rowNo": n + 1,
        }
        for n in range(14)
    ]
    body = json.dumps(
        [
            {
                "ids": [{"id": item_id, "idType": "itemId"}],
                "customsDeclarationCN22": {
                    "countryOfOrigin": "SE",
                    "categoryOfItem": {"categoryType": ["merchandise"]},
                    "detailedDescription": lines,
                    "totalValue": {"amount": 1.4, "currency": "USD"},
                },
            }
        ]
    )
    settings = gateway.settings
    response = lib.request(
        url=f"{settings.server_url}/rest/shipment/v3/customs/declaration"
        f"?apikey={settings.apikey}",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    print(f"[probe] response: {str(response)[:600]}")


def _report(checks):
    for name, passed, detail in checks:
        mark = "PASS" if passed else "FAIL"
        print(f"[check] {mark}: {name} ({detail!r})")


def main():
    if "POSTNORD_APIKEY" not in os.environ:
        print("POSTNORD_APIKEY is required (sandbox apikey; atapi2 host is used)")
        return 2

    gateway = _gateway()
    scenario_0(gateway)
    shipment = scenario_a(gateway)
    scenario_b(gateway)
    scenario_c(gateway)
    if os.environ.get("POSTNORD_PROBE_SERVER_LIMIT") == "1":
        item_id = shipment.tracking_number if shipment else None
        scenario_d(gateway, item_id)

    print("\nDone. Paste this output back into the session for recording under docs/notes/.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
