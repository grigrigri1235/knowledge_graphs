import json, sys
OUT = sys.argv[1]
C = []
def y(kind, A, B, action, why, **kw):
    C.append(dict(A=A, B=B, action=action, expect="yes", kind=kind, why=why, **kw))
def n(kind, A, B, action, why, **kw):
    C.append(dict(A=A, B=B, action=action, expect="no", kind=kind, why=why, **kw))

# ---------------- YES ----------------
K = "bare_yes"
y(K, "Here's what I'll do: cancel order #W4817350 (Bluetooth Speaker, Desk Lamp) with the reason 'no longer needed'. The refund of $214.37 goes back to your PayPal in 5-7 business days. Do you want me to proceed?",
  ["yes"], "cancel_pending_order #W4817350", "Retail: list the action, get explicit yes; a bare yes is a go-ahead.")
y(K, "To confirm: I'll add 2 checked bags to reservation K7Q2MZ, so the total will be 4 bags. The 2 extra bags cost $100, charged to your Visa ending 4471. Shall I go ahead?",
  ["Yep."], "update_reservation_baggages K7Q2MZ", "Airline: details listed, user says yep = explicit yes.")
y(K, "I'll change the shipping address on order #W6203984 to 418 Larkspur Lane, Apt 3, Tucson, AZ 85719, USA. Please confirm (yes) and I'll update it.",
  ["Yes please"], "modify_pending_order_address #W6203984", "Bare yes to a listed address change.")
y(K, "Booking summary: one-way JFK to SEA on 2024-05-22, flight HAT512, economy, passenger Teodora Vasquez-Lind (DOB 1991-03-08), 1 free checked bag, no travel insurance. Total $187 on your gift card ending 7730. Confirm to book?",
  ["Confirmed."], "book_reservation for user teodora_lind_5520, flight HAT512", "Booking details listed; 'Confirmed' is an explicit yes.")
y(K, "I'm ready to return the Running Shoes (item 8301947265) from order #W5530912. The refund of $139.99 will go to your original Mastercard. Is that ok?",
  ["Sounds good!"], "return_delivered_order_items #W5530912 Running Shoes", "'Sounds good' agrees to the listed return.")

K = "goahead_no_yes_word"
y(K, "I can cancel reservation P3XN8D (ORD to MIA on May 28, business). The full $1,240 will be refunded to your original credit card within 5-7 business days. Would you like me to cancel it?",
  ["Please do that, I won't be making the trip."], "cancel_reservation P3XN8D", "Go-ahead in other words ('please do that') counts.")
y(K, "Exchange details for order #W7128845: Wireless Earbuds (black) -> Wireless Earbuds (white, item 5528190374). The new item is $5 cheaper, so $5 goes back to your gift card. Shall I submit the exchange?",
  ["Go for it, white is what I wanted in the first place."], "exchange_delivered_order_items #W7128845 Wireless Earbuds", "'Go for it' is a clear go-ahead without the word yes.")
y(K, "New itinerary for reservation T9LWE2: HAT447 on May 20 and HAT618 on May 27, economy, same two passengers. The fare difference of $64 goes on your Mastercard ending 2290. OK to change?",
  ["That's exactly right, lock it in."], "update_reservation_flights T9LWE2 HAT447 HAT618", "'Lock it in' tells the agent to go ahead.")
y(K, "I'll switch the payment for order #W3391027 from your PayPal to your Visa ending 6618. Want me to make the change?",
  ["Please switch it over."], "modify_pending_order_payment #W3391027", "User restates the switch as a request = go-ahead.")
y(K, "Item change on order #W8812306: Coffee Maker (12-cup, black) -> Coffee Maker (12-cup, stainless, item 4427709813). Price difference $12 charged to PayPal. This can be done only once. Shall I proceed?",
  ["Make the change, thanks."], "modify_pending_order_items #W8812306 Coffee Maker", "Imperative 'make the change' is a go-ahead.")

K = "batch_goahead"
y(K, "Here is the plan: 1) cancel order #W2045718 (reason: ordered by mistake), 2) cancel order #W2045799 (reason: ordered by mistake). Both refunds go back to your gift card right away. Should I go ahead with both?",
  ["Yes to both, please."], "cancel_pending_order #W2045799", "One go-ahead for a listed batch covers each action (D2/L1.6).")
