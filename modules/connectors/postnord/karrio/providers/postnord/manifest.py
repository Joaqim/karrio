"""Karrio PostNord manifest implementation.

PostNord has no scan-form/end-of-day manifest endpoint (D2), so a Karrio
manifest is mapped to a physical pickup booking against
``/rest/shipment/v3/pickups``. The request is a pickup ``ediInstruction``
(``ManifestRequestType``); the response (``ManifestResponseType``) carries a
``bookingId`` and per-item ids. There is no scan-form document, so
``ManifestDetails.doc`` is empty and the pickup id(s) go into ``meta``.
"""

import datetime
import karrio.schemas.postnord.manifest_request as postnord_req
import karrio.schemas.postnord.manifest_response as postnord_res

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
    messages = error.parse_error_response(response, settings)

    has_manifest = bool(response.get("bookingId")) and not any(messages)
    manifest = _extract_details(response, settings) if has_manifest else None

    return manifest, messages


def _extract_details(
    data: dict,
    settings: provider_utils.Settings,
) -> models.ManifestDetails:
    response = lib.to_object(postnord_res.ManifestResponseType, data)
    informations = response.idInformation or []
    pickup_ids = [
        _id.value
        for info in informations
        for _id in (info.ids or [])
        if _id.value
    ]

    return models.ManifestDetails(
        carrier_id=settings.carrier_id,
        carrier_name=settings.carrier_name,
        doc=models.ManifestDocument(manifest=""),
        meta=dict(
            booking_id=response.bookingId,
            pickup_ids=pickup_ids or None,
        ),
    )


def manifest_request(
    payload: models.ManifestRequest,
    settings: provider_utils.Settings,
) -> lib.Serializable:
    address = lib.to_address(payload.address) if payload.address else None
    options = payload.options or {}

    party = lib.identity(
        postnord_req.PartyType(
            nameIdentification=postnord_req.NameIdentificationType(
                name=address.person_name or address.company_name,
                companyName=address.company_name,
            ),
            address=postnord_req.AddressType(
                streets=[_ for _ in [address.address_line1, address.address_line2] if _],
                postalCode=address.postal_code,
                city=address.city,
                countryCode=address.country_code,
            ),
            contact=postnord_req.ContactType(
                contactName=address.person_name,
                emailAddress=address.email,
                phoneNo=address.phone_number,
            ),
        )
        if address is not None
        else None
    )

    request = postnord_req.ManifestRequestType(
        messageDate=datetime.datetime.now().isoformat(timespec="seconds"),
        updateIndicator="Original",
        testIndicator=settings.test_mode,
        application=postnord_req.ApplicationType(name="Karrio"),
        shipment=[
            postnord_req.ShipmentType(
                dateAndTimes=lib.identity(
                    postnord_req.DateAndTimesType(
                        earliestPickupDate=options.get("earliest_pickup_date"),
                        latestPickupDate=options.get("latest_pickup_date"),
                    )
                    if options.get("earliest_pickup_date")
                    or options.get("latest_pickup_date")
                    else None
                ),
                parties=lib.identity(
                    postnord_req.PartiesType(
                        consignor=postnord_req.ConsignorType(
                            issuerCode=settings.issuer_code,
                            partyIdentification=lib.identity(
                                postnord_req.PartyIdentificationType(
                                    partyId=settings.customer_number,
                                    partyIdType="160",
                                )
                                if settings.customer_number
                                else None
                            ),
                            party=party,
                        ),
                        pickupParty=lib.identity(
                            postnord_req.PickupPartyType(party=party)
                            if party is not None
                            else None
                        ),
                    )
                    if party is not None or settings.customer_number
                    else None
                ),
            )
        ],
    )

    return lib.Serializable(request, lib.to_dict)
