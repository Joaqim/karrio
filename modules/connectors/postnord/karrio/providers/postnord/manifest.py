"""Karrio PostNord manifest implementation.

PostNord has no scan-form / end-of-day manifest (D2) endpoint: the Booking API
exposes label and pickup booking, but nothing that produces a consolidated
manifest document over a set of shipments. Manifesting is therefore explicitly
unsupported. To collect already-booked parcels, use Karrio's Pickup API
(``schedule_pickup`` → ``POST /rest/shipment/v3/pickups``) instead.

The request is a no-op; the parse surfaces an explicit Message and no manifest
details, mirroring the carrier's other unsupported-operation placeholders.
"""

import typing
import karrio.lib as lib
import karrio.core.models as models
import karrio.providers.postnord.error as error
import karrio.providers.postnord.utils as provider_utils


def parse_manifest_response(
    _response: lib.Deserializable[dict],
    settings: provider_utils.Settings,
) -> typing.Tuple[models.ManifestDetails, typing.List[models.Message]]:
    response = _response.deserialize()
    messages = [
        *error.parse_error_response(response, settings),
        models.Message(
            carrier_id=settings.carrier_id,
            carrier_name=settings.carrier_name,
            message=(
                "PostNord has no manifest/scan-form endpoint; "
                "use Pickup scheduling instead."
            ),
            code="not_supported",
        ),
    ]

    return None, messages


def manifest_request(
    payload: models.ManifestRequest,
    settings: provider_utils.Settings,
) -> lib.Serializable:
    return lib.Serializable({"shipmentIdentifiers": payload.shipment_identifiers}, lib.to_dict)