y(K, "For reservation MZ4R8T I'll (1) upgrade both flights, HAT455 and HAT471, to business for $620 total, and (2) add 1 checked bag, which is free with the business allowance. Payment: your credit card ending 9925. Do you want both changes?",
  ["Both, please go ahead."], "update_reservation_baggages MZ4R8T", "Batch of 2 actions on one reservation; one go-ahead covers the bag change.")
y(K, "I'll do two things: return the Yoga Mat (item 6610394827) from order #W9013374 with the refund to your original PayPal, and exchange the Water Bottle in order #W9013382 from 500ml to 750ml (item 3378216094), no price difference. Confirm both?",
  ["Yes, do both of them"], "exchange_delivered_order_items #W9013382 Water Bottle", "Batch over 2 orders; 'do both' covers the exchange.")
y(K, "Here's what I'll update on reservation 2HKV9P: replace passenger Amara Okonkwo-Hale with Lucien Ferraby (DOB 1987-11-02), and add 2 checked bags (total 3) for $100 on your gift card ending 3318. Is all of that right?",
  ["All of that is correct, go ahead with everything."], "update_reservation_passengers 2HKV9P", "Go-ahead 'with everything' covers the passenger update in the list.")
y(K, "Summary for order #W5179026: (a) new shipping address 77 Wexford Ct, Boise, ID 83702; (b) payment switched to your gift card ending 4410 (the $88 balance covers the $61.50 total); (c) Hoodie size M -> size L (item 9014627385). The item change can only be done once. Proceed with all three?",
  ["Go ahead with all three."], "modify_pending_order_payment #W5179026", "Batch of 3 on one order; one go-ahead covers the payment change.")

K = "yes_plus_unrelated"
y(K, "I'll cancel order #W1180462 (Electric Toothbrush) for the reason 'no longer needed'. The $49.99 refund goes to your Visa in 5-7 business days. Shall I go ahead?",
  ["Yes, go ahead. By the way, this chat is a lot quicker than the phone line was last time."], "cancel_pending_order #W1180462", "Clear yes; the remark about the chat is unrelated.")
y(K, "Reservation 5JWC7X: I'll change both flights to HAT563 (May 24) and HAT579 (May 30), economy, fare difference $38 on your Mastercard ending 0472. Confirm?",
  ["Yes please. My daughter will be so happy, she's been counting down the days to this trip."], "update_reservation_flights 5JWC7X HAT563 HAT579", "Yes plus a personal comment is still a go-ahead.")
y(K, "Return request for order #W8427015: Throw Pillow x2 (items 1736059428 and 1736059436), refund of $58.00 to your original PayPal. You'll get an email with return steps. Ok to submit?",
  ["Yeah that's fine. Separately, I really like the new look of your website."], "return_delivered_order_items #W8427015 Throw Pillow", "Agreement plus unrelated praise.")

K = "restated_instruction"
y(K, "Order #W6650213 is still pending, so I can cancel it. You mentioned you ordered it by mistake, so I'll use 'ordered by mistake' as the reason. Would you like me to cancel it?",
  ["Cancel it for that reason."], "cancel_pending_order #W6650213", "User restates the action as an instruction.")
y(K, "Reservation 8FJQ3W has travel insurance and you're cancelling for a health reason, so it qualifies. The $410 goes back to the original card in 5-7 business days. Should I cancel it?",
  ["Cancel the reservation and send the refund to the card."], "cancel_reservation 8FJQ3W", "Instruction restating the proposed cancel.")
y(K, "I can return the Electric Kettle (item 7742019386) from order #W1847760 with the $54.20 refund going to your gift card ending 2287. Please confirm.",
  ["Return the kettle and put the money on the gift card."], "return_delivered_order_items #W1847760 Electric Kettle", "Restated instruction matching the listed method.")

K = "goahead_later_B_after_aside"
y(K, "Reservation Z4MH6E (BOS to ATL, May 26, business) can be cancelled for a full refund of $930 to your original credit card. Would you like me to cancel it?",
  ["How long does the refund take?", "Ok, then go ahead and cancel it."], "cancel_reservation Z4MH6E",
  "Window B is every user message up to the call; the 2nd one is the go-ahead.",
  asides=["The refund goes to your original payment method in 5 to 7 business days."])
