# TGR rules: airline (luna-dev, it4)

Flags: A+B. Rules: 35. Predicates: 40.

## Rules

| id | action(s) | logic | description | sentences |
|---|---|---|---|---|
| 1 | book_reservation | `book_reservation IMPLIES booking_user_id_known` | The booking user's ID must be known before booking. | S9 |
| 2 | book_reservation | `book_reservation IMPLIES booking_trip_details_known` | The trip type, origin, and destination must be known before booking. | S9 |
| 3 | book_reservation | `book_reservation IMPLIES reservation_has_at_most_five_passengers` | A reservation may contain no more than five passengers. | S10 |
| 4 | book_reservation | `book_reservation IMPLIES every_passenger_has_required_identity_details` | Each passenger must have the required identifying details. | S11 |
| 5 | book_reservation | `book_reservation IMPLIES all_passengers_share_flights_and_cabin` | All passengers must share the same flights and cabin. | S12 |
| 6 | book_reservation | `book_reservation IMPLIES booking_payment_method_limits_respected` | The payment-method limits for a reservation must be respected. | S13 |
| 7 | book_reservation | `book_reservation IMPLIES booking_payment_methods_are_in_user_profile` | All payment methods used for booking must already be in the user's profile. | S15 |
| 8 | book_reservation | `book_reservation IMPLIES baggage_counts_match_member_allowance` | Booking baggage counts must reflect the applicable membership allowance. | S16, S17, S18 |
| 9 | book_reservation | `book_reservation IMPLIES travel_insurance_choice_was_requested` | The agent must ask whether the user wants travel insurance before booking. | S20 |
| 10 | book_reservation | `book_reservation IMPLIES pending_booking_change_details_were_listed` | The booking details must be listed before the database update. | S3 |
| 11 | book_reservation | `book_reservation IMPLIES user_explicitly_confirmed_pending_change_after_details` | The user must explicitly confirm the listed booking details with yes. | S3 |
| 12 | update_reservation_flights | `update_reservation_flights IMPLIES user_id_known AND reservation_id_known` | The user ID and reservation ID must be known before modifying flights. | S21 |
| 13 | update_reservation_flights | `update_reservation_flights IMPLIES pending_booking_change_details_were_listed` | The flight-update details must be listed before the database update. | S3 |
| 14 | update_reservation_flights | `update_reservation_flights IMPLIES user_explicitly_confirmed_pending_change_after_details` | The user must explicitly confirm the listed flight-update details with yes. | S3 |
| 15 | update_reservation_baggages | `update_reservation_baggages IMPLIES user_id_known AND reservation_id_known` | The user ID and reservation ID must be known before modifying baggage. | S21 |
| 16 | update_reservation_baggages | `update_reservation_baggages IMPLIES pending_booking_change_details_were_listed` | The baggage-update details must be listed before the database update. | S3 |
| 17 | update_reservation_baggages | `update_reservation_baggages IMPLIES user_explicitly_confirmed_pending_change_after_details` | The user must explicitly confirm the listed baggage-update details with yes. | S3 |
| 18 | update_reservation_passengers | `update_reservation_passengers IMPLIES user_id_known AND reservation_id_known` | The user ID and reservation ID must be known before modifying passengers. | S21 |
| 19 | update_reservation_passengers | `update_reservation_passengers IMPLIES pending_booking_change_details_were_listed` | The passenger-update details must be listed before the database update. | S3 |
| 20 | update_reservation_passengers | `update_reservation_passengers IMPLIES user_explicitly_confirmed_pending_change_after_details` | The user must explicitly confirm the listed passenger-update details with yes. | S3 |
| 21 | update_reservation_flights | `update_reservation_flights IMPLIES NOT reservation_is_basic_economy OR reservation_flight_itinerary_unchanged` | Basic economy flights may not be changed, but a cabin-only update that leaves the itinerary unchanged is permitted. | S22, S26 |
| 22 | update_reservation_flights | `update_reservation_flights IMPLIES reservation_origin_destination_and_trip_type_unchanged` | A flight update must preserve the reservation's origin, destination, and trip type. | S23, S25 |
| 23 | update_reservation_flights | `update_reservation_flights IMPLIES all_updated_flight_segments_use_one_cabin` | All flights in the reservation must use the same cabin class. | S28 |
| 24 | update_reservation_baggages | `update_reservation_baggages IMPLIES reservation_baggage_is_not_reduced` | A baggage update may add bags but may not remove checked bags. | S29 |
| 25 | update_reservation_baggages | `update_reservation_baggages IMPLIES baggage_counts_match_member_allowance` | Updated baggage counts must reflect the applicable membership allowance. | S16, S17, S18 |
| 26 | update_reservation_passengers | `update_reservation_passengers IMPLIES reservation_passenger_count_is_unchanged` | Passenger information may be changed only while keeping the passenger count unchanged. | S31 |
| 27 | update_reservation_flights | `update_reservation_flights IMPLIES flight_change_payment_method_is_user_provided_credit_or_gift_card` | A flight change must use the one credit card or gift card provided by the user as a payment or refund method. | S33 |
| 28 | update_reservation_flights | `update_reservation_flights IMPLIES agent_asked_for_payment_or_refund_method` | The agent must ask for the payment or refund method before updating flights. | S34 |
| 29 | cancel_reservation | `cancel_reservation IMPLIES user_id_known AND reservation_id_known AND cancellation_reason_is_known_and_valid` | The user ID, reservation ID, and a valid cancellation reason must be known before cancellation. | S35 |
| 30 | cancel_reservation | `cancel_reservation IMPLIES reservation_was_booked_within_24_hours_of_policy_time OR airline_cancelled_the_reservation OR reservation_is_business_cabin OR reservation_is_basic_or_economy_cabin AND reservation_has_travel_insurance AND cancellation_reason_is_health_or_weather` | Cancellation is permitted within 24 hours of booking, for an airline-cancelled flight, for business cabin, or for basic economy/economy with insurance and a qualifying health or weather reason; membership status does not affect eligibility. | S36, S37, S38, S39 |
| 31 | cancel_reservation | `cancel_reservation IMPLIES no_reservation_segments_have_been_flown_or_used` | Cancellation is permitted only for a whole trip with no segments already flown or used. | S40 |
| 32 | transfer_to_human_agents | `transfer_to_human_agents IMPLIES request_is_outside_available_agent_scope` | Transfer is permitted only when the request cannot be handled within the agent's available scope. | S8 |
| 33 | send_certificate | `send_certificate IMPLIES user_complained_about_cancelled_reservation_flights AND compensation_eligibility_criterion_met AND disruption_facts_were_confirmed_with_user AND certificate_amount_is_100_dollars_per_passenger OR user_complained_about_delayed_reservation_flights AND user_wants_change_or_cancellation_due_to_delay AND compensation_eligibility_criterion_met AND disruption_facts_were_confirmed_with_user AND reservation_change_or_cancellation_succeeded_before_certificate AND certificate_amount_is_50_dollars_per_passenger` | A certificate must fit one of the policy's cancelled-flight or delayed-flight gesture cases, including its eligibility, confirmation, completion, and amount requirements. | S43, S44 |
| 34 | send_certificate | `send_certificate IMPLIES user_explicitly_requested_compensation` | The user must explicitly ask for compensation before a certificate is sent as compensation. | S45 |
| 35 | send_certificate | `send_certificate IMPLIES NOT user_is_regular_uninsured_and_flies_basic_or_economy` | No compensation certificate may be sent to a regular member with no insurance who flies basic economy or economy. | S46 |

