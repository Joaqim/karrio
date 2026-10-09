"""Sandbox gate for the nordic-customs-invoice-mapping change (tasks 1.2, 1.3).

Books ``postnord_parcel`` (basic service code 18) SE -> NO in the PostNord
TEST environment (``atapi2.postnord.com``, ``testIndicator=true``) with a
hand-built ``customsInvoice`` on the shipment, because the connector does not
build one yet.
The connector serializes the booking without customs; the script injects the
``customsInvoice`` into ``shipment[0]`` and POSTs the body itself so the HTTP
status is observable.

Run from the repository root with the repo environment active:

    source bin/activate-env
    python openspec/changes/nordic-customs-invoice-mapping/verify_live.py

Environment (read by name only; values are never printed):
    POSTNORD_APIKEY            required; sandbox apikey
    POSTNORD_CUSTOMER_NUMBER   required; seller partyIdentification (type 160)
                                 and booking consignor id
    POSTNORD_EORI              required for variant A; seller eoriNo
    POSTNORD_ISSUER_CODE       optional; defaults to Z12 (Sweden)

Variants:
    A  customsInvoice with the EORI on the seller
    B  customsInvoice with no registration number (no eoriNo, voec, ioss)
"""

import base64
import io
import json
import os
import sys
import urllib.error
import urllib.request

import pypdf

import karrio.core.models as models
import karrio.lib as lib
import karrio.sdk as karrio

SANDBOX_URL = "https://atapi2.postnord.com"
BOOKING_PATH = "/rest/shipment/v3/edi/labels/pdf"

SHIPPER = {
    "address_line1": "Sandhamnsgatan 61",
    "city": "Stockholm",
    "postal_code": "11528",
    "country_code": "SE",
    "person_name": "John Sender",
    "company_name": "ACME Sender AB",
    "phone_number": "+46701234567",
    "email": "sender@example.com",
}

RECIPIENT = {
    "address_line1": "Karl Johans gate 1",
    "city": "Oslo",
    "postal_code": "0154",
    "country_code": "NO",
    "person_name": "Kari Receiver",
    "company_name": "Receiver AS",
    "phone_number": "+4791234567",
    "email": "receiver@example.com",
}

SELLER_VAT_NO = "SE556123471101"

COMMODITIES = [
    {
        "content": "Wool socks",
        "quantity": 2,
        "hs": "6115950000",
        "origin": "SE",
        "unit_value": 150.0,
        "unit_weight": 0.2,
    },
    {
        "content": "Knitted cap",
        "quantity": 1,
        "hs": "6505003000",
        "origin": "SE",
        "unit_value": 200.0,
        "unit_weight": 0.1,
    },
]
CURRENCY = "SEK"
INVOICE_KEYWORDS = ("INVOICE", "COMMERCIAL", "FAKTURA", "CN23", "CN22")


def _secret_values():
    return [
        os.environ[name]
        for name in ("POSTNORD_APIKEY", "POSTNORD_EORI", "POSTNORD_LIVE_APIKEY")
        if os.environ.get(name)
    ]


def _redact(text):
    for value in _secret_values():
        text = text.replace(value, "<redacted>")
    return text


def _gateway():
    return karrio.gateway["postnord"].create(
        dict(
            apikey=os.environ["POSTNORD_APIKEY"],
            customer_number=os.environ["POSTNORD_CUSTOMER_NUMBER"],
            issuer_code=os.environ.get("POSTNORD_ISSUER_CODE", "Z12"),
            test_mode=True,
        )
    )


def _base_body(gateway, variant):
    payload = {
        "shipper": SHIPPER,
        "recipient": RECIPIENT,
        "parcels": [
            {
                "weight": 1.0,
                "width": 20.0,
                "height": 10.0,
                "length": 30.0,
                "weight_unit": "KG",
                "dimension_unit": "CM",
            }
        ],
        "service": "postnord_parcel",
        "reference": f"CI-VERIFY-{variant}-{os.getpid()}",
    }
    request = gateway.mapper.create_shipment_request(
        lib.to_object(models.ShipmentRequest, payload)
    )
    return request.serialize()


def _party(address, extra):
    return {
        **extra,
        "name": address["company_name"],
        "streets": [address["address_line1"]],
        "city": address["city"],
        "postalCode": address["postal_code"],
        "countryCode": address["country_code"],
        "contacts": {
            "name": address["person_name"],
            "phoneNo": address["phone_number"],
            "emailAddress": address["email"],
        },
    }