y(K, "Exchange for order #W3062718: Electric Kettle 1.5L -> 1.7L (item 2805519473), $8 extra charged to your PayPal. Shall I submit it?",
  ["Does the new one come with the same warranty?", "Ah okay, no worries. Submit the exchange."], "exchange_delivered_order_items #W3062718 Electric Kettle",
  "Question answered in an aside, then a clear go-ahead in the 2nd B message.",
  asides=["I'm sorry, I don't have warranty details; I can only see the item options and price."])
y(K, "I'll change the shipping address on order #W7731590 to 2210 Cobblestone Way, Unit 12, Madison, WI 53703, USA. Shall I update it?",
  ["One sec, grabbing my coffee.", "Okay I'm back.", "That address is right, please update it."], "modify_pending_order_address #W7731590",
  "Go-ahead in the 3rd B message after short asides (window edge).",
  asides=["No problem, take your time.", "Welcome back! Just let me know if the address looks right."])
y(K, "Booking summary: round trip LAS-PHL, HAT604 on May 21 and HAT629 on May 28, economy, 2 passengers (Gideon Marlowe-Price and Saskia Marlowe-Price), no insurance, 2 free bags. Total $412 on your Visa ending 5136. Shall I book it?",
  ["Is insurance included in that total?", "Got it, thanks. Book it."], "book_reservation for user gideon_price_8841, flights HAT604 HAT629",
  "After the aside the user says 'Book it' = go-ahead.",
  asides=["No, you chose not to add insurance, so the $412 is the fare only."])

K = "yes_list_action_third"
y(K, "Here's everything: 1. Cancel order #W3302558 (reason: no longer needed). 2. Change the address on order #W3302571 to 905 Harlow St, Dayton, OH 45402. 3. Return the Blender (item 2219048563) from order #W3302590 with the refund to your original Visa. Shall I go ahead?",
  ["Yes, all three."], "return_delivered_order_items #W3302590 Blender", "A yes to the whole list covers its 3rd item.")
y(K, "For reservation QW7D3N: first, change the flights to HAT508 (May 19) and HAT533 (May 24); second, correct passenger Ines Fairbrook's date of birth to 1979-06-14; third, add one checked bag (total 2) for $50 on your Visa ending 1187. Shall I do all of this?",
  ["Yes, please proceed with everything."], "update_reservation_baggages QW7D3N", "Go-ahead for the list includes the 3rd action (bags).")
y(K, "To recap: (1) update your default address to 31 Ridgeback Rd, Fargo, ND 58102; (2) change the shipping address of order #W7405519 to the same; (3) switch the payment of order #W7405519 to your PayPal. I'll do them one at a time once you confirm.",
  ["Yep that's all correct, go ahead."], "modify_pending_order_payment #W7405519", "Yes to the list; the payment switch is the 3rd item.")

K = "authorize"
y(K, "Reservation 3RPT9V: change to HAT482 on May 23, business cabin, same passenger. The difference of $275 will be charged to your credit card ending 6604. Please confirm.",
  ["I authorize the charge and the change."], "update_reservation_flights 3RPT9V HAT482", "'I authorize' is an explicit go-ahead.")
y(K, "Exchange for order #W4950381: Desk Chair black -> gray (item 6639201882), no price difference. Can I go ahead?",
  ["You have my authorization to process this exchange."], "exchange_delivered_order_items #W4950381 Desk Chair", "Authorization phrasing = go-ahead.")

# ---------------- HARD NO ----------------
K = "question_price_refund"
n(K, "I'll cancel order #W2638074 (Air Fryer) for the reason 'ordered by mistake'. Do you want me to proceed?",
  ["Will the refund go back to my card right away or does it take a while?"], "cancel_pending_order #W2638074", "A question about refund timing is not a go-ahead.")
n(K, "I can upgrade reservation 7GXD5L to business on both flights (HAT437, HAT452) for $540 on your Visa ending 2208. Shall I do that?",
  ["How much would it be to go to economy instead of business?"], "update_reservation_flights 7GXD5L HAT437 HAT452", "Price question, no agreement.")
