"""Karrio DHL Freight client proxy."""

import karrio.lib as lib
import karrio.api.proxy as proxy
import karrio.mappers.dhl_freight_sweden.settings as provider_settings


class Proxy(proxy.Proxy):
    settings: provider_settings.Settings

    def create_shipment(self, request: lib.Serializable) -> lib.Deserializable[str]:
        """Book a transport instruction, then print its documents.

        The Print API has no by-id request type in the generated schemas, so
        the printed documents are produced by feeding the Shipment echoed in
        the booking response (which now carries the shipment id and piece ids)
        into ``/print/printdocuments`` (PrintOptions.shipment).
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
                url=f"{self.settings.print_url}/print/printdocuments",
                data=lib.to_json(
                    dict(
                        # Re-send the shipment echoed by the booking response
                        # intact: it is the same Shipment model the Print API
                        # accepts, and round-tripping through the generated
                        # print ShipmentType silently drops optional fields it
                        # was not sampled with (totalNumberOfPieces, totalWeight).
                        shipment=instruction,
                        options=ctx.get("print_options") or {},
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
