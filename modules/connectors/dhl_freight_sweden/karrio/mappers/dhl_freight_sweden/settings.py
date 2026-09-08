"""Karrio DHL Freight client settings."""

import attr
import typing
import jstruct
import karrio.core.models as models
import karrio.providers.dhl_freight_sweden.utils as provider_utils
import karrio.providers.dhl_freight_sweden.units as provider_units
import karrio.universal.mappers.rating_proxy as rating_proxy


@attr.s(auto_attribs=True)
class Settings(provider_utils.Settings, rating_proxy.RatingMixinSettings):
    """DHL Freight (Sweden API Farm) connection settings."""

    # API Farm authenticates with a single API key sent as the `client-key` header.
    client_key: str
    account_number: str = None

    # generic properties
    id: str = None
    test_mode: bool = False
    carrier_id: str = "dhl_freight_sweden"
    account_country_code: str = "SE"
    metadata: dict = {}
    config: dict = {}

    # Static rate sheet: the SE API Farm pricequote API is out of Phase 0
    # scope, so per-merchant contract rates arrive server-side via Karrio's
    # RateSheet and are resolved by the universal rating mixin against these
    # service levels.
    services: typing.List[models.ServiceLevel] = jstruct.JList[
        models.ServiceLevel, False, dict(default=provider_units.DEFAULT_SERVICES)
    ]  # type: ignore

    @property
    def shipping_services(self) -> typing.List[models.ServiceLevel]:
        return (
            self.services
            if any(self.services or [])
            else provider_units.DEFAULT_SERVICES
        )