## Predicates

| name | description | source |
|---|---|---|
| agent_asked_for_payment_or_refund_method | Before the pending flight update, the agent asked the user for a payment or refund method. | agent_messages |
| airline_cancelled_the_reservation | The user stated, or an earlier tool result indicates, that the airline cancelled the reservation's flight. | user_messages, tool_outputs |
| all_passengers_share_flights_and_cabin | The passengers in the pending reservation arguments are assigned the same flights and cabin. | call_arguments |
| all_updated_flight_segments_use_one_cabin | All flight segments in the pending flight-update arguments use the same cabin class. | call_arguments |
| baggage_counts_match_member_allowance | The pending baggage totals and nonfree baggage count match the free allowance calculated for the passenger count, cabin, and user membership tier: regular members receive 0, 1, or 2 free bags per passenger for basic economy, economy, or business; silver members receive 1, 2, or 3; gold members receive 2, 3, or 3; any bags beyond the total free allowance are counted as nonfree. | call_arguments, tool_outputs |
| booking_payment_method_limits_respected | The pending reservation arguments use no more than one travel certificate, one credit card, and three gift cards. | call_arguments |
| booking_payment_methods_are_in_user_profile | Every payment method in the pending reservation arguments is present in the user's profile according to an earlier tool result. | call_arguments, tool_outputs |
| booking_trip_details_known | The trip type, origin, and destination for the pending reservation have been stated by the user or returned by an earlier tool call. | user_messages, tool_outputs |
| booking_user_id_known | The booking user's ID has been stated by the user or returned by an earlier tool call. | user_messages, tool_outputs |
| cancellation_reason_is_health_or_weather | The user stated that the cancellation is needed for a health or weather reason. | user_messages |
| cancellation_reason_is_known_and_valid | The user has provided a cancellation reason that is change of plan, airline-cancelled flight, or another reason. | user_messages |
| certificate_amount_is_100_dollars_per_passenger | The pending certificate amount equals $100 multiplied by the reservation's passenger count shown in an earlier tool result. | call_arguments, tool_outputs |
| certificate_amount_is_50_dollars_per_passenger | The pending certificate amount equals $50 multiplied by the reservation's passenger count shown in an earlier tool result. | call_arguments, tool_outputs |
| compensation_eligibility_criterion_met | Earlier tool results show that the user is silver or gold, or the reservation has travel insurance, or the reservation flies business cabin. | tool_outputs |
| disruption_facts_were_confirmed_with_user | The agent stated the relevant cancelled-flight or delayed-flight facts to the user, those facts are supported by earlier tool results or user statements, and the user confirmed them. | agent_messages, user_messages, tool_outputs |
| every_passenger_has_required_identity_details | Every passenger in the pending reservation arguments has a first name, last name, and date of birth. | call_arguments |
| flight_change_payment_method_is_user_provided_credit_or_gift_card | The pending flight-update payment ID corresponds to one credit card or gift card the user provided as the payment or refund method. | call_arguments, user_messages, tool_outputs |
| no_reservation_segments_have_been_flown_or_used | An earlier tool result indicates that none of the reservation's flight segments have been flown or used. | tool_outputs |
| pending_booking_change_details_were_listed | Before the pending database update, the agent listed the details of that specific booking or reservation change, matching the pending action arguments. | agent_messages, call_arguments |
| request_is_outside_available_agent_scope | From the user's stated goal, available tools, and prior tool results, the requested outcome cannot be completed within the agent's permitted actions. | user_messages, tool_outputs, call_arguments |
| reservation_baggage_is_not_reduced | The pending baggage-update arguments do not reduce the reservation's total checked baggage compared with an earlier tool result. | call_arguments, tool_outputs |
| reservation_change_or_cancellation_succeeded_before_certificate | An earlier tool result shows a successful change or cancellation of the reservation associated with the delayed-flight complaint. | tool_outputs |
| reservation_flight_itinerary_unchanged | The flights and itinerary in the pending flight-update arguments match the reservation's flights and itinerary in an earlier tool result. | call_arguments, tool_outputs |
| reservation_has_at_most_five_passengers | The pending reservation arguments contain no more than five passengers. | call_arguments |
| reservation_has_travel_insurance | An earlier tool result indicates that the reservation has travel insurance. | tool_outputs |
| reservation_id_known | The reservation ID has been stated by the user or returned by an earlier tool call. | user_messages, tool_outputs |
| reservation_is_basic_economy | An earlier tool result identifies the reservation as basic economy. | tool_outputs |
| reservation_is_basic_or_economy_cabin | An earlier tool result identifies the reservation as basic economy or economy cabin. | tool_outputs |
| reservation_is_business_cabin | An earlier tool result identifies the reservation as business cabin. | tool_outputs |
| reservation_origin_destination_and_trip_type_unchanged | The pending flight-update arguments preserve the reservation's original origin, destination, and trip type, as shown by an earlier tool result. | call_arguments, tool_outputs |
| reservation_passenger_count_is_unchanged | The pending passenger-update arguments contain the same number of passengers as the reservation in an earlier tool result. | call_arguments, tool_outputs |
| reservation_was_booked_within_24_hours_of_policy_time | An earlier tool result gives a booking time no more than 24 hours before the current time stated in policy sentence S1. | tool_outputs |
| travel_insurance_choice_was_requested | Before the pending booking action, the agent asked the user whether they wanted to buy travel insurance. | agent_messages |
| user_complained_about_cancelled_reservation_flights | The user complained about cancelled flights in a reservation. | user_messages |
| user_complained_about_delayed_reservation_flights | The user complained about delayed flights in a reservation. | user_messages |
| user_explicitly_confirmed_pending_change_after_details | After the agent listed the details matching the pending database update, the user explicitly replied yes to proceeding with that change. | agent_messages, user_messages, call_arguments |
| user_explicitly_requested_compensation | The user explicitly asked for compensation for the complained-about situation. | user_messages |
| user_id_known | The user ID has been stated by the user or returned by an earlier tool call. | user_messages, tool_outputs |
| user_is_regular_uninsured_and_flies_basic_or_economy | Earlier tool results show that the user is a regular member, the reservation has no travel insurance, and the reservation flies basic economy or economy. | tool_outputs |
| user_wants_change_or_cancellation_due_to_delay | The user wants to change or cancel the reservation because of the complained-about flight delay. | user_messages |

