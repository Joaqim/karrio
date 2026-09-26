"""Karrio PostNord pickup scheduling implementation.

PostNord books a courier collection through ``POST /rest/shipment/v3/pickups``.
The pickups endpoint reuses the booking schema (``pickupBooking`` wrapping a
``shipmentCustomsv2`` array), but only ``consignor`` is a required party, so a
pickup is modeled as the courier-collection it is: the ``PickupRequest.address``
is the collection location, mapped to both ``consignor.party`` and
``pickupParty.party``. No consignee/destination is sent — a pickup carries a
pickup address and a time window, not a route.

The response (``PickupResponseType``) carries a ``bookingId`` (used as the
Karrio ``confirmation_number``) and per-item ids/references under
``idInformation[]``.
"""

import datetime
import karrio.schemas.postnord.pickup_request as postnord_req
import karrio.schemas.postnord.pickup_response as postnord_res

import typing
import karrio.lib as lib
import karrio.core.models as models
import karrio.providers.postnord.error as error
import karrio.providers.postnord.units as provider_units
import karrio.providers.postnord.utils as provider_utils


def parse_pickup_response(
    _response: lib.Deserializable[dict],
    settings: provider_utils.Settings,
) -> typing.Tuple[models.PickupDetails, typing.List[models.Message]]:
    response = _response.deserialize()
    messages = error.parse_error_response(response, settings)

    has_pickup = bool(response.get("bookingId")) and not any(messages)
    pickup = _extract_details(response, settings) if has_pickup else None

    return pickup, messages


def _extract_details(
    data: dict,
    settings: provider_utils.Settings,
) -> models.PickupDetails:
    response = lib.to_object(postnord_res.PickupResponseType, data)
    informations = response.idInformation or []
    pickup_ids = [
        _id.value
        for info in informations
        for _id in (info.ids or [])
        if _id.value
    ]
    reference_nos = [
        ref.referenceNo
        for info in informations
        for ref in (getattr(info.references, "shipment", None) or [])
        if ref.referenceNo
    ]

    return models.PickupDetails(
        carrier_id=settings.carrier_id,
        carrier_name=settings.carrier_name,
        confirmation_number=response.bookingId,
        id=lib.identity(pickup_ids[0] if pickup_ids else None),
        meta=dict(
            booking_id=response.bookingId,
            pickup_ids=pickup_ids or None,
            references=reference_nos or None,
        ),
    )


def pickup_request(
    payload: models.PickupRequest,
    settings: provider_utils.Settings,
) -> lib.Serializable:
    address = lib.to_address(payload.address)
    options = payload.options or {}
    identifiers = payload.shipment_identifiers or []
    service = options.get("service") or provider_units.ShippingService.postnord_return_pickup.value

    # The booked parcels to be collected map to goodsItem items keyed by their
    # parcel/tracking id; absent any identifier, PostNord allocates from "0".
    items = [
        postnord_req.ItemType(
            itemIdentification=postnord_req.ItemIdentificationType(itemId=identifier),
        )
        for identifier in identifiers
    ] or [
        postnord_req.ItemType(
            itemIdentification=postnord_req.ItemIdentificationType(itemId="0"),
        )
    ]

    party = postnord_req.PartyType(
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
            smsNo=address.phone_number,
        ),
    )

    instruction = lib.text(payload.instruction or payload.package_location)

    request = postnord_req.PickupRequestType(
        messageDate=datetime.datetime.now().isoformat(timespec="seconds"),
        updateIndicator="Original",
        testIndicator=settings.test_mode,
        application=postnord_req.ApplicationType(
            name="Karrio",
            applicationId=lib.to_int(settings.application_id),
        ),
        shipment=[
            postnord_req.ShipmentType(
                dateAndTimes=postnord_req.DateAndTimesType(
                    earliestPickupDate=_window(payload.pickup_date, payload.ready_time),
                    latestPickupDate=_window(payload.pickup_date, payload.closing_time),
                ),
                service=postnord_req.ServiceType(basicServiceCode=service),
                freeText=lib.identity(
                    [postnord_req.FreeTextType(usageCode="PICKUP", text=instruction)]
                    if instruction
                    else None
                ),
                goodsItem=[postnord_req.GoodsItemType(items=items)],
                parties=postnord_req.PartiesType(
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
                    pickupParty=postnord_req.PickupPartyType(party=party),
                ),
            )
        ],
    )

    return lib.Serializable(request, lib.to_dict)


def _window(date: typing.Optional[str], time: typing.Optional[str]) -> typing.Optional[str]:
    """Combine a pickup date and a time-of-day into an ISO datetime.

    ``PickupRequest`` carries ``pickup_date`` (a date) and ``ready_time`` /
    ``closing_time`` (times of day) separately; PostNord's
    ``earliestPickupDate`` / ``latestPickupDate`` are single ISO datetimes.
    When the time already encodes a full datetime it is used as-is.
    """
    if not date and not time:
        return None
    if time and "T" in str(time):
        return time
    if date and time:
        return f"{date}T{time}"
    return date or time
