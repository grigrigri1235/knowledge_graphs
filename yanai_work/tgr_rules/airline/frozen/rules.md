# TGR rules: airline (luna-dev, it5)

Flags: A+B. Rules: 34. Predicates: 42.

## Rules

| id | action(s) | logic | description | sentences |
|---|---|---|---|---|
| 1 | book_reservation | `book_reservation IMPLIES pending_database_change_details_listed_and_explicitly_confirmed` | Require listed booking details and explicit user confirmation before booking. | S3 |
| 2 | update_reservation_flights | `update_reservation_flights IMPLIES pending_database_change_details_listed_and_explicitly_confirmed` | Require listed flight-update details and explicit user confirmation before changing flights. | S3 |
| 3 | update_reservation_baggages | `update_reservation_baggages IMPLIES pending_database_change_details_listed_and_explicitly_confirmed` | Require listed baggage-update details and explicit user confirmation before changing baggage. | S3 |
| 4 | update_reservation_passengers | `update_reservation_passengers IMPLIES pending_database_change_details_listed_and_explicitly_confirmed` | Require listed passenger-update details and explicit user confirmation before changing passenger information. | S3 |
| 5 | book_reservation | `book_reservation IMPLIES booking_required_information_established` | Require the booking user's ID, trip type, origin, and destination to be established. | S9 |
| 6 | book_reservation | `book_reservation IMPLIES booking_has_at_most_five_passengers` | Limit each reservation to five passengers. | S10 |
| 7 | book_reservation | `book_reservation IMPLIES passenger_identity_details_established` | Require established first name, last name, and date of birth for every passenger. | S11 |
| 8 | book_reservation | `book_reservation IMPLIES all_booking_passengers_share_flights_and_cabin` | Require all passengers in a reservation to share the same flights and cabin. | S12 |
| 9 | book_reservation | `book_reservation IMPLIES booking_payment_method_counts_within_limits` | Enforce the payment-method count limits for a reservation. | S13 |
| 10 | book_reservation | `book_reservation IMPLIES booking_payment_methods_found_in_user_profile` | Require every booking payment method to be in the user's profile. | S15 |
| 11 | book_reservation | `book_reservation IMPLIES NOT booking_user_is_regular_member OR regular_member_booking_baggage_counts_correct` | Apply the regular-member checked-bag allowance when the booking user is regular. | S16 |
| 12 | book_reservation | `book_reservation IMPLIES NOT booking_user_is_silver_member OR silver_member_booking_baggage_counts_correct` | Apply the silver-member checked-bag allowance when the booking user is silver. | S17 |
| 13 | book_reservation | `book_reservation IMPLIES NOT booking_user_is_gold_member OR gold_member_booking_baggage_counts_correct` | Apply the gold-member checked-bag allowance when the booking user is gold. | S18 |
| 14 | book_reservation | `book_reservation IMPLIES booking_insurance_decision_established_and_matched` | Require the user's travel-insurance decision to be established and reflected in the booking. | S20 |
| 15 | update_reservation_flights | `update_reservation_flights IMPLIES modification_user_and_reservation_ids_established` | Require the user's ID and the pending reservation ID to be established before changing flights. | S21 |
| 16 | update_reservation_baggages | `update_reservation_baggages IMPLIES modification_user_and_reservation_ids_established` | Require the user's ID and the pending reservation ID to be established before changing baggage. | S21 |
| 17 | update_reservation_passengers | `update_reservation_passengers IMPLIES modification_user_and_reservation_ids_established` | Require the user's ID and the pending reservation ID to be established before changing passenger information. | S21 |
| 18 | update_reservation_flights | `update_reservation_flights IMPLIES NOT pending_flight_update_is_basic_economy OR pending_flight_segments_are_unchanged` | Block basic-economy flight changes while retaining the cabin-only change exception when the flights remain unchanged. | S22, S26 |
| 19 | update_reservation_flights | `update_reservation_flights IMPLIES origin_destination_and_trip_type_preserved` | Require a flight update to preserve origin, destination, and trip type. | S23, S25 |
| 20 | update_reservation_flights | `update_reservation_flights IMPLIES all_pending_flight_segments_have_one_cabin` | Require the cabin to be consistent across all flight segments in the reservation. | S28 |
| 21 | update_reservation_baggages | `update_reservation_baggages IMPLIES pending_baggage_total_not_reduced` | Prevent baggage updates from removing checked bags. | S29 |
| 22 | update_reservation_passengers | `update_reservation_passengers IMPLIES pending_passenger_count_unchanged` | Prevent passenger updates from changing the number of passengers. | S31 |
| 23 | update_reservation_flights | `update_reservation_flights IMPLIES NOT pending_flight_update_changes_flights OR user_selected_eligible_flight_change_payment_method` | Require a user-selected gift card or credit card for a flight change. | S33, S34 |
| 24 | cancel_reservation | `cancel_reservation IMPLIES cancellation_context_established` | Require the user's ID, reservation ID, and cancellation reason to be established. | S35 |
| 25 | cancel_reservation | `cancel_reservation IMPLIES cancellation_is_within_24_hours OR airline_cancelled_flight_confirmed OR reservation_has_business_cabin OR reservation_has_basic_or_economy_cabin AND reservation_has_travel_insurance AND insured_cancellation_condition_met` | Allow cancellation within 24 hours, for an airline-cancelled flight, or under the applicable cabin and insurance conditions, without a membership-based exception. | S36, S37, S38, S39 |
| 26 | cancel_reservation | `cancel_reservation IMPLIES reservation_has_no_used_flight_segments` | Prevent cancellation of a trip with any already-used segment. | S40, S41 |
| 27 | transfer_to_human_agents | `transfer_to_human_agents IMPLIES request_cannot_be_handled_with_available_tools` | Restrict transfers to requests that cannot be handled within the agent's scope and available tools. | S8 |
| 28 | send_certificate | `send_certificate IMPLIES cancelled_flight_certificate_send_conditions_met OR delayed_flight_certificate_send_conditions_met` | Restrict certificate issuance to a qualifying, confirmed cancelled-flight or delayed-flight compensation case with the prescribed amount. | S43, S44 |
| 29 | send_certificate | `send_certificate IMPLIES user_complained_about_relevant_flight_situation AND user_explicitly_requested_compensation` | Prevent proactive certificate compensation without a relevant complaint and explicit compensation request. | S45 |
| 30 | send_certificate | `send_certificate IMPLIES NOT compensation_is_prohibited_for_relevant_reservation` | Block compensation for a regular member with no insurance who flies basic economy or economy. | S46 |
| 31 | respond | `respond IMPLIES NOT pending_response_offers_cancelled_flight_certificate OR cancelled_flight_certificate_response_conditions_and_amount_met` | Restrict cancelled-flight certificate offers to confirmed eligible cases with the prescribed amount. | S43 |
| 32 | respond | `respond IMPLIES NOT pending_response_offers_delayed_flight_certificate OR delayed_flight_certificate_response_conditions_and_amount_met` | Restrict delayed-flight certificate offers to confirmed eligible cases after the reservation is changed or cancelled and with the prescribed amount. | S44 |
| 33 | respond | `respond IMPLIES NOT pending_response_offers_any_compensation_certificate OR user_complained_about_relevant_flight_situation AND user_explicitly_requested_compensation` | Prevent proactive compensation-certificate offers without a relevant complaint and explicit compensation request. | S45 |
| 34 | respond | `respond IMPLIES NOT pending_response_offers_any_compensation_certificate OR NOT compensation_is_prohibited_for_relevant_reservation` | Prevent offering compensation to a regular member with no insurance who flies basic economy or economy. | S46 |

