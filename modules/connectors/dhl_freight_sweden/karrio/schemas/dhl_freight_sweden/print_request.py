import attr
import jstruct
import typing


@attr.s(auto_attribs=True)
class PageOptionsType:
    pageType: typing.Optional[str] = None
    marginLeft: typing.Optional[int] = None
    marginTop: typing.Optional[int] = None
    padding: typing.Optional[int] = None
    paddingTop: typing.Optional[int] = None


@attr.s(auto_attribs=True)
class OptionsType:
    label: typing.Optional[bool] = None
    waybill: typing.Optional[bool] = None
    returnLabel: typing.Optional[bool] = None
    guarantee: typing.Optional[bool] = None
    shipmentList: typing.Optional[bool] = None
    shipmentListType: typing.Optional[str] = None
    qrCode: typing.Optional[bool] = None
    licensePlateBarCode: typing.Optional[str] = None
    itemStartSequence: typing.Optional[int] = None
    pageOptions: typing.Optional[PageOptionsType] = jstruct.JStruct[PageOptionsType]


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
    numberOfPieces: typing.Optional[int] = None
    weight: typing.Optional[float] = None


@attr.s(auto_attribs=True)
class ShipmentType:
    id: typing.Optional[str] = None
    productCode: typing.Optional[int] = None
    payerCode: typing.Optional[PayerCodeType] = jstruct.JStruct[PayerCodeType]
    parties: typing.Optional[typing.List[PartyType]] = jstruct.JList[PartyType]
    pieces: typing.Optional[typing.List[PieceType]] = jstruct.JList[PieceType]


@attr.s(auto_attribs=True)
class PrintRequestType:
    shipment: typing.Optional[ShipmentType] = jstruct.JStruct[ShipmentType]
    options: typing.Optional[OptionsType] = jstruct.JStruct[OptionsType]
