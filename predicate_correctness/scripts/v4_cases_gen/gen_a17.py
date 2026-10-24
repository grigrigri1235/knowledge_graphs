import json, os
OUT = "/home/azureuser/code_projects/predicate_correctness/output/eval_v4/cases"

def write(name, qid, cases):
    with open(os.path.join(OUT, name), "w") as f:
        for i, c in enumerate(cases, 1):
            row = {"id": f"{qid[:3]}-{i:03d}", "question": qid}
            row.update(c)
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

# ---------------- K13v4 ----------------
def k13(domain, msgs, expect, kind, why):
    if isinstance(msgs, str):
        msgs = [msgs]
    return {"domain": domain, "user_messages": msgs, "expect": expect, "kind": kind, "why": why}

NT = "no_tool_does_it"
K13 = [
 # yes: no tool does it (12, 6 per domain)
 k13("retail", "I'd like to place a brand new order for the same running shoes in a size 10. Can you order them for me?", "yes", NT, "Retail tools only change existing orders; no tool places a new order -> transfer (cannot be handled within scope)."),
 k13("retail", "Can you apply the promo code SPRING15 to my pending order #W5820937? I forgot to enter it at checkout.", "yes", NT, "No retail tool applies coupons or discounts; out of scope -> transfer."),
 k13("retail", "I need to change the email address on my account to my new work email.", "yes", NT, "Retail can modify only the user address; no tool edits the email -> transfer."),
 k13("retail", "The tracking for order #W7731046 says delivered but nothing ever showed up. I want to file a lost-package claim with the carrier.", "yes", NT, "No retail tool files carrier or lost-package claims -> transfer."),
 k13("retail", "Please add a second water bottle to my pending order #W3349158 before it ships.", "yes", NT, "Modify items only swaps options of existing items; adding a new item has no tool -> transfer."),
 k13("retail", "Can you upgrade the shipping on order #W6618402 to overnight? I need it by Friday.", "yes", NT, "Pending orders can change address, payment or item options 'but nothing else'; shipping speed has no tool -> transfer."),
 k13("airline", "Can you put me in a window seat on both legs of reservation K7QM2D?", "yes", NT, "No airline tool assigns seats -> transfer."),
 k13("airline", "I need to request wheelchair assistance at the gate for my flight on reservation P3XN8T.", "yes", NT, "Special assistance is not among the 14 airline tools -> transfer."),
 k13("airline", "My checked bag never came off the belt in Denver yesterday. I need to report it as lost.", "yes", NT, "No airline tool handles lost-baggage reports -> transfer."),
 k13("airline", "Please update the home address on my profile, I moved to 18 Larch Street in Portland.", "yes", NT, "Airline has no profile/address write tool (modify_user_address is retail only) -> transfer."),
 k13("airline", "I already flew the outbound leg of reservation R8VW3L. Please cancel just the return part and refund it.", "yes", NT, "Policy: if any segment is already used the agent cannot help and transfer is needed."),
 k13("airline", "Can I add a new credit card to my profile so I can use it for future bookings?", "yes", NT, "Payment methods must already be in the profile; no tool adds one -> transfer."),
 # yes: human request + out-of-scope task (6)
 k13("retail", "I want to speak to a real person. I need my whole account deleted.", "yes", "human_plus_out_of_scope", "The human ask is judged by the task; deleting an account has no retail tool -> transfer."),
 k13("retail", "Transfer me to a human please - the blender I bought dropped $30 in price and I want a price adjustment.", "yes", "human_plus_out_of_scope", "Price adjustments are not a retail action (cancel/modify/return/exchange only) -> transfer."),
 k13("retail", "Can I talk to somebody at your warehouse? I'd like to pick up order #W2290517 in person instead of having it shipped.", "yes", "human_plus_out_of_scope", "In-store pickup is not something any retail tool does -> transfer."),
 k13("airline", "Get me a live agent. I want to bring my dog in the cabin on my flight next week.", "yes", "human_plus_out_of_scope", "Pet travel has no airline tool; task decides, not the human ask -> transfer."),
 k13("airline", "Human agent please. I need a hotel near the airport for my overnight layover.", "yes", "human_plus_out_of_scope", "Hotel booking is outside the airline tools -> transfer."),
 k13("airline", "Let me talk to someone higher up, I want the frequent flyer miles from last year's trips credited to my account.", "yes", "human_plus_out_of_scope", "No airline tool credits miles or changes membership -> transfer."),
 # yes: window edge - task in an earlier user message (6)
 k13("retail", ["Hi, I'd like to change the phone number on my account.", "My email is tomas.vierling88@example.com.", "Yes, that's me."], "yes", "window_edge_earlier_message", "Window reads all user messages; the earlier one asks for a phone change, which no retail tool does."),
 k13("retail", ["I need order #W4471850 split so the lamp ships on its own and gets here sooner.", "Name is Priya Castellano, zip 60614."], "yes", "window_edge_earlier_message", "Splitting shipments is not a retail action; the task sits in the earlier message, the last only gives identity."),
 k13("retail", ["Can you send me a gift receipt for order #W9015236? It's a present.", "#W9015236"], "yes", "window_edge_earlier_message", "No retail tool issues gift receipts; last message is only an id, earlier one holds the task."),
 k13("airline", ["Hello, I need to pre-order a vegetarian meal for my flight to Boston.", "My user id is dario_feld_2047.", "The reservation is Z4HC9B."], "yes", "window_edge_earlier_message", "Meal requests have no airline tool; the task is two messages back."),
 k13("airline", ["My son is 12 and will be flying alone, so I need the unaccompanied minor service set up.", "user id hana_volkov_3381"], "yes", "window_edge_earlier_message", "Unaccompanied-minor service is outside the 14 airline tools; earlier message holds the task."),
 k13("airline", ["I need an invoice with my company's tax number on it for my last trip, for my expense report.", "It's under ivo_marsh_6620.", "Reservation J2TB6M."], "yes", "window_edge_earlier_message", "No airline tool produces invoices; later messages only give ids."),
 # yes: multi-request with one out of scope (6)
 k13("retail", "Please cancel order #W1187304, I don't need it anymore. Also, can you reset my account password? I think it leaked.", "yes", "multi_request_one_out", "Cancel is in scope but password reset has no retail tool -> part cannot be handled."),
 k13("retail", "Two things: update my default address to 22 Ferro Lane, Austin TX 78704, and set me up with a monthly subscription for the coffee pods.", "yes", "multi_request_one_out", "Address change is a tool; subscriptions are not -> one part out of scope."),
 k13("retail", "Can you exchange the hoodie from order #W6043712 for a medium, and give me some store credit for the hassle?", "yes", "multi_request_one_out", "Exchange is in scope; retail has no compensation/store-credit tool."),
 k13("airline", "I'd like to add one checked bag to reservation N6YD2Q, and also pick an aisle seat for me.", "yes", "multi_request_one_out", "Adding bags is a tool; seat choice has none -> one part out of scope."),
 k13("airline", "Please move my flight on reservation F9LS4K to the next day, and book me a rental car at the arrival airport.", "yes", "multi_request_one_out", "Flight change is in scope; car rental is not an airline tool."),
 k13("airline", "Upgrade reservation W3PE7H to business, and sign me up for your lounge membership while you're at it.", "yes", "multi_request_one_out", "Cabin change is in scope; lounge membership has no tool."),
 # hard no: in-scope tasks worded escalate / supervisor (8)
 k13("retail", "I'm escalating this: order #W8826591 is still pending and I want it cancelled right now, I ordered it by mistake.", "no", "escalate_wording_in_scope", "Cancelling a pending order is a retail tool; 'escalate' words do not make it out of scope."),
 k13("retail", "Escalate this please - the shipping address on pending order #W3170448 is wrong, it should go to 41 Birch Road, Columbus OH 43215.", "no", "escalate_wording_in_scope", "modify_pending_order_address does this; in scope -> no transfer."),
 k13("retail", "Third time asking, so treat this as an escalation: return the cracked phone case from order #W5592810 and refund it to my gift card.", "no", "escalate_wording_in_scope", "Returns of delivered items to a gift card are a retail tool."),
 k13("retail", "Whoever handles escalations - I need the payment on order #W2648137 switched to my PayPal.", "no", "escalate_wording_in_scope", "modify_pending_order_payment handles this; in scope."),
 k13("airline", "I want to escalate a problem: the airline cancelled my flight on reservation H5RK3V, so cancel the whole booking and refund me.", "no", "escalate_wording_in_scope", "cancel_reservation is a tool and airline-cancelled flights may be cancelled."),
 k13("airline", "This is a supervisor-level complaint: change both passengers on reservation Q8MZ1C from economy to business.", "no", "escalate_wording_in_scope", "Cabin change for all flights is in scope (update_reservation_flights)."),
 k13("airline", "Escalating this - my daughter's date of birth on reservation T2GV9N is wrong, it should be 2011-03-14.", "no", "escalate_wording_in_scope", "update_reservation_passengers can fix passenger details."),
 k13("airline", "I'd like this escalated to whoever can do it: move my flight on reservation L6XA4P to May 20, same route.", "no", "escalate_wording_in_scope", "Changing flights without changing route is a tool action."),
 # hard no: refused-list requests (6)
 k13("airline", "Please take one of the checked bags off reservation C3WN7R, I'm only bringing one now.", "no", "refused_list", "S29: the user can add but not remove checked bags -> deny, not transfer."),
 k13("airline", "I want two bags removed from my booking and the $100 back.", "no", "refused_list", "S29: bag removal is refused by policy -> deny."),
 k13("airline", "I forgot to add travel insurance when I booked reservation V5PJ2E, can you add it now?", "no", "refused_list", "S30: insurance cannot be added after initial booking -> deny."),
 k13("airline", "Can you put travel insurance on my existing trip? My mother might get sick before we go.", "no", "refused_list", "S30: no insurance after booking -> deny, not transfer."),
 k13("airline", "Add my husband as a third passenger on reservation G4TK8S.", "no", "refused_list", "S31-S32: the number of passengers cannot change, even a human cannot help -> deny."),
 k13("airline", "Please drop one passenger from reservation B7RF3Y, my friend can't come anymore.", "no", "refused_list", "S31-S32: no change of passenger count -> deny."),
 # hard no: human request with an in-scope task (6)
 k13("retail", "Can I talk to a human? I need to return the headphones from order #W7310592.", "no", "human_plus_in_scope", "Human ask counts only by the task; returns are a retail tool."),
 k13("retail", "Transfer me to an agent please, I just want to update my default shipping address.", "no", "human_plus_in_scope", "modify_user_address does it; in scope."),
 k13("retail", "I'd rather speak to a person. What's the status of order #W4182706?", "no", "human_plus_in_scope", "Order info is in scope after authentication (get_order_details)."),
 k13("airline", "Get me a human agent, I need to cancel reservation D9HQ5L because my plans changed.", "no", "human_plus_in_scope", "cancel_reservation is a tool; the human ask does not count."),
 k13("airline", "I want a live person. I'd like to book a one-way flight from Seattle to Miami on June 2.", "no", "human_plus_in_scope", "Booking is in scope (search + book_reservation)."),
 k13("airline", "Connect me to a human, I need to add a checked bag to reservation M2CU8W.", "no", "human_plus_in_scope", "Adding bags is update_reservation_baggages; in scope."),
 # hard no: asks nothing new (5)
 k13("retail", "My zip code is 30318.", "no", "asks_nothing_new", "Only gives a detail; a message that asks for nothing new is no."),
 k13("retail", "#W6093517", "no", "asks_nothing_new", "Only an order id; asks for nothing new."),
 k13("airline", "Yes, that's right.", "no", "asks_nothing_new", "Only a yes; asks for nothing new."),
 k13("airline", "The reason is a change of plans.", "no", "asks_nothing_new", "Only a reason; asks for nothing new."),
 k13("retail", "The black one, please.", "no", "asks_nothing_new", "Only a choice; asks for nothing new."),
 # hard no: option changes of an item (5)
 k13("retail", "I'd like the desk lamp in my pending order #W5207483 in white instead of black.", "no", "item_option_change", "Same product, different option on a pending order = modify_pending_order_items."),
 k13("retail", "Can I swap the size L t-shirt I got in order #W8341269 for a size M?", "no", "item_option_change", "Delivered item to another option of the same product = exchange tool."),
 k13("retail", "Change the keyboard on my pending order to the version with brown switches.", "no", "item_option_change", "Option change of the same product is in scope."),
 k13("retail", "The sneakers I received are too small, I want them in a 9.5 instead.", "no", "item_option_change", "Exchange to another size of the same product is in scope."),
 k13("retail", "For order #W2758134, switch the backpack to the 30-liter option.", "no", "item_option_change", "Product option change, not a product type change -> tool can do it."),
]

