"""Karrio PostNord client settings."""

import attr
import typing
import jstruct
import karrio.core.models as models
import karrio.providers.postnord.utils as provider_utils
import karrio.providers.postnord.units as provider_units
import karrio.universal.mappers.rating_proxy as rating_proxy


@attr.s(auto_attribs=True)
class Settings(provider_utils.Settings, rating_proxy.RatingMixinSettings):
    """PostNord connection settings."""

    # PostNord uses a single apikey credential (query param) for all operations.
    apikey: str = None
    issuer_code: str = "Z12"
    customer_number: str = None
    application_id: str = None

    # generic properties
    id: str = None
    test_mode: bool = False
    carrier_id: str = "postnord"
    account_country_code: str = "SE"
    metadata: dict = {}
    config: dict = {}

    # Static rate sheet: PostNord has no live rate API, so per-merchant contract
    # rates are supplied server-side via Karrio's RateSheet and resolved by the
    # universal rating mixin against these service levels.
    services: typing.List[models.ServiceLevel] = jstruct.JList[models.ServiceLevel, False, dict(default=provider_units.DEFAULT_SERVICES)]  # type: ignore

    @property
    def shipping_services(self) -> typing.List[models.ServiceLevel]:
        if any(self.services or []):
            return self.services

        return provider_units.DEFAULT_SERVICES
