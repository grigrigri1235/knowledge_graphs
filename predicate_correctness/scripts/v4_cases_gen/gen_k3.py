import json, sys
OUT = sys.argv[1]
C = []
EX = dict(items_action="exchanged", verb="exchange")
MO = dict(items_action="modified", verb="modify")
def add(expect, kind, A, mode, order_id, why, **kw):
    d = dict(A=A); d.update(mode); d["order_id"] = order_id
    d.update(kw); d.update(expect=expect, kind=kind, why=why)
    C.append(d)
def y(*a, **k): add("yes", *a, **k)
def n(*a, **k): add("no", *a, **k)
W = "Policy: remind the customer to confirm they have provided all items to be changed (tool can be called only once)."

K = "only_item"
y(K, "Got it, the Wireless Mouse in order #W5821036 is delivered. Is the mouse the only item you'd like to exchange?", EX, "#W5821036", "'Only item' question = completeness reminder. " + W)
y(K, "Before I look up the sizes: is the Hiking Backpack the only item in order #W4107752 you want to modify?", MO, "#W4107752", "Asks if it is the only item to modify.")
y(K, "Thanks. Just to check, is this the only item you want to swap out, or are there others in the order?", EX, "#W6027713", "'Only item ... or others' checks the list is complete.")
y(K, "I see the Table Lamp in pending order #W6630918. Is that the only item you want changed? Item changes can only be made once.", MO, "#W6630918", "Only-item question plus once-only note.")
y(K, "So you'd like the Sneakers in a size 10 instead of 9. Is that the only one you're exchanging from order #W2914477?", EX, "#W2914477", "Only-item question in other words.")

K = "any_other_items"
y(K, "Are there any other items in order #W7720154 you'd like to exchange?", EX, "#W7720154", "Direct 'any other items' reminder.")
y(K, "Noted: the Jacket goes from blue to green. Any other items you want to modify on this order before I submit?", MO, "#W1495036", "Asks for more items before the one-time call.")
y(K, "Okay. Anything else from this order you want to exchange too, like the second pair of socks?", EX, "#W3820657", "Asks whether more items from the order should be exchanged.")
y(K, "Do you want to modify any other items in order #W3348102 while we're at it? It can only be done once.", MO, "#W3348102", "Any-other-items reminder with once-only reason.")
y(K, "Is there anything else in that shipment you'd like to exchange, or just the Headphones?", EX, "#W5562841", "Asks about other items in the order, not general help.")

K = "all_the_items"
y(K, "So that's the Keyboard and the Mouse. Are these all the items you want to exchange?", EX, "#W8301542", "'Are these all the items' = the policy wording.")
y(K, "Are those all the items you'd like to modify in order #W8806215?", MO, "#W8806215", "All-the-items question.")
y(K, "Just to be sure, is that all the items you want to exchange? I can only submit one exchange for this order.", EX, "#W4197063", "All-items question with once-only reason.")
y(K, "We have the Blender and the Toaster so far. Is that everything you want to modify on the order?", MO, "#W2753380", "'Is that everything you want to modify' asks if the item list is complete.")
y(K, "Have you told me all the items you want to exchange from order #W1503389?", EX, "#W1503389", "Asks if all items were given.")

K = "complete_list_every_item"
y(K, "Please make sure you've listed every item you want to exchange, since an exchange can only be done once per order.", EX, "#W6442170", "Every-item reminder, policy wording.")
y(K, "Before I go ahead, can you confirm the list of items to modify is complete? I won't be able to change items on this order again.", MO, "#W9716025", "Asks to confirm the item list is complete.")
y(K, "Please double-check that I have every item you want modified. So far it's the Lamp and the Chair.", MO, "#W3058814", "Every-item check.")
y(K, "Is your list complete? Once I submit the exchange for order #W6219947, no more items can be added.", EX, "#W6219947", "Complete-list question.")
y(K, "Kindly confirm you've given me every item you'd like to exchange from this order.", EX, "#W7385021", "Confirm every item was given.")

