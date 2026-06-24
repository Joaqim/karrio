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
import karrio.providers.postnord.units as provider_units
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
    identifiers = payload.shipment_identifiers or []

    # The pickup endpoint (POST /rest/shipment/v3/pickups) takes a
    # pickupBooking whose shipment[] elements reuse the booking schema
    # (shipmentCustomsv2), so each shipment REQUIRES service, parties, and a
    # goodsItem with at least one items[] entry. The booked parcels to be
    # collected map to items keyed by their parcel/tracking id; when no
    # identifiers are supplied, PostNord allocates an id from itemId "0".
    items = [
        postnord_req.ItemType(
            itemIdentification=postnord_req.ItemIdentificationType(
                itemId=identifier,
            ),
        )
        for identifier in identifiers
    ] or [
        postnord_req.ItemType(
            itemIdentification=postnord_req.ItemIdentificationType(itemId="0"),
        )
    ]

    # Best-effort Return-Pickup probe: PostNord Return Pickup (basicServiceCode
    # "20") is a return SHIPMENT requiring a full consignor->consignee route
    # with SMS (smsNo) on both contacts, not a bare pickup. ManifestRequest
    # carries no recipient, so the consignee destination is taken from
    # options["destination"] when provided, otherwise it falls back to the
    # pickup address (a degenerate SE->SE route). A proper pickup likely needs a
    # real destination via the karrio Pickup API, pending the PostNord v3
    # reference manual.
    def _party(addr) -> typing.Optional[postnord_req.PartyType]:
        return lib.identity(
            postnord_req.PartyType(
                nameIdentification=postnord_req.NameIdentificationType(
                    name=addr.person_name or addr.company_name,
                    companyName=addr.company_name,
                ),
                address=postnord_req.AddressType(
                    streets=[_ for _ in [addr.address_line1, addr.address_line2] if _],
                    postalCode=addr.postal_code,
                    city=addr.city,
                    countryCode=addr.country_code,
                ),
                contact=postnord_req.ContactType(
                    contactName=addr.person_name,
                    emailAddress=addr.email,
                    phoneNo=addr.phone_number,
                    smsNo=addr.phone_number,
                ),
            )
            if addr is not None
            else None
        )

    destination = options.get("destination")
    consignee_address = lib.to_address(destination) if destination else address

    party = _party(address)
    consignee_party = _party(consignee_address)

    request = postnord_req.ManifestRequestType(
        messageDate=datetime.datetime.now().isoformat(timespec="seconds"),
        updateIndicator="Original",
        testIndicator=settings.test_mode,
        application=postnord_req.ApplicationType(
            name="Karrio",
            applicationId=lib.to_int(settings.application_id),
        ),
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
                service=postnord_req.ServiceType(
                    basicServiceCode=provider_units.ShippingService.postnord_return_pickup.value,
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
                        consignee=lib.identity(
                            postnord_req.ConsigneeType(
                                issuerCode=settings.issuer_code,
                                party=consignee_party,
                            )
                            if consignee_party is not None
                            else None
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
                goodsItem=[postnord_req.GoodsItemType(items=items)],
            )
        ],
    )

    return lib.Serializable(request, lib.to_dict)
