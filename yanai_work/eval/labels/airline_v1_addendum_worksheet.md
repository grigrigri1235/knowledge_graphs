# E2 worksheet — airline — output/auto_aspm/airline/v1_addendum

Auto rules: 121

## AIR-GEN-01a
- gold quote: "Before taking any actions that update the booking database (booking, modifying flights, editing baggage, upgrading cabin class, or updating passenger information), you must list the action details"
- gold reading: Before any booking-database update, the agent lists the action details to the user.
- GOLD AIR-R001: The agent must list the action details to the user before calling any tool that updates the booking database (booking, cancelling, changing flights or cabin, editing baggage, or updating passengers).
- aligned auto clauses: S0-C03
  - SRC S0-C02-R1 [book_reservation; must_not]: The agent must not book a reservation unless the action details are listed and explicit user confirmation (yes) to proceed.
  - SRC S0-C02-R2 [book_reservation,cancel_reservation,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must_not]: The agent must not modify flight reservations unless the action details are listed and explicit user confirmation (yes) to proceed.
  - SRC S0-C02-R3 [update_reservation_baggages; must_not]: The agent must not update baggage information unless the action details are listed and explicit user confirmation (yes) to proceed.
  - SRC S0-C02-R4 [book_reservation,update_reservation_flights; must_not]: The agent must not upgrade cabin class unless the action details are listed and explicit user confirmation (yes) to proceed.
  - SRC S0-C02-R5 [update_reservation_passengers; must_not]: The agent must not update passenger information unless the action details are listed and explicit user confirmation (yes) to proceed.
  - SRC S0-C02-R6 [cancel_reservation; must_not]: The agent must not cancel a reservation unless the action details are listed and explicit user confirmation (yes) to proceed.
  - SRC S0-C03-R1 [book_reservation,cancel_reservation,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must]: The agent must list the action details and obtain explicit user confirmation (yes) to proceed before taking any actions that update the booking database (booking, modifying flights, editing baggage, upgrading cabin class, or updating passenger information).
  - SRC S0-C07-R2 [book_reservation; must_not]: The agent must not book a reservation in response to a user request that is against this policy.
  - SRC S0-C07-R3 [update_reservation_flights; must_not]: The agent must not update flight information in a reservation in response to a user request that is against this policy.
  - SRC S0-C07-R4 [update_reservation_baggages; must_not]: The agent must not update baggage information in a reservation in response to a user request that is against this policy.
  - SRC S0-C07-R5 [update_reservation_passengers; must_not]: The agent must not update passenger information in a reservation in response to a user request that is against this policy.
  - SRC S0-C07-R6 [book_reservation,update_reservation_flights; must_not]: The agent must not upgrade cabin class in a reservation in response to a user request that is against this policy.
  - SIM S5-C03-R3 [cancel_reservation,respond_to_user,send_certificate,update_reservation_flights,update_reservation_passengers; may]: The agent must offer a certificate as a gesture after confirming the facts and changing or cancelling the reservation, with the amount being $50 times the number of passengers, if the user is silver/gold member or has travel insurance or flies business, and complains about delayed flights in a reservation and wants to change or cancel the reservation.
  - SIM S3-C07-R2 [book_reservation,cancel_reservation,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must]: The agent must list the details of the actions to be performed before calling any booking-modifying API.

## AIR-GEN-01b
- gold quote: "obtain explicit user confirmation (yes) to proceed."
- gold reading: Before any booking-database update, the agent obtains an explicit 'yes' from the user.
- GOLD AIR-R002: The agent must obtain an explicit 'yes' from the user, given after the action details were listed, before calling any tool that updates the booking database.
- aligned auto clauses: S0-C03
  - SRC S0-C02-R1 [book_reservation; must_not]: The agent must not book a reservation unless the action details are listed and explicit user confirmation (yes) to proceed.
  - SRC S0-C02-R2 [book_reservation,cancel_reservation,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must_not]: The agent must not modify flight reservations unless the action details are listed and explicit user confirmation (yes) to proceed.
  - SRC S0-C02-R3 [update_reservation_baggages; must_not]: The agent must not update baggage information unless the action details are listed and explicit user confirmation (yes) to proceed.
  - SRC S0-C02-R4 [book_reservation,update_reservation_flights; must_not]: The agent must not upgrade cabin class unless the action details are listed and explicit user confirmation (yes) to proceed.
  - SRC S0-C02-R5 [update_reservation_passengers; must_not]: The agent must not update passenger information unless the action details are listed and explicit user confirmation (yes) to proceed.
  - SRC S0-C02-R6 [cancel_reservation; must_not]: The agent must not cancel a reservation unless the action details are listed and explicit user confirmation (yes) to proceed.
  - SRC S0-C03-R1 [book_reservation,cancel_reservation,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must]: The agent must list the action details and obtain explicit user confirmation (yes) to proceed before taking any actions that update the booking database (booking, modifying flights, editing baggage, upgrading cabin class, or updating passenger information).
  - SRC S0-C07-R2 [book_reservation; must_not]: The agent must not book a reservation in response to a user request that is against this policy.
  - SRC S0-C07-R3 [update_reservation_flights; must_not]: The agent must not update flight information in a reservation in response to a user request that is against this policy.
  - SRC S0-C07-R4 [update_reservation_baggages; must_not]: The agent must not update baggage information in a reservation in response to a user request that is against this policy.
  - SRC S0-C07-R5 [update_reservation_passengers; must_not]: The agent must not update passenger information in a reservation in response to a user request that is against this policy.
  - SRC S0-C07-R6 [book_reservation,update_reservation_flights; must_not]: The agent must not upgrade cabin class in a reservation in response to a user request that is against this policy.
  - SIM S3-C07-R3 [book_reservation,cancel_reservation,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must]: The agent must obtain explicit confirmation from the user before calling any booking-modifying API.
  - SIM S3-C07-R2 [book_reservation,cancel_reservation,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must]: The agent must list the details of the actions to be performed before calling any booking-modifying API.

## AIR-GEN-02a
- gold quote: "You should not provide any information, knowledge, or procedures not provided by the user or available tools"
- gold reading: The agent must not state information/knowledge/procedures that come neither from the user nor from tool outputs.
- GOLD AIR-R003: The agent must not provide information, knowledge, or procedures that were not provided by the user or by the available tools.
- aligned auto clauses: S0-C04
  - SRC S0-C02-R8 [respond_to_user,think; must_not]: The agent must not provide any information, knowledge, or procedures not provided by the user or available tools, or give subjective recommendations or comments.
  - SRC S0-C04-R1 [respond_to_user; must_not]: The agent must not provide any information, knowledge, or procedures not provided by the user or available tools.
  - SRC S0-C04-R2 [respond_to_user; must_not]: The agent must not give subjective recommendations or comments.
  - SIM S0-C02-R12 [transfer_to_human_agents; if_and_only_if]: The agent must transfer the user to a human agent if and only if the request cannot be handled within the scope of your actions.

## AIR-GEN-02b
- gold quote: "or give subjective recommendations or comments."
- gold reading: The agent must not give subjective recommendations or comments.
- GOLD AIR-R004: The agent must not give subjective recommendations or comments.
- aligned auto clauses: S0-C04
  - SRC S0-C02-R8 [respond_to_user,think; must_not]: The agent must not provide any information, knowledge, or procedures not provided by the user or available tools, or give subjective recommendations or comments.
  - SRC S0-C04-R1 [respond_to_user; must_not]: The agent must not provide any information, knowledge, or procedures not provided by the user or available tools.
  - SRC S0-C04-R2 [respond_to_user; must_not]: The agent must not give subjective recommendations or comments.
  - SIM S2-C12-R1 [book_reservation,respond_to_user; may]: The agent must ask if the user wants to buy the travel insurance.

## AIR-GEN-03a
- gold quote: "You should only make one tool call at a time"
- gold reading: At most one tool call per agent turn.
- GOLD AIR-R005: The agent must make at most one tool call per turn.
- aligned auto clauses: S0-C05
  - SRC S0-C02-R9 [book_reservation,calculate,cancel_reservation,get_reservation_details,get_user_details,list_all_airports,search_direct_flight,search_onestop_flight,send_certificate,think,transfer_to_human_agents,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must_not]: The agent must not make more than one tool call at a time, and if you make a tool call, you should not respond to the user simultaneously.
  - SRC S0-C05-R1 [book_reservation,calculate,cancel_reservation,get_reservation_details,get_user_details,list_all_airports,search_direct_flight,search_onestop_flight,send_certificate,think,transfer_to_human_agents,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must_not]: The agent must not make more than one tool call at a time.
  - SRC S0-C05-R2 [book_reservation,calculate,cancel_reservation,get_reservation_details,get_user_details,list_all_airports,respond_to_user,search_direct_flight,search_onestop_flight,send_certificate,think,transfer_to_human_agents,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must_not]: The agent must not respond to the user at the same time as a tool call is made.
  - SIM S0-C06-R2 [book_reservation,cancel_reservation,get_reservation_details,get_user_details,list_all_airports,search_direct_flight,search_onestop_flight,send_certificate,transfer_to_human_agents,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must]: The agent must only make one tool call at a time, and if the agent makes a tool call, the agent must not respond to the user simultaneously.

## AIR-GEN-03b
- gold quote: "if you make a tool call, you should not respond to the user simultaneously."
- gold reading: A turn with a tool call contains no user-facing message.
- GOLD AIR-R006: The agent must not respond to the user and make a tool call in the same turn.
- aligned auto clauses: S0-C05
  - SRC S0-C02-R9 [book_reservation,calculate,cancel_reservation,get_reservation_details,get_user_details,list_all_airports,search_direct_flight,search_onestop_flight,send_certificate,think,transfer_to_human_agents,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must_not]: The agent must not make more than one tool call at a time, and if you make a tool call, you should not respond to the user simultaneously.
  - SRC S0-C05-R1 [book_reservation,calculate,cancel_reservation,get_reservation_details,get_user_details,list_all_airports,search_direct_flight,search_onestop_flight,send_certificate,think,transfer_to_human_agents,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must_not]: The agent must not make more than one tool call at a time.
  - SRC S0-C05-R2 [book_reservation,calculate,cancel_reservation,get_reservation_details,get_user_details,list_all_airports,respond_to_user,search_direct_flight,search_onestop_flight,send_certificate,think,transfer_to_human_agents,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must_not]: The agent must not respond to the user at the same time as a tool call is made.
  - SIM S0-C06-R2 [book_reservation,cancel_reservation,get_reservation_details,get_user_details,list_all_airports,search_direct_flight,search_onestop_flight,send_certificate,transfer_to_human_agents,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must]: The agent must only make one tool call at a time, and if the agent makes a tool call, the agent must not respond to the user simultaneously.

## AIR-GEN-03c
- gold quote: "If you respond to the user, you should not make a tool call at the same time."
- gold reading: A turn with a user-facing message contains no tool call (converse of AIR-GEN-03b).
- GOLD AIR-R006: The agent must not respond to the user and make a tool call in the same turn.
- aligned auto clauses: S0-C06
  - SRC S0-C02-R9 [book_reservation,calculate,cancel_reservation,get_reservation_details,get_user_details,list_all_airports,search_direct_flight,search_onestop_flight,send_certificate,think,transfer_to_human_agents,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must_not]: The agent must not make more than one tool call at a time, and if you make a tool call, you should not respond to the user simultaneously.
  - SRC S0-C02-R10 [respond_to_user; must_not]: The agent must not respond to the user while a tool call is in progress.
  - SRC S0-C06-R1 [book_reservation,calculate,cancel_reservation,get_reservation_details,get_user_details,list_all_airports,search_direct_flight,search_onestop_flight,send_certificate,think,transfer_to_human_agents,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must]: The agent must not perform a tool call while sending a response to the user.
  - SRC S0-C06-R2 [book_reservation,cancel_reservation,get_reservation_details,get_user_details,list_all_airports,search_direct_flight,search_onestop_flight,send_certificate,transfer_to_human_agents,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must]: The agent must only make one tool call at a time, and if the agent makes a tool call, the agent must not respond to the user simultaneously.
  - SIM S0-C05-R2 [book_reservation,calculate,cancel_reservation,get_reservation_details,get_user_details,list_all_airports,respond_to_user,search_direct_flight,search_onestop_flight,send_certificate,think,transfer_to_human_agents,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must_not]: The agent must not respond to the user at the same time as a tool call is made.

## AIR-GEN-04
- gold quote: "You should deny user requests that are against this policy."
- gold reading: The agent refuses (does not carry out) requests that violate the policy.
- GOLD AIR-R007: The agent must deny (refuse to carry out) user requests that are against this policy.
- aligned auto clauses: S0-C07
  - SRC S0-C07-R1 [respond_to_user; must]: The agent must deny user requests that are against this policy.
  - SRC S0-C07-R2 [book_reservation; must_not]: The agent must not book a reservation in response to a user request that is against this policy.
  - SRC S0-C07-R3 [update_reservation_flights; must_not]: The agent must not update flight information in a reservation in response to a user request that is against this policy.
  - SRC S0-C07-R4 [update_reservation_baggages; must_not]: The agent must not update baggage information in a reservation in response to a user request that is against this policy.
  - SRC S0-C07-R5 [update_reservation_passengers; must_not]: The agent must not update passenger information in a reservation in response to a user request that is against this policy.
  - SRC S0-C07-R6 [book_reservation,update_reservation_flights; must_not]: The agent must not upgrade cabin class in a reservation in response to a user request that is against this policy.

## AIR-GEN-05a
- gold quote: "You should transfer the user to a human agent if and only if the request cannot be handled within the scope of your actions."
- gold reading: ONLY-IF direction: the agent must not transfer when the request can be handled within its scope.
- GOLD AIR-R008: The agent must not transfer the user to a human agent unless the request cannot be handled within the scope of the agent's actions or the user explicitly asks for a human agent.
- aligned auto clauses: S0-C08
  - SRC S0-C02-R12 [transfer_to_human_agents; if_and_only_if]: The agent must transfer the user to a human agent if and only if the request cannot be handled within the scope of your actions.
  - SIM S4-C07-R6 [book_reservation,cancel_reservation,get_reservation_details,get_user_details,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must]: The agent must transfer to a human agent if any of the segments are already used.
  - SIM S4-C09-R2 [cancel_reservation,get_reservation_details,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must]: The agent must transfer to human agents if any of the segments are already used.

