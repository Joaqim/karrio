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
        help_text="1-based page index",
    )
    x = serializers.FloatField(help_text="Millimetres from the page top-left")
    y = serializers.FloatField(help_text="Millimetres from the page top-left")
    width = serializers.FloatField(
        help_text="Draw width in millimetres before rotation",
    )
    height = serializers.FloatField(
        help_text="Draw height in millimetres before rotation",
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
        help_text="ZPL target density; ignored by the PDF backend",
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
        help_text="Anchor rectangle; omit only when a carrier/doc_type seed exists",
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


class StampedDocument(serializers.Serializer):
    doc_file = serializers.CharField(
        required=True,
        help_text="A base64 file content",
    )
    format = serializers.CharField(
        required=False,
        help_text="Format of the stamped document",
    )
