# TGR rules: airline (luna-dev, final_nob)

Flags: A+noB. Rules: 20. Predicates: 45.

## Rules

| id | action(s) | logic | description | sentences |
|---|---|---|---|---|
| 1 | book_reservation, cancel_reservation, update_reservation_baggages, update_reservation_flights, update_reservation_passengers | `ALWAYS (book_reservation OR update_reservation_flights OR update_reservation_baggages OR update_reservation_passengers OR cancel_reservation IMPLIES pending_database_update_details_listed AND user_explicitly_confirmed_pending_database_update)` | Require listed action details and the user's explicit yes before booking, modifying, or cancelling a reservation. | S3 |
| 2 | book_reservation | `ALWAYS (book_reservation IMPLIES booking_required_information_known)` | Require the booking user ID, trip type, origin, and destination to be known before booking. | S9 |
| 3 | book_reservation | `ALWAYS (book_reservation IMPLIES booking_passenger_count_within_limit AND booking_passengers_have_required_identity_details)` | Enforce the passenger limit and required passenger identity details for a booking. | S10, S11 |
| 4 | book_reservation | `ALWAYS (book_reservation IMPLIES booking_passengers_share_flights_and_cabin)` | Require all booked passengers to share the same flights and cabin. | S12 |
| 5 | book_reservation | `ALWAYS (book_reservation IMPLIES booking_payment_method_counts_within_limits AND booking_payment_methods_are_in_user_profile)` | Enforce booking payment-method limits and require all methods to be in the user's profile. | S13, S15 |
| 6 | book_reservation | `ALWAYS (book_reservation IMPLIES booking_baggage_counts_and_fees_follow_allowance)` | Require booking baggage counts and disclosed extra-bag fees to follow the member's allowance. | S16, S17, S18, S19 |
| 7 | book_reservation | `ALWAYS (book_reservation IMPLIES travel_insurance_offer_made AND travel_insurance_decision_known AND booking_insurance_argument_matches_user_choice)` | Require an insurance offer and a known, correctly applied user decision before booking. | S20 |
| 8 | update_reservation_baggages, update_reservation_flights, update_reservation_passengers | `ALWAYS (update_reservation_flights OR update_reservation_baggages OR update_reservation_passengers IMPLIES modification_identifiers_known AND reservation_details_available)` | Require the user and reservation IDs and existing reservation details before a reservation modification. | S21, S25 |
| 9 | update_reservation_flights | `ALWAYS (update_reservation_flights IMPLIES NOT pending_update_changes_flight_segments OR NOT reservation_is_basic_economy AND flight_update_preserves_origin_destination_and_trip_type AND kept_segments_retain_original_prices)` | Block flight changes to basic-economy reservations and require permitted flight changes to preserve route, trip type, and retained-segment prices. | S22, S23, S24, S25 |
| 10 | update_reservation_flights | `ALWAYS (update_reservation_flights IMPLIES all_segments_have_same_cabin)` | Require all flight segments in the reservation to have the same cabin. | S28 |
| 11 | update_reservation_flights | `ALWAYS (update_reservation_flights IMPLIES NOT cabin_change_requested OR cabin_change_leaves_flight_segments_unchanged AND cabin_difference_payment_authorized)` | Allow cabin changes, including for basic economy, only without changing flights and with authorization for the fare difference. | S26, S27 |
| 12 | update_reservation_flights | `ALWAYS (update_reservation_flights IMPLIES NOT pending_update_changes_flight_segments OR flight_change_payment_method_requested AND flight_change_payment_method_selected_by_user AND flight_change_payment_method_is_profile_gift_or_credit_card)` | For flight changes, require the agent to ask for a payment or refund method and use a user-selected profile gift card or credit card. | S33, S34 |
| 13 | update_reservation_baggages | `ALWAYS (update_reservation_baggages IMPLIES baggage_update_does_not_remove_checked_bags)` | Prevent baggage updates from removing checked bags. | S29 |
| 14 | update_reservation_passengers | `ALWAYS (update_reservation_passengers IMPLIES passenger_update_preserves_passenger_count)` | Prevent passenger updates from changing the number of passengers. | S31, S32 |
| 15 | cancel_reservation | `ALWAYS (cancel_reservation IMPLIES cancellation_identifiers_and_reason_known AND cancellation_rules_allow_pending_cancellation AND reservation_is_entirely_unflown AND NOT reservation_has_used_segment)` | Require cancellation details, eligibility, and an entirely unflown reservation before cancellation. | S35, S36, S37, S38, S39, S40, S41 |
| 16 | transfer_to_human_agents | `ALWAYS (cancellation_request_involves_used_segment IMPLIES EVENTUALLY transfer_to_human_agents)` | Transfer cancellation requests involving an already-used segment to a human agent. | S41 |
| 17 | transfer_to_human_agents | `ALWAYS (transfer_to_human_agents IMPLIES human_transfer_is_appropriate)` | Allow a human transfer only for an explicit human request or an issue that appropriately requires human assistance. | S8 |
| 18 | transfer_to_human_agents | `ALWAYS (human_transfer_is_appropriate IMPLIES EVENTUALLY transfer_to_human_agents)` | Require transfer when the user requests a human or the issue requires human assistance. | S8 |
| 19 | send_certificate | `ALWAYS (send_certificate IMPLIES user_complains_about_cancelled_flight AND user_explicitly_requests_compensation AND reservation_qualifies_for_flight_gesture AND NOT reservation_is_regular_uninsured_basic_economy AND cancelled_flight_facts_confirmed_to_user AND cancelled_flight_certificate_amount_is_correct AND certificate_recipient_matches_reservation_user)` | Permit a cancelled-flight gesture certificate only after the required complaint, compensation request, eligibility, fact confirmation, recipient, and amount checks. | S43, S45, S46 |
| 20 | send_certificate | `ALWAYS (send_certificate IMPLIES user_complains_about_delayed_flight AND user_explicitly_requests_compensation AND reservation_qualifies_for_flight_gesture AND NOT reservation_is_regular_uninsured_basic_economy AND user_wants_change_or_cancel_because_of_delay AND delay_related_change_or_cancellation_completed AND delayed_flight_facts_confirmed_to_user AND delayed_flight_certificate_amount_is_correct AND certificate_recipient_matches_reservation_user)` | Permit a delayed-flight gesture certificate only after the required complaint, compensation request, eligibility, requested and completed reservation action, fact confirmation, recipient, and amount checks. | S44, S45, S46 |