## Background facts for the judge

- [S1] The current time is 2024-05-15 15:00:00 EST.
- [S10] Passengers: Each reservation can have at most five passengers.
- [S13] Payment: each reservation can use at most one travel certificate, at most one credit card, and at most three gift cards.
- [S15] All payment methods must already be in user profile for safety reasons.
- [S16] Checked bag allowance: If the booking user is a regular member, 0 free checked bag for each basic economy passenger, 1 free checked bag for each economy passenger, and 2 free checked bags for each business passenger.
- [S17] If the booking user is a silver member, 1 free checked bag for each basic economy passenger, 2 free checked bag for each economy passenger, and 3 free checked bags for each business passenger.
- [S18] If the booking user is a gold member, 2 free checked bag for each basic economy passenger, 3 free checked bag for each economy passenger, and 3 free checked bags for each business passenger.
- [S20] Travel insurance: the agent should ask if the user wants to buy the travel insurance, which is 30 dollars per passenger and enables full refund if the user needs to cancel the flight given health or weather reasons.
- [S36] All reservations can be cancelled within 24 hours of booking, or if the airline cancelled the flight.
- [S37] Otherwise, basic economy or economy flights can be cancelled only if travel insurance is bought and the condition is met, and business flights can always be cancelled.
- [S38] The rules are strict regardless of the membership status.
- [S43] If the user is silver/gold member or has travel insurance or flies business, and complains about cancelled flights in a reservation, the agent can offer a certificate as a gesture after confirming the facts, with the amount being $100 times the number of passengers.
- [S44] If the user is silver/gold member or has travel insurance or flies business, and complains about delayed flights in a reservation and wants to change or cancel the reservation, the agent can offer a certificate as a gesture after confirming the facts and changing or cancelling the reservation, with the amount being $50 times the number of passengers.
- [S46] Do not compensate if the user is regular member and has no travel insurance and flies (basic) economy.
- [S2] As an airline agent, you can help users book, modify, or cancel flight reservations.
- [S14] The remaining amount of a travel certificate is not refundable.
- [S19] Each extra baggage is 50 dollars.
- [S24] Some flight segments can be kept, but their prices will not be updated based on the current price.
- [S32] This is something that even a human agent cannot assist with.
- [S42] The refund will go to original payment methods in 5 to 7 business days.

