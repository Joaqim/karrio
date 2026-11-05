"""Production probe for the nordic-customs-invoice-mapping change (task 6.2).

Books one ``postnord_parcel`` SE -> NO in PRODUCTION (``api2.postnord.com``)
through the karrio gateway and the branch connector, so the customs invoice,
the booking printout composition, and the implicit printId-keyed by-id customs
document fetch are all produced by the connector itself.
PostNord offers no cancellation; the booking is left unshipped, which the user
confirmed is not billed.

Run from the feat-postnord-customs-invoice worktree root, with explicit user
approval immediately before running:

    python <docs-openspec>/openspec/changes/nordic-customs-invoice-mapping/verify_prod_probe.py --production

Environment (read by name only; values are never printed):
    POSTNORD_LIVE_APIKEY            required; production apikey
    POSTNORD_LIVE_CUSTOMER_NUMBER   required; production customer number
    POSTNORD_LIVE_APPLICATION_ID    optional; production application id
    POSTNORD_EORI                   required only for attempt B
    POSTNORD_SHIPPER_VAT_NO         optional; real shipper VAT number
                                    (defaults to the sandbox fixture value)

Attempts:
    A  customs invoice without registration numbers (no EORI, VOEC, IOSS)
    B  only when A is rejected for registration (SACUS-BR-24062502):
       the same booking with the EORI as customs option eori_number
Any other rejection stops the probe; at most one booking succeeds.
"""

import base64
import datetime
import importlib.util
import json
import os
import sys

import karrio.core.models as models
import karrio.lib as lib
import karrio.providers.postnord as provider
import karrio.sdk as karrio

PRODUCTION_URL = "https://api2.postnord.com"
REGISTRATION_FAULT = "SACUS-BR-24062502"
SECRET_NAMES = (
    "POSTNORD_LIVE_APIKEY",
    "POSTNORD_LIVE_CUSTOMER_NUMBER",
    "POSTNORD_LIVE_APPLICATION_ID",
    "POSTNORD_EORI",
    "POSTNORD_APIKEY",
    "POSTNORD_CUSTOMER_NUMBER",
    "POSTNORD_SHIPPER_VAT_NO",
)


def _fixture_vat_no():
    """Reuse the sandbox gate's fixture seller VAT number from verify_live.py."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "verify_live.py")
    spec = importlib.util.spec_from_file_location("verify_live", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.SELLER_VAT_NO


SHIPPER = {
    "address_line1": "Sandhamnsgatan 61",
    "city": "Stockholm",
    "postal_code": "11528",
    "country_code": "SE",
    "person_name": "John Sender",
    "company_name": "ACME Sender AB",
    "phone_number": "+46701234567",
    "email": "sender@example.com",
    "federal_tax_id": os.environ.get("POSTNORD_SHIPPER_VAT_NO") or _fixture_vat_no(),
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

COMMODITY = {
    "description": "Candy",
    "quantity": 2,
    "hs_code": "1704906500",
    "origin_country": "SE",
    "value_amount": 15.0,
    "value_currency": "EUR",
    "weight": 0.19,
    "weight_unit": "KG",
}


def _redact(text):
    text = str(text)
    for name in SECRET_NAMES:
        value = os.environ.get(name)
        if value:
            text = text.replace(value, f"<{name}>")
    return text


def _say(*parts):
    print(_redact(" ".join(str(part) for part in parts)))


class _Recorder:
    """Wrap ``lib.request`` to keep each call's path and raw response."""

    def __init__(self):
        self.calls = []
        self._request = lib.request

    def __call__(self, **kwargs):
        response = self._request(**kwargs)
        path = kwargs.get("url", "").split("?")[0].replace(PRODUCTION_URL, "")
        self.calls.append((path, response))
        return response


def _gateway():
    return karrio.gateway["postnord"].create(
        dict(
            apikey=os.environ["POSTNORD_LIVE_APIKEY"],
            customer_number=os.environ["POSTNORD_LIVE_CUSTOMER_NUMBER"],
            application_id=os.environ.get("POSTNORD_LIVE_APPLICATION_ID"),
            issuer_code="Z12",
            test_mode=False,
        )
    )


def _payload(attempt, with_eori):
    return {
        "shipper": SHIPPER,
        "recipient": RECIPIENT,
        "parcels": [
            {
                "weight": 0.5,
                "width": 20.0,
                "height": 10.0,
                "length": 30.0,
                "weight_unit": "KG",
                "dimension_unit": "CM",
            }
        ],
        "service": "postnord_parcel",
        "reference": f"CI-PROD-{attempt}-{os.getpid()}",
        "customs": {
            "commercial_invoice": True,
            "invoice": f"INV-PROD-{attempt}-{os.getpid()}",
            "invoice_date": datetime.date.today().isoformat(),
            "content_type": "merchandise",
            "commodities": [COMMODITY],
            **(
                {"options": {"eori_number": os.environ["POSTNORD_EORI"]}}
                if with_eori
                else {}
            ),
        },
    }