# ---------------- K16v4 ----------------
def k16(msgs, expect, kind, why):
    if isinstance(msgs, str):
        msgs = [msgs]
    return {"domain": "airline", "user_messages": msgs, "expect": expect, "kind": kind, "why": why}

W = "whole_trip_cancel"; P = "part_of_trip"; R = "cancel_with_reason"; I = "indirect_cancel"
K16 = [
 k16("Please cancel my reservation X8PL4D.", "yes", W, "Direct ask to cancel a reservation (Cancel flight section)."),
 k16("I need to cancel my whole trip to Chicago next week.", "yes", W, "Asks to cancel the whole trip."),
 k16("Cancel booking QN2R7E, both flights.", "yes", W, "Imperative cancel of a whole booking."),
 k16("Can you cancel my flight reservation? The number is HT7J3K.", "yes", W, "Request to cancel phrased as a question is still a request."),
 k16("I want to cancel the entire round trip, reservation EK5W9B.", "yes", W, "Whole round trip cancel."),
 k16("Hi, I'd like to call off my trip to Orlando - please cancel the reservation.", "yes", W, "Call off + cancel the reservation."),
 k16("cancel reservation ZM4T8Q pls", "yes", W, "Terse lower-case cancel request."),
 k16("Go ahead and cancel the whole booking for me and my wife.", "yes", W, "Cancel the booking for all passengers."),
 k16("I'd like reservation UD3V6N cancelled in full.", "yes", W, "Passive wording of a cancel request."),
 k16("Could you cancel everything on reservation JS9K2P?", "yes", W, "Cancel everything on a reservation."),
 k16("Please cancel just the return flight on reservation W2HF8M.", "yes", P, "Question counts part of a trip; policy only allows whole-trip cancel but the ask still counts."),
 k16("I only need to cancel the second leg, Denver to Phoenix.", "yes", P, "Cancel one leg = part of the trip."),
 k16("Can you drop the outbound flight but keep my return?", "yes", P, "Drop one flight = partial cancel."),
 k16("Cancel the May 22 flight from my round trip, I'll take the train back.", "yes", P, "Partial cancel of one dated segment."),
 k16("I want to cancel only my part of the trip, the flight out of Atlanta.", "yes", P, "Partial cancel request."),
 k16("Cancel the last segment of my trip, the one into Newark.", "yes", P, "Partial cancel of one segment."),
 k16("I have to cancel reservation R5GB2X - I broke my ankle and can't travel.", "yes", R, "Cancel with a health reason."),
 k16("My company called off the conference, so please cancel my booking.", "yes", R, "Cancel with a change-of-plan reason."),
 k16("The airline cancelled my flight, so I want the whole reservation cancelled.", "yes", R, "Cancel with 'airline cancelled flight' reason."),
 k16("Please cancel my trip, there's a hurricane heading straight for Miami.", "yes", R, "Cancel with a weather reason."),
 k16("Change of plans - cancel reservation KT6Y3H.", "yes", R, "Cancel with change of plans."),
 k16("My daughter has the flu, we need to cancel our family trip.", "yes", R, "Cancel with a passenger illness."),
 k16("I found a cheaper ticket on another airline, so cancel this reservation please.", "yes", R, "Cancel with an 'other' reason."),
 k16("Cancel it, my visa didn't come through in time.", "yes", R, "Cancel with an 'other' reason."),
 k16("I won't be flying anymore, please get rid of the booking.", "yes", I, "Indirect: get rid of the booking = cancel."),
 k16("I'm not going to make that trip after all, can you scrap it?", "yes", I, "Indirect: scrap the trip = cancel."),
 k16("Just void the reservation, I don't need those flights.", "yes", I, "Indirect: void the reservation."),
 k16("Take me off those flights entirely, I'm staying home.", "yes", I, "Indirect: remove the user from the trip."),
 k16("I'm not traveling on the 18th anymore. Please undo the booking and refund what you can.", "yes", I, "Indirect: undo the booking."),
 k16("Please release my seats on reservation NC4Q7V, the trip is off.", "yes", I, "Indirect: release the seats, trip off."),
 # hard no: rules questions (8)
 k16("What's your cancellation policy for basic economy tickets?", "no", "rules_question", "Question about the rules without asking to cancel."),
 k16("If I cancelled reservation P6WZ3D, would I get a full refund?", "no", "rules_question", "Hypothetical refund question, no cancel ask."),
 k16("Am I still inside the 24-hour window to cancel for free?", "no", "rules_question", "Asks about the 24-hour rule only."),
 k16("Does travel insurance cover cancelling because of a sick child?", "no", "rules_question", "Asks about insurance conditions, not to cancel."),
 k16("Can business class tickets be cancelled at any time?", "no", "rules_question", "Rules question."),
 k16("How long does a refund take after a cancellation?", "no", "rules_question", "Rules question about refund timing."),
 k16("Hypothetically, if you cancel my flight, can I then cancel my booking and get my money back?", "no", "rules_question", "Hypothetical rules question."),
 k16("Before I decide anything, what would I lose if I cancelled my trip?", "no", "rules_question", "Asks consequences only; no decision to cancel."),
 # hard no: change requests (8)
 k16("I'd like to move my flight to May 25 instead.", "no", "change_request", "Flight change, not a cancel."),
 k16("Can you change reservation HM3T9E to business class?", "no", "change_request", "Cabin change, not a cancel."),
 k16("Please add one checked bag to my booking.", "no", "change_request", "Baggage change."),
 k16("I need to fix the spelling of my last name on the reservation.", "no", "change_request", "Passenger detail change."),
 k16("Instead of cancelling, can I switch to the evening flight?", "no", "change_request", "Mentions cancelling but asks for a change instead."),
 k16("Swap my return flight for the one that leaves at 6 pm.", "no", "change_request", "Flight change."),
 k16("Change the passenger on my booking from my sister to my brother.", "no", "change_request", "Passenger change (same count)."),
 k16("I want to rebook onto a nonstop flight on the same day.", "no", "change_request", "Rebook = change, not cancel."),
 # hard no: refund status (7)
 k16("I cancelled reservation S8KF2R last week, when will I see the refund?", "no", "refund_status", "Cancel already done; asks refund timing only."),
 k16("Where's my refund for the cancelled trip? It's been 8 days.", "no", "refund_status", "Refund status question."),
 k16("You cancelled my flight on Monday and I still haven't been refunded.", "no", "refund_status", "Refund status, no new cancel ask."),
 k16("Has the refund from my cancellation gone back to my Visa yet?", "no", "refund_status", "Refund status."),
 k16("Can you check whether the refund for my cancelled booking was processed?", "no", "refund_status", "Refund status."),
 k16("The trip was already cancelled; I just want to know which card the money goes back to.", "no", "refund_status", "Refund method question after a cancel."),
 k16("Is my cancellation refund showing as pending or completed?", "no", "refund_status", "Refund status."),
 # hard no: asks nothing new (7)
 k16("Yes.", "no", "asks_nothing_new", "Only a yes; asks for nothing new."),
 k16("My user id is lucia_brandt_5172.", "no", "asks_nothing_new", "Only an id."),
 k16("The reservation number is YB7N2C.", "no", "asks_nothing_new", "Only a reservation id."),
 k16("May 19.", "no", "asks_nothing_new", "Only a date."),
 k16("The Mastercard.", "no", "asks_nothing_new", "Only a choice."),
 k16("Thanks, that's all.", "no", "asks_nothing_new", "Only a thank-you."),
 k16("It's booked under my email, mila.ostrowski41@example.com.", "no", "asks_nothing_new", "Only gives an email."),
]

