"""DHL Freight (SE API Farm) EU VAT area classification tests."""

import unittest

from karrio.providers.dhl_freight_sweden import units


class TestDHLFreightEUVATArea(unittest.TestCase):
    def test_in_eu_vat_area(self):
        cases = [
            ("SE", "11143", True),
            ("PL", "00-001", True),
            ("GR", "10552", True),
            ("EL", "10552", True),
            ("DE", "10115", True),
            ("DE", "78266", False),
            ("DE", "27498", False),
            ("IT", "23041", False),
            ("IT", "22061", False),
            ("IT", "00100", True),
            ("FI", "22100", False),
            ("FI", "22 100", False),
            ("FI", "00100", True),
            ("AX", "22100", False),
            ("ES", "35001", False),
            ("ES", "38001", False),
            ("ES", "51001", False),
            ("ES", "52001", False),
            ("ES", "28001", True),
            ("IC", "35001", False),
            ("GP", "97110", False),
            ("GF", "97300", False),
            ("MQ", "97200", False),
            ("RE", "97400", False),
            ("YT", "97600", False),
            ("NO", "0154", False),
            ("GB", "SW1A 1AA", False),
            ("GB", "BT1 1AA", True),
            ("GB", "bt1 1aa", True),
            ("GB", "EC1A 1BB", False),
            ("MC", "98000", True),
            ("FR", "98000", True),
            ("GR", "630 86", False),
            ("CH", "8001", False),
            (None, None, False),
        ]

        for country_code, postal_code, expected in cases:
            with self.subTest(country_code=country_code, postal_code=postal_code):
                self.assertEqual(
                    units.in_eu_vat_area(country_code, postal_code), expected
                )


if __name__ == "__main__":
    unittest.main()