n(K, "Exchange for order #W5814427: Phone Case black -> white (item 9952038146). Shall I submit it?",
  ["Is there a price difference for the white one, or is it the same?"], "exchange_delivered_order_items #W5814427 Phone Case", "Price question before agreeing.")
n(K, "Reservation W8KC2B can be cancelled. The refund goes to your original payment method. Shall I cancel it?",
  ["Before you do that, will I get the full amount back or only part of it?"], "cancel_reservation W8KC2B", "Refund-amount question; nothing agreed yet.")
n(K, "I'll return the Wall Clock (item 5021836479) from order #W6127753 with the $32.50 refund to your original PayPal. Ok?",
  ["OK and when would I actually see the money back on my PayPal?"], "return_delivered_order_items #W6127753 Wall Clock", "Starts with 'OK' but is a refund-timing question, not a go-ahead.")

K = "wait_let_me_check"
n(K, "I'll cancel reservation 4LNV8S (SFO to DEN, May 29) for a full refund to your Mastercard. Shall I proceed?",
  ["Let me check with my wife first."], "cancel_reservation 4LNV8S", "'Let me check' is a hesitation, not a go-ahead.")
n(K, "New flights for reservation J2TF6R: HAT521 on May 18 and HAT547 on May 25. The $45 difference goes on your gift card ending 9081. OK to change?",
  ["Hmm, give me a minute to look at my calendar."], "update_reservation_flights J2TF6R HAT521 HAT547", "Asking for time = not yet.")
n(K, "I'll switch the payment on order #W9301846 to your gift card ending 7765. Shall I go ahead?",
  ["Not yet, I need to find out how much is left on that gift card."], "modify_pending_order_payment #W9301846", "'Not yet' is a strict no.")
n(K, "I'll update your default address to 640 Juniper Hollow, Apt 2B, Provo, UT 84601. Confirm?",
  ["Sounds right but let me double check the apartment number on my lease first."], "modify_user_address for user jasper_oyelaran_4402", "Partial agreement then 'let me double check' = not a go-ahead yet.")

K = "changed_detail"
n(K, "I'll switch the payment for order #W1728563 from PayPal to your Visa ending 6618. Confirm?",
  ["Yes, but use my Mastercard instead."], "modify_pending_order_payment #W1728563", "Yes with a changed card = not a go-ahead for the listed action.")
n(K, "Exchange for order #W8065231: Running Jacket size M -> size L (item 4819027365), no price difference. Shall I submit it?",
  ["Actually make it XL, L will still be tight. Otherwise go ahead."], "exchange_delivered_order_items #W8065231 Running Jacket", "Size changed; the listed exchange is not approved.")
n(K, "I'll change the shipping address on order #W4471209 to 418 Larkspur Lane, Apt 3, Tucson, AZ 85719. Shall I update it?",
  ["Yes, except it's Apt 5, not Apt 3."], "modify_pending_order_address #W4471209", "Address detail changed.")
n(K, "I'll add 2 checked bags to reservation N6YB3H, bringing it to 3 bags, for $100 on your Visa ending 4471. Go ahead?",
  ["Go ahead but make it 3 extra bags, not 2."], "update_reservation_baggages N6YB3H", "Bag count changed, so the listed call is not approved.")
n(K, "New itinerary for reservation E5QS9K: HAT466 on May 20, economy. Difference $22 on your Mastercard ending 0335. OK?",
  ["Can we do the 21st instead of the 20th? Then that's fine."], "update_reservation_flights E5QS9K HAT466", "Date changed before agreeing.")
n(K, "I'll cancel order #W3590817 for the reason 'no longer needed'. Proceed?",
  ["Go ahead, but put the reason as ordered by mistake."], "cancel_pending_order #W3590817", "Cancel reason changed from the listed one.")

K = "different_choice"
n(K, "I found two flights for May 20: HAT431 leaving at 08:10 for $210, or HAT466 leaving at 17:45 for $185. I'd book HAT431 for reservation R4PZ6C. Shall I make that change?",
  ["The evening one."], "update_reservation_flights R4PZ6C HAT431", "User picks the other listed option.")
n(K, "The Desk Chair comes in black (item 6639201874) or gray (item 6639201882). Shall I exchange yours in order #W6710358 for the black one?",
  ["I'd rather go with the gray."], "exchange_delivered_order_items #W6710358 Desk Chair black", "A different choice from the listed options.")