## AIR-GEN-05b
- gold quote: "You should transfer the user to a human agent if and only if the request cannot be handled within the scope of your actions."
- gold reading: IF direction: when the request cannot be handled within scope, the agent transfers.
- GOLD AIR-R009: The agent must transfer the user to a human agent when the request cannot be handled within the scope of the agent's actions.
- aligned auto clauses: S0-C08
  - SRC S0-C02-R12 [transfer_to_human_agents; if_and_only_if]: The agent must transfer the user to a human agent if and only if the request cannot be handled within the scope of your actions.
  - SIM S4-C07-R6 [book_reservation,cancel_reservation,get_reservation_details,get_user_details,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must]: The agent must transfer to a human agent if any of the segments are already used.
  - SIM S4-C09-R2 [cancel_reservation,get_reservation_details,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must]: The agent must transfer to human agents if any of the segments are already used.

## AIR-DOM-04c
- gold quote: "If the status is "delayed" or "on time", the flight has not taken off, cannot be booked."
- gold reading: A flight-date with status 'delayed' or 'on time' must not be booked.
- GOLD AIR-R010: The agent must not book a flight, or add a new flight to an existing reservation, unless the flight's status on that date is 'available'.
- aligned auto clauses: S1-C05, S1-C06
  - SRC S1-C06-R1 [book_reservation; must_not]: The agent must not book the flight if the status is 'delayed' or 'on time'.
  - SIM S1-C08-R1 [book_reservation; must_not]: The agent must not book a flight if the status is "flying".
  - SIM S4-C08-R3 [cancel_reservation; must_not]: The agent must not cancel unless within 24 hours of booking, or the airline cancelled the flight, or the flight is a business flight.

## AIR-DOM-04e
- gold quote: "If the status is "flying", the flight has taken off but not landed, cannot be booked."
- gold reading: A flight-date with status 'flying' must not be booked.
- GOLD AIR-R010: The agent must not book a flight, or add a new flight to an existing reservation, unless the flight's status on that date is 'available'.
- aligned auto clauses: S1-C07, S1-C08
  - SRC S1-C08-R1 [book_reservation; must_not]: The agent must not book a flight if the status is "flying".
  - SIM S4-C08-R3 [cancel_reservation; must_not]: The agent must not cancel unless within 24 hours of booking, or the airline cancelled the flight, or the flight is a business flight.
  - SIM S4-C07-R2 [cancel_reservation; must_not]: The agent must not cancel a reservation unless it is within 24 hours of booking, or if the airline cancelled the flight.

## AIR-BOOK-01a
- gold quote: "The agent must first obtain the user id"
- gold reading: When booking, the agent obtains the user id first (before the trip details).
- GOLD AIR-R011: When booking a flight, the agent must obtain the user id first, before collecting the trip type, origin, and destination.
- aligned auto clauses: S2-C01
  - SRC S2-C01-R1 [book_reservation,cancel_reservation,get_reservation_details,get_user_details,respond_to_user,search_direct_flight,search_onestop_flight,send_certificate,transfer_to_human_agents,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must]: The agent must locate the user id by using the email address or by the user's name and zip code, before performing any other action.
  - SRC S2-C01-R2 [book_reservation,respond_to_user,search_direct_flight,search_onestop_flight; must]: The agent must ask for the trip type, origin, and destination only after the user id has been located.
  - SIM S3-C13-R1 [book_reservation,cancel_reservation,get_reservation_details,get_user_details,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must]: The agent must first obtain the user id and the reservation id.
  - SIM S3-C08-R1 [update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must]: The agent must obtain the user id and the reservation id before proceeding with a cabin change.

## AIR-BOOK-01b
- gold quote: "then ask for the trip type, origin, destination."
- gold reading: When booking, the agent asks for trip type, origin and destination.
- GOLD AIR-R012: The agent must ask the user for the trip type, origin, and destination before booking a flight.
- aligned auto clauses: S2-C01
  - SRC S2-C01-R1 [book_reservation,cancel_reservation,get_reservation_details,get_user_details,respond_to_user,search_direct_flight,search_onestop_flight,send_certificate,transfer_to_human_agents,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must]: The agent must locate the user id by using the email address or by the user's name and zip code, before performing any other action.
  - SRC S2-C01-R2 [book_reservation,respond_to_user,search_direct_flight,search_onestop_flight; must]: The agent must ask for the trip type, origin, and destination only after the user id has been located.
  - SIM S3-C08-R6 [update_reservation_flights; must]: The agent must ensure cabin changes do not modify the origin, destination, or trip type of the reservation.
  - SIM S4-C07-R1 [cancel_reservation; must]: The agent must first obtain the user id, the reservation id, and the reason for cancellation (change of plan, airline cancelled flight, or other reasons) before calling the API.

## AIR-BOOK-02a
- gold quote: "Passengers: Each reservation can have at most five passengers."
- gold reading: A reservation has ≤ 5 passengers.
- GOLD AIR-R013: The agent must not book a reservation with more than five passengers.
- aligned auto clauses: S2-C02
  - SRC S2-C02-R1 [book_reservation,update_reservation_passengers; must_not]: The agent must not create or update a reservation such that the reservation has more than five passengers.
  - SIM S5-C01-R2 [book_reservation,get_reservation_details,get_user_details,update_reservation_flights,update_reservation_passengers; must]: The agent must determine the number of passengers in the reservation.
  - SIM S2-C04-R2 [book_reservation,update_reservation_passengers; must]: The agent must ensure that all passengers are in the same cabin.

## AIR-BOOK-02b
- gold quote: "The agent needs to collect the first name, last name, and date of birth for each passenger."
- gold reading: The agent collects first name, last name and DOB for every passenger.
- GOLD AIR-R014: The agent must collect the first name, last name, and date of birth of every passenger before booking.
- aligned auto clauses: S2-C03
  - SRC S2-C02-R1 [book_reservation,update_reservation_passengers; must_not]: The agent must not create or update a reservation such that the reservation has more than five passengers.
  - SRC S2-C03-R1 [book_reservation,update_reservation_passengers; must]: The agent must collect the first name for each passenger.
  - SRC S2-C03-R2 [book_reservation,update_reservation_passengers; must]: The agent must collect the last name for each passenger.
  - SRC S2-C03-R3 [book_reservation,update_reservation_passengers; must]: The agent must collect the date of birth for each passenger.

## AIR-BOOK-02c
- gold quote: "All passengers must fly the same flights in the same cabin."
- gold reading: All passengers on the same flights and cabin.
- GOLD AIR-R015: The agent must book all passengers of a reservation on the same flights in the same cabin.
- aligned auto clauses: S2-C04
  - SRC S2-C04-R1 [book_reservation,update_reservation_flights,update_reservation_passengers; must]: The agent must ensure that all passengers fly the same flights.
  - SRC S2-C04-R2 [book_reservation,update_reservation_passengers; must]: The agent must ensure that all passengers are in the same cabin.
  - SIM S3-C10-R1 [book_reservation,update_reservation_flights; must]: The agent must ensure the cabin class is the same across all the flights in the same reservation.
  - SIM S3-C08-R3 [book_reservation,update_reservation_flights; must_not]: The agent must not change cabin if cabin class is not the same across all the flights in the same reservation; changing cabin for just one flight segment is not possible.

## AIR-BOOK-03a
- gold quote: "Payment: each reservation can use at most one travel certificate"
- gold reading: ≤ 1 travel certificate per reservation.
- GOLD AIR-R016: The agent must not use more than one travel certificate as payment for a reservation.
- aligned auto clauses: S2-C05
  - SRC S2-C05-R1 [book_reservation,send_certificate; must]: The agent must ensure that each reservation uses at most one travel certificate.
  - SRC S2-C05-R2 [book_reservation; must]: The agent must ensure that each reservation uses at most one credit card.
  - SRC S2-C05-R3 [book_reservation; must]: The agent must ensure that each reservation uses at most three gift cards.
  - SRC S2-C07-R1 [book_reservation,send_certificate; must_not]: The agent must not use a travel certificate for the reservation unless it is already in the user's profile.
  - SRC S2-C07-R2 [book_reservation; must_not]: The agent must not use a credit card for the reservation unless it is already in the user's profile.
  - SRC S2-C07-R3 [book_reservation; must_not]: The agent must not use any gift card for the reservation unless that gift card is already in the user's profile.
  - SIM S5-C03-R2 [get_reservation_details,get_user_details,respond_to_user,send_certificate; may]: The agent must offer a certificate as a gesture after confirming the facts, with the amount being $100 times the number of passengers, if the user is silver/gold member or has travel insurance or flies business, and complains about cancelled flights in a reservation.

## AIR-BOOK-03b
- gold quote: "at most one credit card"
- gold reading: ≤ 1 credit card per reservation.
- GOLD AIR-R017: The agent must not use more than one credit card as payment for a reservation.
- aligned auto clauses: S2-C05
  - SRC S2-C05-R1 [book_reservation,send_certificate; must]: The agent must ensure that each reservation uses at most one travel certificate.
  - SRC S2-C05-R2 [book_reservation; must]: The agent must ensure that each reservation uses at most one credit card.
  - SRC S2-C05-R3 [book_reservation; must]: The agent must ensure that each reservation uses at most three gift cards.
  - SRC S2-C07-R1 [book_reservation,send_certificate; must_not]: The agent must not use a travel certificate for the reservation unless it is already in the user's profile.
  - SRC S2-C07-R2 [book_reservation; must_not]: The agent must not use a credit card for the reservation unless it is already in the user's profile.
  - SRC S2-C07-R3 [book_reservation; must_not]: The agent must not use any gift card for the reservation unless that gift card is already in the user's profile.
  - SIM S3-C16-R1 [update_reservation_flights; only_if]: The agent must obtain from the user one gift card or credit card for payment or refund method only if the flights are changed.

## AIR-BOOK-03c
- gold quote: "and at most three gift cards."
- gold reading: ≤ 3 gift cards per reservation.
- GOLD AIR-R018: The agent must not use more than three gift cards as payment for a reservation.
- aligned auto clauses: S2-C05
  - SRC S2-C05-R1 [book_reservation,send_certificate; must]: The agent must ensure that each reservation uses at most one travel certificate.
  - SRC S2-C05-R2 [book_reservation; must]: The agent must ensure that each reservation uses at most one credit card.
  - SRC S2-C05-R3 [book_reservation; must]: The agent must ensure that each reservation uses at most three gift cards.
  - SRC S2-C07-R1 [book_reservation,send_certificate; must_not]: The agent must not use a travel certificate for the reservation unless it is already in the user's profile.
  - SRC S2-C07-R2 [book_reservation; must_not]: The agent must not use a credit card for the reservation unless it is already in the user's profile.
  - SRC S2-C07-R3 [book_reservation; must_not]: The agent must not use any gift card for the reservation unless that gift card is already in the user's profile.

## AIR-BOOK-03e
- gold quote: "All payment methods must already be in user profile for safety reasons."
- gold reading: Only payment methods already in the user's profile may be used.
- GOLD AIR-R019: The agent must only use payment methods that already exist in the user's profile when booking.
- aligned auto clauses: S2-C07
  - SRC S2-C07-R1 [book_reservation,send_certificate; must_not]: The agent must not use a travel certificate for the reservation unless it is already in the user's profile.
  - SRC S2-C07-R2 [book_reservation; must_not]: The agent must not use a credit card for the reservation unless it is already in the user's profile.
  - SRC S2-C07-R3 [book_reservation; must_not]: The agent must not use any gift card for the reservation unless that gift card is already in the user's profile.
  - SIM S3-C12-R1 [respond_to_user,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must_not]: The agent must not permit the user to add insurance after initial booking.

## AIR-BOOK-04a
- gold quote: "If the booking user is a regular member, 0 free checked bag for each basic economy passenger, 1 free checked bag for each economy passenger, and 2 free checked bags for each business passenger."
- gold reading: Regular booking user: free bags per passenger = 0 (basic economy) / 1 (economy) / 2 (business).
- GOLD AIR-R020: When the booking user is a regular member, the agent must set nonfree_baggages to exactly the number of checked bags in excess of the pooled free allowance (number of passengers x per-passenger allowance), with a per-passenger allowance of 0 bags in basic economy, 1 in economy and 2 in business.
- aligned auto clauses: S2-C08
  - SRC S2-C08-R1 [book_reservation,get_user_details,respond_to_user,update_reservation_baggages; only_if]: The agent must grant 0 free checked bag for each basic economy passenger only if the booking user is a regular member.
  - SRC S2-C08-R2 [book_reservation,update_reservation_baggages; only_if]: The agent must grant 1 free checked bag for each economy passenger only if the booking user is a regular member.
  - SRC S2-C08-R3 [book_reservation,respond_to_user,update_reservation_baggages; only_if]: The agent must grant 2 free checked bags for each business passenger only if the booking user is a regular member.
  - SRC S2-C11-R1 [book_reservation,respond_to_user,update_reservation_baggages; must]: The agent must charge 50 dollars for each extra baggage.
  - SIM S2-C10-R1 [book_reservation,respond_to_user,update_reservation_baggages,update_reservation_passengers; must]: The agent must provide 2 free checked bag for each basic economy passenger if the booking user is a gold member.

## AIR-BOOK-04b
- gold quote: "If the booking user is a silver member, 1 free checked bag for each basic economy passenger, 2 free checked bag for each economy passenger, and 3 free checked bags for each business passenger."
- gold reading: Silver booking user: free bags per passenger = 1 / 2 / 3.
- GOLD AIR-R021: When the booking user is a silver member, the agent must set nonfree_baggages to exactly the number of checked bags in excess of the pooled free allowance (number of passengers x per-passenger allowance), with a per-passenger allowance of 1 bag in basic economy, 2 in economy and 3 in business.
- aligned auto clauses: S2-C09
  - SRC S2-C09-R1 [book_reservation,update_reservation_baggages,update_reservation_passengers; must]: The agent must grant 1 free checked bag for each basic economy passenger if the booking user is a silver member.
  - SRC S2-C09-R2 [book_reservation,update_reservation_baggages; must]: The agent must grant 2 free checked bags for each economy passenger if the booking user is a silver member.
  - SRC S2-C09-R3 [book_reservation,update_reservation_baggages; must]: The agent must grant 3 free checked bags for each business passenger if the booking user is a silver member.
  - SIM S2-C10-R1 [book_reservation,respond_to_user,update_reservation_baggages,update_reservation_passengers; must]: The agent must provide 2 free checked bag for each basic economy passenger if the booking user is a gold member.

