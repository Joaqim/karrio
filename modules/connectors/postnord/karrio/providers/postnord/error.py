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

    PostNord surfaces faults in three places, all sharing the same Fault shape
    (``explanationText``, ``faultCode``, ``paramValues``):

    * a top-level ``errorResponse`` (booking/pickup HTTP error bodies);
    * a per-item ``idInformation[].errorResponse`` (partial failures reported
      inline at HTTP 200/201);
    * a top-level ``faults[]`` list on the tracking ``LinksResponse``.
    """
    responses = response if isinstance(response, list) else [response]

    error_bodies = [
        # tracking LinksResponse: faults at top level
        *[res for res in responses if res.get("faults")],
        # booking/pickup: top-level errorResponse
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

    return [
        models.Message(
            carrier_id=settings.carrier_id,
            carrier_name=settings.carrier_name,
            code=fault.get("faultCode"),
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
                }
            ),
        )
        for body, fault in faults
    ]


def _faults(body: dict) -> typing.List[dict]:
    """Return the fault entries inside an error body (compositeFault or faults)."""
    composite = body.get("compositeFault") or {}
    return composite.get("faults") or body.get("faults") or []


def _has_fault(error_response: dict) -> bool:
    return any(_faults(error_response)) or bool(error_response.get("message"))