## Predicates

| name | description | source |
|---|---|---|
| airline_cancelled_flight_confirmed | Earlier tool outputs or user messages establish that the airline cancelled a flight in the reservation. | tool_outputs, user_messages |
| all_booking_passengers_share_flights_and_cabin | The pending booking assigns every passenger the same flights and the same cabin. | call_arguments |
| all_pending_flight_segments_have_one_cabin | The cabin in the pending flight-update arguments is the same across every flight segment in the entire submitted reservation. | call_arguments |
| booking_has_at_most_five_passengers | The pending booking contains no more than five passengers. | call_arguments |
| booking_insurance_decision_established_and_matched | The user's decision about travel insurance is established in an earlier user message, and the pending booking's insurance argument matches that decision. | call_arguments, user_messages |
| booking_payment_method_counts_within_limits | The pending booking uses no more than one travel certificate, no more than one credit card, and no more than three gift cards. | call_arguments |
| booking_payment_methods_found_in_user_profile | Every payment method in the pending booking appears in an earlier tool output showing the user's profile. | call_arguments, tool_outputs |
| booking_required_information_established | The user ID, trip type, origin, and destination are established in earlier user messages or tool outputs, and the pending booking arguments match those values. | call_arguments, user_messages, tool_outputs |
| booking_user_is_gold_member | An earlier tool output identifies the booking user as a gold member. | tool_outputs |
| booking_user_is_regular_member | An earlier tool output identifies the booking user as a regular member. | tool_outputs |
| booking_user_is_silver_member | An earlier tool output identifies the booking user as a silver member. | tool_outputs |
| cancellation_context_established | The user's ID, the reservation ID in the pending cancellation, and a cancellation reason of change of plan, airline-cancelled flight, or other reasons are established in earlier user messages or tool outputs; the reservation ID matches the pending call argument. | call_arguments, user_messages, tool_outputs |
| cancellation_is_within_24_hours | Earlier tool outputs or user messages establish that the reservation was booked within 24 hours of the current time stated in the policy. | tool_outputs, user_messages |
| cancelled_flight_certificate_response_conditions_and_amount_met | Earlier messages establish a complaint about cancelled flights; earlier tool outputs confirm the relevant cancelled-flight facts and compensation eligibility; and the pending response states $100 multiplied by the relevant reservation's passenger count. | call_arguments, user_messages, tool_outputs |
| cancelled_flight_certificate_send_conditions_met | Earlier messages establish a complaint about cancelled flights; earlier tool outputs confirm the relevant cancelled-flight facts and compensation eligibility; and the pending certificate recipient and amount match the relevant user and $100-per-passenger formula. | call_arguments, user_messages, tool_outputs |
| compensation_is_prohibited_for_relevant_reservation | Earlier tool outputs establish that the user is regular, has no travel insurance for the relevant reservation, and flies basic economy or economy in that reservation. | tool_outputs |
| delayed_flight_certificate_response_conditions_and_amount_met | Earlier messages establish a complaint about delayed flights and a wish to change or cancel the reservation; earlier tool outputs confirm the relevant delay facts, compensation eligibility, and a completed change or cancellation; and the pending response states $50 multiplied by the relevant reservation's passenger count. | call_arguments, user_messages, tool_outputs |
| delayed_flight_certificate_send_conditions_met | Earlier messages establish a complaint about delayed flights and a wish to change or cancel the reservation; earlier tool outputs confirm the relevant delay facts, compensation eligibility, and a completed change or cancellation; and the pending certificate recipient and amount match the relevant user and $50-per-passenger formula. | call_arguments, user_messages, tool_outputs |
| gold_member_booking_baggage_counts_correct | The pending booking's total and nonfree baggage counts match the checked-bag allowances for a gold member and the cabin of each passenger, with nonfree baggage accounting for bags beyond the applicable free allowance. | call_arguments, tool_outputs |
| insured_cancellation_condition_met | Earlier user messages or tool outputs establish that the insured cancellation is needed for a health or weather reason. | user_messages, tool_outputs |
| modification_user_and_reservation_ids_established | The user's ID and the reservation ID in the pending modification are established in earlier user messages or tool outputs, and the established reservation ID matches the pending call argument. | call_arguments, user_messages, tool_outputs |
| origin_destination_and_trip_type_preserved | The origin, destination, and trip type in the pending flight update match the reservation details shown in earlier tool outputs. | call_arguments, tool_outputs |
| passenger_identity_details_established | The first name, last name, and date of birth for every passenger in the pending booking are established in earlier user messages or tool outputs, and match the pending arguments. | call_arguments, user_messages, tool_outputs |
| pending_baggage_total_not_reduced | The pending baggage update's total baggage count is at least the current total shown in earlier reservation details. | call_arguments, tool_outputs |
| pending_database_change_details_listed_and_explicitly_confirmed | The agent previously listed the material details of the pending database change, the user subsequently explicitly replied yes to those details, and the listed details match the pending call arguments. | call_arguments, agent_messages, user_messages |
| pending_flight_segments_are_unchanged | The flights in the pending update match all the reservation's current flight segments shown in earlier tool outputs. | call_arguments, tool_outputs |
| pending_flight_update_changes_flights | The flights in the pending update differ from the current reservation flights shown in earlier tool outputs. | call_arguments, tool_outputs |
| pending_flight_update_is_basic_economy | Earlier reservation details identify the reservation in the pending flight update as basic economy. | call_arguments, tool_outputs |
| pending_passenger_count_unchanged | The number of passengers in the pending passenger update equals the number in earlier reservation details. | call_arguments, tool_outputs |
| pending_response_offers_any_compensation_certificate | The pending response offers or promises a certificate as compensation or a gesture. | call_arguments |
| pending_response_offers_cancelled_flight_certificate | The pending response offers or promises a gesture certificate concerning cancelled flights. | call_arguments |
| pending_response_offers_delayed_flight_certificate | The pending response offers or promises a gesture certificate concerning delayed flights. | call_arguments |
| regular_member_booking_baggage_counts_correct | The pending booking's total and nonfree baggage counts match the checked-bag allowances for a regular member and the cabin of each passenger, with nonfree baggage accounting for bags beyond the applicable free allowance. | call_arguments, tool_outputs |
| request_cannot_be_handled_with_available_tools | The conversation and earlier tool outputs establish that the user's request cannot be completed within the agent's stated scope and available tools, including situations the policy says the agent cannot help with. | user_messages, tool_outputs |
| reservation_has_basic_or_economy_cabin | Earlier reservation details identify a flight in the reservation as basic economy or economy cabin. | tool_outputs |
| reservation_has_business_cabin | Earlier reservation details identify a flight in the reservation as business cabin. | tool_outputs |
| reservation_has_no_used_flight_segments | Earlier reservation details establish that none of the reservation's flight segments has been used. | tool_outputs |
| reservation_has_travel_insurance | Earlier reservation details establish that travel insurance was bought for the reservation. | tool_outputs |
| silver_member_booking_baggage_counts_correct | The pending booking's total and nonfree baggage counts match the checked-bag allowances for a silver member and the cabin of each passenger, with nonfree baggage accounting for bags beyond the applicable free allowance. | call_arguments, tool_outputs |
| user_complained_about_relevant_flight_situation | Earlier user messages establish a complaint about the cancelled or delayed flight situation relevant to the compensation being offered or sent. | user_messages |
| user_explicitly_requested_compensation | The user explicitly requested compensation in an earlier message. | user_messages |
| user_selected_eligible_flight_change_payment_method | The user selected a gift card or credit card for the pending flight change's payment or refund method, and that selection matches the pending payment ID and is shown as a stored payment method in earlier profile outputs. | call_arguments, user_messages, tool_outputs |

