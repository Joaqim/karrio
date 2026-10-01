"""Karrio DHL Freight product matches (connector-local capability).

The SE API Farm Product API returns the products matching a consignor/
consignee address pair (plus optional piece criteria). Karrio has no unified
product-lookup contract, so this capability is connector-local: the lookup is
reached via ``gateway.proxy.find_product_matches`` and parsed into a stable
list of plain dicts (no generated schema), mirroring the postnord
``service_points`` precedent.
"""

import typing
import karrio.lib as lib
import karrio.core.models as models
import karrio.core.errors as errors
import karrio.providers.dhl_freight_sweden.error as error
import karrio.providers.dhl_freight_sweden.utils as provider_utils


class ProductMatchPartiesError(errors.ShippingSDKDetailedError):
    """Raised when a product match query lacks the required address pair."""

    code = "SHIPPING_SDK_FIELD_ERROR"


def product_matches_request(
    payload: dict,
    settings: provider_utils.Settings,
) -> lib.Serializable:
    """Build a ``MatchCriteria`` body from a lookup payload.

    The endpoint's 200 description requires at least one Consignor and one
    Consignee party (a prose-only rule the API does not validate client-side),
    so incomplete parties fail here with the missing payload keys instead of
    as a carrier error.
    """
    shipper = payload.get("shipper") or {}
    recipient = payload.get("recipient") or {}
    missing = [
        name
        for name, party in (("shipper", shipper), ("recipient", recipient))
        if not (party.get("postal_code") and party.get("country_code"))
    ]

    if any(missing):
        raise ProductMatchPartiesError(
            "The product matches lookup requires a Consignor and a Consignee "
            "party with postal code and country code; "
            f"missing {', '.join(missing)}",
            details={
                name: dict(
                    code="required",
                    message="postal code and country code are required",
                )
                for name in missing
            },
        )

    request = dict(
        parties=[
            dict(
                type="Consignor",
                address=_address_match_criteria(shipper),
            ),
            dict(
                type="Consignee",
                address=_address_match_criteria(recipient),
            ),
        ],
        pieces=[
            dict(
                packageType=piece.get("package_type"),
                weight=piece.get("weight"),
                length=piece.get("length"),
                width=piece.get("width"),
                height=piece.get("height"),
                volume=piece.get("volume"),
            )
            for piece in payload.get("parcels") or []
        ],
        totalVolume=payload.get("total_volume"),
        totalNumberOfPieces=payload.get("total_number_of_pieces"),
        totalLoadingMeters=payload.get("total_loading_meters"),
        totalPalletPlaces=payload.get("total_pallet_places"),
        totalWeight=payload.get("total_weight"),
        importExport=payload.get("import_export"),
    )

    return lib.Serializable(request, lib.to_dict)


def parse_product_matches_response(
    _response: lib.Deserializable[dict],
    settings: provider_utils.Settings,
) -> typing.Tuple[typing.List[dict], typing.List[models.Message]]:
    """Parse a product matches response into normalized product dicts + Messages.

    A successful body is a list of ``ProductMatchResult``; any dict body is
    routed through the shared error parser so the productapi's defensive
    ``BadRequestError`` shape and in-band ``errorMessage`` strings both
    surface as Messages.
    """
    response = _response.deserialize()
    matches = response if isinstance(response, list) else []

    products = [
        _normalize_product(match.get("product") or {})
        for match in matches
        if isinstance(match, dict)
    ]
    messages = error.parse_error_response(
        response if isinstance(response, dict) else {},
        settings,
    )

    return products, messages


def _address_match_criteria(party: dict) -> dict:
    return dict(
        countryCode=party.get("country_code"),
        postalCode=party.get("postal_code"),
    )


def _normalize_product(product: dict) -> dict:
    """Normalize one ``Product`` into the connector dict shape.

    ``shipment``/``piece`` rule summaries pass through with their wire keys
    (``actualWeightMin``, ``lengthMax``, ...) so callers see the API's
    min/max bounds verbatim.
    """
    transportation_mode = product.get("transportationMode") or {}

    return lib.to_dict(
        {
            "code": product.get("code"),
            "name": product.get("name"),
            "short_name": product.get("shortName"),
            "is_domestic": product.get("isDomestic"),
            "active": product.get("active"),
            "is_default": product.get("isDefault"),
            "hidden": product.get("hidden"),
            "from_countries": [
                (item.get("country") or {}).get("countryCode")
                for item in product.get("fromCountries") or []
            ],
            "to_countries": [
                (item.get("country") or {}).get("countryCode")
                for item in product.get("toCountries") or []
            ],
            "to_country_postal_excludes": [
                dict(
                    country_code=(item.get("country") or {}).get("countryCode"),
                    postal_code_excludes=item.get("postalCodeExcludes"),
                )
                for item in product.get("toCountries") or []
                if item.get("postalCodeExcludes")
            ],
            "payer_codes": [
                item.get("code") for item in product.get("payerCodes") or []
            ],
            "transportation_mode": lib.to_dict(
                dict(
                    code=transportation_mode.get("code"),
                    name=transportation_mode.get("name"),
                )
            )
            or None,
            "sub_categories": [
                lib.to_dict(
                    dict(
                        code=item.get("code"),
                        name=item.get("name"),
                    )
                )
                for item in product.get("subCategories") or []
            ],
            "rules_for_country_delivery_types": [
                _normalize_rule(item)
                for item in product.get("rulesForCountryAndDeliveryTypes") or []
            ],
        }
    )


def _normalize_rule(rule: dict) -> dict:
    """Normalize one ``RulesPerDeliveryType`` into a min/max summary entry."""
    return lib.to_dict(
        {
            "country_code": (rule.get("country") or {}).get("countryCode"),
            "delivery_type": (rule.get("deliveryType") or {}).get("code"),
            "shipment": rule.get("shipment"),
            "piece": rule.get("piece"),
        }
    )
