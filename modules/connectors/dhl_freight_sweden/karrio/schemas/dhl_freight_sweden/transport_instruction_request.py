import attr
import jstruct
import typing


@attr.s(auto_attribs=True)
class DoorstepDeliveryType:
    accessCode: typing.Optional[int] = None


@attr.s(auto_attribs=True)
class InsuranceType:
    value: typing.Optional[float] = None
    currency: typing.Optional[str] = None


@attr.s(auto_attribs=True)
class AdditionalServicesType:
    notification: typing.Optional[bool] = None
    preAdvice: typing.Optional[bool] = None
    tailLiftUnloading: typing.Optional[bool] = None
    doorstepDelivery: typing.Optional[DoorstepDeliveryType] = jstruct.JStruct[DoorstepDeliveryType]
    insurance: typing.Optional[InsuranceType] = jstruct.JStruct[InsuranceType]


@attr.s(auto_attribs=True)
class CustomsCommodityType:
    countryCodeOfOrigin: typing.Optional[str] = None
    customsValueCurrency: typing.Optional[str] = None
    customsValue: typing.Optional[float] = None
    hsItemId: typing.Optional[int] = None
    commodityDescription: typing.Optional[str] = None
    procedureCode: typing.Optional[int] = None
    netWeight: typing.Optional[float] = None
    numberOfUnits: typing.Optional[int] = None
    goodsDescription: typing.Optional[str] = None


@attr.s(auto_attribs=True)
class CustomsDocumentType:
    id: typing.Optional[str] = None
    type: typing.Optional[str] = None
    transportMovement: typing.Optional[str] = None
    invoiceDate: typing.Optional[str] = None
    invoiceCurrency: typing.Optional[str] = None
    invoiceAmount: typing.Optional[float] = None
    eori: typing.Optional[str] = None


@attr.s(auto_attribs=True)
class CustomsInformationType:
    customsDocuments: typing.Optional[typing.List[CustomsDocumentType]] = jstruct.JList[CustomsDocumentType]
    customsCommodities: typing.Optional[typing.List[CustomsCommodityType]] = jstruct.JList[CustomsCommodityType]


@attr.s(auto_attribs=True)
class AddressType:
    street: typing.Optional[str] = None
    streetNumber: typing.Optional[int] = None
    additionalAddressInfo: typing.Optional[str] = None
    cityName: typing.Optional[str] = None
    postalCode: typing.Optional[int] = None
    countryCode: typing.Optional[str] = None
    accessCode: typing.Optional[int] = None


@attr.s(auto_attribs=True)
class VatType:
    countryCode: typing.Optional[str] = None
    number: typing.Optional[str] = None


@attr.s(auto_attribs=True)
class PartyType:
    id: typing.Optional[str] = None
    type: typing.Optional[str] = None
    vatEoriSocialSecurityNumber: typing.Optional[str] = None
    name: typing.Optional[str] = None
    contactName: typing.Optional[str] = None
    references: typing.Optional[typing.List[str]] = None
    address: typing.Optional[AddressType] = jstruct.JStruct[AddressType]
    phone: typing.Optional[str] = None
    email: typing.Optional[str] = None
    vat: typing.Optional[VatType] = jstruct.JStruct[VatType]
    subType: typing.Optional[str] = None


@attr.s(auto_attribs=True)
class PayerCodeType:
    code: typing.Optional[str] = None
    location: typing.Optional[str] = None


@attr.s(auto_attribs=True)
class PieceType:
    id: typing.Optional[typing.List[str]] = None
    goodsType: typing.Optional[str] = None
    packageType: typing.Optional[str] = None
    marksAndNumbers: typing.Optional[str] = None
    numberOfPieces: typing.Optional[int] = None
    weight: typing.Optional[float] = None
    volume: typing.Optional[float] = None
    loadingMeters: typing.Optional[float] = None
    palletPlaces: typing.Optional[float] = None
    width: typing.Optional[float] = None
    height: typing.Optional[float] = None
    length: typing.Optional[float] = None
    stackable: typing.Optional[bool] = None


@attr.s(auto_attribs=True)
class ReferenceType:
    qualifier: typing.Optional[str] = None
    value: typing.Optional[str] = None


@attr.s(auto_attribs=True)
class TransportInstructionRequestType:
    id: typing.Optional[str] = None
    productCode: typing.Optional[int] = None
    shippingDate: typing.Optional[str] = None
    pickupDate: typing.Optional[str] = None
    requestedDeliveryDate: typing.Optional[str] = None
    plannedDeliveryDate: typing.Optional[str] = None
    pickupInstruction: typing.Optional[str] = None
    deliveryInstruction: typing.Optional[str] = None
    totalNumberOfPieces: typing.Optional[int] = None
    totalWeight: typing.Optional[float] = None
    totalVolume: typing.Optional[float] = None
    totalLoadingMeters: typing.Optional[float] = None
    totalPalletPlaces: typing.Optional[float] = None
    routingCode: typing.Optional[str] = None
    references: typing.Optional[typing.List[ReferenceType]] = jstruct.JList[ReferenceType]
    payerCode: typing.Optional[PayerCodeType] = jstruct.JStruct[PayerCodeType]
    parties: typing.Optional[typing.List[PartyType]] = jstruct.JList[PartyType]
    pieces: typing.Optional[typing.List[PieceType]] = jstruct.JList[PieceType]
    additionalServices: typing.Optional[AdditionalServicesType] = jstruct.JStruct[AdditionalServicesType]
    customsInformation: typing.Optional[CustomsInformationType] = jstruct.JStruct[CustomsInformationType]
