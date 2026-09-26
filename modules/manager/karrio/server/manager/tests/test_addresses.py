import json
from unittest.mock import ANY
from django.urls import reverse
from rest_framework import status
from karrio.server.core.tests import APITestCase
from karrio.server.manager.models import Address


class TestAddresses(APITestCase):
    def test_create_address(self):
        url = reverse("karrio.server.manager:address-list")
        data = ADDRESS_DATA

        response = self.client.post(url, data)
        response_data = json.loads(response.content)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertDictEqual(response_data, ADDRESS_RESPONSE)

    def test_list_addresses(self):
        # Create an address first
        Address.objects.create(
            **{
                "address_line1": "5205 rue riviera",
                "person_name": "Old town Daniel",
                "phone_number": "438 222 2222",
                "city": "Montreal",
                "country_code": "CA",
                "postal_code": "H8Z2Z3",
                "residential": True,
                "state_code": "QC",
                "validate_location": False,
                "validation": None,
                "created_by": self.user,
            }
        )

        url = reverse("karrio.server.manager:address-list")
        response = self.client.get(url)
        response_data = json.loads(response.content)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("results", response_data)
        self.assertGreaterEqual(len(response_data["results"]), 1)


class TestAddressDetails(APITestCase):
    def setUp(self) -> None:
        super().setUp()
        self.address: Address = Address.objects.create(
            **{
                "address_line1": "5205 rue riviera",
                "person_name": "Old town Daniel",
                "phone_number": "438 222 2222",
                "city": "Montreal",
                "country_code": "CA",
                "postal_code": "H8Z2Z3",
                "residential": True,
                "state_code": "QC",
                "validate_location": False,
                "validation": None,
                "created_by": self.user,
            }
        )

    def test_retrieve_address(self):
        url = reverse(
            "karrio.server.manager:address-details", kwargs=dict(pk=self.address.pk)
        )

        response = self.client.get(url)
        response_data = json.loads(response.content)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response_data["id"], self.address.pk)
        self.assertEqual(response_data["object_type"], "address")

    def test_update_address(self):
        url = reverse(
            "karrio.server.manager:address-details", kwargs=dict(pk=self.address.pk)
        )
        data = ADDRESS_UPDATE_DATA

        response = self.client.patch(url, data)
        response_data = json.loads(response.content)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertDictEqual(response_data, ADDRESS_UPDATE_RESPONSE)

    def test_delete_address(self):
        address_pk = self.address.pk
        url = reverse(
            "karrio.server.manager:address-details", kwargs=dict(pk=address_pk)
        )

        response = self.client.delete(url)
        response_data = json.loads(response.content)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response_data["object_type"], "address")
        self.assertFalse(Address.objects.filter(pk=address_pk).exists())


class TestAddressStateNormalization(APITestCase):
    def setUp(self) -> None:
        super().setUp()
        self.url = reverse("karrio.server.manager:address-list")

    def test_create_address_normalizes_state_code(self):
        for country_code, state_code, expected in STATE_NORMALIZATION_CASES:
            with self.subTest(country_code=country_code, state_code=state_code):
                data = {
                    **MINIMAL_ADDRESS_DATA,
                    "country_code": country_code,
                    "state_code": state_code,
                }

                response = self.client.post(self.url, data)
                response_data = json.loads(response.content)

                self.assertEqual(
                    response.status_code, status.HTTP_201_CREATED, response_data
                )
                self.assertEqual(response_data["state_code"], expected)

    def test_references_states_exclude_normalization_only_countries(self):
        response = self.client.get("/v1/references")
        states = json.loads(response.content)["states"]

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("US", states)
        self.assertEqual(sorted({"DK", "FI", "NO", "SE"} & states.keys()), [])

    def test_create_address_without_state_keeps_it_absent(self):
        response = self.client.post(self.url, MINIMAL_ADDRESS_DATA)
        response_data = json.loads(response.content)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIsNone(response_data["state_code"])

    def test_update_address_normalizes_state_code(self):
        address = Address.objects.create(
            **{
                "address_line1": "Postgatan 1",
                "person_name": "Sven Svensson",
                "city": "Göteborg",
                "country_code": "SE",
                "validate_location": False,
                "validation": None,
                "created_by": self.user,
            }
        )
        url = reverse(
            "karrio.server.manager:address-details", kwargs=dict(pk=address.pk)
        )

        response = self.client.patch(
            url, {"country_code": "SE", "state_code": "Västra Götaland"}
        )
        response_data = json.loads(response.content)

        self.assertEqual(response.status_code, status.HTTP_200_OK, response_data)
        self.assertEqual(response_data["state_code"], "O")