## Dispositions (coverage check)

| sentence | section | text | disposition | rules | reason |
|---|---|---|---|---|---|
| S1 | Airline Agent Policy | The current time is 2024-05-15 15:00:00 EST. | fact |  | It supplies the current time used to evaluate the 24-hour cancellation window. |
| S2 | Airline Agent Policy | As an airline agent, you can help users book, modify, or cancel flight reservations. | fact |  | It describes the agent's general service scope. |
| S3 | Airline Agent Policy | Before taking any actions that update the booking database (booking, modifying flights, editing baggage, upgrading cabin class, or updating passenger information), you must list the action details and obtain explicit user confirmation (yes) to proceed. | rule | 10, 11, 13, 14, 16, 17, 19, 20 | Each booking database update requires listed details and explicit user confirmation. |
| S4 | Airline Agent Policy | You should not provide any information, knowledge, or procedures not provided by the user or available tools, or give subjective recommendations or comments. | not_enforceable |  | Grounding, subjectivity, and general response quality cannot be checked as restrictions on one action. |
| S5 | Airline Agent Policy | You should only make one tool call at a time, and if you make a tool call, you should not respond to the user simultaneously. | not_enforceable |  | Simultaneous tool calls and user responses cannot be checked one action at a time. |
| S6 | Airline Agent Policy | If you respond to the user, you should not make a tool call at the same time. | not_enforceable |  | Combining a response and a tool call cannot be checked one action at a time. |
| S7 | Airline Agent Policy | You should deny user requests that are against this policy. | not_enforceable |  | A general obligation to refuse prohibited requests is not a checkable restriction on one action. |
| S8 | Airline Agent Policy | You should transfer the user to a human agent if and only if the request cannot be handled within the scope of your actions. | rule | 32 | The transfer action is restricted to requests outside the available agent scope. |
| S9 | Book flight | The agent must first obtain the user id, then ask for the trip type, origin, destination. | rule | 1, 2 | The required booking identifiers and trip details must be known before booking; the requested order of earlier questions cannot be checked. |
| S10 | Book flight | Passengers: Each reservation can have at most five passengers. | rule | 3 | The passenger limit is checked against the pending booking arguments. |
| S11 | Book flight | The agent needs to collect the first name, last name, and date of birth for each passenger. | rule | 4 | Required passenger details are checked against the pending booking arguments. |
| S12 | Book flight | All passengers must fly the same flights in the same cabin. | rule | 5 | Shared flights and cabin are checked against the pending booking arguments. |
| S13 | Book flight | Payment: each reservation can use at most one travel certificate, at most one credit card, and at most three gift cards. | rule | 6 | The payment-method limits are checked against the pending booking arguments. |
| S14 | Book flight | The remaining amount of a travel certificate is not refundable. | fact |  | It states the refund property of a travel certificate. |
| S15 | Book flight | All payment methods must already be in user profile for safety reasons. | rule | 7 | Booking payment methods are checked against the user's profile. |
| S16 | Book flight | Checked bag allowance: If the booking user is a regular member, 0 free checked bag for each basic economy passenger, 1 free checked bag for each economy passenger, and 2 free checked bags for each business passenger. | rule | 8, 25 | The regular-member baggage allowance is checked for booking and baggage updates. |
| S17 | Book flight | If the booking user is a silver member, 1 free checked bag for each basic economy passenger, 2 free checked bag for each economy passenger, and 3 free checked bags for each business passenger. | rule | 8, 25 | The silver-member baggage allowance is checked for booking and baggage updates. |
| S18 | Book flight | If the booking user is a gold member, 2 free checked bag for each basic economy passenger, 3 free checked bag for each economy passenger, and 3 free checked bags for each business passenger. | rule | 8, 25 | The gold-member baggage allowance is checked for booking and baggage updates. |
| S19 | Book flight | Each extra baggage is 50 dollars. | fact |  | The extra-baggage price is stated, but no available action argument exposes a price to check. |
| S20 | Book flight | Travel insurance: the agent should ask if the user wants to buy the travel insurance, which is 30 dollars per passenger and enables full refund if the user needs to cancel the flight given health or weather reasons. | rule | 9 | The agent must ask about travel insurance before booking. |
| S21 | Modify flight | The agent must first obtain the user id and the reservation id. | rule | 12, 15, 18 | Both identifiers must be known before each reservation modification. |
| S22 | Modify flight | Change flights: Basic economy flights cannot be modified. | rule | 21 | Basic economy flight changes are blocked except for an unchanged itinerary. |
| S23 | Modify flight | Other reservations can be modified without changing the origin, destination, and trip type. | rule | 22 | Flight updates must preserve origin, destination, and trip type. |
| S24 | Modify flight | Some flight segments can be kept, but their prices will not be updated based on the current price. | fact |  | It describes how prices behave for retained segments. |
| S25 | Modify flight | The API does not check these for the agent, so the agent must make sure the rules apply before calling the API! | rule | 21, 22 | The applicable flight-change restrictions are checked before the update action. |
| S26 | Modify flight | Change cabin: all reservations, including basic economy, can change cabin without changing the flights. | exception | 21 | A cabin-only change with an unchanged itinerary is the exception to the basic-economy flight-change prohibition. |
| S27 | Modify flight | Cabin changes require the user to pay for the difference between their current cabin and the new cabin class. | not_enforceable |  | The available flight-update arguments do not expose the cabin price difference or whether that amount was paid. |
| S28 | Modify flight | Cabin class must be the same across all the flights in the same reservation; changing cabin for just one flight segment is not possible. | rule | 23 | The cabin class across updated flight segments is checked in the pending arguments. |
| S29 | Modify flight | Change baggage and insurance: The user can add but not remove checked bags. | rule | 24 | The pending baggage total is compared with the current reservation. |
| S30 | Modify flight | The user cannot add insurance after initial booking. | not_enforceable |  | No available action can add insurance after the initial booking. |
| S31 | Modify flight | Change passengers: The user can modify passengers but cannot modify the number of passengers. | rule | 26 | The passenger count is compared with the current reservation. |
| S32 | Modify flight | This is something that even a human agent cannot assist with. | fact |  | It describes a limitation on human-agent assistance. |
| S33 | Modify flight | Payment: If the flights are changed, the user needs to provide one gift card or credit card for payment or refund method. | rule | 27 | The pending flight update must use a user-provided credit card or gift card. |
| S34 | Modify flight | The agent should ask for the payment or refund method instead. | rule | 28 | The agent must ask for a payment or refund method before the flight update. |
| S35 | Cancel flight | The agent must first obtain the user id, the reservation id, and the reason for cancellation (change of plan, airline cancelled flight, or other reasons) | rule | 29 | The required identifiers and cancellation reason must be known before cancellation. |
| S36 | Cancel flight | All reservations can be cancelled within 24 hours of booking, or if the airline cancelled the flight. | rule | 30 | The 24-hour window and airline-cancellation exception are included in the cancellation eligibility condition. |
| S37 | Cancel flight | Otherwise, basic economy or economy flights can be cancelled only if travel insurance is bought and the condition is met, and business flights can always be cancelled. | rule | 30 | The cabin, insurance, and qualifying-reason cancellation conditions are included. |
| S38 | Cancel flight | The rules are strict regardless of the membership status. | rule | 30 | The cancellation eligibility condition does not depend on membership status. |
| S39 | Cancel flight | The API does not check these for the agent, so the agent must make sure the rules apply before calling the API! | rule | 30 | The cancellation eligibility restrictions are checked before cancellation. |
| S40 | Cancel flight | The agent can only cancel the whole trip that is not flown. | rule | 31 | Cancellation is blocked when any segment has already been flown or used. |
| S41 | Cancel flight | If any of the segments are already used, the agent cannot help and transfer is needed. | not_enforceable |  | A block-only guardrail cannot require the agent to initiate the needed transfer. |
| S42 | Cancel flight | The refund will go to original payment methods in 5 to 7 business days. | fact |  | It states the refund destination and processing timeframe. |
| S43 | Refund | If the user is silver/gold member or has travel insurance or flies business, and complains about cancelled flights in a reservation, the agent can offer a certificate as a gesture after confirming the facts, with the amount being $100 times the number of passengers. | rule | 33 | The cancelled-flight certificate case and its eligibility, confirmation, and amount conditions are checked. |
| S44 | Refund | If the user is silver/gold member or has travel insurance or flies business, and complains about delayed flights in a reservation and wants to change or cancel the reservation, the agent can offer a certificate as a gesture after confirming the facts and changing or cancelling the reservation, with the amount being $50 times the number of passengers. | rule | 33 | The delayed-flight certificate case and its eligibility, confirmation, completion, and amount conditions are checked. |
| S45 | Refund | Do not proactively offer these unless the user complains about the situation and explicitly asks for some compensation. | rule | 34 | A compensation certificate requires an explicit user request for compensation. |
| S46 | Refund | Do not compensate if the user is regular member and has no travel insurance and flies (basic) economy. | rule | 35 | The specified regular-member, uninsured, economy case is prohibited from receiving compensation. |

## Validation

- repair rounds: 0
- remaining errors: none
- invalid rules dropped: none
- exact duplicates dropped: none
- declared but unused predicates: none
