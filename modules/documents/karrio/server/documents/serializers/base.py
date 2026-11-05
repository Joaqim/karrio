import karrio.lib as lib
import karrio.core.utils.stamping as stamping
import karrio.server.serializers as serializers
import karrio.server.documents.models as models
import karrio.server.core.validators as validators


class TemplateRelatedObject(lib.StrEnum):
    shipment = "shipment"
    order = "order"
    other = "other"


class DocumentTemplateData(serializers.Serializer):
    name = serializers.CharField(max_length=255, help_text="The template name")
    slug = serializers.CharField(max_length=255, help_text="The template slug")
    template = serializers.CharField(help_text="The template content")
    active = serializers.BooleanField(default=True, help_text="disable template flag.")
    description = serializers.CharField(
        max_length=255, help_text="The template description", required=False
    )
    metadata = serializers.PlainDictField(
        help_text="The template metadata", required=False
    )
    options = serializers.PlainDictField(
        help_text="The template rendering options", required=False
    )
    related_object = serializers.ChoiceField(
        choices=TemplateRelatedObject,
        help_text="The template related object",
        required=False,
        default=TemplateRelatedObject.other,
    )


class DocumentTemplate(serializers.EntitySerializer, DocumentTemplateData):
    object_type = serializers.CharField(
        default="document-template", help_text="Specifies the object type"
    )
    preview_url = serializers.URLField(
        help_text="The template preview URL",
        required=False,
    )


class DocumentData(serializers.Serializer):
    template_id = serializers.CharField(
        help_text="The template name. **Required if template is not provided.**",
        required=False,
    )
    template = serializers.CharField(
        help_text="The template content. **Required if template_id is not provided.**",
        required=False,
    )
    doc_format = serializers.CharField(
        help_text="The format of the document",
        required=False,
    )
    doc_name = serializers.CharField(
        help_text="The file name",
        required=False,
    )
    data = serializers.PlainDictField(
        help_text="The template data",
        required=False,
        default={},
    )
    options = serializers.PlainDictField(
        help_text="The template rendering options",
        required=False,
    )


class GeneratedDocument(serializers.Serializer):
    template_id = serializers.CharField(
        help_text="The template name",
        required=False,
    )
    doc_format = serializers.CharField(
        help_text="The format of the document",
        required=False,
    )
    doc_name = serializers.CharField(
        help_text="The file name",
        required=False,
    )
    doc_file = serializers.CharField(
        help_text="A base64 file content",
        required=True,
    )


class StampPlacementData(serializers.Serializer):
    page = serializers.IntegerField(
        required=False,
        default=1,
        min_value=1,
        help_text="1-based PDF page or ZPL ^XA...^XZ format index",
    )
    unit = serializers.ChoiceField(
        choices=lib.STAMP_UNITS,
        required=False,
        default="mm",
        help_text=(
            "Unit of x, y, width and height: mm, pt (1/72 in), or px (printer "
            "dots at dpi for ZPL, pixels of the page rendered at dpi for PDF)"
        ),
    )
    x = serializers.FloatField(
        required=False,
        help_text=(
            "Offset from the page top-left, or from the located keyword when "
            "a keyword is supplied; required with y otherwise"
        ),
    )
    y = serializers.FloatField(
        required=False,
        help_text=(
            "Offset from the page top-left, or from the located keyword when "
            "a keyword is supplied; required with x otherwise"
        ),
    )
    width = serializers.FloatField(
        help_text="Box width before rotation; the image is fitted inside it",
    )
    height = serializers.FloatField(
        help_text="Box height before rotation; the image is fitted inside it",
    )
    rotation = serializers.FloatField(
        required=False,
        default=0,
        help_text=(
            "Degrees clockwise; the rotated extent's top-left corner is "
            "anchored at (x, y)"
        ),
    )
    dpi = serializers.IntegerField(
        required=False,
        default=203,
        help_text="ZPL target density, and the render density of px on PDF",
    )


class StampData(serializers.Serializer):
    document = serializers.CharField(
        help_text="base64 carrier document (PDF or ZPL); format is sniffed",
    )
    image = serializers.CharField(
        help_text="base64 PNG to composite (signature or letterhead)",
    )
    placement = StampPlacementData(
        required=False,
        help_text=(
            "Anchor rectangle, or the keyword geometry when a keyword is "
            "supplied; omit only when a keyword or a carrier/doc_type seed "
            "resolves it"
        ),
    )
    keyword = serializers.CharField(
        required=False,
        help_text=(
            "Text printed on the carrier document that the stamp is anchored "
            "to; the placement's x and y become offsets from it"
        ),
    )
    layer = serializers.ChoiceField(
        choices=["overlay", "underlay"],
        required=False,
        default="overlay",
        help_text="overlay (signature) or underlay (letterhead, PDF only)",
    )
    carrier = serializers.CharField(
        required=False,
        help_text="Registry seed key segment; ignored when placement is supplied",
    )
    doc_type = serializers.CharField(
        required=False,
        help_text="ShippingDocumentCategory name keying the registry seed",
    )
    format = serializers.CharField(
        required=False,
        help_text="Optional format hint; the document bytes are sniffed regardless",
    )
    date = serializers.CharField(
        required=False,
        help_text="Pre-formatted date string composited preceding the image",
    )
    graphic_name = serializers.RegexField(
        regex=stamping.ZPL_GRAPHIC_NAME_PATTERN,
        required=False,
        help_text=(
            "ZPL ~DY/^XG send-once cache opt-in, for example R:SIGN.GRF; "
            "ignored by the PDF backend"
        ),
    )
    page = serializers.IntegerField(
        required=False,
        min_value=1,
        help_text=(
            "One-based PDF page or ZPL format on which the seed or keyword is "
            "applied; rejected with a placement carrying x and y and no keyword"
        ),
    )
    compression = serializers.ChoiceField(
        choices=lib.STAMP_COMPRESSIONS,
        required=False,
        help_text="ZPL graphic compression; omit for uncompressed hex",
    )

    def validate(self, data):
        placement = data.get("placement")
        if placement is None or data.get("keyword"):
            return data

        anchors = [field for field in ("x", "y") if placement.get(field) is not None]
        if len(anchors) == 1:
            (given,) = anchors
            missing = "y" if given == "x" else "x"
            raise serializers.ValidationError(
                {
                    "placement": (
                        f"StampPlacement.{missing} is required with "
                        f"StampPlacement.{given} unless a keyword is supplied"
                    )
                }
            )
        if not anchors:
            raise serializers.ValidationError(
                {
                    "placement": "A placement without x and y needs a keyword to locate it"
                }
            )

        return data


class StampedDocument(serializers.Serializer):
    doc_file = serializers.CharField(
        required=True,
        help_text="A base64 file content",
    )
    format = serializers.CharField(
        required=False,
        help_text="Format of the stamped document",
    )
