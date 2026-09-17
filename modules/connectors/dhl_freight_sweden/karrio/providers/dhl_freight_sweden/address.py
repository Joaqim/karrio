"""Karrio DHL Freight address validation (PostalCodes API).

The SE API Farm PostalCodes API resolves a postal code to its delivery
route; the product manual (§10.14.8) ties the route's ``homeDeliveryParcel``
flag to product 118 availability. The unified ``validate_address`` protocol
method and the booking pre-flight share this evaluation.
"""

import typing
import karrio.lib as lib
import karrio.core.models as models
import karrio.core.errors as errors
import karrio.providers.dhl_freight_sweden.error as error
import karrio.providers.dhl_freight_sweden.utils as provider_utils
import karrio.providers.dhl_freight_sweden.units as provider_units


# Per-product servability flags on the route response; products without a
# documented flag fall back to the general ``bookable`` flag.
PRODUCT_SERVICABILITY_FLAGS = {"118": "homeDeliveryParcel"}


class PostalCodeNotServableError(errors.ShippingSDKDetailedError):
    """Raised when the destination postal code is not servable for the product."""

    code = "SHIPPING_SDK_FIELD_ERROR"


def evaluate_route(route: dict, product: str = None) -> bool:
    """Return the servability of a product on a postal-code route response."""
    flag = PRODUCT_SERVICABILITY_FLAGS.get(product or "")
    return bool(route.get(flag or "bookable"))


def check_booking_route(
    response: typing.Optional[lib.Deserializable[dict]],
    settings: provider_utils.Settings,
    mode: str,
) -> typing.List[models.Message]:
    """Apply the booking pre-flight verdict to a route lookup.

    ``warn`` returns the verdict as shipment messages; ``enforce`` raises
    ``PostalCodeNotServableError`` on a definitive negative (an unservable
    product flag or a DHL 4xx error body) so the transport instruction is
    never sent. A lookup that could not produce a verdict — no response, a
    5xx, or an unrecognized body — yields a warning in both modes, so an
    API outage cannot block bookable shipments.
    """
    route = lib.identity(response.deserialize() if response else {})
    product = str((response.ctx.get("service") if response else None) or "")

    if _is_route(route):
        if evaluate_route(route, product):
            return []
        messages = [_servability_warning(route, product, settings)]
    else:
        messages = error.parse_error_response(route, settings) or [
            _unverified_warning(settings)
        ]
        if not _is_rejection(route):
            return messages

    if mode == provider_units.ServabilityMode.enforce:
        raise PostalCodeNotServableError(
            messages[0].message,
            details={
                "recipient.postal_code": dict(
                    code="not_servable", message=messages[0].message
                )
            },
        )

    return messages


def _is_rejection(route: dict) -> bool:
    # ``lib.error_decoder`` enriches error bodies with the HTTP status; only
    # a 4xx from the postalcodeapi is a definitive negative.
    status = route.get("http_status")
    return isinstance(status, int) and 400 <= status < 500


def _servability_warning(
    route: dict, product: str, settings: provider_utils.Settings
) -> models.Message:
    flag = PRODUCT_SERVICABILITY_FLAGS.get(product) or "bookable"

    return models.Message(
        carrier_name=settings.carrier_name,
        carrier_id=settings.carrier_id,
        code="postal_code_not_servable",
        message=(
            f"Destination postal code {route.get('postalCode')} is not "
            f"servable for product {product} ({flag} is false)"
        ),
        details=dict(postal_code=route.get("postalCode"), product=product),
    )


def _unverified_warning(settings: provider_utils.Settings) -> models.Message:
    return models.Message(
        carrier_name=settings.carrier_name,
        carrier_id=settings.carrier_id,
        code="address_validation_unavailable",
        message=(
            "Destination servability could not be verified (address "
            "validation API error); the booking proceeded without the check"
        ),
    )


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
    route fields yields no details; messages appear only when the body
    matches a known error shape, so a failure body outside those shapes
    (e.g. a 5xx) returns empty lists — detect it via ``details is None``.
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