## AIR-BOOK-04c
- gold quote: "If the booking user is a gold member, 2 free checked bag for each basic economy passenger, 3 free checked bag for each economy passenger, and 3 free checked bags for each business passenger."
- gold reading: Gold booking user: free bags per passenger = 2 / 3 / 3.
- GOLD AIR-R022: When the booking user is a gold member, the agent must set nonfree_baggages to exactly the number of checked bags in excess of the pooled free allowance (number of passengers x per-passenger allowance), with a per-passenger allowance of 2 bags in basic economy, 3 in economy and 3 in business.
- aligned auto clauses: S2-C10
  - SRC S2-C10-R1 [book_reservation,respond_to_user,update_reservation_baggages,update_reservation_passengers; must]: The agent must provide 2 free checked bag for each basic economy passenger if the booking user is a gold member.
  - SRC S2-C10-R2 [book_reservation,respond_to_user,update_reservation_baggages; must]: The agent must provide 3 free checked bag for each economy passenger if the booking user is a gold member.
  - SRC S2-C10-R3 [book_reservation,respond_to_user,update_reservation_baggages; must]: The agent must provide 3 free checked bags for each business passenger if the booking user is a gold member.

## AIR-BOOK-04d
- gold quote: "Each extra baggage is 50 dollars."
- gold reading: Each non-free bag costs $50.
- GOLD AIR-R023: The agent must charge 50 dollars for each extra (non-free) checked bag.
- aligned auto clauses: S2-C11
  - SRC S2-C11-R1 [book_reservation,respond_to_user,update_reservation_baggages; must]: The agent must charge 50 dollars for each extra baggage.
  - SIM S2-C08-R3 [book_reservation,respond_to_user,update_reservation_baggages; only_if]: The agent must grant 2 free checked bags for each business passenger only if the booking user is a regular member.
  - SIM S2-C08-R2 [book_reservation,update_reservation_baggages; only_if]: The agent must grant 1 free checked bag for each economy passenger only if the booking user is a regular member.

## AIR-BOOK-05a
- gold quote: "Travel insurance: the agent should ask if the user wants to buy the travel insurance"
- gold reading: When booking, the agent asks whether the user wants travel insurance.
- GOLD AIR-R024: The agent must ask the user whether they want to buy travel insurance before booking.
- aligned auto clauses: S2-C12
  - SRC S2-C12-R1 [book_reservation,respond_to_user; may]: The agent must ask if the user wants to buy the travel insurance.
  - SIM S2-C07-R1 [book_reservation,send_certificate; must_not]: The agent must not use a travel certificate for the reservation unless it is already in the user's profile.
  - SIM S3-C12-R1 [respond_to_user,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must_not]: The agent must not permit the user to add insurance after initial booking.

## AIR-BOOK-05b
- gold quote: "which is 30 dollars per passenger"
- gold reading: Insurance costs $30 per passenger.
- GOLD AIR-R025: The agent must charge travel insurance at 30 dollars per passenger when the user buys it.
- aligned auto clauses: S2-C13
  - SIM S2-C12-R1 [book_reservation,respond_to_user; may]: The agent must ask if the user wants to buy the travel insurance.
  - SIM S4-C03-R1 [cancel_reservation; must_not]: The agent must not cancel basic economy or economy flights unless travel insurance is bought and the condition is met.
  - SIM S4-C07-R3 [cancel_reservation; must_not]: The agent must not cancel basic economy or economy flights unless travel insurance is bought and the condition is met.

## AIR-MOD-01a
- gold quote: "The agent must first obtain the user id and the reservation id."
- gold reading: Before modifying, the agent obtains the user id.
- GOLD AIR-R026: The agent must obtain the user id before modifying a reservation (flights, cabin, baggage, or passengers).
- aligned auto clauses: S3-C01
  - SRC S3-C01-R1 [book_reservation,cancel_reservation,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must]: The agent must obtain the user id and the reservation id before taking any other modification-related actions.
  - SRC S3-C07-R1 [book_reservation,cancel_reservation,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must]: The agent must verify that all applicable rules apply before calling any booking-modifying API, specifically the rules listed in S3-C01 through S3-C17.
  - SRC S3-C08-R1 [update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must]: The agent must obtain the user id and the reservation id before proceeding with a cabin change.
  - SRC S3-C11-R3 [update_reservation_baggages; must]: The agent must first obtain the user id and the reservation id before updating baggage.
  - SRC S3-C13-R1 [book_reservation,cancel_reservation,get_reservation_details,get_user_details,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must]: The agent must first obtain the user id and the reservation id.

## AIR-MOD-01b
- gold quote: "The agent must first obtain the user id and the reservation id."
- gold reading: Before modifying, the agent obtains the reservation id.
- GOLD AIR-R027: The agent must obtain the reservation id before modifying a reservation (flights, cabin, baggage, or passengers).
- aligned auto clauses: S3-C01
  - SRC S3-C01-R1 [book_reservation,cancel_reservation,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must]: The agent must obtain the user id and the reservation id before taking any other modification-related actions.
  - SRC S3-C07-R1 [book_reservation,cancel_reservation,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must]: The agent must verify that all applicable rules apply before calling any booking-modifying API, specifically the rules listed in S3-C01 through S3-C17.
  - SRC S3-C08-R1 [update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must]: The agent must obtain the user id and the reservation id before proceeding with a cabin change.
  - SRC S3-C11-R3 [update_reservation_baggages; must]: The agent must first obtain the user id and the reservation id before updating baggage.
  - SRC S3-C13-R1 [book_reservation,cancel_reservation,get_reservation_details,get_user_details,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must]: The agent must first obtain the user id and the reservation id.
  - SIM S4-C01-R2 [cancel_reservation; must]: The agent must obtain the reservation id before making the cancellation.

## AIR-MOD-02a
- gold quote: "Change flights: Basic economy flights cannot be modified."
- gold reading: The flights of a basic economy reservation must not be changed.
- GOLD AIR-R028: The agent must not change the flights of a basic economy reservation; for a basic economy reservation it may only change the cabin while keeping exactly the same flights (flight numbers and dates).
- aligned auto clauses: S3-C02
  - SRC S3-C02-R1 [update_reservation_flights; must_not]: The agent must not modify flights for basic economy reservations.
  - SRC S3-C07-R1 [book_reservation,cancel_reservation,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must]: The agent must verify that all applicable rules apply before calling any booking-modifying API, specifically the rules listed in S3-C01 through S3-C17.
  - SIM S3-C08-R3 [book_reservation,update_reservation_flights; must_not]: The agent must not change cabin if cabin class is not the same across all the flights in the same reservation; changing cabin for just one flight segment is not possible.
  - SIM S3-C10-R1 [book_reservation,update_reservation_flights; must]: The agent must ensure the cabin class is the same across all the flights in the same reservation.

## AIR-MOD-02b
- gold quote: "Other reservations can be modified without changing the origin, destination, and trip type."
- gold reading: Flight changes keep origin, destination and trip type.
- GOLD AIR-R029: When changing flights, the agent must keep the reservation's origin and destination unchanged.
- GOLD AIR-R030: When changing flights, the agent must keep the reservation's trip type (one way or round trip) unchanged.
- aligned auto clauses: S3-C03
  - SRC S3-C03-R1 [update_reservation_flights; must_not]: The agent must not change the origin of the reservation being modified.
  - SRC S3-C03-R2 [update_reservation_flights; must_not]: The agent must not change the destination of the reservation being modified.
  - SRC S3-C03-R3 [update_reservation_flights; must_not]: The agent must not change the trip type of the reservation being modified.
  - SRC S3-C03-R4 [book_reservation,cancel_reservation,get_reservation_details,get_user_details,list_all_airports,search_direct_flight,search_onestop_flight,send_certificate,transfer_to_human_agents,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must]: The agent must make sure the rules apply before calling the API.
  - SRC S3-C07-R1 [book_reservation,cancel_reservation,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must]: The agent must verify that all applicable rules apply before calling any booking-modifying API, specifically the rules listed in S3-C01 through S3-C17.
  - SRC S3-C08-R6 [update_reservation_flights; must]: The agent must ensure cabin changes do not modify the origin, destination, or trip type of the reservation.

## AIR-MOD-02d
- gold quote: "The API does not check these for the agent, so the agent must make sure the rules apply before calling the API!"
- gold reading: The agent itself checks the change-flight rules before calling update_reservation_flights.
- GOLD AIR-R028: The agent must not change the flights of a basic economy reservation; for a basic economy reservation it may only change the cabin while keeping exactly the same flights (flight numbers and dates).
- GOLD AIR-R029: When changing flights, the agent must keep the reservation's origin and destination unchanged.
- GOLD AIR-R030: When changing flights, the agent must keep the reservation's trip type (one way or round trip) unchanged.
- aligned auto clauses: S3-C06, S3-C07
  - SRC S3-C03-R4 [book_reservation,cancel_reservation,get_reservation_details,get_user_details,list_all_airports,search_direct_flight,search_onestop_flight,send_certificate,transfer_to_human_agents,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must]: The agent must make sure the rules apply before calling the API.
  - SRC S3-C07-R1 [book_reservation,cancel_reservation,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must]: The agent must verify that all applicable rules apply before calling any booking-modifying API, specifically the rules listed in S3-C01 through S3-C17.
  - SRC S3-C07-R2 [book_reservation,cancel_reservation,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must]: The agent must list the details of the actions to be performed before calling any booking-modifying API.
  - SRC S3-C07-R3 [book_reservation,cancel_reservation,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must]: The agent must obtain explicit confirmation from the user before calling any booking-modifying API.
  - SRC S3-C08-R2 [book_reservation,cancel_reservation,get_reservation_details,get_user_details,list_all_airports,search_direct_flight,search_onestop_flight,send_certificate,transfer_to_human_agents,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must]: The agent must make sure the rules apply before calling the API.
  - SRC S3-C11-R4 [book_reservation,cancel_reservation,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must]: The agent must not call any modification API to the reservation unless the rules apply before the API call.
  - SRC S3-C13-R2 [book_reservation,cancel_reservation,get_reservation_details,get_user_details,list_all_airports,search_direct_flight,search_onestop_flight,send_certificate,transfer_to_human_agents,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must]: The agent must make sure the rules apply before calling the API.
  - SRC S3-C15-R1 [cancel_reservation; must_not]: The agent must not attempt to assist with the request described by S3-C15, as this is something that even a human agent cannot assist with.
  - SIM S3-C02-R1 [update_reservation_flights; must_not]: The agent must not modify flights for basic economy reservations.
  - SIM S3-C08-R6 [update_reservation_flights; must]: The agent must ensure cabin changes do not modify the origin, destination, or trip type of the reservation.
  - SIM S3-C08-R3 [book_reservation,update_reservation_flights; must_not]: The agent must not change cabin if cabin class is not the same across all the flights in the same reservation; changing cabin for just one flight segment is not possible.

## AIR-MOD-03a
- gold quote: "Change cabin: all reservations, including basic economy, can change cabin without changing the flights."
- gold reading: Cabin change (keeping flights) is permitted for every reservation incl. basic economy.
- GOLD AIR-R028: The agent must not change the flights of a basic economy reservation; for a basic economy reservation it may only change the cabin while keeping exactly the same flights (flight numbers and dates).
- aligned auto clauses: S3-C08
  - SRC S3-C07-R1 [book_reservation,cancel_reservation,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must]: The agent must verify that all applicable rules apply before calling any booking-modifying API, specifically the rules listed in S3-C01 through S3-C17.
  - SRC S3-C08-R1 [update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must]: The agent must obtain the user id and the reservation id before proceeding with a cabin change.
  - SRC S3-C08-R2 [book_reservation,cancel_reservation,get_reservation_details,get_user_details,list_all_airports,search_direct_flight,search_onestop_flight,send_certificate,transfer_to_human_agents,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must]: The agent must make sure the rules apply before calling the API.
  - SRC S3-C08-R3 [book_reservation,update_reservation_flights; must_not]: The agent must not change cabin if cabin class is not the same across all the flights in the same reservation; changing cabin for just one flight segment is not possible.
  - SRC S3-C08-R4 [book_reservation,update_reservation_flights; must]: The agent must ensure the user pays for the difference between their current cabin and the new cabin class.
  - SRC S3-C08-R5 [update_reservation_flights,update_reservation_passengers; must]: The agent must ask for the payment or refund method before processing cabin changes.
  - SRC S3-C08-R6 [update_reservation_flights; must]: The agent must ensure cabin changes do not modify the origin, destination, or trip type of the reservation.
  - SIM S3-C02-R1 [update_reservation_flights; must_not]: The agent must not modify flights for basic economy reservations.
  - SIM S3-C10-R1 [book_reservation,update_reservation_flights; must]: The agent must ensure the cabin class is the same across all the flights in the same reservation.

## AIR-MOD-03b
- gold quote: "Cabin changes require the user to pay for the difference between their current cabin and the new cabin class."
- gold reading: A cabin change is charged the fare difference.
- GOLD AIR-R031: When changing the cabin of a reservation, the agent must charge the user the price difference between the current and the new cabin class and must not waive it.
- aligned auto clauses: S3-C09
  - SRC S3-C07-R1 [book_reservation,cancel_reservation,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must]: The agent must verify that all applicable rules apply before calling any booking-modifying API, specifically the rules listed in S3-C01 through S3-C17.
  - SRC S3-C08-R4 [book_reservation,update_reservation_flights; must]: The agent must ensure the user pays for the difference between their current cabin and the new cabin class.
  - SRC S3-C09-R2 [update_reservation_flights; must_not]: The agent must not change the cabin without receiving the payment difference.
  - SIM S3-C08-R3 [book_reservation,update_reservation_flights; must_not]: The agent must not change cabin if cabin class is not the same across all the flights in the same reservation; changing cabin for just one flight segment is not possible.
  - SIM S0-C07-R6 [book_reservation,update_reservation_flights; must_not]: The agent must not upgrade cabin class in a reservation in response to a user request that is against this policy.