## Predicates

| name | description | source |
|---|---|---|
| all_segments_have_same_cabin | The pending flight-update arguments assign the same cabin class to every flight segment in the reservation. | call_arguments |
| baggage_update_does_not_remove_checked_bags | The pending baggage update's total checked-bag count is at least the existing reservation's total checked-bag count. | call_arguments, tool_outputs |
| booking_baggage_counts_and_fees_follow_allowance | The pending booking's total and nonfree baggage counts follow the member and cabin-class allowances, and its disclosed extra-baggage fee is $50 per extra bag. | call_arguments, tool_outputs, agent_messages |
| booking_insurance_argument_matches_user_choice | The insurance value in the pending booking arguments matches the user's stated decision. | call_arguments, user_messages |
| booking_passenger_count_within_limit | The pending booking contains no more than five passengers. | call_arguments |
| booking_passengers_have_required_identity_details | Every passenger in the pending booking has a first name, last name, and date of birth in the booking arguments. | call_arguments |
| booking_passengers_share_flights_and_cabin | Every passenger in the pending booking is assigned the same flights and the same cabin. | call_arguments |
| booking_payment_method_counts_within_limits | The pending booking uses no more than one travel certificate, one credit card, and three gift cards. | call_arguments |
| booking_payment_methods_are_in_user_profile | Every payment method in the pending booking is present in the user's profile according to available tool results. | call_arguments, tool_outputs |
| booking_required_information_known | The conversation or earlier tool results establish the booking user ID, trip type, origin, and destination. | user_messages, tool_outputs |
| cabin_change_leaves_flight_segments_unchanged | The pending cabin change leaves every flight segment unchanged from the existing reservation. | call_arguments, tool_outputs |
| cabin_change_requested | The pending flight update changes the reservation's cabin class from its existing cabin. | call_arguments, tool_outputs |
| cabin_difference_payment_authorized | The user has authorized payment of the cabin-price difference using the stored payment method in the pending call, and available pre-action information establishes the difference. | user_messages, tool_outputs, call_arguments |
| cancellation_identifiers_and_reason_known | The conversation or earlier tool results establish the user ID, reservation ID, and one of the cancellation reasons change of plan, airline-cancelled flight, or other reasons. | user_messages, tool_outputs |
| cancellation_request_involves_used_segment | The user is seeking cancellation of a reservation for which earlier tool results establish that at least one segment has already been used. | user_messages, tool_outputs |
| cancellation_rules_allow_pending_cancellation | The reservation's booking time, current time, cancellation reason, cabin, insurance status, and any health or weather circumstance satisfy the cancellation eligibility rules, with membership status ignored. | user_messages, tool_outputs |
| cancelled_flight_certificate_amount_is_correct | The pending certificate amount equals $100 multiplied by the number of passengers in the relevant reservation. | call_arguments, tool_outputs |
| cancelled_flight_facts_confirmed_to_user | The relevant cancelled-flight facts have been checked against available information and confirmed to the user. | tool_outputs, agent_messages |
| certificate_recipient_matches_reservation_user | The user ID in the pending certificate call matches the user associated with the relevant reservation. | call_arguments, tool_outputs |
| delay_related_change_or_cancellation_completed | Earlier tool results establish that the relevant reservation was changed or cancelled after the user's delayed-flight complaint. | tool_outputs, user_messages |
| delayed_flight_certificate_amount_is_correct | The pending certificate amount equals $50 multiplied by the number of passengers in the relevant reservation. | call_arguments, tool_outputs |
| delayed_flight_facts_confirmed_to_user | The relevant delayed-flight facts have been checked against available information and confirmed to the user. | tool_outputs, agent_messages |
| flight_change_payment_method_is_profile_gift_or_credit_card | The payment method in the pending flight-update call is a gift card or credit card stored in the user's profile. | call_arguments, tool_outputs |
| flight_change_payment_method_requested | Before the pending flight change, the agent asked the user to provide or select a payment or refund method. | agent_messages |
| flight_change_payment_method_selected_by_user | The user selected or provided the payment or refund method used in the pending flight-update call. | user_messages, call_arguments |
| flight_update_preserves_origin_destination_and_trip_type | The pending flight update preserves the reservation's existing origin, destination, and trip type. | call_arguments, tool_outputs |
| human_transfer_is_appropriate | The user explicitly requests a human agent, or the issue cannot be resolved with the listed actions and is within a human agent's scope. | user_messages, tool_outputs |
| kept_segments_retain_original_prices | Each flight segment retained in the pending flight update keeps its original reservation price. | call_arguments, tool_outputs |
| modification_identifiers_known | The conversation or earlier tool results establish both the user ID and reservation ID for the pending modification. | user_messages, tool_outputs |
| passenger_update_preserves_passenger_count | The pending passenger update contains the same number of passengers as the existing reservation. | call_arguments, tool_outputs |
| pending_database_update_details_listed | Before the pending database update, the agent told the user the specific changes and material details corresponding to the pending action, its arguments, and available reservation data. | agent_messages, call_arguments, tool_outputs |
| pending_update_changes_flight_segments | The pending flight-update arguments change at least one flight segment from the existing reservation. | call_arguments, tool_outputs |
| reservation_details_available | Earlier tool results provide the reservation details needed to compare the pending change with the existing reservation. | tool_outputs |
| reservation_has_used_segment | Earlier tool results establish that at least one segment in the reservation has already been used. | tool_outputs |
| reservation_is_basic_economy | Earlier tool results establish that the reservation's current cabin is basic economy. | tool_outputs |
| reservation_is_entirely_unflown | Earlier tool results establish that no segment in the reservation has been flown or used. | tool_outputs |
| reservation_is_regular_uninsured_basic_economy | Available profile and reservation information establishes regular membership, no travel insurance, and basic-economy travel. | tool_outputs |
| reservation_qualifies_for_flight_gesture | Available profile and reservation information establishes silver or gold membership, travel insurance, or business-class travel for the reservation. | tool_outputs |
| travel_insurance_decision_known | The user's decision to buy or decline travel insurance is known from the conversation. | user_messages |
| travel_insurance_offer_made | Before booking, the agent asked whether the user wants travel insurance and stated its $30-per-passenger price and its full-refund coverage for health or weather cancellation reasons. | agent_messages |
| user_complains_about_cancelled_flight | The user complains about a cancelled flight in a reservation. | user_messages |
| user_complains_about_delayed_flight | The user complains about a delayed flight in a reservation. | user_messages |
| user_explicitly_confirmed_pending_database_update | After the agent listed the pending database update details, the user explicitly replied yes to proceeding with those details. | user_messages, agent_messages, call_arguments |
| user_explicitly_requests_compensation | The user explicitly asks for compensation for the relevant flight disruption. | user_messages |
| user_wants_change_or_cancel_because_of_delay | The user wants to change or cancel the reservation because of a delayed flight. | user_messages |

