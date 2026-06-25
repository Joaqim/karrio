"""PostNord carrier tests fixtures."""

import karrio.sdk as karrio


_settings = dict(
    id="123456789",
    test_mode=True,
    carrier_id="postnord",
    apikey="TEST_API_KEY",
    issuer_code="Z12",
    customer_number="00000000",
    application_id="2458",
    account_country_code="SE",
    # PostNord has no live rate API: per-merchant contract prices arrive via
    # Karrio's server-side RateSheet, modeled here as service-level zones.
    services=[
        dict(
            service_name="PostNord Parcel",
            service_code="postnord_parcel",
            carrier_service_code="18",
            currency="SEK",
            transit_days=2,
            domicile=True,
            international=False,
            zones=[dict(label="Sweden", rate=89.0, country_codes=["SE"])],
        ),
        dict(
            service_name="PostNord MyPack Home",
            service_code="postnord_mypack_home",
            carrier_service_code="17",
            currency="SEK",
            transit_days=2,
            domicile=True,
            international=False,
            zones=[dict(label="Sweden", rate=99.0, country_codes=["SE"])],
        ),
    ],
)

# Default gateway: transit-time enrichment OFF (no carrier call on rate()).
gateway = karrio.gateway["postnord"].create(dict(_settings))

# Opt-in gateway: transit-time enrichment ON via connection config.
gateway_with_transit = karrio.gateway["postnord"].create(
    dict(_settings, config=dict(enable_transit_times=True))
)