## AIR-MOD-03c
- gold quote: "Cabin class must be the same across all the flights in the same reservation"
- gold reading: One cabin for all flights of a reservation.
- GOLD AIR-R032: The agent must apply a cabin change to all flights in the reservation and must not change the cabin of only some flight segments.
- aligned auto clauses: S3-C10
  - SRC S3-C07-R1 [book_reservation,cancel_reservation,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must]: The agent must verify that all applicable rules apply before calling any booking-modifying API, specifically the rules listed in S3-C01 through S3-C17.
  - SRC S3-C08-R3 [book_reservation,update_reservation_flights; must_not]: The agent must not change cabin if cabin class is not the same across all the flights in the same reservation; changing cabin for just one flight segment is not possible.
  - SRC S3-C10-R1 [book_reservation,update_reservation_flights; must]: The agent must ensure the cabin class is the same across all the flights in the same reservation.
  - SRC S3-C10-R2 [book_reservation,update_reservation_flights; must_not]: The agent must not change cabin for just one flight segment.

## AIR-MOD-03d
- gold quote: "changing cabin for just one flight segment is not possible."
- gold reading: No per-segment cabin change.
- GOLD AIR-R032: The agent must apply a cabin change to all flights in the reservation and must not change the cabin of only some flight segments.
- aligned auto clauses: S3-C10
  - SRC S3-C07-R1 [book_reservation,cancel_reservation,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must]: The agent must verify that all applicable rules apply before calling any booking-modifying API, specifically the rules listed in S3-C01 through S3-C17.
  - SRC S3-C08-R3 [book_reservation,update_reservation_flights; must_not]: The agent must not change cabin if cabin class is not the same across all the flights in the same reservation; changing cabin for just one flight segment is not possible.
  - SRC S3-C10-R1 [book_reservation,update_reservation_flights; must]: The agent must ensure the cabin class is the same across all the flights in the same reservation.
  - SRC S3-C10-R2 [book_reservation,update_reservation_flights; must_not]: The agent must not change cabin for just one flight segment.

## AIR-MOD-04a
- gold quote: "Change baggage and insurance: The user can add but not remove checked bags."
- gold reading: Checked bags can be added, never removed.
- GOLD AIR-R033: The agent must not remove checked bags from a reservation: the new total number of checked bags must not be lower than the current total.
- aligned auto clauses: S3-C11
  - SRC S3-C07-R1 [book_reservation,cancel_reservation,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must]: The agent must verify that all applicable rules apply before calling any booking-modifying API, specifically the rules listed in S3-C01 through S3-C17.
  - SRC S3-C11-R1 [update_reservation_baggages; must_not]: The agent must not remove checked bags from a reservation.
  - SRC S3-C11-R2 [update_reservation_baggages; must]: The agent must update the reservation baggage to add checked bags when the user requests to add checked bags.
  - SRC S3-C11-R3 [update_reservation_baggages; must]: The agent must first obtain the user id and the reservation id before updating baggage.
  - SRC S3-C11-R4 [book_reservation,cancel_reservation,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must]: The agent must not call any modification API to the reservation unless the rules apply before the API call.
  - SIM S2-C08-R3 [book_reservation,respond_to_user,update_reservation_baggages; only_if]: The agent must grant 2 free checked bags for each business passenger only if the booking user is a regular member.

## AIR-MOD-04b
- gold quote: "The user cannot add insurance after initial booking."
- gold reading: No insurance after booking.
- GOLD AIR-R034: The agent must not add travel insurance to a reservation after it has been booked.
- aligned auto clauses: S3-C12
  - SRC S3-C07-R1 [book_reservation,cancel_reservation,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must]: The agent must verify that all applicable rules apply before calling any booking-modifying API, specifically the rules listed in S3-C01 through S3-C17.
  - SRC S3-C12-R1 [respond_to_user,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must_not]: The agent must not permit the user to add insurance after initial booking.
  - SIM S2-C07-R1 [book_reservation,send_certificate; must_not]: The agent must not use a travel certificate for the reservation unless it is already in the user's profile.
  - SIM S2-C02-R1 [book_reservation,update_reservation_passengers; must_not]: The agent must not create or update a reservation such that the reservation has more than five passengers.

## AIR-MOD-05a
- gold quote: "Change passengers: The user can modify passengers but cannot modify the number of passengers."
- gold reading: Passenger details may change; passenger count may not.
- GOLD AIR-R035: The agent must not change the number of passengers in a reservation: an updated passenger list must have the same number of passengers as the current list.
- aligned auto clauses: S3-C13, S3-C14
  - SRC S0-C02-R7 [book_reservation,cancel_reservation,get_reservation_details,get_user_details,respond_to_user,send_certificate,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must]: The agent must authenticate the user by locating the user id via email or via name + zip code before any other action or disclosure of information.
  - SRC S3-C07-R1 [book_reservation,cancel_reservation,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must]: The agent must verify that all applicable rules apply before calling any booking-modifying API, specifically the rules listed in S3-C01 through S3-C17.
  - SRC S3-C13-R1 [book_reservation,cancel_reservation,get_reservation_details,get_user_details,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must]: The agent must first obtain the user id and the reservation id.
  - SRC S3-C13-R2 [book_reservation,cancel_reservation,get_reservation_details,get_user_details,list_all_airports,search_direct_flight,search_onestop_flight,send_certificate,transfer_to_human_agents,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must]: The agent must make sure the rules apply before calling the API.
  - SRC S3-C14-R1 [book_reservation,update_reservation_passengers; must_not]: The agent must not modify the number of passengers.
  - SIM S2-C02-R1 [book_reservation,update_reservation_passengers; must_not]: The agent must not create or update a reservation such that the reservation has more than five passengers.
  - SIM S5-C01-R2 [book_reservation,get_reservation_details,get_user_details,update_reservation_flights,update_reservation_passengers; must]: The agent must determine the number of passengers in the reservation.

## AIR-MOD-05b
- gold quote: "This is something that even a human agent cannot assist with."
- gold reading: A passenger-count change cannot be escalated: transferring to a human for it is not appropriate.
- GOLD AIR-R036: The agent must not transfer the user to a human agent for a request to change the number of passengers.
- aligned auto clauses: S3-C15
  - SRC S3-C07-R1 [book_reservation,cancel_reservation,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must]: The agent must verify that all applicable rules apply before calling any booking-modifying API, specifically the rules listed in S3-C01 through S3-C17.
  - SRC S3-C15-R1 [cancel_reservation; must_not]: The agent must not attempt to assist with the request described by S3-C15, as this is something that even a human agent cannot assist with.
  - SIM S0-C02-R12 [transfer_to_human_agents; if_and_only_if]: The agent must transfer the user to a human agent if and only if the request cannot be handled within the scope of your actions.
  - SIM S3-C14-R1 [book_reservation,update_reservation_passengers; must_not]: The agent must not modify the number of passengers.
  - SIM S4-C07-R6 [book_reservation,cancel_reservation,get_reservation_details,get_user_details,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must]: The agent must transfer to a human agent if any of the segments are already used.

## AIR-MOD-06a
- gold quote: "Payment: If the flights are changed, the user needs to provide one gift card or credit card for payment or refund method."
- gold reading: Flight change uses exactly one gift card or credit card as payment/refund method.
- GOLD AIR-R037: When changing flights, the agent must use exactly one payment method, which must be a gift card or a credit card from the user's profile (not a travel certificate).
- aligned auto clauses: S3-C16
  - SRC S3-C07-R1 [book_reservation,cancel_reservation,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must]: The agent must verify that all applicable rules apply before calling any booking-modifying API, specifically the rules listed in S3-C01 through S3-C17.
  - SRC S3-C16-R1 [update_reservation_flights; only_if]: The agent must obtain from the user one gift card or credit card for payment or refund method only if the flights are changed.
  - SIM S2-C07-R3 [book_reservation; must_not]: The agent must not use any gift card for the reservation unless that gift card is already in the user's profile.
  - SIM S2-C07-R2 [book_reservation; must_not]: The agent must not use a credit card for the reservation unless it is already in the user's profile.

## AIR-MOD-06b
- gold quote: "The agent should ask for the payment or refund method instead."
- gold reading: For a flight change the agent asks the user which payment/refund method to use.
- GOLD AIR-R038: When changing flights, the agent must ask the user which payment or refund method to use rather than choosing a method itself.
- aligned auto clauses: S3-C17
  - SRC S3-C07-R1 [book_reservation,cancel_reservation,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must]: The agent must verify that all applicable rules apply before calling any booking-modifying API, specifically the rules listed in S3-C01 through S3-C17.
  - SRC S3-C08-R5 [update_reservation_flights,update_reservation_passengers; must]: The agent must ask for the payment or refund method before processing cabin changes.
  - SRC S3-C17-R1 [book_reservation,cancel_reservation; must]: The agent must ask the user for the payment or refund method instead.
  - SIM S4-C04-R5 [respond_to_user; must]: The agent must inform the user that the refund will go to original payment methods in 5 to 7 business days.

## AIR-CAN-01a
- gold quote: "The agent must first obtain the user id, the reservation id, and the reason for cancellation (change of plan, airline cancelled flight, or other reasons)"
- gold reading: Before cancelling, the agent obtains the user id.
- GOLD AIR-R039: The agent must obtain the user id before cancelling a reservation.
- aligned auto clauses: S4-C01
  - SRC S0-C02-R7 [book_reservation,cancel_reservation,get_reservation_details,get_user_details,respond_to_user,send_certificate,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must]: The agent must authenticate the user by locating the user id via email or via name + zip code before any other action or disclosure of information.
  - SRC S4-C01-R1 [cancel_reservation; must]: The agent must obtain the user id before making the cancellation.
  - SRC S4-C01-R2 [cancel_reservation; must]: The agent must obtain the reservation id before making the cancellation.
  - SRC S4-C01-R3 [cancel_reservation; must]: The agent must obtain the reason for cancellation (change of plan, airline cancelled flight, or other reasons) before making the cancellation.
  - SRC S4-C02-R2 [cancel_reservation; must]: The agent must list the action details and obtain explicit confirmation from the user before cancelling, including the reservation id and the reason for cancellation (change of plan, airline cancelled flight, or other reasons).
  - SRC S4-C04-R2 [cancel_reservation; must]: The agent must obtain the user id, the reservation id, and the reason for cancellation (change of plan, airline cancelled flight, or other reasons) before performing cancellation.
  - SRC S4-C04-R3 [cancel_reservation,respond_to_user; must]: The agent must list the cancellation details to the user and obtain explicit confirmation before calling the API to cancel.
  - SRC S4-C05-R1 [cancel_reservation; must]: The agent must apply the cancellation rules strictly regardless of the user’s membership status.
  - SRC S4-C07-R1 [cancel_reservation; must]: The agent must first obtain the user id, the reservation id, and the reason for cancellation (change of plan, airline cancelled flight, or other reasons) before calling the API.
  - SRC S4-C08-R2 [cancel_reservation; must]: The agent must first obtain the user id, the reservation id, and the reason for cancellation (change of plan, airline cancelled flight, or other reasons).
  - SIM S3-C08-R1 [update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must]: The agent must obtain the user id and the reservation id before proceeding with a cabin change.

## AIR-CAN-01b
- gold quote: "The agent must first obtain the user id, the reservation id, and the reason for cancellation (change of plan, airline cancelled flight, or other reasons)"
- gold reading: Before cancelling, the agent obtains the reservation id.
- GOLD AIR-R040: The agent must obtain the reservation id before cancelling a reservation.
- aligned auto clauses: S4-C01
  - SRC S0-C02-R7 [book_reservation,cancel_reservation,get_reservation_details,get_user_details,respond_to_user,send_certificate,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must]: The agent must authenticate the user by locating the user id via email or via name + zip code before any other action or disclosure of information.
  - SRC S4-C01-R1 [cancel_reservation; must]: The agent must obtain the user id before making the cancellation.
  - SRC S4-C01-R2 [cancel_reservation; must]: The agent must obtain the reservation id before making the cancellation.
  - SRC S4-C01-R3 [cancel_reservation; must]: The agent must obtain the reason for cancellation (change of plan, airline cancelled flight, or other reasons) before making the cancellation.
  - SRC S4-C02-R2 [cancel_reservation; must]: The agent must list the action details and obtain explicit confirmation from the user before cancelling, including the reservation id and the reason for cancellation (change of plan, airline cancelled flight, or other reasons).
  - SRC S4-C04-R2 [cancel_reservation; must]: The agent must obtain the user id, the reservation id, and the reason for cancellation (change of plan, airline cancelled flight, or other reasons) before performing cancellation.
  - SRC S4-C04-R3 [cancel_reservation,respond_to_user; must]: The agent must list the cancellation details to the user and obtain explicit confirmation before calling the API to cancel.
  - SRC S4-C05-R1 [cancel_reservation; must]: The agent must apply the cancellation rules strictly regardless of the user’s membership status.
  - SRC S4-C07-R1 [cancel_reservation; must]: The agent must first obtain the user id, the reservation id, and the reason for cancellation (change of plan, airline cancelled flight, or other reasons) before calling the API.
  - SRC S4-C08-R2 [cancel_reservation; must]: The agent must first obtain the user id, the reservation id, and the reason for cancellation (change of plan, airline cancelled flight, or other reasons).
  - SIM S3-C08-R1 [update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must]: The agent must obtain the user id and the reservation id before proceeding with a cabin change.

