# Tasks

## 1. Branch and PRD

- [x] 1.1 Create `.worktrees/postnord-service-point-booking` with an explicit start point at `feat-postnord-connector` (never from generated `develop`), and register the branch in `BRANCHES` on `docs-openspec` after `feat-postnord-connector`; verify `develop-status.sh --fetch` lists the branch.
- [x] 1.2 Put `PRDs/POSTNORD_SERVICE_POINT_BOOKING.md` as the first commit above `feat-postnord-connector`; verify `git log feat-postnord-connector..postnord-service-point-booking` lists the PRD commit last (oldest).

## 2. Service point parse

- [x] 2.1 Add `visiting_address` to `_normalize_service_point` in `modules/connectors/postnord/karrio/providers/postnord/service_points.py`, keeping the `address` source; verify with `test_parse_service_points_exposes_visiting_and_delivery_addresses` and a `ServicePointsResponse` fixture point carrying distinct delivery and visiting addresses in `tests/postnord/test_servicepoints.py`.

## 3. Booking to a chosen point

- [x] 3.1 Add the six `postnord_service_point_*` options and `SERVICE_POINT_DETAIL_OPTIONS` to `modules/connectors/postnord/karrio/providers/postnord/units.py`, and exclude the set from the `additionalServiceCode` list in `shipment/create.py`; verify `test_delivery_party_is_booked_with_the_chosen_point` asserts `["A7", "A3"]` with no detail codes.
- [x] 3.2 Add `_service_point_details` and `_delivery_party` to `shipment/create.py` and send `deliveryParty` with `partyIdType` `"156"`; verify the `deliveryParty` assertions in `tests/postnord/test_service_point_booking.py` and `test_without_options_no_delivery_party_and_no_a7`.
- [x] 3.3 Append `A7` and, on a recipient phone, `A3` when absent; verify `test_explicit_sms_opt_out_is_overridden_for_a_chosen_point`, `test_chosen_point_without_consignee_phone_books_only_a7` and `test_chosen_point_with_sms_opt_in_does_not_duplicate_a3`.
- [x] 3.4 Refuse incomplete details with a field error before the request; verify `test_incomplete_point_details_refuse_before_the_request` asserts the proxy is not called.
- [x] 3.5 Document the options, the `deliveryParty` mapping and the `A3` exception in `modules/connectors/postnord/README.md`; verify the shipment options table and the Service points section agree with the spec delta.
- [x] 3.6 Run `python -m unittest discover -v -f modules/connectors/postnord/tests` from the feature worktree in the nix dev shell; verify every test passes.

## 4. Develop

- [x] 4.1 Regenerate `develop` with `rebuild-develop.sh` from the main checkout and push it after the user's go-ahead; verify `develop-status.sh --fetch` reports `postnord-service-point-booking` contained in `develop` and `origin/develop`.