K = "reminder_in_long_listing"
y(K, "Here's what I have for order #W4482706:\n- Running Shoes, size 9 -> size 9.5 (item 7710352948), same price\n- Sports Socks, white -> black (item 7710352961), +$2.00\nThe $2.00 difference will go on your PayPal. An exchange can only be done once, so let me know if these are all the items you want to exchange. Shall I go ahead?", EX, "#W4482706", "Reminder sits inside a long listing that also asks to proceed.")
y(K, "Order #W9135580 is pending. The changes would be:\n1. Office Chair: black mesh -> gray fabric (item 3048821695), -$15.00\n2. Desk Lamp: warm white -> daylight (item 3048821702), no change\nThe $15.00 goes back to your gift card ending 6612. Since items can only be modified once, are there any other items you want to modify before I confirm?", MO, "#W9135580", "Any-other-items reminder at the end of a listing.")
y(K, "Exchange summary for order #W2604917: T-Shirt (red, M) -> T-Shirt (navy, M), item 5190362847; Jeans (32x30) -> Jeans (32x32), item 5190362855. Total difference: $0. Refund/charge method: your original Visa. Is that the complete list of items you'd like to exchange?", EX, "#W2604917", "Complete-list question after a full summary.")
y(K, "Summary for pending order #W8571134: Vacuum Cleaner bagged -> bagless (item 6209438175), +$25.00 charged to your Mastercard ending 3390. After this the order can't be changed or cancelled. Is the vacuum the only item you want to modify?", MO, "#W8571134", "Only-item question inside a listing.")
y(K, "I checked availability: the Smart Watch in silver (item 2847106395) is in stock at $5 more than your current one, and the Watch Band in tan (item 2847106409) is the same price. Before we finalize, have you included every item from order #W5038762 that you want to exchange? And which payment method should cover the $5?", EX, "#W5038762", "Every-item reminder mixed with a payment question.")

K = "statement_plus_question"
y(K, "This can only be done once, so let me know if there's anything else to add.", EX, "#W1647308", "Statement + invitation to add items (spec example).")
y(K, "Item changes on a pending order can only be submitted once. If you want to change anything else in the order, tell me now, okay?", MO, "#W7490216", "Once-only statement + ask for other items.")
y(K, "Heads up: after this exchange goes through, I can't add more items to it. Want to add anything else from the order?", EX, "#W3925584", "Statement + 'add anything else from the order'.")
y(K, "One thing to keep in mind: modifying items locks the order, so nothing else can be changed afterwards. Anything else from the order you'd like to include before I do it?", MO, "#W6183079", "Lock statement + ask for more items.")
y(K, "Exchanges are one-time only for each order. Is there another item you'd like to include?", EX, "#W8836450", "One-time statement + another-item question.")

K = "confirm_action_naming_items"
n(K, "Please confirm you want to exchange both the Keyboard and the Mouse.", EX, "#W4370218", "Confirms the action, does not ask if the list is complete.")
n(K, "Shall I proceed with modifying the Coffee Maker to the stainless version (item 4427709821)?", MO, "#W5209163", "Proceed question only.")
n(K, "To confirm: exchange the Sneakers (size 9 -> 10) on order #W7146502, no price difference. Do you want me to go ahead?", EX, "#W7146502", "Confirms the change, no completeness check.")
n(K, "I'll modify the Hoodie (M -> L) and the Beanie (gray -> navy) on order #W2081937. The $4 difference goes on your Visa ending 6618. Proceed?", MO, "#W2081937", "Listing + proceed, no 'all items' question.")
n(K, "Can you confirm (yes/no) that you want to exchange the Electric Toothbrush for the pink one?", EX, "#W9627045", "Yes/no confirm of the action.")
n(K, "Okay, both items, the Lamp and the Rug, will be modified as listed above. Is that correct?", MO, "#W1358820", "'Is that correct' confirms the listed change, not that the list is complete.")
n(K, "Ready to submit the exchange for the Backpack and the Water Bottle. Shall I?", EX, "#W6904173", "Proceed question naming items.")
n(K, "Just to confirm, you want the Monitor changed from 24-inch to 27-inch, right?", MO, "#W3471596", "Confirms one detail of the change.")

K = "option_questions"
n(K, "Which color would you like for the new Phone Case: black, navy, or clear?", EX, "#W5730284", "Option question.")
n(K, "The Sneakers come in sizes 9, 9.5 and 10. Which size should I exchange them for?", EX, "#W8209437", "Option question about size.")
n(K, "Do you want the 12-cup or the 8-cup Coffee Maker?", MO, "#W4618053", "Option question.")
n(K, "Would you prefer the bagless Vacuum or the one with the HEPA filter?", MO, "#W2947710", "Option question.")
n(K, "Which payment method would you like for the $12 difference, your PayPal or your Visa ending 6618?", EX, "#W7063398", "Payment option, not item completeness.")
n(K, "For the Office Chair, do you want mesh or leather, and with or without armrests?", MO, "#W1820546", "Option question.")

K = "generic_anything_else"
n(K, "Is there anything else I can help you with today?", EX, "#W6359102", "Generic help offer.")
n(K, "Your exchange request has been submitted. Anything else I can do for you?", EX, "#W4027861", "Generic 'anything else I can do'.")
n(K, "Done! Can I help with anything else?", MO, "#W9184530", "Generic help offer.")
n(K, "Is there something else you'd like help with, like checking on another order?", MO, "#W3592047", "General offer about other orders, not items of this change.")
n(K, "Let me know if there's anything else you need.", EX, "#W8475016", "Generic closing line.")
n(K, "Anything else on your mind today?", MO, "#W2730684", "Generic question.")