## AIR-CAN-01c
- gold quote: "The agent must first obtain the user id, the reservation id, and the reason for cancellation (change of plan, airline cancelled flight, or other reasons)"
- gold reading: Before cancelling, the agent obtains the cancellation reason (change of plan / airline cancelled flight / other reasons).
- GOLD AIR-R041: The agent must obtain the user's reason for cancellation (change of plan, airline cancelled flight, or other reasons) before cancelling a reservation.
- aligned auto clauses: S4-C01
  - SRC S0-C02-R7 [book_reservation,cancel_reservation,get_reservation_details,get_user_details,respond_to_user,send_certificate,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must]: The agent must authenticate the user by locating the user id via email or via name + zip code before any other action or disclosure of information.
  - SRC S4-C01-R1 [cancel_reservation; must]: The agent must obtain the user id before making the cancellation.
  - SRC S4-C01-R2 [cancel_reservation; must]: The agent must obtain the reservation id before making the cancellation.
  - SRC S4-C01-R3 [cancel_reservation; must]: The agent must obtain the reason for cancellation (change of plan, airline cancelled flight, or other reasons) before making the cancellation.
  - SRC S4-C02-R2 [cancel_reservation; must]: The agent must list the action details and obtain explicit confirmation from the user before cancelling, including the reservation id and the reason for cancellation (change of plan, airline cancelled flight, or other reasons).
  - SRC S4-C04-R2 [cancel_reservation; must]: The agent must obtain the user id, the reservation id, and the reason for cancellation (change of plan, airline cancelled flight, or other reasons) before performing cancellation.
  - SRC S4-C04-R3 [cancel_reservation,respond_to_user; must]: The agent must list the cancellation details to the user and obtain explicit confirmation before calling the API to cancel.
  - SRC S4-C05-R1 [cancel_reservation; must]: The agent must apply the cancellation rules strictly regardless of the user’s membership status.
  - SRC S4-C07-R1 [cancel_reservation; must]: The agent must first obtain the user id, the reservation id, and the reason for cancellation (change of plan, airline cancelled flight, or other reasons) before calling the API.
  - SRC S4-C08-R2 [cancel_reservation; must]: The agent must first obtain the user id, the reservation id, and the reason for cancellation (change of plan, airline cancelled flight, or other reasons).

## AIR-CAN-02a
- gold quote: "All reservations can be cancelled within 24 hours of booking, or if the airline cancelled the flight."
- gold reading: Exception: any reservation may be cancelled within 24h of booking.
- GOLD AIR-R042: The agent must not cancel a basic economy or economy reservation unless it was created within the 24 hours before the current time, the airline cancelled a flight in the reservation, or travel insurance was bought and the cancellation reason is covered by it (health or weather).
- aligned auto clauses: S4-C02
  - SRC S0-C02-R7 [book_reservation,cancel_reservation,get_reservation_details,get_user_details,respond_to_user,send_certificate,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must]: The agent must authenticate the user by locating the user id via email or via name + zip code before any other action or disclosure of information.
  - SRC S4-C02-R1 [cancel_reservation; must_not]: The agent must not cancel a reservation unless the cancellation is within 24 hours of booking, or the airline cancelled the flight.
  - SRC S4-C02-R2 [cancel_reservation; must]: The agent must list the action details and obtain explicit confirmation from the user before cancelling, including the reservation id and the reason for cancellation (change of plan, airline cancelled flight, or other reasons).
  - SRC S4-C03-R2 [cancel_reservation; must]: The agent must ensure that cancellation-related rules are applied before calling the API to cancel the reservation.
  - SRC S4-C05-R1 [cancel_reservation; must]: The agent must apply the cancellation rules strictly regardless of the user’s membership status.
  - SRC S4-C07-R2 [cancel_reservation; must_not]: The agent must not cancel a reservation unless it is within 24 hours of booking, or if the airline cancelled the flight.
  - SRC S4-C08-R3 [cancel_reservation; must_not]: The agent must not cancel unless within 24 hours of booking, or the airline cancelled the flight, or the flight is a business flight.

## AIR-CAN-02b
- gold quote: "All reservations can be cancelled within 24 hours of booking, or if the airline cancelled the flight."
- gold reading: Exception: any reservation may be cancelled if the airline cancelled a flight.
- GOLD AIR-R042: The agent must not cancel a basic economy or economy reservation unless it was created within the 24 hours before the current time, the airline cancelled a flight in the reservation, or travel insurance was bought and the cancellation reason is covered by it (health or weather).
- aligned auto clauses: S4-C02
  - SRC S0-C02-R7 [book_reservation,cancel_reservation,get_reservation_details,get_user_details,respond_to_user,send_certificate,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must]: The agent must authenticate the user by locating the user id via email or via name + zip code before any other action or disclosure of information.
  - SRC S4-C02-R1 [cancel_reservation; must_not]: The agent must not cancel a reservation unless the cancellation is within 24 hours of booking, or the airline cancelled the flight.
  - SRC S4-C02-R2 [cancel_reservation; must]: The agent must list the action details and obtain explicit confirmation from the user before cancelling, including the reservation id and the reason for cancellation (change of plan, airline cancelled flight, or other reasons).
  - SRC S4-C03-R2 [cancel_reservation; must]: The agent must ensure that cancellation-related rules are applied before calling the API to cancel the reservation.
  - SRC S4-C05-R1 [cancel_reservation; must]: The agent must apply the cancellation rules strictly regardless of the user’s membership status.
  - SRC S4-C07-R2 [cancel_reservation; must_not]: The agent must not cancel a reservation unless it is within 24 hours of booking, or if the airline cancelled the flight.
  - SRC S4-C08-R3 [cancel_reservation; must_not]: The agent must not cancel unless within 24 hours of booking, or the airline cancelled the flight, or the flight is a business flight.

## AIR-CAN-02c
- gold quote: "Otherwise, basic economy or economy flights can be cancelled only if travel insurance is bought and the condition is met"
- gold reading: Otherwise (basic) economy may be cancelled only if insured AND the insured condition (health/weather) holds.
- GOLD AIR-R042: The agent must not cancel a basic economy or economy reservation unless it was created within the 24 hours before the current time, the airline cancelled a flight in the reservation, or travel insurance was bought and the cancellation reason is covered by it (health or weather).
- aligned auto clauses: S4-C03
  - SRC S4-C03-R1 [cancel_reservation; must_not]: The agent must not cancel basic economy or economy flights unless travel insurance is bought and the condition is met.
  - SRC S4-C03-R2 [cancel_reservation; must]: The agent must ensure that cancellation-related rules are applied before calling the API to cancel the reservation.
  - SRC S4-C05-R1 [cancel_reservation; must]: The agent must apply the cancellation rules strictly regardless of the user’s membership status.
  - SRC S4-C07-R3 [cancel_reservation; must_not]: The agent must not cancel basic economy or economy flights unless travel insurance is bought and the condition is met.
  - SIM S4-C02-R1 [cancel_reservation; must_not]: The agent must not cancel a reservation unless the cancellation is within 24 hours of booking, or the airline cancelled the flight.
  - SIM S4-C07-R2 [cancel_reservation; must_not]: The agent must not cancel a reservation unless it is within 24 hours of booking, or if the airline cancelled the flight.
  - SIM S4-C08-R3 [cancel_reservation; must_not]: The agent must not cancel unless within 24 hours of booking, or the airline cancelled the flight, or the flight is a business flight.

## AIR-CAN-02d
- gold quote: "and business flights can always be cancelled."
- gold reading: Business reservations are not restricted by the eligibility rule.
- GOLD AIR-R042: The agent must not cancel a basic economy or economy reservation unless it was created within the 24 hours before the current time, the airline cancelled a flight in the reservation, or travel insurance was bought and the cancellation reason is covered by it (health or weather).
- aligned auto clauses: S4-C04
  - SRC S4-C04-R1 [cancel_reservation; must]: The agent must determine whether the reservation contains business-class flight segments and that none of the segments have been used before proceeding to cancellation.
  - SRC S4-C04-R2 [cancel_reservation; must]: The agent must obtain the user id, the reservation id, and the reason for cancellation (change of plan, airline cancelled flight, or other reasons) before performing cancellation.
  - SRC S4-C04-R3 [cancel_reservation,respond_to_user; must]: The agent must list the cancellation details to the user and obtain explicit confirmation before calling the API to cancel.
  - SRC S4-C04-R4 [cancel_reservation; must]: The agent must cancel the whole reservation that contains business-class flight segments, and none of the segments are used.
  - SRC S4-C04-R5 [respond_to_user; must]: The agent must inform the user that the refund will go to original payment methods in 5 to 7 business days.
  - SRC S4-C04-R6 [cancel_reservation,get_reservation_details; must]: The agent must perform the required checks before invoking the cancellation API, since the API does not check these for the agent.
  - SRC S4-C05-R1 [cancel_reservation; must]: The agent must apply the cancellation rules strictly regardless of the user’s membership status.
  - SRC S4-C08-R3 [cancel_reservation; must_not]: The agent must not cancel unless within 24 hours of booking, or the airline cancelled the flight, or the flight is a business flight.
  - SIM S4-C02-R1 [cancel_reservation; must_not]: The agent must not cancel a reservation unless the cancellation is within 24 hours of booking, or the airline cancelled the flight.
  - SIM S4-C07-R2 [cancel_reservation; must_not]: The agent must not cancel a reservation unless it is within 24 hours of booking, or if the airline cancelled the flight.

## AIR-CAN-02e
- gold quote: "The rules are strict regardless of the membership status."
- gold reading: No membership-based exceptions.
- GOLD AIR-R042: The agent must not cancel a basic economy or economy reservation unless it was created within the 24 hours before the current time, the airline cancelled a flight in the reservation, or travel insurance was bought and the cancellation reason is covered by it (health or weather).
- aligned auto clauses: S4-C05
  - SRC S4-C05-R1 [cancel_reservation; must]: The agent must apply the cancellation rules strictly regardless of the user’s membership status.
  - SRC S4-C07-R4 [cancel_reservation; must]: The agent must apply the cancellation rules regardless of the membership status.
  - SIM S4-C02-R1 [cancel_reservation; must_not]: The agent must not cancel a reservation unless the cancellation is within 24 hours of booking, or the airline cancelled the flight.
  - SIM S4-C07-R2 [cancel_reservation; must_not]: The agent must not cancel a reservation unless it is within 24 hours of booking, or if the airline cancelled the flight.
  - SIM S4-C08-R3 [cancel_reservation; must_not]: The agent must not cancel unless within 24 hours of booking, or the airline cancelled the flight, or the flight is a business flight.

## AIR-CAN-02f
- gold quote: "The API does not check these for the agent, so the agent must make sure the rules apply before calling the API!"
- gold reading: The agent itself checks cancellation eligibility before calling cancel_reservation.
- GOLD AIR-R042: The agent must not cancel a basic economy or economy reservation unless it was created within the 24 hours before the current time, the airline cancelled a flight in the reservation, or travel insurance was bought and the cancellation reason is covered by it (health or weather).
- aligned auto clauses: S4-C06, S4-C07
  - SRC S4-C01-R1 [cancel_reservation; must]: The agent must obtain the user id before making the cancellation.
  - SRC S4-C01-R2 [cancel_reservation; must]: The agent must obtain the reservation id before making the cancellation.
  - SRC S4-C01-R3 [cancel_reservation; must]: The agent must obtain the reason for cancellation (change of plan, airline cancelled flight, or other reasons) before making the cancellation.
  - SRC S4-C03-R2 [cancel_reservation; must]: The agent must ensure that cancellation-related rules are applied before calling the API to cancel the reservation.
  - SRC S4-C04-R1 [cancel_reservation; must]: The agent must determine whether the reservation contains business-class flight segments and that none of the segments have been used before proceeding to cancellation.
  - SRC S4-C04-R2 [cancel_reservation; must]: The agent must obtain the user id, the reservation id, and the reason for cancellation (change of plan, airline cancelled flight, or other reasons) before performing cancellation.
  - SRC S4-C04-R3 [cancel_reservation,respond_to_user; must]: The agent must list the cancellation details to the user and obtain explicit confirmation before calling the API to cancel.
  - SRC S4-C04-R4 [cancel_reservation; must]: The agent must cancel the whole reservation that contains business-class flight segments, and none of the segments are used.
  - SRC S4-C04-R6 [cancel_reservation,get_reservation_details; must]: The agent must perform the required checks before invoking the cancellation API, since the API does not check these for the agent.
  - SRC S4-C05-R1 [cancel_reservation; must]: The agent must apply the cancellation rules strictly regardless of the user’s membership status.
  - SRC S4-C07-R1 [cancel_reservation; must]: The agent must first obtain the user id, the reservation id, and the reason for cancellation (change of plan, airline cancelled flight, or other reasons) before calling the API.
  - SRC S4-C07-R2 [cancel_reservation; must_not]: The agent must not cancel a reservation unless it is within 24 hours of booking, or if the airline cancelled the flight.
  - SRC S4-C07-R3 [cancel_reservation; must_not]: The agent must not cancel basic economy or economy flights unless travel insurance is bought and the condition is met.
  - SRC S4-C07-R4 [cancel_reservation; must]: The agent must apply the cancellation rules regardless of the membership status.
  - SRC S4-C07-R5 [cancel_reservation; must_not]: The agent must not cancel if any of the segments are already used.
  - SRC S4-C07-R6 [book_reservation,cancel_reservation,get_reservation_details,get_user_details,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must]: The agent must transfer to a human agent if any of the segments are already used.
  - SRC S4-C07-R7 [cancel_reservation; must]: The agent must cancel the whole trip only if none of the segments have been flown.
  - SRC S4-C07-R8 [cancel_reservation; must]: The agent must perform the necessary checks for cancellation before calling the API because the API does not check these for the agent.
  - SRC S4-C08-R3 [cancel_reservation; must_not]: The agent must not cancel unless within 24 hours of booking, or the airline cancelled the flight, or the flight is a business flight.
  - SRC S4-C08-R4 [cancel_reservation; must_not]: The agent must not cancel if any of the segments are already used; transfer is needed.
  - SRC S4-C08-R5 [book_reservation,cancel_reservation,get_reservation_details,get_user_details,list_all_airports,search_direct_flight,search_onestop_flight,send_certificate,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must]: The agent must make sure the rules apply before calling the API!
  - SIM S4-C02-R1 [cancel_reservation; must_not]: The agent must not cancel a reservation unless the cancellation is within 24 hours of booking, or the airline cancelled the flight.