# ---------------- K17v4 ----------------
def k17(A, B, expect, kind, why, earlier=None):
    d = {"A": A, "B": B}
    if earlier is not None:
        d["earlier_outside_span"] = earlier
    d.update({"expect": expect, "kind": kind, "why": why})
    return d

# p7 fix: the three cases that used the few-shot's agent text ("Would you like to add travel insurance for $30 per
# passenger?") got new made-up agent texts, so no case equals or nearly equals a K17 few-shot
# (check: scripts/v4_cases_gen/check_fewshot_overlap.py).
K17 = [
 # added: one-word yes (6)
 k17("Before I finalize the reservation, do you want travel insurance? It costs $30 per traveler and covers health or weather cancellations.", "Yes.", "added", "yes_to_question", "A asks about insurance and B answers yes -> that is the choice (policy: ask if the user wants insurance)."),
 k17("Travel insurance is $30 per passenger and gives a full refund if you need to cancel for health or weather reasons. Do you want it?", "Yep.", "added", "yes_to_question", "Yes answer to the insurance question."),
 k17("Do you want to buy travel insurance for both passengers? That would be $60 total.", "sure", "added", "yes_to_question", "Yes answer to the insurance question."),
 k17("One more thing before I book: would you like travel insurance on this reservation?", "Yes please.", "added", "yes_to_question", "Yes answer to the insurance question."),
 k17("Should I include travel insurance at $30 each for the three travelers?", "Yeah.", "added", "yes_to_question", "Yes answer to the insurance question."),
 k17("Would you like to protect this trip with travel insurance ($30 per passenger)?", "Definitely.", "added", "yes_to_question", "Yes answer to the insurance question."),
 # added: "add the insurance" (5)
 k17("", "Book the 9 am economy flight to Dallas for me and add the travel insurance.", "added", "add_the_insurance", "User asks for insurance on this booking."),
 k17("I found two economy options on May 24: the 8:10 departure at $212 and the 13:45 at $189.", "I'll take the 13:45 one, and please add insurance for both of us.", "added", "add_the_insurance", "User wants insurance included."),
 k17("", "Include the travel insurance too, I want to be covered in case I get sick.", "added", "add_the_insurance", "User asks to include insurance."),
 k17("Is there anything else you'd like on this booking?", "Yes, throw in the travel insurance.", "added", "add_the_insurance", "User adds insurance."),
 k17("", "I want coverage on this one - put the $30 insurance on each passenger.", "added", "add_the_insurance", "Coverage wanted = added."),
 # added: listing says included + go ahead (5)
 k17("Here is the booking: one way from JFK to SFO on May 21, economy, 1 passenger (Ines Darrow), 1 free checked bag, travel insurance: yes ($30). Total $342 charged to your credit card ending 5521. Shall I proceed?", "Go ahead.", "added", "listing_included_go_ahead", "Listing includes insurance and the user agrees -> added."),
 k17("To confirm: round trip ORD to MIA, May 26 out and May 30 back, business class, 2 passengers, travel insurance included for both ($60). Total $1,904 on gift card ending 4410. Do you want me to book it?", "Yes, book it.", "added", "listing_included_go_ahead", "Insurance in the listing + yes."),
 k17("Booking summary: LAX to SEA, May 19, basic economy, passengers Rafe Ondine and Kit Ondine, 0 checked bags, with travel insurance ($30 x 2). Please confirm.", "Confirmed.", "added", "listing_included_go_ahead", "Insurance listed + confirm."),
 k17("I'll book the one-stop via Denver on May 27, economy, 1 passenger, with travel insurance, paid by your travel certificate. Is that all correct?", "That's correct, please continue.", "added", "listing_included_go_ahead", "Insurance in the proposal + go-ahead."),
 k17("Final details: one way BOS to ATL, May 23, economy, 3 passengers, 2 extra bags ($100), travel insurance added ($90). Total $801. Proceed?", "proceed", "added", "listing_included_go_ahead", "Insurance added in listing + proceed."),
 # not_added: one-word no (5)
 k17("Would you care to buy travel insurance for this flight? It's an extra $30 for each passenger.", "No.", "not_added", "no_to_question", "A asks and B answers no -> declined."),
 k17("Do you want travel insurance on this flight? It's $30 per person.", "Nope.", "not_added", "no_to_question", "No answer to the insurance question."),
 k17("Shall I add travel insurance for the two of you?", "Nah.", "not_added", "no_to_question", "No answer to the insurance question."),
 k17("Would you like travel insurance, which allows a full refund for health or weather cancellations?", "Pass.", "not_added", "no_to_question", "'Pass' declines the offer."),
 k17("Any interest in travel insurance for this reservation?", "No thanks.", "not_added", "no_to_question", "No answer to the insurance question."),
 # not_added: "no thanks, skip it" (5)
 k17("Would you like to add travel insurance for $30 per passenger?", "No thanks, skip the insurance.", "not_added", "skip_it", "Explicit decline."),
 k17("Travel insurance is available at $30 per traveler. Would you like it?", "I'll pass on the insurance this time.", "not_added", "skip_it", "Explicit decline."),
 k17("", "Don't need insurance, just book the cheapest economy flight.", "not_added", "skip_it", "User says insurance not wanted."),
 k17("Should I add insurance to protect the trip?", "Skip it, I never buy that stuff.", "not_added", "skip_it", "Decline of the insurance question."),
 k17("", "No insurance for us, thanks - book the 7:30 flight.", "not_added", "skip_it", "User declines insurance up front."),
 # not_added: listing says no insurance + go ahead (4)
 k17("Here's what I'll book: one way PHX to DEN, May 20, economy, 1 passenger, 1 free bag, no travel insurance. Total $156 on your credit card ending 7302. Shall I go ahead?", "Yes, book it.", "not_added", "listing_no_insurance_go_ahead", "Listing says no insurance and the user agrees."),
 k17("Summary: round trip SFO to LAS, business, 2 passengers, travel insurance: not included. Total $1,120. Please confirm.", "That's correct, go ahead.", "not_added", "listing_no_insurance_go_ahead", "Not included + go-ahead."),
 k17("I'll book the 16:05 flight to Houston for you, economy, without travel insurance, paid with your gift card. OK?", "OK.", "not_added", "listing_no_insurance_go_ahead", "Without insurance + OK."),
 k17("Booking details: MSP to DTW on May 29, basic economy, 1 passenger, travel insurance declined, total $98. Confirm?", "Confirm.", "not_added", "listing_no_insurance_go_ahead", "Declined in listing + confirm."),
 # hard: question with no reply -> not_said (6)
 k17("Do you want me to include travel insurance? The price is $30 for every passenger on the booking.", "", "not_said", "question_no_reply", "A question about insurance with no answer is not_said."),
 k17("Do you want travel insurance for the two passengers? It's $30 each.", "", "not_said", "question_no_reply", "No reply yet -> not_said."),
 k17("Last question: should I add travel insurance?", "", "not_said", "question_no_reply", "Unanswered insurance question."),
 k17("Would you like travel insurance on this booking ($30 per person)?", "Wait, how many checked bags can I bring in economy?", "not_said", "question_no_reply", "Reply ignores the insurance question -> no answer -> not_said."),
 k17("Before I finalize, would you like to add travel insurance?", "Actually, can we look at the afternoon flights first?", "not_said", "question_no_reply", "User changes topic; insurance not answered."),
 k17("Do you want to protect this trip with travel insurance?", "Hmm, what's the total so far without extras?", "not_said", "question_no_reply", "Asks about the total, not a choice on insurance."),
 # hard: user asks the price only -> not_said (6)
 k17("Would you like to add travel insurance to this booking?", "How much is the insurance?", "not_said", "price_question_only", "A price question is not a choice."),
 k17("Do you want travel insurance?", "Is that per person or for the whole booking?", "not_said", "price_question_only", "Price-basis question only."),
 k17("Should I add travel insurance for the family?", "What would that add to the total for two adults and a child?", "not_said", "price_question_only", "Asks the cost only."),
 k17("", "And the travel insurance costs how much again?", "not_said", "price_question_only", "Price question with no choice."),
 k17("Travel insurance is optional for this booking. Would you like it?", "Before I decide, what does it cost?", "not_said", "price_question_only", "User says they have not decided."),
 k17("Would you like insurance on the flights?", "How much would it be for three of us, roughly?", "not_said", "price_question_only", "Price question only."),
 # hard: yes to booking but "without the insurance" -> not_added (6)
 k17("I can book the 10:20 economy flight from Austin to Nashville on May 22 for $174. Would you like travel insurance as well, and shall I go ahead?", "Yes, book it, but without the insurance.", "not_added", "yes_but_without_insurance", "Yes covers the booking; insurance explicitly excluded."),
 k17("Shall I book the round trip for both of you? I can also add travel insurance at $30 each.", "Go ahead - no insurance though.", "not_added", "yes_but_without_insurance", "Go-ahead with insurance excluded."),
 k17("Here are the flights: IAH to ORD May 25, return May 28, economy. Want me to book them, and would you like insurance?", "Confirm the flights, leave off the insurance.", "not_added", "yes_but_without_insurance", "Booking yes, insurance no."),
 k17("I'll reserve the 6:45 nonstop to Boston, economy, 1 passenger. Insurance is available for $30. Ready to book?", "Sounds good, minus the travel insurance.", "not_added", "yes_but_without_insurance", "Agrees to booking minus insurance."),
 k17("Everything is ready: one way to Seattle, May 30, basic economy. Shall I book, and do you want travel insurance?", "Book it. I don't want the insurance.", "not_added", "yes_but_without_insurance", "Booking yes, insurance not wanted."),
 k17("Shall I go ahead with the business class booking for three passengers, with or without travel insurance?", "Yes to everything except the insurance.", "not_added", "yes_but_without_insurance", "All yes except insurance."),
 # hard: listing says insurance + user removes it -> not_added (6)
 k17("Booking summary: DFW to LGA, May 21, economy, 2 passengers, travel insurance: yes ($60). Total $618. Shall I proceed?", "Actually take the insurance off, then go ahead.", "not_added", "listing_insurance_user_removes", "User removes insurance listed by the agent."),
 k17("To confirm: one way SAN to PDX, May 24, business, 1 passenger, with travel insurance ($30). OK to book?", "Everything is right except I don't want insurance after all.", "not_added", "listing_insurance_user_removes", "User drops the listed insurance."),
 k17("Here's the plan: round trip to Denver, economy, 2 passengers, insurance included ($60), paid by credit card ending 9184. Proceed?", "Remove the insurance and book it.", "not_added", "listing_insurance_user_removes", "Remove insurance + book."),
 k17("I'll book CLT to MCO on May 26 for 4 passengers with travel insurance ($120). Confirm?", "Hmm, drop the insurance - I'll take my chances. Then yes.", "not_added", "listing_insurance_user_removes", "Insurance removed, rest confirmed."),
 k17("Final: basic economy, May 19, one passenger, travel insurance added. Total $129. Shall I book?", "Can you redo it without insurance? Then yes.", "not_added", "listing_insurance_user_removes", "User asks the booking without insurance."),
 k17("Booking: ATL to BOS, May 23, economy, 2 passengers, 2 bags, travel insurance $60. Total $504. Go ahead?", "Let's not do the insurance. The rest is fine.", "not_added", "listing_insurance_user_removes", "Insurance taken out, rest accepted."),
 # hard: insurance asked for another booking earlier (window edge) (6)
 k17("Your Boston trip is booked. For the second trip: one way to Denver on May 28, economy, 1 passenger, paid by the same card. Shall I book it?", "Yes.", "not_said", "window_edge_other_booking",
     "Insurance yes belonged to the earlier booking (before the last worked write); this span says nothing about insurance.",
     [{"role": "agent", "text": "Would you like travel insurance on the Boston booking?"}, {"role": "user", "text": "Yes, add it."}, {"role": "tool", "text": "book_reservation -> success (reservation TQ5W8D, insurance yes)"}, {"role": "user", "text": "Great. Now I need a second trip."}]),
 k17("For the return booking on May 31, would you like travel insurance?", "Yes, for this one I want it.", "added", "window_edge_other_booking",
     "Earlier booking declined insurance, but the choice in this span is yes for the new booking.",
     [{"role": "user", "text": "No insurance on the outbound, thanks."}, {"role": "tool", "text": "book_reservation -> success (reservation NV3K6S, insurance no)"}, {"role": "user", "text": "Now please book my return as a separate reservation."}]),
 k17("Do you want travel insurance on this new booking too?", "No, not this time.", "not_added", "window_edge_other_booking",
     "Earlier booking had insurance; in this span the user declines for the new booking.",
     [{"role": "agent", "text": "Shall I add travel insurance ($30)?"}, {"role": "user", "text": "Yes please."}, {"role": "tool", "text": "book_reservation -> success (reservation PL8F2C, insurance yes)"}, {"role": "user", "text": "Thanks. Can you book another flight for my next trip?"}]),
 k17("Booking for your trip to Phoenix: May 27, economy, 1 passenger, total $203. Shall I proceed?", "Go ahead.", "not_said", "window_edge_other_booking",
     "Insurance 'no' was for the earlier booking; this listing does not say anything about insurance.",
     [{"role": "user", "text": "Skip the insurance."}, {"role": "tool", "text": "book_reservation -> success (reservation GB6M4R, insurance no)"}, {"role": "user", "text": "Okay, one more booking please, to Phoenix."}]),
 k17("", "Now book my sister's flight on the same date, same cabin.", "not_said", "window_edge_other_booking",
     "Earlier insurance yes is outside the span; 'same cabin' says nothing about insurance.",
     [{"role": "agent", "text": "Would you like insurance?"}, {"role": "user", "text": "Yes."}, {"role": "tool", "text": "book_reservation -> success (reservation XW2H7J, insurance yes)"}, {"role": "user", "text": "Perfect, that one's done."}]),
 k17("Here's the second booking: SEA to SFO, May 22, economy, 1 passenger, travel insurance: no. Shall I book?", "Confirmed.", "not_added", "window_edge_other_booking",
     "User added insurance on the earlier booking; this span lists no insurance and the user confirms.",
     [{"role": "user", "text": "Add the insurance to that one."}, {"role": "tool", "text": "book_reservation -> success (reservation DK9P3V, insurance yes)"}, {"role": "user", "text": "Now the Seattle to San Francisco one."}]),
]

