"""Karrio DHL Freight client proxy."""

import typing

import karrio.lib as lib
import karrio.api.proxy as proxy
import karrio.core.models as models
import karrio.mappers.dhl_freight_sweden.settings as provider_settings
import karrio.providers.dhl_freight_sweden.address as provider_address
import karrio.schemas.dhl_freight_sweden.print_request_by_id as dhl_freight_sweden_print
from karrio.universal.mappers.rating_proxy import RatingMixinProxy


class Proxy(proxy.Proxy):
    settings: provider_settings.Settings

    def validate_address(self, request: lib.Serializable) -> lib.Deserializable[dict]:
        """Look up the postal-code route for an address (PostalCodes API).

        GETs ``/postalcodes/{countryCode}/{postalCode}/route`` with the
        standard client-key header; the route body feeds the unified
        ``AddressValidationDetails`` through the shared evaluation helpers.
        """
        params = request.serialize()
        response = lib.request(
            url=f"{self.settings.postal_code_api_url}/postalcodes/"
            f"{str(params.get('country_code') or '').upper()}/"
            f"{params.get('postal_code')}/route",
            trace=self.trace_as("json"),
            method="GET",
            headers={"client-key": self.settings.client_key},
            on_error=lib.error_decoder,
        )

        return lib.Deserializable(response, lib.to_dict, request.ctx)

    def get_rates(self, request: lib.Serializable) -> lib.Deserializable:
        """Resolve static prices from the server-side rate sheet.

        The SE API Farm pricequote API is out of Phase 0 scope, so rating
        delegates to the universal rating mixin against the service levels
        seeded in ``units.DEFAULT_SERVICES``; no carrier call is made.
        """
        return RatingMixinProxy.get_rates(self, request)

    def create_shipment(self, request: lib.Serializable) -> lib.Deserializable[str]:
        """Book a transport instruction, then print its documents by id.

        The shipment id only exists once the booking response returns, so the
        by-id print request is completed here with the runtime id and posted
        to ``/print/printdocumentsbyid`` — the booked shipment is not re-sent.
        A config-gated address-validation pre-flight runs first; its verdict
        travels to the parser as an optional trailing element.
        """
        ctx = request.ctx or {}
        headers = {
            "Content-Type": "application/json",
            "client-key": self.settings.client_key,
        }
        warnings = self._destination_route_messages(request)

        booking = lib.request(
            url=f"{self.settings.transport_instruction_url}/transportinstruction/sendtransportinstruction",
            data=lib.to_json(request.serialize()),
            trace=self.trace_as("json"),
            method="POST",
            headers=headers,
            on_error=lib.error_decoder,
        )

        instruction = (lib.to_dict(booking) or {}).get("transportInstruction") or {}
        shipment_id = instruction.get("id")

        printed = lib.identity(
            lib.request(
                url=f"{self.settings.print_url}/print/printdocumentsbyid",
                data=lib.to_json(
                    lib.to_dict(
                        dhl_freight_sweden_print.PrintRequestByIDType(
                            shipmentIds=[shipment_id],
                            options=lib.to_object(
                                dhl_freight_sweden_print.OptionsType,
                                ctx.get("print_options") or {},
                            ),
                        )
                    )
                ),
                trace=self.trace_as("json"),
                method="POST",
                headers=headers,
                on_error=lib.error_decoder,
            )
            if shipment_id
            else "{}"
        )

        return lib.Deserializable(
            [booking, printed, *warnings],
            lambda responses: [lib.to_dict(response) for response in responses],
            ctx,
        )

    def _destination_route_messages(
        self, request: lib.Serializable
    ) -> typing.List[models.Message]:
        """Run the config-gated destination servability pre-flight.

        Off mode, products without a documented per-product flag, non-Swedish
        consignees, and missing postal codes skip the check with no HTTP
        call; the mode branch and fail-open semantics live in the provider's
        ``check_booking_route``.
        """
        mode = self.settings.connection_config.address_validation.state or "off"
        destination = _booking_destination(lib.to_dict(request.serialize()))

        if mode == "off" or destination is None:
            return []

        lookup = lib.Serializable(
            dict(
                country_code=destination["country_code"],
                postal_code=destination["postal_code"],
            ),
            lib.to_dict,
            dict(service=destination["product"]),
        )
        # A route-lookup failure (network error, timeout, unparseable error
        # body) must not block the booking, so it fails open to a warning.
        response = lib.failsafe(lambda: self.validate_address(lookup))

        return provider_address.check_booking_route(response, self.settings, mode)

    def find_product_matches(
        self, request: lib.Serializable
    ) -> lib.Deserializable[dict]:
        """Look up matching products for an address pair (connector-local).

        POSTs the serialized ``MatchCriteria`` body to the Product API's
        ``/productmatches`` endpoint with the standard client-key headers; the
        caller invokes this duck-typed method directly on the proxy, as with
        the postnord ``find_service_points`` precedent.
        """
        response = lib.request(
            url=f"{self.settings.product_api_url}/productmatches",
            data=lib.to_json(request.serialize()),
            trace=self.trace_as("json"),
            method="POST",
            headers={
                "Content-Type": "application/json",
                "client-key": self.settings.client_key,
            },
            on_error=lib.error_decoder,
        )

        return lib.Deserializable(response, lib.to_dict)

    def find_service_points(
        self, request: lib.Serializable
    ) -> lib.Deserializable[dict]:
        """Look up the nearest service points for an address (connector-local).

        POSTs the serialized ``NearestServicePointRequest`` body to the
        Servicepoint API's ``findnearestservicepoints`` endpoint with the
        standard client-key headers; the caller invokes this duck-typed method
        directly on the proxy, as with the postnord precedent.
        """
        response = lib.request(
            url=f"{self.settings.service_point_locator_url}/servicepoint/findnearestservicepoints",
            data=lib.to_json(request.serialize()),
            trace=self.trace_as("json"),
            method="POST",
            headers={
                "Content-Type": "application/json",
                "client-key": self.settings.client_key,
            },
            on_error=lib.error_decoder,
        )

        return lib.Deserializable(response, lib.to_dict)


def _booking_destination(data: dict) -> typing.Optional[dict]:
    """Consignee destination of a serialized transport instruction.

    Returns None unless the product has a documented per-product servability
    flag and the consignee is Swedish with a postal code — the pre-flight
    trigger scope.
    """
    parties = data.get("parties") or []
    consignee = next(
        (party for party in parties if party.get("type") == "Consignee"), None
    )
    address = (consignee or {}).get("address") or {}
    product = str(data.get("productCode") or "")
    postal_code = address.get("postalCode")

    if (
        product not in provider_address.PRODUCT_SERVICABILITY_FLAGS
        or str(address.get("countryCode") or "").upper() != "SE"
        or not postal_code
    ):
        return None

    return dict(
        country_code=str(address.get("countryCode")).upper(),
        postal_code=str(postal_code),
        product=product,
    )