## Background facts for the judge

- [S1] The current time is 2024-05-15 15:00:00 EST.
- [S16] Checked bag allowance: If the booking user is a regular member, 0 free checked bag for each basic economy passenger, 1 free checked bag for each economy passenger, and 2 free checked bags for each business passenger.
- [S17] If the booking user is a silver member, 1 free checked bag for each basic economy passenger, 2 free checked bag for each economy passenger, and 3 free checked bags for each business passenger.
- [S18] If the booking user is a gold member, 2 free checked bag for each basic economy passenger, 3 free checked bag for each economy passenger, and 3 free checked bags for each business passenger.
- [S20] Travel insurance: the agent should ask if the user wants to buy the travel insurance, which is 30 dollars per passenger and enables full refund if the user needs to cancel the flight given health or weather reasons.
- [S36] All reservations can be cancelled within 24 hours of booking, or if the airline cancelled the flight.
- [S43] If the user is silver/gold member or has travel insurance or flies business, and complains about cancelled flights in a reservation, the agent can offer a certificate as a gesture after confirming the facts, with the amount being $100 times the number of passengers.
- [S44] If the user is silver/gold member or has travel insurance or flies business, and complains about delayed flights in a reservation and wants to change or cancel the reservation, the agent can offer a certificate as a gesture after confirming the facts and changing or cancelling the reservation, with the amount being $50 times the number of passengers.
- [S2] As an airline agent, you can help users book, modify, or cancel flight reservations.
- [S14] The remaining amount of a travel certificate is not refundable.
- [S24] Some flight segments can be kept, but their prices will not be updated based on the current price.
- [S32] This is something that even a human agent cannot assist with.
- [S42] The refund will go to original payment methods in 5 to 7 business days.