def _customs_invoice(invoice_no, with_eori):
    lines = [
        {
            "quantity": line["quantity"],
            "hsTariffNumber": line["hs"],
            "content": line["content"],
            "countryOfOrigin": line["origin"],
            "netWeight": {
                "value": round(line["unit_weight"] * line["quantity"], 3),
                "unit": "KGM",
            },
            "grossWeight": {
                "value": round(line["unit_weight"] * line["quantity"], 3),
                "unit": "KGM",
            },
            "itemValue": {
                "amount": round(line["unit_value"] * line["quantity"], 2),
                "currency": CURRENCY,
            },
        }
        for line in COMMODITIES
    ]
    seller_extra = {
        "partyIdentification": {
            "partyId": os.environ["POSTNORD_CUSTOMER_NUMBER"],
            "partyIdType": "160",
        },
        "vatNo": SELLER_VAT_NO,
    }
    if with_eori:
        seller_extra["eoriNo"] = os.environ["POSTNORD_EORI"]
    return {
        "type": "COMMERCIAL",
        "declarationType": "invoiceExportDeclaration",
        "seller": _party(SHIPPER, seller_extra),
        "buyer": _party(RECIPIENT, {}),
        "invoice": {
            "invoiceNo": invoice_no,
            "shippingDate": "2026-09-25",
            "reasonForExportation": "1000",
        },
        "detailedDescription": lines,
        "invoiceTotal": {
            "amount": round(sum(l["itemValue"]["amount"] for l in lines), 2),
            "currency": CURRENCY,
        },
        "totalGrossWeight": {
            "value": round(sum(l["grossWeight"]["value"] for l in lines), 3),
            "unit": "KGM",
        },
    }


def _post(body):
    url = f"{SANDBOX_URL}{BOOKING_PATH}?apikey={os.environ['POSTNORD_APIKEY']}"
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status, response.read().decode()
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode()
    except urllib.error.URLError as error:
        return None, f"transport error: {type(error.reason).__name__}"


def _describe_printout(printout):
    data = printout.get("data") or ""
    raw = base64.b64decode(data) if data else b""
    summary = (
        f"format={printout.get('labelFormat')} base64_chars={len(data)} "
        f"magic={raw[:5]!r}"
    )
    if not raw.startswith(b"%PDF-"):
        return summary
    pages = pypdf.PdfReader(io.BytesIO(raw)).pages
    texts = [page.extract_text() or "" for page in pages]
    keywords = {
        word: [n + 1 for n, text in enumerate(texts) if word in text.upper()]
        for word in INVOICE_KEYWORDS
    }
    return f"{summary} pdf_pages={len(pages)} keyword_pages={keywords}"


def _summarize(status, text):
    print(f"[http] status={status}")
    try:
        data = json.loads(text)
    except ValueError:
        print(f"[body] {_redact(text)[:1500]}")
        return
    faults = (data.get("compositeFault") or {}).get("faults") or []
    for fault in faults:
        print(f"[fault] {fault.get('faultCode')}: {fault.get('explanationText')}")
    if data.get("message"):
        print(f"[message] {data.get('message')}")
    booking = data.get("bookingResponse") or {}
    if booking:
        print(f"[booking] {_redact(json.dumps(booking))[:1500]}")
    printouts = data.get("labelPrintout") or []
    for printout in printouts:
        print(f"[printout] printoutComposition={printout.get('printoutComposition')}")
        print(f"[printout] {_describe_printout(printout.get('printout') or {})}")
    if data and not booking and not printouts and not faults:
        print(f"[body] {_redact(text)[:1500]}")
    verdict = "ACCEPTED" if status == 200 and not faults else "REJECTED"
    print(f"[verdict] {verdict}")
    if verdict == "REJECTED" and not faults:
        print(f"[body] {_redact(text)[:1500]}")


def run_variant(gateway, variant, with_eori):
    label = "EORI on seller" if with_eori else "no registration numbers"
    print(
        f"\n=== Variant {variant}: postnord_parcel SE->NO with customsInvoice, {label} ==="
    )
    body = _base_body(gateway, variant)
    assert body.get("testIndicator") is True, "refusing: testIndicator is not true"
    shipment = body["shipment"][0]
    for key in ("customsDeclarationCN22", "customsDeclarationCN23"):
        shipment.pop(key, None)
    invoice_no = f"INV-{variant}-{os.getpid()}"
    shipment["customsInvoice"] = _customs_invoice(invoice_no, with_eori)
    customs_invoice = shipment["customsInvoice"]
    registration = [
        key
        for key, present in [
            ("eoriNo", "eoriNo" in customs_invoice["seller"]),
            ("voec", "voec" in customs_invoice),
            ("ioss", "ioss" in customs_invoice),
        ]
        if present
    ]
    print(f"[request] basicServiceCode={shipment['service'].get('basicServiceCode')}")
    print(f"[request] customsInvoice seller keys={sorted(customs_invoice['seller'])}")
    print(f"[request] registration fields present={registration}")
    status, text = _post(body)
    _summarize(status, text)


def main():
    missing = [
        name
        for name in ("POSTNORD_APIKEY", "POSTNORD_CUSTOMER_NUMBER", "POSTNORD_EORI")
        if not os.environ.get(name)
    ]
    if missing:
        print(f"missing environment variables: {missing}")
        return 2
    if os.environ.get("POSTNORD_LIVE_APIKEY") == os.environ["POSTNORD_APIKEY"]:
        print("refusing: POSTNORD_APIKEY equals POSTNORD_LIVE_APIKEY")
        return 2

    gateway = _gateway()
    assert gateway.settings.server_url == SANDBOX_URL, "refusing: not the sandbox host"
    run_variant(gateway, "A", with_eori=True)
    run_variant(gateway, "B", with_eori=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
