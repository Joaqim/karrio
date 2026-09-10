"""Karrio DHL Freight client proxy."""

import karrio.lib as lib
import karrio.api.proxy as proxy
import karrio.mappers.dhl_freight_sweden.settings as provider_settings
import karrio.schemas.dhl_freight_sweden.print_request_by_id as dhl_freight_sweden_print
from karrio.universal.mappers.rating_proxy import RatingMixinProxy


class Proxy(proxy.Proxy):
    settings: provider_settings.Settings

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
        """
        ctx = request.ctx or {}
        headers = {
            "Content-Type": "application/json",
            "client-key": self.settings.client_key,
        }

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
            [booking, printed],
            lambda responses: [
                lib.to_dict(responses[0]),
                lib.to_dict(responses[1]),
            ],
            ctx,
        )

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
