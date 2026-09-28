import django.urls as urls
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response

import karrio.lib as lib
import karrio.core.models as core_models
import karrio.core.utils.helpers as helpers
import karrio.server.openapi as openapi
import karrio.server.core.views.api as api
import karrio.server.documents.serializers as serializers
from karrio.server.core.logging import logger

ENDPOINT_ID = "&&&&@@"  # unique operation-id prefix; must not collide with others


def _to_placement(placement):
    """Build the SDK StampPlacement from validated placement data, if supplied."""
    if placement is None:
        return None
    return lib.StampPlacement(**placement)


class DocumentStamper(api.BaseAPIView):
    # Skip LoggingMixin: responses include base64-encoded documents that bloat
    # the APILogIndex table, exactly as the DocumentGenerator response does.

    @openapi.extend_schema(
        tags=["Documents"],
        operation_id=f"{ENDPOINT_ID}stampDocument",
        summary="Stamp a document",
        request=serializers.StampData(),
        responses={
            201: serializers.StampedDocument(),
            400: serializers.ErrorResponse(),
            500: serializers.ErrorResponse(),
        },
    )
    def post(self, request: Request):
        """Composite an image onto a returned carrier document.

        The base64 document (PDF or ZPL) and a base64 PNG image are
        composited by the SDK stamping utility, which sniffs the document
        format and returns a document of the same format as base64.
        """
        try:
            data = serializers.StampData.map(data=request.data).data

            # Sniff the document format so the response echoes it; the utility
            # sniffs the bytes regardless, so the optional client hint only
            # breaks ties when the leading bytes match no known signature.
            document_format = helpers.sniff_document_format(
                data["document"],
                content_type=data.get("format"),
                default=data.get("format"),
            )

            document = core_models.ShippingDocument(
                category=data.get("doc_type") or "other",
                format=document_format,
                base64=data["document"],
            )

            try:
                stamped = lib.stamp_document(
                    document,
                    image=data.get("image"),
                    placement=_to_placement(data.get("placement")),
                    layer=data.get("layer") or "overlay",
                    carrier=data.get("carrier"),
                    doc_type=data.get("doc_type"),
                    date=data.get("date"),
                    graphic_name=data.get("graphic_name"),
                )

                result = serializers.StampedDocument.map(
                    data={"doc_file": stamped.base64, "format": stamped.format}
                )

                return Response(result.data, status=status.HTTP_201_CREATED)

            except ValueError as e:
                return Response(
                    {"errors": [{"message": str(e)}]},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            except Exception as e:
                logger.exception("Document stamping failed", error=str(e))
                return Response(
                    {"errors": [{"message": f"Document stamping failed: {str(e)}"}]},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

        except serializers.ValidationError as e:
            logger.error("Document stamp validation error", error=str(e))
            return Response(
                {"errors": [{"message": "Invalid input data"}]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            logger.exception("Unexpected error in document stamper", error=str(e))
            return Response(
                {"errors": [{"message": "Internal server error"}]},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


urlpatterns = [
    urls.path(
        "documents/stamp",
        DocumentStamper.as_view(),
        name="document-stamper",
    ),
]
