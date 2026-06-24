"""Karrio PostNord service points (connector-local capability).

PostNord's Service Points v5 API returns nearby pickup locations (agents,
parcel lockers, collect-in-store) for a destination. Karrio has no unified
service-point contract, so this capability is connector-local: the lookup is
reached via ``gateway.proxy.find_service_points`` and parsed into a stable
list of plain dicts (no generated schema), mirroring the transit-time
dict-parsing precedent.
"""

import typing
import karrio.lib as lib
import karrio.core.models as models
import karrio.providers.postnord.error as error
import karrio.providers.postnord.utils as provider_utils


def service_points_request(
    payload: dict,
    settings: provider_utils.Settings,
) -> lib.Serializable:
    """Build a Service Points v5 query from a lookup payload.

    The chosen endpoint path (``byaddress`` vs ``bycoordinates``) is carried on
    the returned ``Serializable``'s ctx so the proxy can route the GET. Routing
    is by which inputs are present: a ``northing``/``easting`` pair selects the
    coordinate variant; otherwise the address variant is used.
    """
    northing = payload.get("northing")
    easting = payload.get("easting")
    by_coordinates = northing is not None and easting is not None

    path = (
        "/rest/businesslocation/v5/servicepoints/nearest/bycoordinates"
        if by_coordinates
        else "/rest/businesslocation/v5/servicepoints/nearest/byaddress"
    )

    params = {
        "returnType": "json",
        "countryCode": payload.get("country_code"),
        "numberOfServicePoints": payload.get("number_of_points"),
        "typeId": payload.get("type_id"),
        "context": payload.get("context"),
        "srId": payload.get("sr_id"),
        **(
            {
                "northing": northing,
                "easting": easting,
            }
            if by_coordinates
            else {
                "postalCode": payload.get("postal_code"),
                "city": payload.get("city"),
                "streetName": payload.get("street_name"),
                "streetNumber": payload.get("street_number"),
            }
        ),
    }

    return lib.Serializable(
        {key: value for key, value in params.items() if value is not None},
        lib.to_dict,
        ctx={"path": path},
    )


def parse_service_points_response(
    _response: lib.Deserializable[dict],
    settings: provider_utils.Settings,
) -> typing.Tuple[typing.List[dict], typing.List[models.Message]]:
    """Parse a Service Points v5 response into normalized point dicts + Messages.

    The response wraps a ``servicePointInformationResponse`` carrying both the
    ``servicePoints`` list and, on failure, a ``compositeFault`` (handled by the
    shared error parser). Each point is normalized defensively, omitting missing
    keys via ``lib`` guarded access.
    """
    response = _response.deserialize()
    information = response.get("servicePointInformationResponse") or {}

    points = [
        _normalize_service_point(point)
        for point in (information.get("servicePoints") or [])
    ]
    messages = error.parse_error_response(information, settings)

    return points, messages


def _normalize_service_point(point: dict) -> dict:
    """Normalize one ``ServicePointInformationStore`` to the connector dict shape."""
    address = point.get("deliveryAddress") or point.get("visitingAddress") or {}
    coordinate = next(iter(point.get("coordinates") or []), {})
    point_type = point.get("type") or {}
    type_id = point_type.get("typeId")
    # Keep ``type`` a string: typeId is numeric in the spec, so coerce the
    # fallback rather than emit a mixed str/int field.
    type_label = point_type.get("typeName") or (
        str(type_id) if type_id is not None else None
    )

    return lib.to_dict(
        {
            "id": point.get("servicePointId"),
            "name": point.get("name"),
            "type": type_label,
            "address": lib.to_dict(
                {
                    "address_line1": lib.text(
                        address.get("streetName"),
                        address.get("streetNumber"),
                    ),
                    "city": address.get("city"),
                    "postal_code": address.get("postalCode"),
                    "country_code": address.get("countryCode"),
                }
            )
            or None,
            "coordinates": lib.to_dict(
                {
                    "northing": coordinate.get("northing"),
                    "easting": coordinate.get("easting"),
                    "sr_id": coordinate.get("srId"),
                }
            )
            or None,
            "opening_hours": point.get("openingHours"),
            "distance": point.get("routeDistance"),
        }
    )
