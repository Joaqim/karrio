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


def error_result_fields(response: dict) -> dict:
    """Pick the postalcodeapi ErrorResult fields in either casing.

    The vendored spec declares camelCase (errorCode/userMessage); the live
    API returns PascalCase (ErrorCode/UserMessage), so keys are matched
    case-insensitively.
    """
    return dict(
        error_code=next(
            (value for key, value in response.items() if key.lower() == "errorcode"),
            None,
        ),
        user_message=next(
            (value for key, value in response.items() if key.lower() == "usermessage"),
            None,
        ),
    )


def _extract_errors(response: dict) -> typing.List[dict]:
    """Normalize an ErrorResponse into a flat list of error dicts.

    Only responses carrying error fields are inspected; successful booking and
    print payloads are ignored so they are not mis-parsed as errors.
    """
    if not isinstance(response, dict):
        return []
    if not (response.get("errorMessage") or response.get("validationErrors")):
        # The productapi declares no 4xx responses and signals failures as a
        # BadRequestError body ({error, errors[]}); the item shape matches
        # ValidationErrorType, so remap it onto the shared ErrorResponse.
        if response.get("error") or response.get("errors"):
            response = dict(
                errorMessage=response.get("error"),
                validationErrors=response.get("errors"),
            )
        # The postalcodeapi signals failures as an ErrorResult
        # ({status, errorCode, userMessage}) in either casing; remap it onto
        # the shared ErrorResponse as a single validation error.
        else:
            fields = error_result_fields(response)
            if fields["user_message"] or fields["error_code"] is not None:
                response = dict(
                    errorMessage=fields["user_message"],
                    validationErrors=[
                        dict(
                            errorCode=(
                                fields["error_code"]
                                if fields["error_code"] is not None
                                else response.get("status", response.get("Status"))
                            ),
                            message=fields["user_message"],
                        )
                    ],
                )
            else:
                return []

    error = lib.to_object(dhl_freight.ErrorResponseType, response)
    # JList renders an explicit ``validationErrors=None`` as [None] (a missing
    # key defaults to []), so null entries are dropped before field access.
    validation_errors = [item for item in (error.validationErrors or []) if item]

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
