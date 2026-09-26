import attr
import jstruct
import typing


@attr.s(auto_attribs=True)
class AddressType:
    street: typing.Optional[str] = None
    cityName: typing.Optional[str] = None
    postalCode: typing.Optional[int] = None
    countryCode: typing.Optional[str] = None


@attr.s(auto_attribs=True)
class PartyType:
    id: typing.Optional[str] = None
    type: typing.Optional[str] = None
    name: typing.Optional[str] = None
    address: typing.Optional[AddressType] = jstruct.JStruct[AddressType]


@attr.s(auto_attribs=True)
class PayerCodeType:
    code: typing.Optional[str] = None
    location: typing.Optional[str] = None


@attr.s(auto_attribs=True)
class PieceType:
    id: typing.Optional[typing.List[str]] = None
    goodsType: typing.Optional[str] = None
    packageType: typing.Optional[str] = None
    numberOfPieces: typing.Optional[int] = None
    weight: typing.Optional[float] = None
    volume: typing.Optional[float] = None
    width: typing.Optional[float] = None
    height: typing.Optional[float] = None
    length: typing.Optional[float] = None
    stackable: typing.Optional[bool] = None


@attr.s(auto_attribs=True)
class ReferenceType:
    qualifier: typing.Optional[str] = None
    value: typing.Optional[str] = None


@attr.s(auto_attribs=True)
class TransportInstructionType:
    id: typing.Optional[str] = None
    productCode: typing.Optional[int] = None
    shippingDate: typing.Optional[str] = None
    pickupDate: typing.Optional[str] = None
    requestedDeliveryDate: typing.Optional[str] = None
    plannedDeliveryDate: typing.Optional[str] = None
    totalNumberOfPieces: typing.Optional[int] = None
    totalWeight: typing.Optional[float] = None
    totalVolume: typing.Optional[float] = None
    routingCode: typing.Optional[str] = None
    references: typing.Optional[typing.List[ReferenceType]] = jstruct.JList[ReferenceType]
    payerCode: typing.Optional[PayerCodeType] = jstruct.JStruct[PayerCodeType]
    parties: typing.Optional[typing.List[PartyType]] = jstruct.JList[PartyType]
    pieces: typing.Optional[typing.List[PieceType]] = jstruct.JList[PieceType]


@attr.s(auto_attribs=True)
class TransportInstructionResponseType:
    status: typing.Optional[str] = None
    transportInstruction: typing.Optional[TransportInstructionType] = jstruct.JStruct[TransportInstructionType]
