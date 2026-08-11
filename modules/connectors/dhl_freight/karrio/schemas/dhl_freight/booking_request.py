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
    type: typing.Optional[str] = None
    id: typing.Optional[str] = None
    name: typing.Optional[str] = None
    contactName: typing.Optional[str] = None
    phone: typing.Optional[str] = None
    email: typing.Optional[str] = None
    address: typing.Optional[AddressType] = jstruct.JStruct[AddressType]


@attr.s(auto_attribs=True)
class PayerCodeType:
    code: typing.Optional[str] = None
    location: typing.Optional[str] = None


@attr.s(auto_attribs=True)
class PieceType:
    id: typing.Optional[typing.List[typing.Any]] = None
    goodsType: typing.Optional[str] = None
    packageType: typing.Optional[str] = None
    numberOfPieces: typing.Optional[int] = None
    weight: typing.Optional[int] = None
    volume: typing.Optional[float] = None
    width: typing.Optional[int] = None
    height: typing.Optional[int] = None
    length: typing.Optional[int] = None
    stackable: typing.Optional[bool] = None


@attr.s(auto_attribs=True)
class ReferenceType:
    qualifier: typing.Optional[str] = None
    value: typing.Optional[str] = None


@attr.s(auto_attribs=True)
class BookingRequestType:
    id: typing.Optional[str] = None
    productCode: typing.Optional[str] = None
    pickupDate: typing.Optional[str] = None
    totalNumberOfPieces: typing.Optional[int] = None
    totalWeight: typing.Optional[int] = None
    goodsDescription: typing.Optional[str] = None
    references: typing.Optional[typing.List[ReferenceType]] = jstruct.JList[ReferenceType]
    payerCode: typing.Optional[PayerCodeType] = jstruct.JStruct[PayerCodeType]
    parties: typing.Optional[typing.List[PartyType]] = jstruct.JList[PartyType]
    pieces: typing.Optional[typing.List[PieceType]] = jstruct.JList[PieceType]
