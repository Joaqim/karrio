import attr
import jstruct
import typing


@attr.s(auto_attribs=True)
class LabelsIDSRequestElementType:
    id: typing.Optional[str] = None
    labelType: typing.Optional[str] = None