def _summarize_booking(body):
    data = lib.failsafe(lambda: json.loads(body)) or {}
    if not isinstance(data, dict):
        _say("[booking body]", str(body)[:800])
        return
    faults = (data.get("compositeFault") or {}).get("faults") or []
    for fault in faults:
        _say("[fault]", fault.get("faultCode"), fault.get("explanationText"))
    booking = data.get("bookingResponse") or {}
    for info in booking.get("idInformation") or []:
        _say(
            "[ids]",
            json.dumps(
                {
                    "status": info.get("status"),
                    "ids": [
                        {k: i.get(k) for k in ("idType", "value", "printId")}
                        for i in info.get("ids") or []
                    ],
                }
            ),
        )
    for entry in data.get("labelPrintout") or []:
        printout = entry.get("printout") or {}
        _say(
            "[booking printout] composition=",
            entry.get("printoutComposition"),
            f"format={printout.get('labelFormat')}",
            f"base64_chars={len(printout.get('data') or '')}",
        )
    if not faults and not booking:
        _say("[booking body]", str(body)[:800])


def _summarize_by_id(body):
    entries = lib.failsafe(lambda: json.loads(body))
    if not isinstance(entries, list):
        _say("[by-id body]", str(body)[:800])
        return
    for entry in entries:
        for member in entry.get("itemIds") or []:
            _say(
                "[by-id member]",
                f"status={member.get('status')}",
                f"error={(member.get('errorResponse') or {}).get('message')}",
            )
        printout = entry.get("printout") or {}
        _say(
            "[by-id printout] composition=",
            entry.get("printoutComposition"),
            f"format={printout.get('labelFormat')}",
            f"base64_chars={len(printout.get('data') or '')}",
        )


def _run(gateway, recorder, attempt, with_eori):
    _say(
        f"\n=== Attempt {attempt}: postnord_parcel SE->NO customs invoice,",
        "EORI option" if with_eori else "no registration numbers",
        "===",
    )
    recorder.calls.clear()
    shipment, messages = (
        karrio.Shipment.create(lib.to_object(models.ShipmentRequest, _payload(attempt, with_eori)))
        .from_(gateway)
        .parse()
    )
    for path, body in recorder.calls:
        _say(f"[call] {path}")
        if "/labels/ids/" in path:
            _summarize_by_id(body)
        else:
            _summarize_booking(body)
    for message in messages:
        _say("[message]", message.code, message.message)
    if shipment is None:
        return None, messages
    _say("[shipment] tracking_number=", shipment.tracking_number)
    _say("[shipment] meta=", json.dumps(shipment.meta))
    label = base64.b64decode(shipment.docs.label or "")
    _say(f"[label] bytes={len(label)} magic={label[:5]!r}")
    for document in shipment.docs.extra_documents or []:
        raw = base64.b64decode(document.base64 or "")
        _say(
            f"[extra_document] category={document.category}",
            f"format={document.format} bytes={len(raw)} magic={raw[:5]!r}",
        )
    return shipment, messages


def main():
    if "--production" not in sys.argv[1:]:
        print("refusing: pass --production to book in the PostNord production environment")
        return 2
    missing = [
        name
        for name in ("POSTNORD_LIVE_APIKEY", "POSTNORD_LIVE_CUSTOMER_NUMBER", "POSTNORD_EORI")
        if not os.environ.get(name)
    ]
    if missing:
        print(f"missing environment variables: {missing}")
        return 2

    _say("[connector]", provider.__file__)
    _say(
        "[shipper] vat source=",
        "POSTNORD_SHIPPER_VAT_NO" if os.environ.get("POSTNORD_SHIPPER_VAT_NO") else "fixture",
    )
    gateway = _gateway()
    assert gateway.settings.server_url == PRODUCTION_URL, "refusing: not the production host"

    recorder = _Recorder()
    lib.request = recorder
    try:
        shipment, messages = _run(gateway, recorder, "A", with_eori=False)
        if shipment is not None:
            _say("\n[verdict] attempt A accepted; attempt B not run")
            return 0
        if not any(REGISTRATION_FAULT in f"{m.code} {m.message}" for m in messages):
            _say("\n[verdict] attempt A rejected for another reason; stopping")
            return 1
        shipment, _ = _run(gateway, recorder, "B", with_eori=True)
        _say(
            "\n[verdict] attempt B",
            "accepted" if shipment is not None else "rejected; stopping",
        )
        return 0 if shipment is not None else 1
    finally:
        lib.request = recorder._request


if __name__ == "__main__":
    sys.exit(main())
