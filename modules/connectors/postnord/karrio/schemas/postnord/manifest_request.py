import attr
import jstruct
import typing


@attr.s(auto_attribs=True)
class ApplicationType:
    name: typing.Optional[str] = None
    version: typing.Optional[str] = None
    applicationId: typing.Optional[int] = None


@attr.s(auto_attribs=True)
class DateAndTimesType:
    earliestPickupDate: typing.Optional[str] = None
    latestPickupDate: typing.Optional[str] = None


@attr.s(auto_attribs=True)
class FreeTextType:
    usageCode: typing.Optional[str] = None
    text: typing.Optional[str] = None


@attr.s(auto_attribs=True)
class GrossWeightType:
    value: typing.Optional[float] = None
    unit: typing.Optional[str] = None


@attr.s(auto_attribs=True)
class ItemIdentificationType:
    itemId: typing.Optional[str] = None
    itemIdType: typing.Optional[str] = None


@attr.s(auto_attribs=True)
class ItemType:
    itemIdentification: typing.Optional[ItemIdentificationType] = jstruct.JStruct[ItemIdentificationType]
    grossWeight: typing.Optional[GrossWeightType] = jstruct.JStruct[GrossWeightType]


@attr.s(auto_attribs=True)
class NumberOfPackageType:
    value: typing.Optional[int] = None


@attr.s(auto_attribs=True)
class GoodsItemType:
    packageTypeCode: typing.Optional[str] = None
    numberOfPackageTypeCodeItems: typing.Optional[NumberOfPackageType] = jstruct.JStruct[NumberOfPackageType]
    items: typing.Optional[typing.List[ItemType]] = jstruct.JList[ItemType]


@attr.s(auto_attribs=True)
class AddressType:
    streets: typing.Optional[typing.List[str]] = None
    postalCode: typing.Optional[int] = None
    city: typing.Optional[str] = None
    countryCode: typing.Optional[str] = None


@attr.s(auto_attribs=True)
class ContactType:
    contactName: typing.Optional[str] = None
    emailAddress: typing.Optional[str] = None
    phoneNo: typing.Optional[str] = None
    smsNo: typing.Optional[str] = None


@attr.s(auto_attribs=True)
class NameIdentificationType:
    name: typing.Optional[str] = None
    companyName: typing.Optional[str] = None


@attr.s(auto_attribs=True)
class PartyType:
    nameIdentification: typing.Optional[NameIdentificationType] = jstruct.JStruct[NameIdentificationType]
    address: typing.Optional[AddressType] = jstruct.JStruct[AddressType]
    contact: typing.Optional[ContactType] = jstruct.JStruct[ContactType]


@attr.s(auto_attribs=True)
class ConsigneeType:
    issuerCode: typing.Optional[str] = None
    party: typing.Optional[PartyType] = jstruct.JStruct[PartyType]


@attr.s(auto_attribs=True)
class PartyIdentificationType:
    partyId: typing.Optional[str] = None
    partyIdType: typing.Optional[int] = None


@attr.s(auto_attribs=True)
class ConsignorType:
    issuerCode: typing.Optional[str] = None
    partyIdentification: typing.Optional[PartyIdentificationType] = jstruct.JStruct[PartyIdentificationType]
    party: typing.Optional[PartyType] = jstruct.JStruct[PartyType]


@attr.s(auto_attribs=True)
class ReferenceType:
    referenceNo: typing.Optional[str] = None
    referenceType: typing.Optional[str] = None


@attr.s(auto_attribs=True)
class PickupPartyType:
    party: typing.Optional[PartyType] = jstruct.JStruct[PartyType]
    reference: typing.Optional[ReferenceType] = jstruct.JStruct[ReferenceType]


@attr.s(auto_attribs=True)
class PartiesType:
    consignor: typing.Optional[ConsignorType] = jstruct.JStruct[ConsignorType]
    consignee: typing.Optional[ConsigneeType] = jstruct.JStruct[ConsigneeType]
    pickupParty: typing.Optional[PickupPartyType] = jstruct.JStruct[PickupPartyType]


@attr.s(auto_attribs=True)
class ServiceType:
    basicServiceCode: typing.Optional[int] = None


@attr.s(auto_attribs=True)
class ShipmentIdentificationType:
    shipmentId: typing.Optional[str] = None


@attr.s(auto_attribs=True)
class ShipmentType:
    shipmentIdentification: typing.Optional[ShipmentIdentificationType] = jstruct.JStruct[ShipmentIdentificationType]
    dateAndTimes: typing.Optional[DateAndTimesType] = jstruct.JStruct[DateAndTimesType]
    service: typing.Optional[ServiceType] = jstruct.JStruct[ServiceType]
    numberOfPackages: typing.Optional[NumberOfPackageType] = jstruct.JStruct[NumberOfPackageType]
    totalGrossWeight: typing.Optional[GrossWeightType] = jstruct.JStruct[GrossWeightType]
    freeText: typing.Optional[typing.List[FreeTextType]] = jstruct.JList[FreeTextType]
    goodsItem: typing.Optional[typing.List[GoodsItemType]] = jstruct.JList[GoodsItemType]
    parties: typing.Optional[PartiesType] = jstruct.JStruct[PartiesType]


@attr.s(auto_attribs=True)
class ManifestRequestType:
    messageDate: typing.Optional[str] = None
    updateIndicator: typing.Optional[str] = None
    testIndicator: typing.Optional[bool] = None
    application: typing.Optional[ApplicationType] = jstruct.JStruct[ApplicationType]
    shipment: typing.Optional[typing.List[ShipmentType]] = jstruct.JList[ShipmentType]