## Dispositions (coverage check)

| sentence | section | text | disposition | rules | reason |
|---|---|---|---|---|---|
| S1 | Airline Agent Policy | The current time is 2024-05-15 15:00:00 EST. | fact |  | The current time is a fixed fact used to evaluate the cancellation window. |
| S2 | Airline Agent Policy | As an airline agent, you can help users book, modify, or cancel flight reservations. | fact |  | This describes the agent's general service scope. |
| S3 | Airline Agent Policy | Before taking any actions that update the booking database (booking, modifying flights, editing baggage, upgrading cabin class, or updating passenger information), you must list the action details and obtain explicit user confirmation (yes) to proceed. | rule | 1, 2, 3, 4 | Each database-update action requires listed details and explicit confirmation. |
| S4 | Airline Agent Policy | You should not provide any information, knowledge, or procedures not provided by the user or available tools, or give subjective recommendations or comments. | not_enforceable |  | General grounding and subjectivity requirements cannot be checked as restrictions on a single action. |
| S5 | Airline Agent Policy | You should only make one tool call at a time, and if you make a tool call, you should not respond to the user simultaneously. | not_enforceable |  | Combining or sequencing multiple calls and messages in a turn cannot be checked one action at a time. |
| S6 | Airline Agent Policy | If you respond to the user, you should not make a tool call at the same time. | not_enforceable |  | Combining a response and a tool call in one turn cannot be checked one action at a time. |
| S7 | Airline Agent Policy | You should deny user requests that are against this policy. | not_enforceable |  | A general requirement to deny policy-violating requests is not a restriction on one specific action. |
| S8 | Airline Agent Policy | You should transfer the user to a human agent if and only if the request cannot be handled within the scope of your actions. | rule | 27 | The transfer action is restricted to requests outside the available scope. |
| S9 | Book flight | The agent must first obtain the user id, then ask for the trip type, origin, destination. | rule | 5 | The required booking information must be established before booking. |
| S10 | Book flight | Passengers: Each reservation can have at most five passengers. | rule | 6 | The pending booking's passenger count is checkable. |
| S11 | Book flight | The agent needs to collect the first name, last name, and date of birth for each passenger. | rule | 7 | Passenger identity information must be established for every passenger. |
| S12 | Book flight | All passengers must fly the same flights in the same cabin. | rule | 8 | The passengers' flights and cabin can be checked in the pending booking. |
| S13 | Book flight | Payment: each reservation can use at most one travel certificate, at most one credit card, and at most three gift cards. | rule | 9 | Payment-method counts are checkable from the pending booking arguments. |
| S14 | Book flight | The remaining amount of a travel certificate is not refundable. | fact |  | This describes the refund treatment of a certificate balance. |
| S15 | Book flight | All payment methods must already be in user profile for safety reasons. | rule | 10 | Profile outputs can establish whether each payment method is already on file. |
| S16 | Book flight | Checked bag allowance: If the booking user is a regular member, 0 free checked bag for each basic economy passenger, 1 free checked bag for each economy passenger, and 2 free checked bags for each business passenger. | rule | 11 | The regular-member baggage allowance can be checked against the booking arguments. |
| S17 | Book flight | If the booking user is a silver member, 1 free checked bag for each basic economy passenger, 2 free checked bag for each economy passenger, and 3 free checked bags for each business passenger. | rule | 12 | The silver-member baggage allowance can be checked against the booking arguments. |
| S18 | Book flight | If the booking user is a gold member, 2 free checked bag for each basic economy passenger, 3 free checked bag for each economy passenger, and 3 free checked bags for each business passenger. | rule | 13 | The gold-member baggage allowance can be checked against the booking arguments. |
| S19 | Book flight | Each extra baggage is 50 dollars. | not_enforceable |  | The booking action exposes no price or charge amount to check against the per-bag fee. |
| S20 | Book flight | Travel insurance: the agent should ask if the user wants to buy the travel insurance, which is 30 dollars per passenger and enables full refund if the user needs to cancel the flight given health or weather reasons. | rule | 14 | The user's insurance decision must be established and reflected in the booking. |
| S21 | Modify flight | The agent must first obtain the user id and the reservation id. | rule | 15, 16, 17 | Each reservation-modification action requires the user and reservation IDs to be established. |
| S22 | Modify flight | Change flights: Basic economy flights cannot be modified. | rule | 18 | The flight-update action blocks flight changes for basic-economy reservations. |
| S23 | Modify flight | Other reservations can be modified without changing the origin, destination, and trip type. | rule | 19 | The pending flight update can be checked for preserved origin, destination, and trip type. |
| S24 | Modify flight | Some flight segments can be kept, but their prices will not be updated based on the current price. | fact |  | This describes how kept flight segments are priced. |
| S25 | Modify flight | The API does not check these for the agent, so the agent must make sure the rules apply before calling the API! | rule | 18, 19 | The API warning is represented by preconditions enforcing the applicable flight-change limits. |
| S26 | Modify flight | Change cabin: all reservations, including basic economy, can change cabin without changing the flights. | exception | 18 | The unchanged-flight alternative permits a cabin-only change, including for basic economy. |
| S27 | Modify flight | Cabin changes require the user to pay for the difference between their current cabin and the new cabin class. | not_enforceable |  | The action arguments do not expose the cabin-price difference or evidence that it was paid. |
| S28 | Modify flight | Cabin class must be the same across all the flights in the same reservation; changing cabin for just one flight segment is not possible. | rule | 20 | The cabin consistency of all submitted flight segments is checkable. |
| S29 | Modify flight | Change baggage and insurance: The user can add but not remove checked bags. | rule | 21 | The pending baggage total can be compared with the current reservation total. |
| S30 | Modify flight | The user cannot add insurance after initial booking. | not_enforceable |  | No available action adds insurance to an existing reservation. |
| S31 | Modify flight | Change passengers: The user can modify passengers but cannot modify the number of passengers. | rule | 22 | The submitted passenger count can be compared with the current reservation. |
| S32 | Modify flight | This is something that even a human agent cannot assist with. | fact |  | This describes the limits of human-agent assistance. |
| S33 | Modify flight | Payment: If the flights are changed, the user needs to provide one gift card or credit card for payment or refund method. | rule | 23 | A flight-changing update requires an established user-selected payment or refund method. |
| S34 | Modify flight | The agent should ask for the payment or refund method instead. | rule | 23 | The selected payment or refund method must be established before the flight update. |
| S35 | Cancel flight | The agent must first obtain the user id, the reservation id, and the reason for cancellation (change of plan, airline cancelled flight, or other reasons) | rule | 24 | The required cancellation context must be established before cancellation. |
| S36 | Cancel flight | All reservations can be cancelled within 24 hours of booking, or if the airline cancelled the flight. | exception | 25 | The 24-hour and airline-cancellation cases are alternatives in the cancellation restriction. |
| S37 | Cancel flight | Otherwise, basic economy or economy flights can be cancelled only if travel insurance is bought and the condition is met, and business flights can always be cancelled. | rule | 25 | The cancellation rule checks cabin, insurance, and the insured cancellation condition. |
| S38 | Cancel flight | The rules are strict regardless of the membership status. | rule | 25 | The cancellation eligibility rule does not provide a membership-based exception. |
| S39 | Cancel flight | The API does not check these for the agent, so the agent must make sure the rules apply before calling the API! | rule | 25 | The API warning is represented by the cancellation eligibility precondition. |
| S40 | Cancel flight | The agent can only cancel the whole trip that is not flown. | rule | 26 | Cancellation is restricted to reservations with no used segments. |
| S41 | Cancel flight | If any of the segments are already used, the agent cannot help and transfer is needed. | rule | 26 | The used-segment case blocks cancellation; the separate obligation to transfer cannot be enforced as a restriction. |
| S42 | Cancel flight | The refund will go to original payment methods in 5 to 7 business days. | fact |  | This states the refund destination and processing timeframe. |
| S43 | Refund | If the user is silver/gold member or has travel insurance or flies business, and complains about cancelled flights in a reservation, the agent can offer a certificate as a gesture after confirming the facts, with the amount being $100 times the number of passengers. | rule | 28, 31 | Certificate issuance and cancelled-flight offers are limited to confirmed eligible cases with the required amount. |
| S44 | Refund | If the user is silver/gold member or has travel insurance or flies business, and complains about delayed flights in a reservation and wants to change or cancel the reservation, the agent can offer a certificate as a gesture after confirming the facts and changing or cancelling the reservation, with the amount being $50 times the number of passengers. | rule | 28, 32 | Delayed-flight certificate actions require confirmed eligibility, a completed change or cancellation, and the required amount. |
| S45 | Refund | Do not proactively offer these unless the user complains about the situation and explicitly asks for some compensation. | rule | 29, 33 | Certificate sending and offers require a relevant complaint and explicit compensation request. |
| S46 | Refund | Do not compensate if the user is regular member and has no travel insurance and flies (basic) economy. | rule | 30, 34 | The prohibited membership, insurance, and cabin combination blocks certificate sending and offers. |

## Validation

- repair rounds: 1
- remaining errors: none
- invalid rules dropped: none
- exact duplicates dropped: none
- declared but unused predicates: ['cancelled_flight_compensation_facts_confirmed', 'compensation_eligibility_established_for_reservation', 'delayed_flight_compensation_facts_confirmed', 'pending_certificate_amount_matches_cancelled_flight_formula', 'pending_certificate_amount_matches_delayed_flight_formula', 'pending_certificate_recipient_matches_relevant_user', 'relevant_reservation_changed_or_cancelled_before', 'user_complained_about_cancelled_flights', 'user_complained_about_delayed_flights', 'user_wants_change_or_cancellation_for_delay']
