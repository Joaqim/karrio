import attr
import jstruct
import typing


@attr.s(auto_attribs=True)
class ShipmentType:
    id: typing.Optional[str] = None
    productCode: typing.Optional[str] = None
    parties: typing.Optional[typing.List[typing.Any]] = None
    pieces: typing.Optional[typing.List[typing.Any]] = None


@attr.s(auto_attribs=True)
class BookingResponseType:
    status: typing.Optional[str] = None
    shipment: typing.Optional[ShipmentType] = jstruct.JStruct[ShipmentType]
