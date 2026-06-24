import attr
import jstruct
import typing


@attr.s(auto_attribs=True)
class ConsignType:
    postalCode: typing.Optional[int] = None
    city: typing.Optional[str] = None
    countryCode: typing.Optional[str] = None


@attr.s(auto_attribs=True)
class DimensionsType:
    height: typing.Optional[float] = None
    width: typing.Optional[float] = None
    length: typing.Optional[float] = None
    unit: typing.Optional[str] = None


@attr.s(auto_attribs=True)
class GrossWeightType:
    value: typing.Optional[float] = None
    unit: typing.Optional[str] = None


@attr.s(auto_attribs=True)
class PackageType:
    packageTypeCode: typing.Optional[str] = None
    grossWeight: typing.Optional[GrossWeightType] = jstruct.JStruct[GrossWeightType]
    dimensions: typing.Optional[DimensionsType] = jstruct.JStruct[DimensionsType]


@attr.s(auto_attribs=True)
class RateRequestType:
    issuerCode: typing.Optional[str] = None
    services: typing.Optional[typing.List[int]] = None
    consignor: typing.Optional[ConsignType] = jstruct.JStruct[ConsignType]
    consignee: typing.Optional[ConsignType] = jstruct.JStruct[ConsignType]
    packages: typing.Optional[typing.List[PackageType]] = jstruct.JList[PackageType]
