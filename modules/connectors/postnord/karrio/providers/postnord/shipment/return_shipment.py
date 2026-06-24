"""Karrio PostNord return shipment API implementation."""

# Return shipments allow customers to send packages back to the shipper.
# For carriers with a dedicated return API, implement the carrier-specific
# return endpoint here. For carriers that reuse the same shipment API
# for returns, you can delegate to the create shipment functions.

import typing
import karrio.lib as lib
import karrio.core.models as models
import karrio.providers.postnord.error as error
import karrio.providers.postnord.utils as provider_utils
import karrio.providers.postnord.units as provider_units


def parse_return_shipment_response(
    _response: lib.Deserializable[dict],
    settings: provider_utils.Settings,
) -> typing.Tuple[models.ShipmentDetails, typing.List[models.Message]]:
    """
    Parse return shipment response from carrier API.

    For carriers that reuse the shipment API for returns, you can import
    and delegate to parse_shipment_response from the create module:
        from karrio.providers.postnord.shipment.create import parse_shipment_response
        return parse_shipment_response(_response, settings)
    """
    response = _response.deserialize()
    messages = error.parse_error_response(response, settings)

    shipment = None  # TODO: extract return shipment details from response

    return shipment, messages


def return_shipment_request(
    payload: models.ShipmentRequest,
    settings: provider_utils.Settings,
) -> lib.Serializable:
    """
    Create a return shipment request for the carrier API.

    Note: The addresses have already been auto-swapped by the SDK fluent
    interface, so payload.shipper is the return origin (customer) and
    payload.recipient is the return destination (merchant/warehouse).

    For carriers that reuse the shipment API for returns, you can import
    and delegate to shipment_request from the create module:
        from karrio.providers.postnord.shipment.create import shipment_request
        return shipment_request(payload, settings)
    """
    # Convert karrio models to carrier-specific format
    shipper = lib.to_address(payload.shipper)
    recipient = lib.to_address(payload.recipient)
    packages = lib.to_packages(payload.parcels)
    service = provider_units.ShippingService.map(payload.service).value_or_key
    options = lib.to_shipping_options(
        payload.options,
        package_options=packages.options,
        initializer=provider_units.shipping_options_initializer,
    )

    # TODO: Create the carrier-specific return shipment request
    request = {}

    return lib.Serializable(request, lib.to_dict)
