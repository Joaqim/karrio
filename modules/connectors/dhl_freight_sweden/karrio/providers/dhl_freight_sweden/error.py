"""Karrio DHL Freight error parser."""

import typing
import karrio.lib as lib
import karrio.core.models as models
import karrio.schemas.dhl_freight_sweden.error_response as dhl_freight
import karrio.providers.dhl_freight_sweden.utils as provider_utils


def parse_error_response(
    response: typing.Union[typing.List[dict], dict],
    settings: provider_utils.Settings,
    **kwargs,
) -> typing.List[models.Message]:
    responses = response if isinstance(response, list) else [response]
    errors = [error for _response in responses for error in _extract_errors(_response)]

    return [
        models.Message(
            carrier_id=settings.carrier_id,
            carrier_name=settings.carrier_name,
            code=error["code"],
            message=error["message"],
            details={**kwargs, **error["details"]},
        )
        for error in errors
    ]


def _extract_errors(response: dict) -> typing.List[dict]:
    """Normalize an ErrorResponse into a flat list of error dicts.

    Only responses carrying error fields are inspected; successful booking and
    print payloads are ignored so they are not mis-parsed as errors.
    """
    if not isinstance(response, dict):
        return []
    if not (response.get("errorMessage") or response.get("validationErrors")):
        return []

    error = lib.to_object(dhl_freight.ErrorResponseType, response)
    validation_errors = error.validationErrors or []

    field_errors = [
        dict(
            code=(
                str(item.errorCode) if item.errorCode is not None else "ValidationError"
            ),
            message=item.message or error.errorMessage or "Validation error",
            details=lib.identity(dict(field=item.field) if item.field else {})
            | lib.identity(
                dict(incompatible_fields=item.incompatibleFields)
                if item.incompatibleFields
                else {}
            ),
        )
        for item in validation_errors
    ]

    top_level = lib.identity(
        [
            dict(
                code=error.status or "error",
                message=error.errorMessage,
                details={},
            )
        ]
        if error.errorMessage and not field_errors
        else []
    )

    return field_errors + top_level