ADDRESS_DATA = {
    "address_line1": "5205 rue riviera",
    "person_name": "Old town Daniel",
    "phone_number": "438 222 2222",
    "city": "Montreal",
    "country_code": "CA",
    "postal_code": "H8Z2Z3",
    "residential": True,
    "state_code": "QC",
}

ADDRESS_RESPONSE = {
    "id": ANY,
    "object_type": "address",
    "postal_code": "H8Z2Z3",
    "city": "Montreal",
    "federal_tax_id": None,
    "state_tax_id": None,
    "person_name": "Old town Daniel",
    "company_name": None,
    "country_code": "CA",
    "email": None,
    "phone_number": "+1 438-222-2222",
    "state_code": "QC",
    "street_number": None,
    "residential": True,
    "address_line1": "5205 rue riviera",
    "address_line2": None,
    "validate_location": False,
    "validation": None,
    "meta": {},
}

ADDRESS_UPDATE_DATA = {
    "person_name": "John Doe",
    "company_name": "Doe corp",
    "residential": False,
}

ADDRESS_UPDATE_RESPONSE = {
    "id": ANY,
    "object_type": "address",
    "postal_code": "H8Z2Z3",
    "city": "Montreal",
    "federal_tax_id": None,
    "state_tax_id": None,
    "person_name": "John Doe",
    "company_name": "Doe corp",
    "country_code": "CA",
    "email": None,
    "phone_number": "438 222 2222",
    "state_code": "QC",
    "street_number": None,
    "residential": False,
    "address_line1": "5205 rue riviera",
    "address_line2": None,
    "validate_location": False,
    "validation": None,
    "meta": {},
}

MINIMAL_ADDRESS_DATA = {
    "address_line1": "Postgatan 1",
    "person_name": "Sven Svensson",
    "city": "Göteborg",
    "country_code": "SE",
}

STATE_NORMALIZATION_CASES = [
    ("SE", "Västra Götaland", "O"),
    ("SE", "Västra Götalands län", "O"),
    ("SE", "SE-O", "O"),
    ("SE", "skåne", "M"),
    ("NO", "Vestland", "46"),
    ("NO", "More og Romsdal", "15"),
    ("NO", "Østfold", "31"),
    ("NO", "Ostfold", "31"),
    ("NO", "Akershus", "32"),
    ("NO", "Buskerud", "33"),
    ("NO", "Vestfold", "39"),
    ("NO", "Telemark", "40"),
    ("NO", "Troms", "55"),
    ("NO", "Finnmark", "56"),
    ("NO", "Svalbard", "21"),
    ("NO", "Jan Mayen", "22"),
    ("NO", "03", "03"),
    ("NO", "NO-32", "32"),
    ("NO", "Aust-Agder", "Aust-Agder"),
    ("NO", "Vest-Agder", "Vest-Agder"),
    ("NO", "Hedmark", "Hedmark"),
    ("NO", "Oppland", "Oppland"),
    ("NO", "Hordaland", "Hordaland"),
    ("NO", "Sogn og Fjordane", "Sogn og Fjordane"),
    ("NO", "Nord-Trøndelag", "Nord-Trøndelag"),
    ("NO", "Sør-Trøndelag", "Sør-Trøndelag"),
    ("NO", "Viken", "Viken"),
    ("NO", "Vestfold og Telemark", "Vestfold og Telemark"),
    ("NO", "Troms og Finnmark", "Troms og Finnmark"),
    ("NO", "30", "30"),
    ("DK", "Region Hovedstaden", "84"),
    ("DK", "Sjelland", "85"),
    ("DK", "Sjaelland", "85"),
    ("FI", "Pirkanmaa", "11"),
    ("CA", "qc", "QC"),
    ("CA", "CA-QC", "QC"),
    ("CA", "PQ", "QC"),
    ("US", "California", "CA"),
    ("US", "Washington", "WA"),
    ("US", "Washington State", "WA"),
    ("US", "N/A", "N/A"),
    ("SE", "SE-XX", "SE-XX"),
    ("DE", "Bayern", "Bayern"),
]