## Background facts for the judge

- [S1] The current time is 2024-05-15 15:00:00 EST.
- [S10] Passengers: Each reservation can have at most five passengers.
- [S13] Payment: each reservation can use at most one travel certificate, at most one credit card, and at most three gift cards.
- [S16] Checked bag allowance: If the booking user is a regular member, 0 free checked bag for each basic economy passenger, 1 free checked bag for each economy passenger, and 2 free checked bags for each business passenger.
- [S17] If the booking user is a silver member, 1 free checked bag for each basic economy passenger, 2 free checked bag for each economy passenger, and 3 free checked bags for each business passenger.
- [S18] If the booking user is a gold member, 2 free checked bag for each basic economy passenger, 3 free checked bag for each economy passenger, and 3 free checked bags for each business passenger.
- [S19] Each extra baggage is 50 dollars.
- [S20] Travel insurance: the agent should ask if the user wants to buy the travel insurance, which is 30 dollars per passenger and enables full refund if the user needs to cancel the flight given health or weather reasons.
- [S22] Change flights: Basic economy flights cannot be modified.
- [S23] Other reservations can be modified without changing the origin, destination, and trip type.
- [S24] Some flight segments can be kept, but their prices will not be updated based on the current price.
- [S26] Change cabin: all reservations, including basic economy, can change cabin without changing the flights.
- [S27] Cabin changes require the user to pay for the difference between their current cabin and the new cabin class.
- [S28] Cabin class must be the same across all the flights in the same reservation; changing cabin for just one flight segment is not possible.
- [S29] Change baggage and insurance: The user can add but not remove checked bags.
- [S30] The user cannot add insurance after initial booking.
- [S31] Change passengers: The user can modify passengers but cannot modify the number of passengers.
- [S32] This is something that even a human agent cannot assist with.
- [S33] Payment: If the flights are changed, the user needs to provide one gift card or credit card for payment or refund method.
- [S35] The agent must first obtain the user id, the reservation id, and the reason for cancellation (change of plan, airline cancelled flight, or other reasons)
- [S36] All reservations can be cancelled within 24 hours of booking, or if the airline cancelled the flight.
- [S37] Otherwise, basic economy or economy flights can be cancelled only if travel insurance is bought and the condition is met, and business flights can always be cancelled.
- [S38] The rules are strict regardless of the membership status.
- [S40] The agent can only cancel the whole trip that is not flown.
- [S41] If any of the segments are already used, the agent cannot help and transfer is needed.
- [S43] If the user is silver/gold member or has travel insurance or flies business, and complains about cancelled flights in a reservation, the agent can offer a certificate as a gesture after confirming the facts, with the amount being $100 times the number of passengers.
- [S44] If the user is silver/gold member or has travel insurance or flies business, and complains about delayed flights in a reservation and wants to change or cancel the reservation, the agent can offer a certificate as a gesture after confirming the facts and changing or cancelling the reservation, with the amount being $50 times the number of passengers.
- [S45] Do not proactively offer these unless the user complains about the situation and explicitly asks for some compensation.
- [S46] Do not compensate if the user is regular member and has no travel insurance and flies (basic) economy.

## Validation

- repair rounds: 0
- remaining errors: none
- invalid rules dropped: none
- exact duplicates dropped: none
- declared but unused predicates: none