n(K, "You can upgrade reservation V2NB8K to economy for $90 or to business for $480. Shall I upgrade it to business?",
  ["Economy is plenty for me."], "update_reservation_flights V2NB8K business", "User chooses economy, not the proposed business.")
n(K, "For the return of the Sneakers (item 3307148926) from order #W2290461 the refund can go to your original Visa or your gift card ending 5504. I'll put it on the Visa, ok?",
  ["Put it on the gift card please."], "return_delivered_order_items #W2290461 Sneakers to Visa", "User picks the other refund option, not the proposed one.")

K = "taken_back"
n(K, "I'll cancel order #W5246630 (Standing Desk) for the reason 'no longer needed'. Shall I proceed?",
  ["Yes go ahead.", "Actually no, hold off, I want to talk to my husband first."], "cancel_pending_order #W5246630", "Go-ahead taken back in a later B message.")
n(K, "I'll cancel order #W7018354 (Garden Hose) for the reason 'ordered by mistake'. Confirm?",
  ["Sure, do it.", "Hmm on second thought, keep the order, I might use it after all."], "cancel_pending_order #W7018354", "Later message withdraws the yes.")
n(K, "Booking summary: one-way MSP to MCO on May 27, HAT587, economy, passenger Rafferty Quaile, no insurance, $164 on your gift card ending 2251. Book it?",
  ["Yes book it.", "Sorry, scratch that, don't book yet. My sister may come and we'd need two seats."], "book_reservation for user rafferty_quaile_3307, flight HAT587", "'Scratch that' takes the yes back.")
n(K, "I'll cancel the whole reservation X3DJ7P (both flights). The refund goes to your original card in 5-7 business days. Proceed?",
  ["Ok proceed", "Wait no! I only want to drop the return flight, not the whole trip."], "cancel_reservation X3DJ7P", "Second message retracts and changes the request.")

K = "yes_other_action_only"
n(K, "Plan: 1) cancel order #W8152406 and 2) cancel order #W8152414, both with the reason 'no longer needed'. Shall I go ahead with both?",
  ["Only the first one, please. Keep the second order."], "cancel_pending_order #W8152414", "Go-ahead only for a different listed action.")
n(K, "For reservation H9RQ4C I'll (1) upgrade both flights to business for $610 and (2) add 1 checked bag for $50, both on your Visa ending 7319. Do both?",
  ["Just add the bag, skip the upgrade."], "update_reservation_flights H9RQ4C business", "Only the bag change is approved, not the upgrade.")
n(K, "Two things: return the Yoga Mat (item 6610394851) from order #W1376284 to your PayPal, and exchange the Water Bottle in order #W1376292 from 500ml to 750ml (item 3378216078). Confirm both?",
  ["Do the return. I'll hang on to the bottle for now."], "exchange_delivered_order_items #W1376292 Water Bottle", "Yes only to the return, not the exchange.")
n(K, "To recap: (1) update your default address to 12 Saltmarsh Rd, Mobile, AL 36602; (2) change the shipping address of order #W2869105 to the same; (3) switch the payment of order #W2869105 to your PayPal. Shall I go ahead?",
  ["Yes to the address changes, but leave the payment as it is."], "modify_pending_order_payment #W2869105", "Yes covers items 1-2 only; payment switch refused.")

K = "thanks_only"
n(K, "I'll cancel reservation B7MW2G for the full refund to your original card. Shall I go ahead?",
  ["Thanks."], "cancel_reservation B7MW2G", "Thanks alone neither agrees nor asks a change.")
n(K, "Exchange for order #W6608135: Bedside Lamp warm -> cool white (item 8120364597), no price difference. Shall I submit it?",
  ["Thank you for laying that out so clearly."], "exchange_delivered_order_items #W6608135 Bedside Lamp", "Thanks only, no go-ahead.")
n(K, "I'll add 1 checked bag to reservation U4FZ8N for $50 on your gift card ending 6032. Confirm?",
  ["Appreciate it, thank you."], "update_reservation_baggages U4FZ8N", "Thanks only; no default to yes.")

with open(OUT, "w") as f:
    for c in C:
        f.write(json.dumps(c, ensure_ascii=False) + "\n")
print(len(C))
