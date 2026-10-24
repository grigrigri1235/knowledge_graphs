# Tracker v4 P1: K2-style form check (tau-bench v1 database only, $0)

Written by `predicate_correctness/scoring/v4_form_check.py` (stdlib, no network, no LLM). Numbers also in `form_check.json`.

**Sources (the only files read):** `envs/retail/data/users.json`, `envs/retail/data/orders.json`, `envs/retail/data/products.json`, `envs/airline/data/users.json`, `envs/airline/data/reservations.json`, `envs/airline/data/flights.json`, `envs/retail/wiki.md`, `envs/airline/wiki.md` under `~/opt/tau-bench-59a200c/tau_bench/`; sha256 in `form_check.json` (`inputs_sha256`). No task file, user instruction, expected action or conversation is read; `tests/test_v4_form_check.py` checks this.

**Why DB only:** an earlier version also counted the user-simulator task texts and their expected actions (retail train, retail and airline test minus test-66, retail dev-20). That leaked task knowledge into the v4 form decisions (overview.md section 3). Those parts and the dev-20 overlap section are removed; every decision is re-based below on the database, the policy wiki, or a generic reason.

**Main points**
- Cards: 0 of 239 retail and 0 of 503 airline card ids end in the card's last four. So the id digits and the last four are always different numbers: accept both.
- Same-brand cards: 0 retail users, 85 airline users have 2+ cards of one brand. A brand word alone names a card only when the owner has one of that brand (checked per user).
- 4-digit clashes inside one user: retail 0 / 1, airline 0 / 0 users (same id tail / id tail = another card's last four). Methods that need 5+ ending digits: retail 1, airline 0.
- Orders with 2+ items of one product: 91 of 1000. There the product name alone does not pick the item.
- Short option values (<= 2 chars) 26, number-only values 11, products with one value under 2+ option names 1: these need the option name next to the value.
- Retail address2 empty: 0 of 1500; non-USA country: 0. Dropping the country line loses nothing.
- Airline passengers who are not the user or a saved passenger: 1163 of 3593; paid bags 0 in 2000 of 2000 reservations.
- User mei_johansson_1199: the id credit_card_7574044 ends in 4044, which is also the last four of another of their cards. For this user 'ending in 4044' alone is unclear.

## The table

| where | value kind | forms that occur | count | v4 form decision | note |
|---|---|---|---|---|---|
| retail DB | payment method kinds | credit_card 239, gift_card 234, paypal 222 | 695 methods, 500 users | all accepted |  |
| retail DB | payment id forms | credit_card_9999999 239, gift_card_9999999 234, paypal_9999999 222 | 695 | full id; 4+ ending digits of the id number | every id = kind word + _ + 7 digits |
| retail DB | credit card: id ends in last four | id tail vs `last_four` | 0 of 239 (0.0 %) | both accepted | the id digits and the last four are never the same number on one card |
| retail DB | card brands | mastercard 133, visa 106 | 239 | brand word optional |  |
| retail DB | users with 2+ cards |  | 23 of 216 (10.6 %) card holders | - | 2+ cards of one brand: 0; same last four twice: 0 |
| retail DB | users with 2+ of one kind | credit_card 23 | 23 users | kind / brand word alone only when it fits one method of the owner |  |
| retail DB | 4-digit clashes inside one user | same id tail twice; id tail = another card's last four | 0 users; 1 users | a 4-digit form of 2 methods names neither | methods that need 5+ ending digits: 1 |
| retail DB | gift card balance | min 0, max 100 | 234 | not an argument; '$N' names a gift card only when unique for the owner |  |
| retail DB | order id | #W9999999 1000 | 1000 | `#W1234567` or `W1234567`, any case | status: pending 423, delivered 373, processed 102, cancelled 102 |
| retail DB | product id / item id | product id lengths {10: 50}; item id lengths {10: 591} | 50 products, 591 items | item id: yes; product id: not an argument | item ids that equal a product id: 0 |
| retail DB | items per order | 2 217, 5 208, 1 202, 3 190, 4 183 | 1000 | - |  |
| retail DB | order with 2+ items of one product | same product name twice | 91 of 1000 (9.1 %) | name alone NOT enough there: item id or an option value only that item has | same item id twice: 7; orders where two products share a name word: 26 (52 of 2885 (order, product) pairs) |
| retail DB | option names | 68 names; most common color 31, material 16, size 13, type 7, capacity 6, storage 5 | 50 products | - |  |
| retail DB | short option values (<= 2 chars) | 10, 11, 12, 1L, 2K, 2L, 3x, 4K, 5K, 5x, 6, 7, 8, 9, A4, A5, A6, L, M, S, XL, XS, i5, i7, i9, no | 26 | only with the option name within 3 words | e.g. size 'S' / 'M' / '8' match ordinary words and numbers |
| retail DB | 3-char option values | 10x, 4GB, 4mm, 500, 5mm, 60%, 6GB, 6mm, 80%, 8GB, EVA, LCD, PVC, RGB, TPE, USB, XXL, art, gas, low, men, red, yes | 23 | whole value, no option name needed (unless number-only or shared) |  |
| retail DB | number-only option values | 6, 7, 8, 9, 10, 11, 12, 500, 1000, 1500, 2000 | 11 | only with the option name within 3 words |  |
| retail DB | yes / no option values | no, none, yes | 3 | only with the option name within 3 words |  |
| retail DB | one value under 2+ option names in one product | Sunglasses: black (frame color/lens color) | 1 products | only with the option name within 3 words |  |
| retail DB | value inside another value of the same option | Smartphone.color: 'gold' in 'rose gold'; Sunglasses.lens type: 'polarized' in 'non-polarized'; E-Reader.connectivity: 'Wi-Fi' in 'Wi-Fi + Cellular' | 3 pairs | whole-value match | 'black' must not count inside 'black and white' |
| retail DB | variant pairs of one product: options that differ | 2 1622, 3 1098, 1 853, 4 126, 5 17 | 3716 | a new item: its id, or every changed option value |  |
| retail DB | address2 | Suite N 1500 | 1500 addresses (500 users + 1000 orders); empty 0 | line 2 when it changes; Suite / Ste / Apt / Unit / # + the number, or the number right after line 1 |  |
| retail DB | country | USA 1500 | 1500 | dropped (no line) |  |
| retail DB | zip | 99999 1500 | 1500 | the 5 digits | leading 0: 0 |
| retail DB | state | 2 capitals 1500 | 1500 | 2-letter code or the full name |  |
| retail DB | address1 start / last word | N 1500; last word Street 446, Drive 359, Lane 271, Avenue 257, Broadway 86, Road 81 | 1500 | the street line; Street / St, Avenue / Ave ... both |  |
| retail DB | orders shipped to the user's default address |  | 800 of 1000 (80.0 %) | 'your default address' when the call's address is the default |  |
| retail DB | original payment method (payment_history[0]) | paypal 359, gift_card 337, credit_card 304 | 1000 | 'the original payment method' when the call uses it |  |
| airline DB | payment method kinds | gift_card 516, credit_card 503, certificate 467 | 1486 methods, 500 users | all accepted |  |
| airline DB | payment id forms | gift_card_9999999 516, credit_card_9999999 503, certificate_9999999 467 | 1486 | full id; 4+ ending digits of the id number |  |
| airline DB | credit card: id ends in last four | id tail vs `last_four` | 0 of 503 (0.0 %) | both accepted |  |
| airline DB | card brands | visa 260, mastercard 243 | 503 | brand word optional |  |
| airline DB | users with 2+ cards / 2+ of one brand |  | 130 / 85 users | brand word alone only when it fits one card of the owner | same last four twice in one user: 0 |
| airline DB | users with 2+ of one kind | credit_card 130, gift_card 129, certificate 117 | 376 users | 'the certificate' / 'gift card' alone only when the owner has one |  |
| airline DB | 4-digit clashes inside one user | same id tail twice; id tail = another card's last four | 0 users; 0 users | a 4-digit form of 2 methods names neither | methods that need 5+ ending digits: 0 |
| airline DB | certificate amount | 250 123, 500 122, 150 112, 100 110 | 467 | '$N certificate' only when unique for the owner; send_certificate: the amount | users with 2 certificates of one amount: 49 |
| airline DB | reservation id | 6 chars [A-Z0-9] 2000 | 2000 | the 6 chars, any case, whole token | all digits: 1; all letters: 275 |
| airline DB | flight number | HAT999 300 | 300 | 'HAT170', 'HAT 170', 'flight 170', with its date | distinct digit tails: 300 of 300 |
| airline DB | flight date (reservations) | 9999-99-99 5003 | 5003 | any date form, year optional | years: 2024 5003; reservations with 2+ flights on one date: 1260; with one flight number on 2+ dates: 8 |
| airline DB | flight status (flights DB) | available 4500, landed 3982, cancelled 373, on time 57, flying 47, delayed 41 | 9000 | no line (DB state, not a call detail) |  |
| airline DB | cabin | economy 676, business 675, basic_economy 649 | 2000 | 'basic economy' / 'economy' / 'business' | DB spells `basic_economy`; 'economy' is inside 'basic economy': the longer is matched first |
| airline DB | flight type | one_way 1046, round_trip 954 | 2000 | no line (implied by the flights) |  |
| airline DB | insurance | yes 1005, no 995 | 2000 | not a form: the tiny question K17 |  |
| airline DB | total bags | 0 1075, 1 433, 2 277, 3 99, 4 71, 5 19, 6 19, 8 5, 7 2 | 2000 | the total when > 0; a bag change: the new total or the number added |  |
| airline DB | paid (nonfree) bags | 0 2000 | 2000 | a line only when > 0 (book) | reservations with 0 paid: 2000 |
| airline DB | reservation passengers | user 1600, other 1163, saved passenger 830 | 3593 | first + last name; the DOB only when it is the changed field | user or saved (DOB in DB): 2430 of 3593 (67.6 %); passengers per reservation: 1 920, 2 662, 3 323, 4 95; reservations with one name twice: 6 |
| airline DB | saved passengers per user | 1 328, 2 172 | 500 | - |  |
| airline DB | user address | address2 empty 0; country USA 500 | 500 | no line (not a write argument) |  |
| airline DB | membership | silver 182, gold 175, regular 143 | 500 | no line (DB state, not a call detail) |  |

## Decisions, DB-only

Every v4 form decision: the decision, where it is in the code, where it came from before, and its basis now (a DB count from the table above, a wiki line, or a generic reason that needs no data). The old simulator rows were not used to decide. Line numbers are those of the files at this check.

**Summary:** 40 entries: 32 kept from DB / wiki, 5 kept as generic, 3 comment-only, **0 changed**.

| id | decision | code | before | basis kind | basis now | changes? |
|---|---|---|---|---|---|---|
| P1 | every payment kind (credit card, gift card, PayPal, certificate) is a payment line | state_tracker/v4/listing_v4.py _pay_line | DB rows 'payment method kinds' | DB | retail kinds {'paypal': 222, 'credit_card': 239, 'gift_card': 234}; airline kinds {'credit_card': 503, 'certificate': 467, 'gift_card': 516}; retail wiki.md:23 ("Each payment method is either a gift card") | no |
| P2 | the full payment id is accepted | state_tracker/v4/listing_v4.py:216 exact_payment_forms | DB rows 'payment id forms' | DB | every id is kind + '_' + 7 digits: retail {'paypal_9999999': 222, 'credit_card_9999999': 239, 'gift_card_9999999': 234}, airline {'credit_card_9999999': 503, 'certificate_9999999': 467, 'gift_card_9999999': 516} | no |
| P3 | 4+ ending digits of the id number are accepted (also 5 and 6 digits) | state_tracker/v4/listing_v4.py:217-222 | DB rows 'payment id forms' + simulator rows 'every 4-digit number', 'payment id as named' | DB + generic | generic: the id is what the agent's own tool output shows, its ending digits are the short form of it; DB: card ids ending in the card's last four: retail 0 of 239, airline 0 of 503, so the id digits never collide with the card's own last four; methods whose 4-digit tail fits another method of the owner (they need 5+ digits): retail 1, airline 0 | no |
| P4 | a card's last four is accepted, brand word optional | state_tracker/v4/listing_v4.py:202-203, 238-242 | DB rows 'credit card: id ends in last four', 'card brands' | DB | every card has `last_four` (retail 239, airline 503 cards); brands retail {'mastercard': 133, 'visa': 106}, airline {'visa': 260, 'mastercard': 243} | no |
| P5 | a 4-digit number that is a 4-digit form of 2 of the owner's methods names neither (unless a brand word next to it picks one) | state_tracker/v4/listing_v4.py:221-222; state_tracker/v4/helpers_go_ahead_v4.py:18-22 (form_map_v4, methods_named_v4, 246-318) | DB rows '4-digit clashes' + code comment state_tracker/v4/helpers_go_ahead_v4.py:18 'after the v1 form check' | DB | users with such a clash: retail 0 (same tail) / 1 (tail = another card's last four), airline 0 / 0; retail example [{'user': 'mei_johansson_1199', 'id': 'credit_card_7574044', 'other_card_last_four': '4044'}] | no |
| P6 | kind word / brand word / 'the card' / the balance name a method only when they fit one method of the owner (per user, at run time) | state_tracker/v3/message_view.py _unique_word_forms (used by state_tracker/v4/listing_v4.py:223) | DB rows 'users with 2+ of one kind', 'users with 2+ cards of one brand' + simulator row 'brand only: retail yes, airline no' | DB | same-brand card users: retail 0, airline 85; 2+ of one kind: retail {'credit_card': 23}, airline {'credit_card': 130, 'certificate': 117, 'gift_card': 129}; users with exactly one card: retail 306, airline 154; 2 certificates of one amount: 49. The check is per user, so the domain split ('retail yes, airline no') follows from the DB and needs no per-domain rule | no |
| P7 | a brand word next to the digits that is not the card's brand is a clash, not a match; negation ('not the Mastercard') does not count | state_tracker/v4/listing_v4.py:236-242; state_tracker/v4/helpers_go_ahead_v4.py:320-356 (brand_mismatch_v4, _payment_clash) | lesson L1 (generic) | generic | a wrong brand next to the digits names a different card; a negated mention is not a choice | no |
| P8 | 'the original payment method' when the call's method is payment_history[0] | state_tracker/v4/listing_v4.py:183-188, 248-251 | DB row 'original payment method' | wiki | retail wiki.md:39 ("refunded via the original payment method"); retail wiki.md:69 ("must either go to the original payment method"); airline wiki.md:62 ("original payment methods"); DB kinds of payment_history[0]: {'gift_card': 337, 'credit_card': 304, 'paypal': 359} | no |
| P9 | airline booking with 2+ methods: each method with its amount | state_tracker/v4/listing_v4.py:623-626, 434-439 | predicate_table book row | wiki | airline wiki.md:34 ("at most one travel certificate, at most one credit card") (a split payment has amounts) | no |
| R1 | order id: '#W1234567' or 'W1234567', any case; also by D6 (newest order id named) | state_tracker/v4/listing_v4.py:418-421, 739-740 | DB row 'order id' + simulator row 'order id as named' | DB + generic | order ids {'#W9999999': 1000} (all '#W' + 7 digits); generic: the '#' and the case carry no meaning | no |
| R2 | item id accepted; product id is not a line | state_tracker/v4/listing_v4.py:458, 720 | DB row 'product id / item id' | DB + generic | 591 item ids, 50 product ids, item ids equal to a product id: 0; generic: the tools take item ids, not product ids | no |
| R3 | old item: the product name, or a word of it that names no other product of the order | state_tracker/v4/listing_v4.py:467-475 | DB row 'order with 2+ items of one product' (word clash note) | DB | (order, product) pairs whose name shares a word with another product of the order: 52 of 2885, so the word must be unique in the order (checked per order at run time) | no |
| R4 | old item when the order has 2+ items of that product and the call does not take all: item id or an option value only that item has | state_tracker/v4/listing_v4.py:453-466 | DB row 'order with 2+ items of one product' + simulator row 'items in expected writes' | DB | orders with 2+ items of one product: 91 of 1000 (same item id twice: 7); there the name names 2 items | no |
| R5 | return: 'all the items' / 'the whole order' when the call returns every item | state_tracker/v4/listing_v4.py:570-573, 285-287 | predicate_table retail row | wiki + generic | retail wiki.md:67 ("the list of items to be returned"); generic: 'all' names every item exactly | no |
| R6 | new item: its id, or every changed option value (whole value) | state_tracker/v4/listing_v4.py:482-504, 778-782 | DB row 'variant pairs' | DB | variant pairs by number of differing options: {2: 1622, 4: 126, 3: 1098, 1: 853, 5: 17}; the new item is fixed by the product (same as the old) plus every changed value | no |
| R7 | option values match as whole values ('black' not inside 'black and white') | state_tracker/v4/listing_v4.py:115-122; state_tracker/v4/helpers_go_ahead_v4.py:18-22, 276-277 (_outer_spans) | DB row 'value inside another value' + code comment state_tracker/v4/helpers_go_ahead_v4.py:18-22 | DB | value pairs where one is a whole word inside another of the same option: 3 | no |
| R8 | a value of <= 2 characters needs its option name within 3 words | state_tracker/v4/listing_v4.py:376 | DB row 'short option values' | DB + generic | 26 such values in the DB; generic: 1-2 character tokens ('S', 'M', '8') occur as ordinary words and numbers. 3-character values (23, e.g. colour words) are whole words and need no option name. Note: predicate_table.md says '<= 3 characters'; the code and this check say <= 2 (code unchanged) | no |
| R9 | a number-only value needs its option name within 3 words | state_tracker/v4/listing_v4.py:376 | DB row 'number-only option values' | DB + generic | 11 number-only values; generic: a bare number also matches prices, quantities and ids | no |
| R10 | a yes / no / none value needs its option name within 3 words | state_tracker/v4/listing_v4.py:376 | DB row 'yes / no option values' | DB + generic | 3 such values; generic: 'yes' and 'no' are reply words | no |
| R11 | a value used under 2+ option names of one product needs its own option name | state_tracker/v4/listing_v4.py:377-381 | DB row 'one value under 2+ option names' | DB | products with one value under 2+ option names: 1 | no |
| A1 | country dropped (no line) | state_tracker/v4/listing_v4.py:73 | DB row 'country' + code comment state_tracker/v4/listing_v4.py:73 | DB | country over 1500 addresses (users + orders): {'USA': 1500}; non-USA 0 | no |
| A2 | address2: line 2 when it changes; 'Suite / Ste / Apt / Unit / #' + the number, or the number right after line 1 | state_tracker/v4/listing_v4.py:294, 335-347 | DB row 'address2' | DB + generic | address2 forms {'Suite N': 1500}, empty 0; generic: the other unit words are common spellings of the same unit and still need the same number | no |
| A3 | zip: the 5 digits, not inside another number | state_tracker/v4/listing_v4.py:356-357 | DB row 'zip' | DB | zip forms {'99999': 1500} | no |
| A4 | state: the 2-letter code or the full name | state_tracker/v4/listing_v4.py:295-305, 350-355 | DB row 'state' | DB + generic | state forms {'2 capitals': 1500}; generic: the full state name is the same state | no |
| A5 | address1: the street line; suffix words and their abbreviations both count (Street / St ...) | state_tracker/v4/listing_v4.py:290-293, 319-327 | DB row 'address1' | DB + generic | DB street lines are 'N Name Suffix'; generic: the abbreviation names the same street | no |
| A6 | 'your default address' when the call's address equals the user's default | state_tracker/v4/listing_v4.py:288-289, 510-528 | predicate_table retail row | DB + wiki | orders shipped to the default address: 800 of 1000; retail wiki.md:3 ("modify their default user address") | no |
| A7 | an unchanged address field needs no line | state_tracker/v4/listing_v4.py:517-518 | predicate_table retail row | generic | the user is asked to confirm a change; an unchanged field changes nothing | no |
| F1 | reservation id: the 6 characters, any case, whole token; also by D6 | state_tracker/v4/listing_v4.py:424-425, 741-742 | DB row 'reservation id' | DB | reservation id forms {'6 chars [A-Z0-9]': 2000}; letters-only ids 275 (matched as a whole token, so no inner-word hit) | no |
| F2 | flight: 'HAT170', 'HAT 170', 'flight 170', each with its date | state_tracker/v4/listing_v4.py:578-587, 698-707 | DB rows 'flight number', 'flight date' | DB + generic | flight numbers {'HAT999': 300}; distinct digit tails 300 of 300 (so '170' alone names one flight); reservations with one flight number on 2+ dates: 8, with 2+ flights on one date: 1260 (the date is part of the line) | no |
| F3 | dates: any common format, year optional | state_tracker/v4/listing_v4.py:586, 707; message_view.text_names_date | DB row 'flight date' + simulator row 'date forms' | generic + DB | generic: a date in any common format names the same day; DB years {'2024': 5003} (one year, so the year adds nothing) | no |
| F4 | cabin: 'basic economy' / 'economy' / 'business'; 'economy' is not matched inside 'basic economy'; flight change: only when it differs | state_tracker/v4/listing_v4.py:590-592, 692-716, 655-656 | DB row 'cabin' | DB + generic | cabins {'business': 675, 'economy': 676, 'basic_economy': 649}; generic: 'economy' is a word of 'basic economy' | no |
| F5 | passenger: first + last name; the date of birth only when it is the changed field | state_tracker/v4/listing_v4.py:595-605, 669-674 | DB row 'reservation passengers' + simulator row 'booking passengers' | DB + wiki | reservations with one passenger name twice: 6 of 2000 (elsewhere first + last name picks one passenger; a change that keeps the name lists the date of birth, so those few still name the changed passenger); passengers who are not the user or a saved passenger: 1163 of 3593; airline wiki.md:32 ("collect the first name, last name, and date of birth") (collecting, not listing) | no |
| F6 | bags: the total when > 0 (book); a bag change: the new total or the number added | state_tracker/v4/listing_v4.py:627-631, 659-666 | DB row 'total bags' | generic | the total and the number added both state the same change | no |
| F7 | paid bags: a line only when > 0 (book), as the number with a paid word or the $ amount; a bag change names the payment method only when it costs money | state_tracker/v4/listing_v4.py:632-635, 667-668 | DB row 'paid bags' | DB + wiki | reservations with 0 paid bags: 2000 of 2000; airline wiki.md:36 ("Each extra baggage is 50 dollars") | no |
| F8 | certificate amount: '$N' (send_certificate) | state_tracker/v4/listing_v4.py:640-644 | DB row 'certificate amount' | wiki | airline wiki.md:66 ("with the amount being $100 times the number of passengers") | no |
| F9 | no line for flight type, flight status, membership, user address, unchanged flights / passengers | state_tracker/v4/listing_v4.py:614-675 | DB rows 'flight type', 'flight status', 'membership', 'user address' | generic | they are not arguments of the call, or they do not change | no |
| F10 | insurance (book): the tiny question K17, not a form | state_tracker/v4/listing_v4.py:636-638 | DB row 'insurance' | generic | not a string form; decided by K17 | no |
| C1 | comment: forms 'counted on the v1 data' -> now 'the DB-only form check' | state_tracker/v4/listing_v4.py:6 | code comment | comment | points to output/eval_v4/form_check.md, section 'decisions, DB-only' | comment only |
| C2 | comment: ambiguity rule 'after the v1 form check' -> now 'the DB-only form check' | state_tracker/v4/helpers_go_ahead_v4.py:18 | code comment | comment | the rule is P5 + P6 above (DB counts) | comment only |
| C3 | comment: test docstring 'form-check traps' -> DB-only form check | tests/test_v4_listing.py:6 | code comment | comment | the traps are DB facts (P5, R4, R7, R8, F1) | comment only |

Old table rows with no decision ('-': users with 2+ cards, items per order, option names, saved passengers per user) stay information only.

## How to rerun
```
cd /home/azureuser/code_projects/predicate_correctness && PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1 /home/azureuser/miniconda3/bin/python3 -B scoring/v4_form_check.py
```