## AIR-CAN-03a
- gold quote: "The agent can only cancel the whole trip that is not flown."
- gold reading: Only entirely unflown reservations may be cancelled.
- GOLD AIR-R043: The agent must not cancel a reservation in which any flight segment has already been flown.
- aligned auto clauses: S4-C08
  - SRC S4-C04-R1 [cancel_reservation; must]: The agent must determine whether the reservation contains business-class flight segments and that none of the segments have been used before proceeding to cancellation.
  - SRC S4-C04-R4 [cancel_reservation; must]: The agent must cancel the whole reservation that contains business-class flight segments, and none of the segments are used.
  - SRC S4-C05-R1 [cancel_reservation; must]: The agent must apply the cancellation rules strictly regardless of the user’s membership status.
  - SRC S4-C07-R7 [cancel_reservation; must]: The agent must cancel the whole trip only if none of the segments have been flown.
  - SRC S4-C08-R1 [book_reservation,cancel_reservation,get_reservation_details,get_user_details,respond_to_user,send_certificate,transfer_to_human_agents,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must]: The agent must authenticate the user by locating the user id via email or via name + zip code, before any other action or disclosure of information.
  - SRC S4-C08-R2 [cancel_reservation; must]: The agent must first obtain the user id, the reservation id, and the reason for cancellation (change of plan, airline cancelled flight, or other reasons).
  - SRC S4-C08-R3 [cancel_reservation; must_not]: The agent must not cancel unless within 24 hours of booking, or the airline cancelled the flight, or the flight is a business flight.
  - SRC S4-C08-R4 [cancel_reservation; must_not]: The agent must not cancel if any of the segments are already used; transfer is needed.
  - SRC S4-C08-R5 [book_reservation,cancel_reservation,get_reservation_details,get_user_details,list_all_airports,search_direct_flight,search_onestop_flight,send_certificate,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must]: The agent must make sure the rules apply before calling the API!
  - SIM S4-C07-R2 [cancel_reservation; must_not]: The agent must not cancel a reservation unless it is within 24 hours of booking, or if the airline cancelled the flight.

## AIR-CAN-03b
- gold quote: "If any of the segments are already used, the agent cannot help and transfer is needed."
- gold reading: If a segment was flown, cancellation requests go to a human agent.
- GOLD AIR-R044: If the user asks to cancel a reservation in which any flight segment has already been flown, the agent must transfer the user to a human agent.
- aligned auto clauses: S4-C09
  - SRC S4-C04-R1 [cancel_reservation; must]: The agent must determine whether the reservation contains business-class flight segments and that none of the segments have been used before proceeding to cancellation.
  - SRC S4-C04-R4 [cancel_reservation; must]: The agent must cancel the whole reservation that contains business-class flight segments, and none of the segments are used.
  - SRC S4-C05-R1 [cancel_reservation; must]: The agent must apply the cancellation rules strictly regardless of the user’s membership status.
  - SRC S4-C07-R5 [cancel_reservation; must_not]: The agent must not cancel if any of the segments are already used.
  - SRC S4-C07-R6 [book_reservation,cancel_reservation,get_reservation_details,get_user_details,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must]: The agent must transfer to a human agent if any of the segments are already used.
  - SRC S4-C08-R4 [cancel_reservation; must_not]: The agent must not cancel if any of the segments are already used; transfer is needed.
  - SRC S4-C09-R1 [cancel_reservation; must_not]: The agent must not assist with cancellation if any of the segments are already used.
  - SRC S4-C09-R2 [cancel_reservation,get_reservation_details,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must]: The agent must transfer to human agents if any of the segments are already used.
  - SIM S4-C07-R7 [cancel_reservation; must]: The agent must cancel the whole trip only if none of the segments have been flown.
  - SIM S4-C02-R2 [cancel_reservation; must]: The agent must list the action details and obtain explicit confirmation from the user before cancelling, including the reservation id and the reason for cancellation (change of plan, airline cancelled flight, or other reasons).
  - SIM S4-C08-R2 [cancel_reservation; must]: The agent must first obtain the user id, the reservation id, and the reason for cancellation (change of plan, airline cancelled flight, or other reasons).

## AIR-COMP-01a
- gold quote: "If the user is silver/gold member or has travel insurance or flies business, and complains about cancelled flights in a reservation, the agent can offer a certificate as a gesture"
- gold reading: Cancelled-flight certificate allowed only for eligible users (silver/gold OR insured OR business) who complain about a cancelled flight.
- GOLD AIR-R045: The agent must not send a certificate to a user who is a regular member, has no travel insurance on the reservation, and flies basic economy or economy in it.
- GOLD AIR-R046: The agent must not offer or send compensation unless the user has complained about the situation and explicitly asked for compensation.
- GOLD AIR-R048: For a complaint about a cancelled flight, the agent must set the certificate amount to exactly 100 dollars times the number of passengers in the reservation.
- aligned auto clauses: S5-C01
  - SRC S5-C01-R1 [respond_to_user,send_certificate; must_not]: The agent must not offer a certificate as a gesture unless the user is silver/gold member or has travel insurance or flies business, and complains about cancelled flights in a reservation, after confirming the facts.
  - SRC S5-C01-R2 [book_reservation,get_reservation_details,get_user_details,update_reservation_flights,update_reservation_passengers; must]: The agent must determine the number of passengers in the reservation.
  - SRC S5-C01-R3 [calculate,send_certificate; must]: The agent must calculate the certificate amount as 100 dollars times the number of passengers.
  - SRC S5-C01-R4 [send_certificate; must]: The agent must send the certificate to the user after confirming the facts and after calculating the amount.
  - SRC S5-C03-R2 [get_reservation_details,get_user_details,respond_to_user,send_certificate; may]: The agent must offer a certificate as a gesture after confirming the facts, with the amount being $100 times the number of passengers, if the user is silver/gold member or has travel insurance or flies business, and complains about cancelled flights in a reservation.
  - SRC S5-C04-R1 [respond_to_user,send_certificate; must_not]: The agent must not compensate if the user is a regular member and has no travel insurance and flies (basic) economy.
  - SIM S5-C03-R1 [respond_to_user; must_not]: The agent must not proactively offer compensation unless the user complains about the situation and explicitly asks for some compensation.

