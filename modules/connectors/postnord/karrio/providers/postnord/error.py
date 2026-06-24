"""Karrio PostNord error parser."""

import typing
import karrio.lib as lib
import karrio.core.models as models
import karrio.providers.postnord.utils as provider_utils


def parse_error_response(
    response: typing.Union[dict, typing.List[dict]],
    settings: provider_utils.Settings,
    **kwargs,
) -> typing.List[models.Message]:
    """Parse PostNord error shapes into Karrio Messages.

    PostNord surfaces faults in several places, all sharing the same Fault
    shape (``explanationText``, optional ``faultCode``/``paramValues``, and a
    ``faultReferences`` key/value list):

    * a top-level body carrying ``message``/``compositeFault`` directly
      (booking/pickup HTTP 4xx error bodies);
    * a top-level ``errorResponse`` wrapper (alternate error envelope);
    * a per-item ``idInformation[].errorResponse`` (partial failures reported
      inline at HTTP 200/201);
    * a top-level ``faults[]`` list on the tracking ``LinksResponse``.
    """
    responses = response if isinstance(response, list) else [response]

    error_bodies = [
        # tracking LinksResponse: faults at top level
        *[res for res in responses if res.get("faults")],
        # booking/pickup 4xx: message/compositeFault directly on the body
        *[
            res
            for res in responses
            if not isinstance(res.get("errorResponse"), dict)
            and (res.get("compositeFault") or res.get("message"))
        ],
        # booking/pickup: top-level errorResponse wrapper
        *[
            res["errorResponse"]
            for res in responses
            if isinstance(res.get("errorResponse"), dict)
        ],
        # partial failures: idInformation[].errorResponse with a real fault
        *[
            info["errorResponse"]
            for res in responses
            for info in (lib.identity(res.get("bookingResponse")) or res).get(
                "idInformation", []
            )
            if isinstance(info.get("errorResponse"), dict)
            and _has_fault(info["errorResponse"])
        ],
    ]

    faults = [
        (body, fault)
        for body in error_bodies
        for fault in _faults(body)
    ]

    messages = [
        models.Message(
            carrier_id=settings.carrier_id,
            carrier_name=settings.carrier_name,
            code=lib.identity(fault.get("faultCode") or _sub_type(fault)),
            message=lib.identity(
                fault.get("explanationText") or body.get("message")
            ),
            details=lib.to_dict(
                {
                    **kwargs,
                    "params": {
                        param.get("param"): param.get("value")
                        for param in (fault.get("paramValues") or [])
                    }
                    or None,
                    "references": {
                        ref.get("key"): ref.get("value")
                        for ref in (fault.get("faultReferences") or [])
                    }
                    or None,
                }
            ),
        )
        for body, fault in faults
    ]

    # A failed request with an unrecognized non-empty body must still surface
    # a message rather than being silently swallowed.
    has_unparsed_error = bool(error_bodies) and not any(faults)
    if has_unparsed_error:
        return [
            models.Message(
                carrier_id=settings.carrier_id,
                carrier_name=settings.carrier_name,
                code=None,
                message=lib.identity(
                    next(
                        (body.get("message") for body in error_bodies if body.get("message")),
                        "An error occurred",
                    )
                ),
                details=lib.to_dict(kwargs) or None,
            )
        ]

    return messages


def _faults(body: dict) -> typing.List[dict]:
    """Return the fault entries inside an error body (compositeFault or faults)."""
    composite = body.get("compositeFault") or {}
    return composite.get("faults") or body.get("faults") or []


def _sub_type(fault: dict) -> typing.Optional[str]:
    """Derive a fault code from the ``...subType`` faultReference when present."""
    return next(
        (
            ref.get("value")
            for ref in (fault.get("faultReferences") or [])
            if (ref.get("key") or "").endswith("subType")
        ),
        None,
    )


def _has_fault(error_response: dict) -> bool:
    return any(_faults(error_response)) or bool(error_response.get("message"))
