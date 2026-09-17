"""Karrio DHL Freight address validation (PostalCodes API).

The SE API Farm PostalCodes API resolves a postal code to its delivery
route; the product manual (§10.14.8) ties the route's ``homeDeliveryParcel``
flag to product 118 availability. The unified ``validate_address`` protocol
method and the booking pre-flight share this evaluation.
"""

import typing
import karrio.lib as lib
import karrio.core.models as models
import karrio.providers.dhl_freight_sweden.error as error
import karrio.providers.dhl_freight_sweden.utils as provider_utils
import karrio.providers.dhl_freight_sweden.units as provider_units


# Per-product servability flags on the route response; products without a
# documented flag fall back to the general ``bookable`` flag.
PRODUCT_SERVICABILITY_FLAGS = {"118": "homeDeliveryParcel"}


def evaluate_route(route: dict, product: str = None) -> bool:
    """Return the servability of a product on a postal-code route response."""
    flag = PRODUCT_SERVICABILITY_FLAGS.get(product or "")
    return bool(route.get(flag or "bookable"))


def address_validation_request(
    payload: models.AddressValidationRequest,
    settings: provider_utils.Settings,
) -> lib.Serializable:
    """Build a route-lookup params payload from the unified request.

    ``options.service`` scopes the lookup to a product (karrio service code
    or carrier product code, resolved like ``shipment_request`` does) and is
    carried in the context for the response parser.
    """
    address = lib.to_address(payload.address)
    service = payload.options.get("service")
    product = lib.identity(
        provider_units.ShippingService.map(service).value_or_key if service else None
    )

    return lib.Serializable(
        dict(
            country_code=address.country_code,
            postal_code=address.postal_code,
            service=product,
        ),
        lib.to_dict,
        dict(service=product),
    )


def parse_address_validation_response(
    _response: lib.Deserializable[dict],
    settings: provider_utils.Settings,
) -> typing.Tuple[models.AddressValidationDetails, typing.List[models.Message]]:
    """Parse a PostalCodeRouteInfo into unified address validation details.

    An unscoped lookup reports the general ``bookable`` flag; a lookup scoped
    through ``options.service`` reports the product's flag. A body without
    route fields is an error payload, so it yields no details and only
    messages.
    """
    response = _response.deserialize()
    route = response if _is_route(response) else {}
    messages = error.parse_error_response(response, settings)

    details = lib.identity(
        models.AddressValidationDetails(
            carrier_id=settings.carrier_id,
            carrier_name=settings.carrier_name,
            success=evaluate_route(route, _response.ctx.get("service")),
            complete_address=models.Address(
                city=route.get("city"),
                postal_code=(
                    str(route["postalCode"]) if route.get("postalCode") else None
                ),
                country_code=route.get("countryCode"),
            ),
        )
        if route
        else None
    )

    return details, messages


def _is_route(response: typing.Any) -> bool:
    return isinstance(response, dict) and any(
        key in response for key in ("bookable", "homeDeliveryParcel")
    )