## AIR-COMP-01b
- gold quote: "after confirming the facts"
- gold reading: Facts verified before offering the cancelled-flight certificate.
- GOLD AIR-R047: The agent must confirm the facts (that the flight in the user's reservation was actually cancelled or delayed, verified via tool lookups) before offering or sending a certificate.
- aligned auto clauses: S5-C01
  - SRC S5-C01-R1 [respond_to_user,send_certificate; must_not]: The agent must not offer a certificate as a gesture unless the user is silver/gold member or has travel insurance or flies business, and complains about cancelled flights in a reservation, after confirming the facts.
  - SRC S5-C01-R2 [book_reservation,get_reservation_details,get_user_details,update_reservation_flights,update_reservation_passengers; must]: The agent must determine the number of passengers in the reservation.
  - SRC S5-C01-R3 [calculate,send_certificate; must]: The agent must calculate the certificate amount as 100 dollars times the number of passengers.
  - SRC S5-C01-R4 [send_certificate; must]: The agent must send the certificate to the user after confirming the facts and after calculating the amount.
  - SRC S5-C03-R2 [get_reservation_details,get_user_details,respond_to_user,send_certificate; may]: The agent must offer a certificate as a gesture after confirming the facts, with the amount being $100 times the number of passengers, if the user is silver/gold member or has travel insurance or flies business, and complains about cancelled flights in a reservation.
  - SRC S5-C04-R1 [respond_to_user,send_certificate; must_not]: The agent must not compensate if the user is a regular member and has no travel insurance and flies (basic) economy.
  - SIM S0-C02-R6 [cancel_reservation; must_not]: The agent must not cancel a reservation unless the action details are listed and explicit user confirmation (yes) to proceed.

## AIR-COMP-01c
- gold quote: "with the amount being $100 times the number of passengers."
- gold reading: Cancelled-flight certificate = $100 × passengers.
- GOLD AIR-R048: For a complaint about a cancelled flight, the agent must set the certificate amount to exactly 100 dollars times the number of passengers in the reservation.
- aligned auto clauses: S5-C01
  - SRC S5-C01-R1 [respond_to_user,send_certificate; must_not]: The agent must not offer a certificate as a gesture unless the user is silver/gold member or has travel insurance or flies business, and complains about cancelled flights in a reservation, after confirming the facts.
  - SRC S5-C01-R2 [book_reservation,get_reservation_details,get_user_details,update_reservation_flights,update_reservation_passengers; must]: The agent must determine the number of passengers in the reservation.
  - SRC S5-C01-R3 [calculate,send_certificate; must]: The agent must calculate the certificate amount as 100 dollars times the number of passengers.
  - SRC S5-C01-R4 [send_certificate; must]: The agent must send the certificate to the user after confirming the facts and after calculating the amount.
  - SRC S5-C03-R2 [get_reservation_details,get_user_details,respond_to_user,send_certificate; may]: The agent must offer a certificate as a gesture after confirming the facts, with the amount being $100 times the number of passengers, if the user is silver/gold member or has travel insurance or flies business, and complains about cancelled flights in a reservation.
  - SRC S5-C04-R1 [respond_to_user,send_certificate; must_not]: The agent must not compensate if the user is a regular member and has no travel insurance and flies (basic) economy.
  - SIM S5-C02-R2 [cancel_reservation,respond_to_user,send_certificate,update_reservation_flights,update_reservation_passengers; may]: The agent must offer a certificate after confirming the facts and changing or cancelling the reservation, with the amount being $50 times the number of passengers, but only if the user is silver/gold member or has travel insurance or flies business, and the user complains about delayed flights in a reservation and wants to change or cancel the reservation, and explicitly asks for compensation.

## AIR-COMP-02a
- gold quote: "If the user is silver/gold member or has travel insurance or flies business, and complains about delayed flights in a reservation and wants to change or cancel the reservation, the agent can offer a certificate as a gesture"
- gold reading: Delayed-flight certificate allowed only for eligible users who complain about a delay AND want to change or cancel.
- GOLD AIR-R045: The agent must not send a certificate to a user who is a regular member, has no travel insurance on the reservation, and flies basic economy or economy in it.
- GOLD AIR-R046: The agent must not offer or send compensation unless the user has complained about the situation and explicitly asked for compensation.
- GOLD AIR-R049: For a complaint about a delayed flight, the agent must send a certificate only if the user wanted to change or cancel the reservation and only after that change or cancellation has been completed.
- GOLD AIR-R050: For a complaint about a delayed flight, the agent must set the certificate amount to exactly 50 dollars times the number of passengers in the reservation.
- aligned auto clauses: S5-C02
  - SRC S5-C02-R1 [respond_to_user,send_certificate; must_not]: The agent must not proactively offer a certificate unless the user is silver/gold member or has travel insurance or flies business, and complains about delayed flights in a reservation and wants to change or cancel the reservation, and explicitly asks for compensation.
  - SRC S5-C02-R2 [cancel_reservation,respond_to_user,send_certificate,update_reservation_flights,update_reservation_passengers; may]: The agent must offer a certificate after confirming the facts and changing or cancelling the reservation, with the amount being $50 times the number of passengers, but only if the user is silver/gold member or has travel insurance or flies business, and the user complains about delayed flights in a reservation and wants to change or cancel the reservation, and explicitly asks for compensation.
  - SRC S5-C03-R3 [cancel_reservation,respond_to_user,send_certificate,update_reservation_flights,update_reservation_passengers; may]: The agent must offer a certificate as a gesture after confirming the facts and changing or cancelling the reservation, with the amount being $50 times the number of passengers, if the user is silver/gold member or has travel insurance or flies business, and complains about delayed flights in a reservation and wants to change or cancel the reservation.
  - SRC S5-C04-R1 [respond_to_user,send_certificate; must_not]: The agent must not compensate if the user is a regular member and has no travel insurance and flies (basic) economy.
  - SIM S5-C03-R1 [respond_to_user; must_not]: The agent must not proactively offer compensation unless the user complains about the situation and explicitly asks for some compensation.

## AIR-COMP-02b
- gold quote: "after confirming the facts and changing or cancelling the reservation"
- gold reading: Delayed-flight certificate only after facts verified and the change/cancellation done.
- GOLD AIR-R047: The agent must confirm the facts (that the flight in the user's reservation was actually cancelled or delayed, verified via tool lookups) before offering or sending a certificate.
- GOLD AIR-R049: For a complaint about a delayed flight, the agent must send a certificate only if the user wanted to change or cancel the reservation and only after that change or cancellation has been completed.
- aligned auto clauses: S5-C02
  - SRC S5-C02-R1 [respond_to_user,send_certificate; must_not]: The agent must not proactively offer a certificate unless the user is silver/gold member or has travel insurance or flies business, and complains about delayed flights in a reservation and wants to change or cancel the reservation, and explicitly asks for compensation.
  - SRC S5-C02-R2 [cancel_reservation,respond_to_user,send_certificate,update_reservation_flights,update_reservation_passengers; may]: The agent must offer a certificate after confirming the facts and changing or cancelling the reservation, with the amount being $50 times the number of passengers, but only if the user is silver/gold member or has travel insurance or flies business, and the user complains about delayed flights in a reservation and wants to change or cancel the reservation, and explicitly asks for compensation.
  - SRC S5-C03-R3 [cancel_reservation,respond_to_user,send_certificate,update_reservation_flights,update_reservation_passengers; may]: The agent must offer a certificate as a gesture after confirming the facts and changing or cancelling the reservation, with the amount being $50 times the number of passengers, if the user is silver/gold member or has travel insurance or flies business, and complains about delayed flights in a reservation and wants to change or cancel the reservation.
  - SRC S5-C04-R1 [respond_to_user,send_certificate; must_not]: The agent must not compensate if the user is a regular member and has no travel insurance and flies (basic) economy.
  - SIM S4-C02-R2 [cancel_reservation; must]: The agent must list the action details and obtain explicit confirmation from the user before cancelling, including the reservation id and the reason for cancellation (change of plan, airline cancelled flight, or other reasons).

## AIR-COMP-02c
- gold quote: "with the amount being $50 times the number of passengers."
- gold reading: Delayed-flight certificate = $50 × passengers.
- GOLD AIR-R050: For a complaint about a delayed flight, the agent must set the certificate amount to exactly 50 dollars times the number of passengers in the reservation.
- aligned auto clauses: S5-C02
  - SRC S5-C02-R1 [respond_to_user,send_certificate; must_not]: The agent must not proactively offer a certificate unless the user is silver/gold member or has travel insurance or flies business, and complains about delayed flights in a reservation and wants to change or cancel the reservation, and explicitly asks for compensation.
  - SRC S5-C02-R2 [cancel_reservation,respond_to_user,send_certificate,update_reservation_flights,update_reservation_passengers; may]: The agent must offer a certificate after confirming the facts and changing or cancelling the reservation, with the amount being $50 times the number of passengers, but only if the user is silver/gold member or has travel insurance or flies business, and the user complains about delayed flights in a reservation and wants to change or cancel the reservation, and explicitly asks for compensation.
  - SRC S5-C03-R3 [cancel_reservation,respond_to_user,send_certificate,update_reservation_flights,update_reservation_passengers; may]: The agent must offer a certificate as a gesture after confirming the facts and changing or cancelling the reservation, with the amount being $50 times the number of passengers, if the user is silver/gold member or has travel insurance or flies business, and complains about delayed flights in a reservation and wants to change or cancel the reservation.
  - SRC S5-C04-R1 [respond_to_user,send_certificate; must_not]: The agent must not compensate if the user is a regular member and has no travel insurance and flies (basic) economy.
  - SIM S5-C03-R2 [get_reservation_details,get_user_details,respond_to_user,send_certificate; may]: The agent must offer a certificate as a gesture after confirming the facts, with the amount being $100 times the number of passengers, if the user is silver/gold member or has travel insurance or flies business, and complains about cancelled flights in a reservation.
  - SIM S5-C01-R3 [calculate,send_certificate; must]: The agent must calculate the certificate amount as 100 dollars times the number of passengers.

## AIR-COMP-03a
- gold quote: "Do not proactively offer these unless the user complains about the situation and explicitly asks for some compensation."
- gold reading: No compensation offer unless the user complained and explicitly asked.
- GOLD AIR-R046: The agent must not offer or send compensation unless the user has complained about the situation and explicitly asked for compensation.
- aligned auto clauses: S5-C03
  - SRC S5-C02-R1 [respond_to_user,send_certificate; must_not]: The agent must not proactively offer a certificate unless the user is silver/gold member or has travel insurance or flies business, and complains about delayed flights in a reservation and wants to change or cancel the reservation, and explicitly asks for compensation.
  - SRC S5-C03-R1 [respond_to_user; must_not]: The agent must not proactively offer compensation unless the user complains about the situation and explicitly asks for some compensation.
  - SRC S5-C03-R2 [get_reservation_details,get_user_details,respond_to_user,send_certificate; may]: The agent must offer a certificate as a gesture after confirming the facts, with the amount being $100 times the number of passengers, if the user is silver/gold member or has travel insurance or flies business, and complains about cancelled flights in a reservation.
  - SRC S5-C03-R3 [cancel_reservation,respond_to_user,send_certificate,update_reservation_flights,update_reservation_passengers; may]: The agent must offer a certificate as a gesture after confirming the facts and changing or cancelling the reservation, with the amount being $50 times the number of passengers, if the user is silver/gold member or has travel insurance or flies business, and complains about delayed flights in a reservation and wants to change or cancel the reservation.
  - SRC S5-C04-R1 [respond_to_user,send_certificate; must_not]: The agent must not compensate if the user is a regular member and has no travel insurance and flies (basic) economy.
  - SIM S0-C02-R12 [transfer_to_human_agents; if_and_only_if]: The agent must transfer the user to a human agent if and only if the request cannot be handled within the scope of your actions.

## AIR-COMP-03b
- gold quote: "Do not compensate if the user is regular member and has no travel insurance and flies (basic) economy."
- gold reading: No compensation for regular + uninsured + (basic economy OR economy).
- GOLD AIR-R045: The agent must not send a certificate to a user who is a regular member, has no travel insurance on the reservation, and flies basic economy or economy in it.
- aligned auto clauses: S5-C04
  - SRC S5-C04-R1 [respond_to_user,send_certificate; must_not]: The agent must not compensate if the user is a regular member and has no travel insurance and flies (basic) economy.
  - SIM S2-C08-R1 [book_reservation,get_user_details,respond_to_user,update_reservation_baggages; only_if]: The agent must grant 0 free checked bag for each basic economy passenger only if the booking user is a regular member.
  - SIM S2-C10-R1 [book_reservation,respond_to_user,update_reservation_baggages,update_reservation_passengers; must]: The agent must provide 2 free checked bag for each basic economy passenger if the booking user is a gold member.

# All auto rules

- S0-C02-R1 [book_reservation; must_not; src S0-C02,S0-C03]: The agent must not book a reservation unless the action details are listed and explicit user confirmation (yes) to proceed.
- S0-C02-R2 [book_reservation,cancel_reservation,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must_not; src S0-C02,S0-C03]: The agent must not modify flight reservations unless the action details are listed and explicit user confirmation (yes) to proceed.
- S0-C02-R3 [update_reservation_baggages; must_not; src S0-C02,S0-C03]: The agent must not update baggage information unless the action details are listed and explicit user confirmation (yes) to proceed.
- S0-C02-R4 [book_reservation,update_reservation_flights; must_not; src S0-C02,S0-C03]: The agent must not upgrade cabin class unless the action details are listed and explicit user confirmation (yes) to proceed.
- S0-C02-R5 [update_reservation_passengers; must_not; src S0-C02,S0-C03]: The agent must not update passenger information unless the action details are listed and explicit user confirmation (yes) to proceed.
- S0-C02-R6 [cancel_reservation; must_not; src S0-C02,S0-C03]: The agent must not cancel a reservation unless the action details are listed and explicit user confirmation (yes) to proceed.
- S0-C02-R7 [book_reservation,cancel_reservation,get_reservation_details,get_user_details,respond_to_user,send_certificate,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must; src S0-C02,S3-C13,S4-C01,S4-C02]: The agent must authenticate the user by locating the user id via email or via name + zip code before any other action or disclosure of information.
- S0-C02-R8 [respond_to_user,think; must_not; src S0-C02,S0-C04]: The agent must not provide any information, knowledge, or procedures not provided by the user or available tools, or give subjective recommendations or comments.
- S0-C02-R9 [book_reservation,calculate,cancel_reservation,get_reservation_details,get_user_details,list_all_airports,search_direct_flight,search_onestop_flight,send_certificate,think,transfer_to_human_agents,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must_not; src S0-C02,S0-C05,S0-C06]: The agent must not make more than one tool call at a time, and if you make a tool call, you should not respond to the user simultaneously.
- S0-C02-R10 [respond_to_user; must_not; src S0-C02,S0-C06]: The agent must not respond to the user while a tool call is in progress.
- S0-C02-R12 [transfer_to_human_agents; if_and_only_if; src S0-C02,S0-C08]: The agent must transfer the user to a human agent if and only if the request cannot be handled within the scope of your actions.
- S0-C03-R1 [book_reservation,cancel_reservation,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must; src S0-C03]: The agent must list the action details and obtain explicit user confirmation (yes) to proceed before taking any actions that update the booking database (booking, modifying flights, editing baggage, upgrading cabin class, or updating passenger information).
- S0-C04-R1 [respond_to_user; must_not; src S0-C04]: The agent must not provide any information, knowledge, or procedures not provided by the user or available tools.
- S0-C04-R2 [respond_to_user; must_not; src S0-C04]: The agent must not give subjective recommendations or comments.
- S0-C05-R1 [book_reservation,calculate,cancel_reservation,get_reservation_details,get_user_details,list_all_airports,search_direct_flight,search_onestop_flight,send_certificate,think,transfer_to_human_agents,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must_not; src S0-C05]: The agent must not make more than one tool call at a time.
- S0-C05-R2 [book_reservation,calculate,cancel_reservation,get_reservation_details,get_user_details,list_all_airports,respond_to_user,search_direct_flight,search_onestop_flight,send_certificate,think,transfer_to_human_agents,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must_not; src S0-C05]: The agent must not respond to the user at the same time as a tool call is made.
- S0-C06-R1 [book_reservation,calculate,cancel_reservation,get_reservation_details,get_user_details,list_all_airports,search_direct_flight,search_onestop_flight,send_certificate,think,transfer_to_human_agents,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must; src S0-C06]: The agent must not perform a tool call while sending a response to the user.
- S0-C06-R2 [book_reservation,cancel_reservation,get_reservation_details,get_user_details,list_all_airports,search_direct_flight,search_onestop_flight,send_certificate,transfer_to_human_agents,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must; src S0-C06]: The agent must only make one tool call at a time, and if the agent makes a tool call, the agent must not respond to the user simultaneously.
- S0-C07-R1 [respond_to_user; must; src S0-C07,S0-C02]: The agent must deny user requests that are against this policy.
- S0-C07-R2 [book_reservation; must_not; src S0-C07,S0-C03]: The agent must not book a reservation in response to a user request that is against this policy.
- S0-C07-R3 [update_reservation_flights; must_not; src S0-C07,S0-C03]: The agent must not update flight information in a reservation in response to a user request that is against this policy.
- S0-C07-R4 [update_reservation_baggages; must_not; src S0-C07,S0-C03]: The agent must not update baggage information in a reservation in response to a user request that is against this policy.
- S0-C07-R5 [update_reservation_passengers; must_not; src S0-C07,S0-C03]: The agent must not update passenger information in a reservation in response to a user request that is against this policy.
- S0-C07-R6 [book_reservation,update_reservation_flights; must_not; src S0-C07,S0-C03]: The agent must not upgrade cabin class in a reservation in response to a user request that is against this policy.
- S1-C06-R1 [book_reservation; must_not; src S1-C06]: The agent must not book the flight if the status is 'delayed' or 'on time'.
- S1-C08-R1 [book_reservation; must_not; src S1-C08]: The agent must not book a flight if the status is "flying".
- S2-C01-R1 [book_reservation,cancel_reservation,get_reservation_details,get_user_details,respond_to_user,search_direct_flight,search_onestop_flight,send_certificate,transfer_to_human_agents,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must; src S2-C01]: The agent must locate the user id by using the email address or by the user's name and zip code, before performing any other action.
- S2-C01-R2 [book_reservation,respond_to_user,search_direct_flight,search_onestop_flight; must; src S2-C01]: The agent must ask for the trip type, origin, and destination only after the user id has been located.
- S2-C02-R1 [book_reservation,update_reservation_passengers; must_not; src S2-C02,S2-C03]: The agent must not create or update a reservation such that the reservation has more than five passengers.
- S2-C03-R1 [book_reservation,update_reservation_passengers; must; src S2-C03]: The agent must collect the first name for each passenger.
- S2-C03-R2 [book_reservation,update_reservation_passengers; must; src S2-C03]: The agent must collect the last name for each passenger.
- S2-C03-R3 [book_reservation,update_reservation_passengers; must; src S2-C03]: The agent must collect the date of birth for each passenger.
- S2-C04-R1 [book_reservation,update_reservation_flights,update_reservation_passengers; must; src S2-C04]: The agent must ensure that all passengers fly the same flights.
- S2-C04-R2 [book_reservation,update_reservation_passengers; must; src S2-C04]: The agent must ensure that all passengers are in the same cabin.
- S2-C05-R1 [book_reservation,send_certificate; must; src S2-C05]: The agent must ensure that each reservation uses at most one travel certificate.
- S2-C05-R2 [book_reservation; must; src S2-C05]: The agent must ensure that each reservation uses at most one credit card.
- S2-C05-R3 [book_reservation; must; src S2-C05]: The agent must ensure that each reservation uses at most three gift cards.
- S2-C06-R1 [cancel_reservation,respond_to_user; must_not; src S2-C06]: The agent must not refund the remaining amount of a travel certificate.
- S2-C07-R1 [book_reservation,send_certificate; must_not; src S2-C07,S2-C05]: The agent must not use a travel certificate for the reservation unless it is already in the user's profile.
- S2-C07-R2 [book_reservation; must_not; src S2-C07,S2-C05]: The agent must not use a credit card for the reservation unless it is already in the user's profile.
- S2-C07-R3 [book_reservation; must_not; src S2-C07,S2-C05]: The agent must not use any gift card for the reservation unless that gift card is already in the user's profile.
- S2-C08-R1 [book_reservation,get_user_details,respond_to_user,update_reservation_baggages; only_if; src S2-C08]: The agent must grant 0 free checked bag for each basic economy passenger only if the booking user is a regular member.
- S2-C08-R2 [book_reservation,update_reservation_baggages; only_if; src S2-C08]: The agent must grant 1 free checked bag for each economy passenger only if the booking user is a regular member.
- S2-C08-R3 [book_reservation,respond_to_user,update_reservation_baggages; only_if; src S2-C08]: The agent must grant 2 free checked bags for each business passenger only if the booking user is a regular member.
- S2-C09-R1 [book_reservation,update_reservation_baggages,update_reservation_passengers; must; src S2-C09]: The agent must grant 1 free checked bag for each basic economy passenger if the booking user is a silver member.
- S2-C09-R2 [book_reservation,update_reservation_baggages; must; src S2-C09]: The agent must grant 2 free checked bags for each economy passenger if the booking user is a silver member.
- S2-C09-R3 [book_reservation,update_reservation_baggages; must; src S2-C09]: The agent must grant 3 free checked bags for each business passenger if the booking user is a silver member.
- S2-C10-R1 [book_reservation,respond_to_user,update_reservation_baggages,update_reservation_passengers; must; src S2-C10]: The agent must provide 2 free checked bag for each basic economy passenger if the booking user is a gold member.
- S2-C10-R2 [book_reservation,respond_to_user,update_reservation_baggages; must; src S2-C10]: The agent must provide 3 free checked bag for each economy passenger if the booking user is a gold member.
- S2-C10-R3 [book_reservation,respond_to_user,update_reservation_baggages; must; src S2-C10]: The agent must provide 3 free checked bags for each business passenger if the booking user is a gold member.
- S2-C11-R1 [book_reservation,respond_to_user,update_reservation_baggages; must; src S2-C11,S2-C08]: The agent must charge 50 dollars for each extra baggage.
- S2-C12-R1 [book_reservation,respond_to_user; may; src S2-C12]: The agent must ask if the user wants to buy the travel insurance.
- S3-C01-R1 [book_reservation,cancel_reservation,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must; src S3-C01]: The agent must obtain the user id and the reservation id before taking any other modification-related actions.
- S3-C02-R1 [update_reservation_flights; must_not; src S3-C02]: The agent must not modify flights for basic economy reservations.
- S3-C03-R1 [update_reservation_flights; must_not; src S3-C03]: The agent must not change the origin of the reservation being modified.
- S3-C03-R2 [update_reservation_flights; must_not; src S3-C03]: The agent must not change the destination of the reservation being modified.
- S3-C03-R3 [update_reservation_flights; must_not; src S3-C03]: The agent must not change the trip type of the reservation being modified.
- S3-C03-R4 [book_reservation,cancel_reservation,get_reservation_details,get_user_details,list_all_airports,search_direct_flight,search_onestop_flight,send_certificate,transfer_to_human_agents,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must; src S3-C03,S3-C07]: The agent must make sure the rules apply before calling the API.
- S3-C04-R1 [update_reservation_flights; must_not; src S3-C04]: The agent must not prevent keeping some flight segments when modifying a flight reservation.
- S3-C07-R1 [book_reservation,cancel_reservation,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must; src S3-C07,S3-C01,S3-C02,S3-C03,S3-C04,S3-C08,S3-C09,S3-C10,S3-C11,S3-C12,S3-C13,S3-C14,S3-C15,S3-C16,S3-C17]: The agent must verify that all applicable rules apply before calling any booking-modifying API, specifically the rules listed in S3-C01 through S3-C17.
- S3-C07-R2 [book_reservation,cancel_reservation,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must; src S3-C07]: The agent must list the details of the actions to be performed before calling any booking-modifying API.
- S3-C07-R3 [book_reservation,cancel_reservation,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must; src S3-C07]: The agent must obtain explicit confirmation from the user before calling any booking-modifying API.
- S3-C08-R1 [update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must; src S3-C08,S3-C01]: The agent must obtain the user id and the reservation id before proceeding with a cabin change.
- S3-C08-R2 [book_reservation,cancel_reservation,get_reservation_details,get_user_details,list_all_airports,search_direct_flight,search_onestop_flight,send_certificate,transfer_to_human_agents,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must; src S3-C08,S3-C07]: The agent must make sure the rules apply before calling the API.
- S3-C08-R3 [book_reservation,update_reservation_flights; must_not; src S3-C08,S3-C10]: The agent must not change cabin if cabin class is not the same across all the flights in the same reservation; changing cabin for just one flight segment is not possible.
- S3-C08-R4 [book_reservation,update_reservation_flights; must; src S3-C08,S3-C09]: The agent must ensure the user pays for the difference between their current cabin and the new cabin class.
- S3-C08-R5 [update_reservation_flights,update_reservation_passengers; must; src S3-C08,S3-C17]: The agent must ask for the payment or refund method before processing cabin changes.
- S3-C08-R6 [update_reservation_flights; must; src S3-C08,S3-C03]: The agent must ensure cabin changes do not modify the origin, destination, or trip type of the reservation.
- S3-C09-R2 [update_reservation_flights; must_not; src S3-C09]: The agent must not change the cabin without receiving the payment difference.
- S3-C10-R1 [book_reservation,update_reservation_flights; must; src S3-C10]: The agent must ensure the cabin class is the same across all the flights in the same reservation.
- S3-C10-R2 [book_reservation,update_reservation_flights; must_not; src S3-C10]: The agent must not change cabin for just one flight segment.
- S3-C11-R1 [update_reservation_baggages; must_not; src S3-C11]: The agent must not remove checked bags from a reservation.
- S3-C11-R2 [update_reservation_baggages; must; src S3-C11]: The agent must update the reservation baggage to add checked bags when the user requests to add checked bags.
- S3-C11-R3 [update_reservation_baggages; must; src S3-C11,S3-C01]: The agent must first obtain the user id and the reservation id before updating baggage.
- S3-C11-R4 [book_reservation,cancel_reservation,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must; src S3-C07,S3-C11]: The agent must not call any modification API to the reservation unless the rules apply before the API call.
- S3-C12-R1 [respond_to_user,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must_not; src S3-C12]: The agent must not permit the user to add insurance after initial booking.
- S3-C13-R1 [book_reservation,cancel_reservation,get_reservation_details,get_user_details,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must; src S3-C13,S3-C01]: The agent must first obtain the user id and the reservation id.
- S3-C13-R2 [book_reservation,cancel_reservation,get_reservation_details,get_user_details,list_all_airports,search_direct_flight,search_onestop_flight,send_certificate,transfer_to_human_agents,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must; src S3-C13,S3-C07]: The agent must make sure the rules apply before calling the API.
- S3-C14-R1 [book_reservation,update_reservation_passengers; must_not; src S3-C14]: The agent must not modify the number of passengers.
- S3-C15-R1 [cancel_reservation; must_not; src S3-C15,S3-C07,S3-C06]: The agent must not attempt to assist with the request described by S3-C15, as this is something that even a human agent cannot assist with.
- S3-C16-R1 [update_reservation_flights; only_if; src S3-C16]: The agent must obtain from the user one gift card or credit card for payment or refund method only if the flights are changed.
- S3-C17-R1 [book_reservation,cancel_reservation; must; src S3-C17]: The agent must ask the user for the payment or refund method instead.
- S4-C01-R1 [cancel_reservation; must; src S4-C01,S4-C07]: The agent must obtain the user id before making the cancellation.
- S4-C01-R2 [cancel_reservation; must; src S4-C01,S4-C07]: The agent must obtain the reservation id before making the cancellation.
- S4-C01-R3 [cancel_reservation; must; src S4-C01,S4-C07]: The agent must obtain the reason for cancellation (change of plan, airline cancelled flight, or other reasons) before making the cancellation.
- S4-C02-R1 [cancel_reservation; must_not; src S4-C02]: The agent must not cancel a reservation unless the cancellation is within 24 hours of booking, or the airline cancelled the flight.
- S4-C02-R2 [cancel_reservation; must; src S4-C02,S4-C01]: The agent must list the action details and obtain explicit confirmation from the user before cancelling, including the reservation id and the reason for cancellation (change of plan, airline cancelled flight, or other reasons).
- S4-C03-R1 [cancel_reservation; must_not; src S4-C03]: The agent must not cancel basic economy or economy flights unless travel insurance is bought and the condition is met.
- S4-C03-R2 [cancel_reservation; must; src S4-C03,S4-C02,S4-C07]: The agent must ensure that cancellation-related rules are applied before calling the API to cancel the reservation.
- S4-C04-R1 [cancel_reservation; must; src S4-C04,S4-C08,S4-C09,S4-C07]: The agent must determine whether the reservation contains business-class flight segments and that none of the segments have been used before proceeding to cancellation.
- S4-C04-R2 [cancel_reservation; must; src S4-C04,S4-C01,S4-C07]: The agent must obtain the user id, the reservation id, and the reason for cancellation (change of plan, airline cancelled flight, or other reasons) before performing cancellation.
- S4-C04-R3 [cancel_reservation,respond_to_user; must; src S4-C04,S4-C01,S4-C07]: The agent must list the cancellation details to the user and obtain explicit confirmation before calling the API to cancel.
- S4-C04-R4 [cancel_reservation; must; src S4-C04,S4-C08,S4-C09,S4-C07]: The agent must cancel the whole reservation that contains business-class flight segments, and none of the segments are used.
- S4-C04-R5 [respond_to_user; must; src S4-C04,S4-C10]: The agent must inform the user that the refund will go to original payment methods in 5 to 7 business days.
- S4-C04-R6 [cancel_reservation,get_reservation_details; must; src S4-C04,S4-C06,S4-C07]: The agent must perform the required checks before invoking the cancellation API, since the API does not check these for the agent.
- S4-C05-R1 [cancel_reservation; must; src S4-C05,S4-C01,S4-C02,S4-C03,S4-C04,S4-C07,S4-C08,S4-C09]: The agent must apply the cancellation rules strictly regardless of the user’s membership status.
- S4-C07-R1 [cancel_reservation; must; src S4-C07,S4-C01]: The agent must first obtain the user id, the reservation id, and the reason for cancellation (change of plan, airline cancelled flight, or other reasons) before calling the API.
- S4-C07-R2 [cancel_reservation; must_not; src S4-C07,S4-C02]: The agent must not cancel a reservation unless it is within 24 hours of booking, or if the airline cancelled the flight.
- S4-C07-R3 [cancel_reservation; must_not; src S4-C07,S4-C03]: The agent must not cancel basic economy or economy flights unless travel insurance is bought and the condition is met.
- S4-C07-R4 [cancel_reservation; must; src S4-C07,S4-C05]: The agent must apply the cancellation rules regardless of the membership status.
- S4-C07-R5 [cancel_reservation; must_not; src S4-C07,S4-C09]: The agent must not cancel if any of the segments are already used.
- S4-C07-R6 [book_reservation,cancel_reservation,get_reservation_details,get_user_details,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must; src S4-C07,S4-C09]: The agent must transfer to a human agent if any of the segments are already used.
- S4-C07-R7 [cancel_reservation; must; src S4-C07,S4-C08]: The agent must cancel the whole trip only if none of the segments have been flown.
- S4-C07-R8 [cancel_reservation; must; src S4-C07,S4-C06]: The agent must perform the necessary checks for cancellation before calling the API because the API does not check these for the agent.
- S4-C08-R1 [book_reservation,cancel_reservation,get_reservation_details,get_user_details,respond_to_user,send_certificate,transfer_to_human_agents,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must; src S4-C08]: The agent must authenticate the user by locating the user id via email or via name + zip code, before any other action or disclosure of information.
- S4-C08-R2 [cancel_reservation; must; src S4-C08,S4-C01]: The agent must first obtain the user id, the reservation id, and the reason for cancellation (change of plan, airline cancelled flight, or other reasons).
- S4-C08-R3 [cancel_reservation; must_not; src S4-C08,S4-C02,S4-C04,S4-C07]: The agent must not cancel unless within 24 hours of booking, or the airline cancelled the flight, or the flight is a business flight.
- S4-C08-R4 [cancel_reservation; must_not; src S4-C08,S4-C09,S4-C07]: The agent must not cancel if any of the segments are already used; transfer is needed.
- S4-C08-R5 [book_reservation,cancel_reservation,get_reservation_details,get_user_details,list_all_airports,search_direct_flight,search_onestop_flight,send_certificate,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must; src S4-C08,S4-C07]: The agent must make sure the rules apply before calling the API!
- S4-C09-R1 [cancel_reservation; must_not; src S4-C09]: The agent must not assist with cancellation if any of the segments are already used.
- S4-C09-R2 [cancel_reservation,get_reservation_details,update_reservation_baggages,update_reservation_flights,update_reservation_passengers; must; src S4-C09]: The agent must transfer to human agents if any of the segments are already used.
- S5-C01-R1 [respond_to_user,send_certificate; must_not; src S5-C01]: The agent must not offer a certificate as a gesture unless the user is silver/gold member or has travel insurance or flies business, and complains about cancelled flights in a reservation, after confirming the facts.
- S5-C01-R2 [book_reservation,get_reservation_details,get_user_details,update_reservation_flights,update_reservation_passengers; must; src S5-C01]: The agent must determine the number of passengers in the reservation.
- S5-C01-R3 [calculate,send_certificate; must; src S5-C01]: The agent must calculate the certificate amount as 100 dollars times the number of passengers.
- S5-C01-R4 [send_certificate; must; src S5-C01]: The agent must send the certificate to the user after confirming the facts and after calculating the amount.
- S5-C02-R1 [respond_to_user,send_certificate; must_not; src S5-C02,S5-C03]: The agent must not proactively offer a certificate unless the user is silver/gold member or has travel insurance or flies business, and complains about delayed flights in a reservation and wants to change or cancel the reservation, and explicitly asks for compensation.
- S5-C02-R2 [cancel_reservation,respond_to_user,send_certificate,update_reservation_flights,update_reservation_passengers; may; src S5-C02]: The agent must offer a certificate after confirming the facts and changing or cancelling the reservation, with the amount being $50 times the number of passengers, but only if the user is silver/gold member or has travel insurance or flies business, and the user complains about delayed flights in a reservation and wants to change or cancel the reservation, and explicitly asks for compensation.
- S5-C03-R1 [respond_to_user; must_not; src S5-C03]: The agent must not proactively offer compensation unless the user complains about the situation and explicitly asks for some compensation.
- S5-C03-R2 [get_reservation_details,get_user_details,respond_to_user,send_certificate; may; src S5-C03,S5-C01]: The agent must offer a certificate as a gesture after confirming the facts, with the amount being $100 times the number of passengers, if the user is silver/gold member or has travel insurance or flies business, and complains about cancelled flights in a reservation.
- S5-C03-R3 [cancel_reservation,respond_to_user,send_certificate,update_reservation_flights,update_reservation_passengers; may; src S5-C03,S5-C02]: The agent must offer a certificate as a gesture after confirming the facts and changing or cancelling the reservation, with the amount being $50 times the number of passengers, if the user is silver/gold member or has travel insurance or flies business, and complains about delayed flights in a reservation and wants to change or cancel the reservation.
- S5-C04-R1 [respond_to_user,send_certificate; must_not; src S5-C04,S5-C01,S5-C02,S5-C03]: The agent must not compensate if the user is a regular member and has no travel insurance and flies (basic) economy.
