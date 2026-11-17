# K2 fix: a concrete definition of "the details are listed" (approved by the user, 2026-10-23)

## The problem (found in p12's development bug check, 2026-10-23)
- K2 (p8, version 1) asks whether the agent's message lists "every detail above (the same ids, items, options,
  amounts, dates, names or payment methods)". The details text shows **every option of every item**.
- So K2 says no to good listings. Example `stage_a.luna.tgr_frozen|retail/0/0|5`: the agent names the order, both
  items with their ids, and the refund card, and asks for yes or no. K2 says no, because the items' options (size,
  colour, type) are not repeated. The judge, the policy and a person all say yes.
- On 200 development conversations: 207 tiny blocks vs 31 for the judge stand-in; K2 makes 121 of the 211
  disagreements with the judge.
- Root: p8. Fake answers (p8) and the judge stand-in (p11) could not show it; p12a was the first real answers.

## The rule (one sentence)
**Message A must state every argument of the call that the user can check, each in a form the user knows.** The
policy line is S6: "list the action detail and obtain explicit user confirmation".

What "a form the user knows" means, fixed for every kind of argument:

| argument kind | counts as stated when message A has | not needed |
|---|---|---|
| order id | the id, with or without `#` | |
| reservation id | the id | |
| an existing item (to return, cancel, or change) | its product name **or** its item id | its options |
| a new item (exchange, modify) | its item id, **or** each option that differs from the old item (e.g. "red" for a colour change) | the options that stay the same |
| payment method | its kind and, for a card, the last four digits; "gift card" or the gift card id; "PayPal" | the internal id (`credit_card_4190576`) |
| address | every non-empty field: street line 1, line 2 (if any), city, state, zip, country | |
| cancellation reason | the reason, in the policy's words or the same meaning ("no longer needed", "ordered by mistake") | |
| flight | its flight number and its date (the year may be left out) | |
| cabin | the cabin name (basic economy, economy, business) | |
| passenger | first and last name, and the date of birth | |
| several payment methods in one call | each method, and the amount paid with each | the amount when there is only one method |
| trip origin, destination, one way / round trip | | implied by the flights; not needed |
| bag counts | the total number of checked bags, and how many are paid | |
| insurance | whether it is added or not | |
| amount of a certificate | the amount | |
| the user's own id | | never needed (it is the user) |

Amounts that are not call arguments (a price difference, a total price) are **not required**: K2 asks only about
what the call will do. They may appear; they never make it a no.

## Per tool (what code renders as the list K2 checks)
Retail:
| tool | lines |
|---|---|
| cancel_pending_order | order id; reason |
| modify_pending_order_address | order id; the new address |
| modify_user_address | the new address |
| modify_pending_order_payment | order id; the new payment method |
| modify_pending_order_items | order id; each old item → its new item; the payment method for the difference |
| exchange_delivered_order_items | order id; each old item → its new item; the payment method for the difference |
| return_delivered_order_items | order id; each returned item; the refund method |

Airline:
| tool | lines |
|---|---|
| book_reservation | each flight; the cabin; each passenger; the payment method(s); the bag counts; insurance |
| update_reservation_flights | reservation id; each flight of the new trip; the cabin; the payment method |
| update_reservation_baggages | reservation id; the bag counts; the payment method (only if paid bags) |
| update_reservation_passengers | reservation id; each passenger |
| cancel_reservation | reservation id |
| send_certificate | the amount (only if the fact is checked for this tool) |

## The new K2 (version 2)
- The details text: one line per item of the per-tool list, each line saying what counts as stated (from the table).
- The question: "Does message A state each line above, in one of the forms that line allows? If any line is missing
  or different, the answer is no. Other details (options that stay the same, prices) are not needed."
- The fact's plain text (retail `consequential_action_details_listed` part b; airline
  `pending_database_change_details_listed_and_explicitly_confirmed` part c) is changed to the same rule. The code parts
  (finding the candidate messages) do not change.

## The other fixes (already agreed)
- Quote check: ignore `**` / `__` marks and line breaks when comparing the quote with the message.
- Done: an agent read the other development disagreements (K13 44, K1 22, K5 13; `p12_other_questions_review.md`). The user approved: K5 and K4 count data as the user's own unless the message says otherwise; K13 gets one sentence and the policy's "but nothing else"; the evaluator no longer stops an OR at the first unclear part. K1, K9: no change.
- The general lesson of K5 and K4 is the same as K2's: a question must get the information it needs, or a stated
  default. The model saw one message and could not know whose order or name it was; code already knows ownership from
  the database, so the question now takes "the user's own unless the message says otherwise".
- Re-ask only the changed questions on the same 200 development conversations (paid, about $0.05, limit $1, inside
  p12's approved $13.24). Then the bug check again. Then p12b freezes v3.

## Why this is fair
It is fixed from the policy text and the tools' arguments, not from examples. The result comes only from unseen data:
the hold-out (p12b) and the live run (p14). Logged in the pre-registration's change log as a change on development
data, before the hold-out.

## Round 2 (approved by the user, 2026-10-23, after the second dev check)
- **Quotes in pieces:** K2 asks about several lines, so the model quotes several pieces. A quote may now be split at
  ";", "…" or line breaks; each piece must be word for word in the message.
- **Only what changes:** some tools take the whole list, not just the change (τ-bench's flight change takes every
  flight of the trip). K2's lines cover only the flights (or passengers) that differ from the database, like item
  options.
- **Kept strict:** a detail the user said themselves (e.g. "use PayPal") still has to be in the agent's listing; the
  order id has to be there too. A block online costs the agent one turn; the live test shows the real cost.
- General lesson for new policies: when a tool's argument is a whole list, the check lines come from the difference
  with the database, never from the raw list.
