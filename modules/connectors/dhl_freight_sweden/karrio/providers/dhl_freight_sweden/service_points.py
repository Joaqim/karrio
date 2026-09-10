"""Karrio DHL Freight service points (connector-local capability).

The SE API Farm Servicepoint API returns the service points nearest an
address, with optional location-type, distance, and piece-capacity filters.
Karrio has no unified service-point contract, so this capability is
connector-local: the lookup is reached via ``gateway.proxy.find_service_points``
and parsed into a stable list of plain dicts (no generated schema), mirroring
the postnord ``service_points`` precedent.
"""

import typing
import karrio.lib as lib
import karrio.core.models as models
import karrio.providers.dhl_freight_sweden.error as error
import karrio.providers.dhl_freight_sweden.utils as provider_utils


def service_points_request(
    payload: dict,
    settings: provider_utils.Settings,
) -> lib.Serializable:
    """Build a ``NearestServicePointRequest`` body from a lookup payload."""
    address = payload.get("address") or {}
    distance = payload.get("distance") or {}
    piece = payload.get("piece") or {}

    request = dict(
        address=dict(
            street=address.get("street"),
            streetNumber=address.get("street_number"),
            additionalAddressInfo=address.get("additional_address_info"),
            cityName=address.get("city"),
            postalCode=address.get("postal_code"),
            countryCode=address.get("country_code"),
        ),
        locationTypes=payload.get("location_types"),
        maxNumberOfItems=payload.get("max_items"),
        distance=distance.get("value"),
        distanceUnit=distance.get("unit"),
        piece=(
            dict(
                width=piece.get("width"),
                height=piece.get("height"),
                length=piece.get("length"),
                weight=piece.get("weight"),
            )
            if payload.get("piece")
            else None
        ),
    )

    return lib.Serializable(request, lib.to_dict)


def parse_service_points_response(
    _response: lib.Deserializable[dict],
    settings: provider_utils.Settings,
) -> typing.Tuple[typing.List[dict], typing.List[models.Message]]:
    """Parse a nearest-service-points response into point dicts + Messages.

    The endpoint signals failures in-band: the 200 body carries ``status`` and
    ``errorMessage``, which the shared error parser turns into Messages (an
    ``errorMessage``-free body parses to no Messages).
    """
    response = _response.deserialize()

    points = [
        _normalize_service_point(point)
        for point in response.get("servicePoints") or []
        if isinstance(point, dict)
    ]
    messages = error.parse_error_response(response, settings)

    return points, messages


def _normalize_service_point(point: dict) -> dict:
    """Normalize one ``ServicePointReference`` into the connector dict shape.

    The point carries its location flat (``street``, ``cityName`` and sibling
    address fields, plus ``latitude``/``longitude``); the dict groups them into
    ``address`` and ``coordinates`` so they map one-to-one onto the PUDO
    options. Both identifiers are kept: the sandbox accepts either at booking,
    and which one DHL consumes downstream is unresolved.
    """
    return lib.to_dict(
        {
            "id": point.get("id"),
            "service_point_id": point.get("servicePointId"),
            "name": point.get("name"),
            "shop_name": point.get("shopName"),
            "type": point.get("locationType"),
            "address": lib.to_dict(
                {
                    "street": point.get("street"),
                    "city": point.get("cityName"),
                    "postal_code": point.get("postalCode"),
                    "country_code": point.get("countryCode"),
                }
            )
            or None,
            "coordinates": lib.to_dict(
                {
                    "latitude": point.get("latitude"),
                    "longitude": point.get("longitude"),
                }
            )
            or None,
            "distance": point.get("distance"),
            "distance_unit": point.get("distanceUnit"),
            "service_types": point.get("serviceTypes"),
        }
    )