# ---------------- K18v4 ----------------
NLN = ("no longer needed", "the user does not need or want the item any more")
OBM = ("ordered by mistake", "the order was placed by accident or is not what the user meant to order")
def k18(rs, speaker, A, expect, kind, why):
    return {"reason": rs[0], "gloss": rs[1], "speaker": speaker, "A": A, "expect": expect, "kind": kind, "why": why}

K18 = [
 # yes: paraphrases of no longer needed (12)
 k18(NLN, "user", "I don't need the blender anymore, please cancel order #W3905128.", "yes", "paraphrase_no_longer_needed", "Cancel reason 'no longer needed' in other words (policy: reason must be one of two)."),
 k18(NLN, "user", "Turns out I won't be using it, so I'd like to cancel.", "yes", "paraphrase_no_longer_needed", "Will not use it = not needed."),
 k18(NLN, "user", "My sister already gave me one, so I have no use for this order now.", "yes", "paraphrase_no_longer_needed", "No use for it = not needed."),
 k18(NLN, "user", "Cancel it - I changed my mind and don't want the headphones now.", "yes", "paraphrase_no_longer_needed", "Does not want it any more."),
 k18(NLN, "user", "The project I bought these cables for got scrapped, so I don't need them.", "yes", "paraphrase_no_longer_needed", "Does not need the items."),
 k18(NLN, "user", "We already picked up a coffee maker locally, so this one isn't needed.", "yes", "paraphrase_no_longer_needed", "Not needed any more."),
 k18(NLN, "user", "I no longer want it, please cancel.", "yes", "paraphrase_no_longer_needed", "Does not want it any more."),
 k18(NLN, "user", "The camping trip is off, so I have no need for the tent anymore.", "yes", "paraphrase_no_longer_needed", "No need any more."),
 k18(NLN, "user", "It's not necessary anymore, so go ahead and cancel order #W6627041.", "yes", "paraphrase_no_longer_needed", "Not necessary = not needed."),
 k18(NLN, "user", "Please cancel, I don't want the jacket any longer.", "yes", "paraphrase_no_longer_needed", "Does not want it any longer."),
 k18(NLN, "user", "Ended up not needing it after all.", "yes", "paraphrase_no_longer_needed", "Not needing it."),
 k18(NLN, "user", "My old monitor got repaired, so I don't require the new one anymore.", "yes", "paraphrase_no_longer_needed", "Does not require it any more."),
 # yes: paraphrases of ordered by mistake (12)
 k18(OBM, "user", "I placed that order by accident, please cancel it.", "yes", "paraphrase_ordered_by_mistake", "By accident = ordered by mistake."),
 k18(OBM, "user", "I hit the buy button twice, so the second order shouldn't exist.", "yes", "paraphrase_ordered_by_mistake", "Accidental duplicate order."),
 k18(OBM, "user", "I meant to get the blue one but picked red without noticing, so cancel it.", "yes", "paraphrase_ordered_by_mistake", "Not what the user meant to order."),
 k18(OBM, "user", "Accidentally ordered it, didn't mean to.", "yes", "paraphrase_ordered_by_mistake", "Accidental order."),
 k18(OBM, "user", "My kid tapped purchase on my phone without me knowing, I never meant to buy this.", "yes", "paraphrase_ordered_by_mistake", "Placed by accident, not intended."),
 k18(OBM, "user", "Oops, wrong model - that was a misclick on my part.", "yes", "paraphrase_ordered_by_mistake", "Misclick = placed by accident."),
 k18(OBM, "user", "I ordered the wrong size by accident.", "yes", "paraphrase_ordered_by_mistake", "Not what the user meant to order."),
 k18(OBM, "user", "That order wasn't intentional, please cancel #W1840573.", "yes", "paraphrase_ordered_by_mistake", "Unintentional order."),
 k18(OBM, "user", "I bought it in error.", "yes", "paraphrase_ordered_by_mistake", "In error = by mistake."),
 k18(OBM, "user", "I mistakenly purchased the wrong vacuum.", "yes", "paraphrase_ordered_by_mistake", "Mistakenly purchased = ordered by mistake."),
 k18(OBM, "user", "This is a duplicate I didn't mean to place.", "yes", "paraphrase_ordered_by_mistake", "Unintended duplicate."),
 k18(OBM, "user", "I picked the wrong item at checkout, cancel it please.", "yes", "paraphrase_ordered_by_mistake", "Not what the user meant to order."),
 # yes: said by the agent in a listing (6)
 k18(NLN, "agent", "To confirm: cancel order #W7158326 (Desk Lamp, Water Bottle) because you don't need the items anymore. The refund goes to your original PayPal. Shall I proceed?", "yes", "agent_listing", "Agent listing states the reason in other words."),
 k18(NLN, "agent", "I'll cancel pending order #W2934610 for the Bluetooth Speaker since you have no further use for it. Refund to your credit card in 5-7 business days. Please confirm.", "yes", "agent_listing", "No further use = not needed."),
 k18(NLN, "agent", "Here are the details: order #W5401872, reason: you won't be using the items. Refund to gift card immediately. Confirm (yes)?", "yes", "agent_listing", "Won't be using = not needed."),
 k18(OBM, "agent", "To confirm: cancel order #W8063517 since it was placed accidentally. Refund to your Visa in 5-7 business days. Shall I go ahead?", "yes", "agent_listing", "Placed accidentally = ordered by mistake."),
 k18(OBM, "agent", "I'll cancel #W3378209 (Running Shoes) as an unintended purchase. Refund to your gift card right away. Is that right?", "yes", "agent_listing", "Unintended purchase = ordered by mistake."),
 k18(OBM, "agent", "Cancellation summary: order #W6915044, reason: you selected the wrong item when ordering. Refund to the original payment method. Proceed?", "yes", "agent_listing", "Wrong item selected = not what the user meant to order."),
 # hard no: other reasons (12)
 k18(NLN, "user", "It's way too expensive, I want to cancel.", "no", "other_reason", "Price is not one of the two allowed reasons."),
 k18(OBM, "user", "Delivery is taking forever, just cancel it.", "no", "other_reason", "Delivery time is another reason."),
 k18(NLN, "user", "I found the same keyboard $20 cheaper at another store.", "no", "other_reason", "Found cheaper is another reason."),
 k18(OBM, "user", "I read a bunch of bad reviews about this vacuum, so cancel the order.", "no", "other_reason", "Bad reviews is another reason."),
 k18(OBM, "user", "I want to pay with a different card, so cancel it and I'll reorder.", "no", "other_reason", "Payment wish is another reason, not a mistaken order."),
 k18(NLN, "user", "The estimated arrival is after my trip, so cancel it.", "no", "other_reason", "Delivery date is another reason."),
 k18(NLN, "user", "The shipping fee is higher than I expected, please cancel.", "no", "other_reason", "Cost is another reason."),
 k18(OBM, "user", "I'd rather buy it in person at the store, cancel this one.", "no", "other_reason", "Preference to buy in store is another reason."),
 k18(NLN, "agent", "To confirm: cancel order #W4729851 because the delivery date is too late for you. Refund to your PayPal. Proceed?", "no", "other_reason", "Agent states a delivery reason, not 'no longer needed'."),
 k18(OBM, "user", "The color in the latest photos looks different from what I expected, so cancel it.", "no", "other_reason", "Look of the product is another reason."),
 k18(NLN, "user", "I'm not comfortable with the warranty terms, cancel the order please.", "no", "other_reason", "Warranty concern is another reason."),
 k18(OBM, "agent", "I'll cancel order #W9306184 because you found a better price elsewhere. Refund in 5-7 business days. Confirm?", "no", "other_reason", "Agent states 'found cheaper', not a mistaken order."),
 # hard no: the other allowed reason (8)
 k18(NLN, "user", "I clicked order by accident, please cancel.", "no", "other_allowed_reason", "Accidental order is 'ordered by mistake', not 'no longer needed'."),
 k18(NLN, "user", "I ordered the wrong color without meaning to.", "no", "other_allowed_reason", "Wrong order = the other allowed reason."),
 k18(NLN, "agent", "To confirm: cancel order #W5182739 because it was placed by accident. Refund to your Mastercard. Proceed?", "no", "other_allowed_reason", "Agent gives the other allowed reason."),
 k18(NLN, "user", "That purchase was a slip of the finger.", "no", "other_allowed_reason", "Accidental purchase = the other reason."),
 k18(OBM, "user", "I just don't need it anymore.", "no", "other_allowed_reason", "Not needing it is 'no longer needed', not a mistaken order."),
 k18(OBM, "user", "We got one as a gift, so we have no use for it now.", "no", "other_allowed_reason", "No use any more = the other reason."),
 k18(OBM, "agent", "I'll cancel order #W2067418 since you won't be using the items anymore. Refund to your gift card right away. Confirm?", "no", "other_allowed_reason", "Agent gives the other allowed reason."),
 k18(OBM, "user", "I changed my mind, I don't want it any more.", "no", "other_allowed_reason", "No longer wanted, not ordered by mistake."),
 # hard no: no reason (10)
 k18(NLN, "user", "Please cancel order #W6740215.", "no", "no_reason", "Only asks to cancel; no reason given."),
 k18(OBM, "user", "Cancel it.", "no", "no_reason", "No reason given."),
 k18(NLN, "user", "Yes, cancel the order.", "no", "no_reason", "Only a yes; no reason."),
 k18(OBM, "user", "Can you cancel the pending order with the speaker in it?", "no", "no_reason", "Cancel request, no reason."),
 k18(NLN, "agent", "I'll cancel order #W8519306 (Bluetooth Speaker). The refund goes to your Mastercard in 5-7 business days. Confirm?", "no", "no_reason", "Agent listing has no reason."),
 k18(OBM, "user", "The order id is #W4093761.", "no", "no_reason", "Only an id."),
 k18(NLN, "user", "I want to cancel - how long does the refund take?", "no", "no_reason", "Cancel + refund question; no reason."),
 k18(OBM, "agent", "Could you tell me why you'd like to cancel this order?", "no", "no_reason", "Agent asks for the reason; none given."),
 k18(NLN, "user", "Cancel my order for the bike helmet, thanks.", "no", "no_reason", "No reason given."),
 k18(OBM, "user", "I need to cancel it, long story.", "no", "no_reason", "Declines to give a reason."),
]

write("K13.jsonl", "K13v4", K13)
write("K16.jsonl", "K16v4", K16)
write("K17.jsonl", "K17v4", K17)
write("K18.jsonl", "K18v4", K18)

from collections import Counter
for n, cs in [("K13", K13), ("K16", K16), ("K17", K17), ("K18", K18)]:
    print(n, len(cs), dict(Counter(c["expect"] for c in cs)))
    print("  ", dict(Counter(c["kind"] for c in cs)))
