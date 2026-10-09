"""PostNord chosen-service-point booking tests.

Asserts the official Shipping v3 (EDI) sample shape ("MyPack Collect (19) +
Addon: Optional Servicepoint"): the chosen point is a deliveryParty carrying
partyIdentification {partyId = servicePointId, partyIdType "156"} plus the
point's name and address, with A7 (optional service point) pairing the
choice and A3 (SMS) following the consignee phone.
"""

import unittest
from unittest.mock import patch

import karrio.sdk as karrio
import karrio.lib as lib
import karrio.core.models as models

from .fixture import gateway


SERVICE_POINT_OPTIONS = {
    "postnord_service_point_id": "588462",
    "postnord_service_point_name": "Hemköp Sjövikshallen",
    "postnord_service_point_street": "17 Sjövikstorget",
    "postnord_service_point_city": "STOCKHOLM",
    "postnord_service_point_postal_code": "11758",
    "postnord_service_point_country_code": "SE",
}

# test_shipment.py's ShipmentPayload minus its options key: the booking base
# a chosen service point rides on, with a consignee phone for the A3 pairing.
BASE_SHIPMENT_PAYLOAD = {
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
    },
    "recipient": {
        "address_line1": "Terminalvagen 24",
        "city": "Solna",
        "postal_code": "17173",
        "country_code": "SE",
        "state_code": "Stockholm",
        "person_name": "Jane Receiver",
        "company_name": "Receiver Co",
        "phone_number": "+46709876543",
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
    "reference": "ORDER-7788",
}


class TestPostNordServicePointBooking(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None

    def request_payload(self, options: dict):
        payload = {**BASE_SHIPMENT_PAYLOAD, "options": options}
        request = gateway.mapper.create_shipment_request(
            models.ShipmentRequest(**payload)
        )
        return lib.to_dict(request.serialize())

    def test_delivery_party_is_booked_with_the_chosen_point(self):
        shipment = self.request_payload(SERVICE_POINT_OPTIONS)["shipment"][0]
        party = shipment["parties"]["deliveryParty"]
        self.assertEqual(
            party["partyIdentification"], {"partyId": "588462", "partyIdType": "156"}
        )
        # The deliveryParty is the collection agent, not a contract party:
        # unlike consignor/consignee it carries no issuerCode.
        self.assertNotIn("issuerCode", party)
        self.assertEqual(
            party["party"]["nameIdentification"]["name"], "Hemköp Sjövikshallen"
        )
        address = party["party"]["address"]
        self.assertEqual(address["streets"], ["17 Sjövikstorget"])
        self.assertEqual(address["city"], "STOCKHOLM")
        # Direct string comparison: postalCode's Optional[int] is a swagger
        # artifact, and a coercion to int would break zero-leading codes.
        self.assertEqual(address["postalCode"], "11758")
        self.assertEqual(address["countryCode"], "SE")
        # A7 switches the product into chosen-point mode and pairs with SMS
        # (A3) on the consignee phone; the detail options never surface as
        # additionalServiceCode values.
        self.assertEqual(shipment["service"]["additionalServiceCode"], ["A7", "A3"])

    def test_explicit_sms_opt_out_is_overridden_for_a_chosen_point(self):
        # The recipient must learn where to collect, so the chosen-point
        # pairing books A3 on the consignee phone even against an explicit
        # sms_notification false (policy, documented in the README).
        options = {**SERVICE_POINT_OPTIONS, "sms_notification": False}
        shipment = self.request_payload(options)["shipment"][0]
        self.assertEqual(shipment["service"]["additionalServiceCode"], ["A7", "A3"])

    def test_chosen_point_without_consignee_phone_books_only_a7(self):
        payload = {
            **BASE_SHIPMENT_PAYLOAD,
            "recipient": {
                key: value
                for key, value in BASE_SHIPMENT_PAYLOAD["recipient"].items()
                if key != "phone_number"
            },
            "options": SERVICE_POINT_OPTIONS,
        }
        request = gateway.mapper.create_shipment_request(
            models.ShipmentRequest(**payload)
        )
        shipment = lib.to_dict(request.serialize())["shipment"][0]
        self.assertEqual(shipment["service"]["additionalServiceCode"], ["A7"])

    def test_chosen_point_with_sms_opt_in_does_not_duplicate_a3(self):
        # A3 already collected from the unified option, the pairing must not
        # append a second one; sorted comparison leaves the emission order
        # open.
        options = {**SERVICE_POINT_OPTIONS, "sms_notification": True}
        codes = self.request_payload(options)["shipment"][0]["service"][
            "additionalServiceCode"
        ]
        self.assertEqual(codes.count("A3"), 1)
        self.assertEqual(sorted(codes), ["A3", "A7"])

    def test_without_options_no_delivery_party_and_no_a7(self):
        shipment = self.request_payload({})["shipment"][0]
        self.assertNotIn("deliveryParty", shipment["parties"])
        self.assertEqual(shipment["service"], {"basicServiceCode": "18"})

    def test_incomplete_point_details_refuse_before_the_request(self):
        # A point id without the full details is refused locally with a field
        # error naming the missing option keys: PostNord would reject an
        # addressless deliveryParty as a booking fault.
        incomplete = {
            key: value
            for key, value in SERVICE_POINT_OPTIONS.items()
            if key != "postnord_service_point_city"
        }
        with patch("karrio.mappers.postnord.proxy.lib.request") as mock:
            mock.return_value = "{}"
            shipment, messages = (
                karrio.Shipment.create(
                    models.ShipmentRequest(
                        **{**BASE_SHIPMENT_PAYLOAD, "options": incomplete}
                    )
                )
                .from_(gateway)
                .parse()
            )
            mock.assert_not_called()
        self.assertIsNone(shipment)
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].code, "SHIPPING_SDK_FIELD_ERROR")
        self.assertEqual(
            messages[0].details,
            {
                "options.postnord_service_point_city": (
                    "a chosen service point requires the complete point details"
                )
            },
        )


if __name__ == "__main__":
    unittest.main()