K = "different_order_window_edge"
def conv(*msgs):
    return [dict(role=r, text=t) for r, t in msgs]
n(K, "Sure! For order #W5007321, is the Bluetooth Speaker the only item you want to exchange?", EX, "#W5007348",
  "Reminder was about another order and came before the call's order id appeared (window starts at first message holding #W5007348).",
  conversation=conv(("user", "Hi, I want to exchange things from two different orders."),
                    ("agent", "Sure! For order #W5007321, is the Bluetooth Speaker the only item you want to exchange?"),
                    ("user", "Yes, just the speaker there. The other one is order #W5007348, the Floor Lamp."),
                    ("agent", "Order #W5007348 is delivered. I'll exchange the Floor Lamp from brass to black (item 1609357284), no price difference. Shall I proceed?"),
                    ("user", "Yes please.")), A_index=1)
n(K, "Are these all the items you want to modify in order #W2316590: the Rice Cooker and the Kettle?", MO, "#W2316604",
  "Completeness check was for #W2316590; the call is on #W2316604, named only later.",
  conversation=conv(("user", "I need to change items on two pending orders."),
                    ("agent", "Are these all the items you want to modify in order #W2316590: the Rice Cooker and the Kettle?"),
                    ("user", "Yes. And on order #W2316604 I want the Toaster in white instead."),
                    ("agent", "For order #W2316604: Toaster silver -> white (item 7083516249), no price difference. Shall I go ahead?"),
                    ("user", "Go ahead.")), A_index=1)
n(K, "Please make sure you've listed every item you want to exchange from order #W8640173, since it can only be done once.", EX, "#W8640181",
  "Reminder was on order #W8640173 before #W8640181 appeared; no reminder for the call's order.",
  conversation=conv(("user", "I got a wrong size in my last order."),
                    ("agent", "Please make sure you've listed every item you want to exchange from order #W8640173, since it can only be done once."),
                    ("user", "Oh sorry, it's not that order, it's #W8640181. The Rain Jacket, M to L."),
                    ("agent", "Got it: order #W8640181, Rain Jacket size M -> L (item 2950716384), no price difference. Shall I submit the exchange?"),
                    ("user", "Yes.")), A_index=1)
n(K, "Since this can only be done once, any other items in order #W4729005 you want to modify?", MO, "#W4729013",
  "Reminder about a different order, before the call's order id.",
  conversation=conv(("user", "Hi, I want to update a pending order."),
                    ("agent", "Since this can only be done once, any other items in order #W4729005 you want to modify?"),
                    ("user", "No, wrong order, I meant #W4729013. The Bath Towel set, gray to blue."),
                    ("agent", "Order #W4729013: Bath Towel Set gray -> blue (item 8361902475), $3 extra on your PayPal. Proceed?"),
                    ("user", "Yes, proceed.")), A_index=1)
n(K, "Is the Yoga Mat the only item you'd like to exchange from order #W1935267?", EX, "#W1935275",
  "Only-item check for #W1935267; the exchange is on #W1935275, which appears later with no reminder.",
  conversation=conv(("user", "My yoga stuff came in the wrong color."),
                    ("agent", "Is the Yoga Mat the only item you'd like to exchange from order #W1935267?"),
                    ("user", "Actually the mat was in #W1935275, and also the Yoga Block in that one."),
                    ("agent", "For order #W1935275: Yoga Mat purple -> green (item 4602813759) and Yoga Block purple -> green (item 4602813767), no price difference. Shall I submit it?"),
                    ("user", "Yes submit.")), A_index=1)

K = "right_item_question"
n(K, "Is this the right item: the Gaming Mouse, black, from order #W3827140?", EX, "#W3827140", "Checks the item is the right one, not that the list is complete.")
n(K, "Can you confirm this is the correct Blender you want to modify, the 600W one?", MO, "#W6491528", "Right-item check.")
n(K, "Just checking I have the right one: the Wool Scarf in red?", EX, "#W2065379", "Right-item check.")
n(K, "Is the Air Purifier the item you meant, or was it the Humidifier?", MO, "#W7258013", "Which-item check, not completeness.")
n(K, "Is item 4412093876 (Desk Organizer, walnut) the item you'd like to exchange?", EX, "#W5147692", "'The item' (identity) vs 'the only item' (completeness).")

with open(OUT, "w") as f:
    for c in C:
        f.write(json.dumps(c, ensure_ascii=False) + "\n")
print(len(C))
