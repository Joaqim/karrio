import attr
import jstruct
import typing


@attr.s(auto_attribs=True)
class ApplicationType:
    name: typing.Optional[str] = None
    version: typing.Optional[str] = None
    applicationId: typing.Optional[int] = None


@attr.s(auto_attribs=True)
class GoodsValueType:
    amount: typing.Optional[float] = None
    currency: typing.Optional[str] = None


@attr.s(auto_attribs=True)
class CashOnDeliveryType:
    transactionIdentifier: typing.Optional[str] = None
    codType: typing.Optional[str] = None
    codAmount: typing.Optional[GoodsValueType] = jstruct.JStruct[GoodsValueType]


@attr.s(auto_attribs=True)
class DateAndTimesType:
    loadingDate: typing.Optional[str] = None


@attr.s(auto_attribs=True)
class FreeTextType:
    usageCode: typing.Optional[str] = None
    text: typing.Optional[str] = None


@attr.s(auto_attribs=True)
class TotalGrossWeightType:
    value: typing.Optional[float] = None
    unit: typing.Optional[str] = None


@attr.s(auto_attribs=True)
class DimensionsType:
    height: typing.Optional[TotalGrossWeightType] = jstruct.JStruct[TotalGrossWeightType]
    width: typing.Optional[TotalGrossWeightType] = jstruct.JStruct[TotalGrossWeightType]
    length: typing.Optional[TotalGrossWeightType] = jstruct.JStruct[TotalGrossWeightType]


@attr.s(auto_attribs=True)
class ItemIdentificationType:
    itemId: typing.Optional[str] = None
    itemIdType: typing.Optional[str] = None


@attr.s(auto_attribs=True)
class ItemReferenceType:
    referenceNo: typing.Optional[str] = None
    referenceType: typing.Optional[str] = None


@attr.s(auto_attribs=True)
class ItemType:
    itemIdentification: typing.Optional[ItemIdentificationType] = jstruct.JStruct[ItemIdentificationType]
    references: typing.Optional[typing.List[ItemReferenceType]] = jstruct.JList[ItemReferenceType]
    dimensions: typing.Optional[DimensionsType] = jstruct.JStruct[DimensionsType]
    grossWeight: typing.Optional[TotalGrossWeightType] = jstruct.JStruct[TotalGrossWeightType]
    volume: typing.Optional[TotalGrossWeightType] = jstruct.JStruct[TotalGrossWeightType]
    itemValue: typing.Optional[GoodsValueType] = jstruct.JStruct[GoodsValueType]


@attr.s(auto_attribs=True)
class NumberOfPackageType:
    value: typing.Optional[int] = None


@attr.s(auto_attribs=True)
class GoodsItemType:
    marking: typing.Optional[str] = None
    goodsDescription: typing.Optional[str] = None
    packageTypeCode: typing.Optional[str] = None
    numberOfPackageTypeCodeItems: typing.Optional[NumberOfPackageType] = jstruct.JStruct[NumberOfPackageType]
    references: typing.Optional[typing.List[ItemReferenceType]] = jstruct.JList[ItemReferenceType]
    items: typing.Optional[typing.List[ItemType]] = jstruct.JList[ItemType]


@attr.s(auto_attribs=True)
class InsuranceType:
    typeOfInsurance: typing.Optional[str] = None
    insuranceAmount: typing.Optional[GoodsValueType] = jstruct.JStruct[GoodsValueType]


@attr.s(auto_attribs=True)
class AddressType:
    streets: typing.Optional[typing.List[str]] = None
    postalCode: typing.Optional[int] = None
    placeName: typing.Optional[str] = None
    state: typing.Optional[str] = None
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
    careOfName: typing.Optional[str] = None


@attr.s(auto_attribs=True)
class PartyType:
    nameIdentification: typing.Optional[NameIdentificationType] = jstruct.JStruct[NameIdentificationType]
    address: typing.Optional[AddressType] = jstruct.JStruct[AddressType]
    contact: typing.Optional[ContactType] = jstruct.JStruct[ContactType]


@attr.s(auto_attribs=True)
class PartyIdentificationType:
    partyId: typing.Optional[str] = None
    partyIdType: typing.Optional[int] = None


@attr.s(auto_attribs=True)
class ConsignType:
    issuerCode: typing.Optional[str] = None
    partyIdentification: typing.Optional[PartyIdentificationType] = jstruct.JStruct[PartyIdentificationType]
    party: typing.Optional[PartyType] = jstruct.JStruct[PartyType]


@attr.s(auto_attribs=True)
class PartiesType:
    consignor: typing.Optional[ConsignType] = jstruct.JStruct[ConsignType]
    consignee: typing.Optional[ConsignType] = jstruct.JStruct[ConsignType]


@attr.s(auto_attribs=True)
class ShipmentReferenceType:
    referenceNo: typing.Optional[str] = None
    referenceType: typing.Optional[str] = None
    referenceDesc: typing.Optional[str] = None


@attr.s(auto_attribs=True)
class ServiceType:
    basicServiceCode: typing.Optional[int] = None
    additionalServiceCode: typing.Optional[typing.List[str]] = None


@attr.s(auto_attribs=True)
class ShipmentIdentificationType:
    shipmentId: typing.Optional[str] = None


@attr.s(auto_attribs=True)
class ShipmentType:
    shipmentIdentification: typing.Optional[ShipmentIdentificationType] = jstruct.JStruct[ShipmentIdentificationType]
    dateAndTimes: typing.Optional[DateAndTimesType] = jstruct.JStruct[DateAndTimesType]
    service: typing.Optional[ServiceType] = jstruct.JStruct[ServiceType]
    cashOnDelivery: typing.Optional[CashOnDeliveryType] = jstruct.JStruct[CashOnDeliveryType]
    insurance: typing.Optional[InsuranceType] = jstruct.JStruct[InsuranceType]
    goodsValue: typing.Optional[GoodsValueType] = jstruct.JStruct[GoodsValueType]
    freeText: typing.Optional[typing.List[FreeTextType]] = jstruct.JList[FreeTextType]
    numberOfPackages: typing.Optional[NumberOfPackageType] = jstruct.JStruct[NumberOfPackageType]
    totalGrossWeight: typing.Optional[TotalGrossWeightType] = jstruct.JStruct[TotalGrossWeightType]
    references: typing.Optional[typing.List[ShipmentReferenceType]] = jstruct.JList[ShipmentReferenceType]
    parties: typing.Optional[PartiesType] = jstruct.JStruct[PartiesType]
    goodsItem: typing.Optional[typing.List[GoodsItemType]] = jstruct.JList[GoodsItemType]


@attr.s(auto_attribs=True)
class ShipmentRequestType:
    messageDate: typing.Optional[str] = None
    updateIndicator: typing.Optional[str] = None
    testIndicator: typing.Optional[bool] = None
    application: typing.Optional[ApplicationType] = jstruct.JStruct[ApplicationType]
    shipment: typing.Optional[typing.List[ShipmentType]] = jstruct.JList[ShipmentType]
