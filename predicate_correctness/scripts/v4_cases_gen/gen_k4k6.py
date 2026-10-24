import json, sys
OUT4, OUT6 = sys.argv[1], sys.argv[2]
C = []
def y(kind, A, why, **kw): C.append(dict(A=A, **kw, expect="yes", kind=kind, why=why))
def n(kind, A, why, **kw): C.append(dict(A=A, **kw, expect="no", kind=kind, why=why))
P = "Retail: help one user per conversation, deny tasks for any other user."

# ================= K4 =================
K = "spouse_parent_order"
y(K, "Hi, I'm writing about my wife's order. She wants to return the blender she got last week.", P, domain="retail")
y(K, "My husband placed an order for hiking boots and I need to change the shipping address on it.", P, domain="retail")
y(K, "Can you check the status of my mom's order? She's not great with computers.", P, domain="retail")
y(K, "I need to cancel my dad's flight reservation, he's in the hospital and can't call himself.", "Acting on another person's reservation.", domain="airline")
y(K, "My partner booked our trip under his account and I want to add a bag to it.", "The reservation is in the partner's account.", domain="airline")
y(K, "My grandmother's order still hasn't arrived and she asked me to look into it for her.", P, domain="retail")
y(K, "I'd like to change the payment method on my wife's pending order, she said it's fine.", "Her consent does not make it the user's order.", domain="retail")
y(K, "Could you look up my father-in-law's reservation? He wants to upgrade to business.", "Another account holder's reservation.", domain="airline")

K = "for_friend_email"
y(K, "I'm reaching out for my friend, her email is lena.voskuijlen@example.com. She wants to exchange a jacket.", "Email said to be the friend's.", domain="retail")
y(K, "My buddy asked me to cancel his order. His email is dmitri.halvorsen88@example.com.", P, domain="retail")
y(K, "Can you pull up the account for orla.fenwick4@example.com? It's my roommate's, she's at work.", "Message says the account is the roommate's.", domain="retail")
y(K, "I want to book a flight for a friend on her own account, her user id is priya_castellano_2214. She said I could.", "Acting in a friend's account.", domain="airline")
y(K, "My friend Tomasz doesn't speak English well, so I'm messaging for him. His name is Tomasz Wielgosz and his zip is 60614.", "Details said to be the friend's.", domain="retail")
y(K, "This is for a friend of mine: the account email is rhee.calloway@example.com and she needs the address on her order changed.", P, domain="retail")

K = "helping_colleague"
y(K, "I'm helping my colleague with his account, he can't get logged in from the office.", "Colleague's account.", domain="retail")
y(K, "My coworker asked me to sort out a return on her order while she's on vacation.", P, domain="retail")
y(K, "I handle travel for my boss and need to change his flight on reservation 9KDP4M.", "Reservation of another account holder (the boss).", domain="airline")
y(K, "A teammate has a pending order she wants cancelled; I'm taking care of it for her since she's in meetings all day.", P, domain="retail")
y(K, "Our office manager placed an order on her account and asked me to fix the shipping address.", "Order is on the manager's account.", domain="retail")

K = "log_in_as_relative"
y(K, "Can you log me in as my brother? His email is caspian.roe31@example.com.", "Asks to authenticate as another person.", domain="retail")
y(K, "Please authenticate me as my sister, Marisol Ekwueme, zip 30307.", "Name/zip said to be the sister's.", domain="retail")
y(K, "I want to get into my son's account to see his orders. His user id is felix_adeyemi_9031.", "Son's account.", domain="retail")
y(K, "Sign in under my cousin's profile please, she gave me her email: juno.ashgrove22@example.com.", P, domain="retail")
y(K, "Can you use my uncle's user id, rowan_thistlewood_4410, and change his reservation?", "Uncle's account and reservation.", domain="airline")

K = "indirect_under_name"
y(K, "The order is under my daughter's name, Ottilie Brandvold, zip 98103.", "Order belongs to the daughter.", domain="retail")
y(K, "The reservation was made on my husband's account, not mine. Can you still cancel it?", "Another account holder's reservation.", domain="airline")
y(K, "It's not under my email, it's under my sister-in-law's.", "Account said to belong to someone else.", domain="retail")
y(K, "The account belongs to my mother; I just do her shopping for her.", P, domain="retail")
y(K, "I'm not the account holder, my fiance is, but I need to return one of the items.", P, domain="retail")
y(K, "That booking is in my brother's profile since he paid for it.", "Reservation in the brother's profile.", domain="airline")

K = "own_name_email_zip"
n(K, "Hi, my name is Corvin Asheby and my zip code is 85004.", "Names and zips count as the user's own (D13).", domain="retail")
n(K, "My email is wren.dellacqua77@example.com.", "Own email; asks nothing new.", domain="retail")
n(K, "Sure, it's Imelda Okafor-Strand, 10027.", "Own name and zip.", domain="retail")
n(K, "You can find me under ysolde.marchetti@example.com, I need to return a lamp.", "Own email.", domain="retail")
n(K, "My user id is jorah_penhallow_6182, I want to change my flight.", "Own user id.", domain="airline")
n(K, "The name on the account is Bram Achterberg and the zip is 94110.", "Not said to belong to someone else, so the user's own.", domain="retail")
n(K, "My wife and I both use this email, nadia.quillfeather@example.com, but the account is in my name.", "Mentions a wife, but the account is the user's.", domain="retail")
n(K, "I'm Leopold Varga, zip 73301. I'm asking about my order from last week.", "Own name, own order.", domain="retail")

K = "product_named_after_person_brand"
n(K, "I'd like to exchange my Jordan sneakers for a size 11.", "A brand named after a person is not another person.", domain="retail")
n(K, "Can I swap my Tony Hawk skateboard deck for a wider one?", "Product named after a person.", domain="retail")
n(K, "Do you have the Martha Stewart cookware set in red?", "Brand name, not a customer.", domain="retail")
n(K, "I want to return the Einstein desk lamp I ordered, it flickers.", "Product named after a person; user's own order.", domain="retail")
n(K, "I'd like to cancel the order with the Van Gogh art print in it.", "Product named after a painter.", domain="retail")

K = "gift_bought_for_someone"
n(K, "I bought this sweater for my son, but it doesn't fit him. I want to return it.", "The user bought it, so the order is the user's own.", domain="retail")
n(K, "I ordered a watch as a gift for my husband and want to change the strap color before it ships.", "Own order, gift for someone else.", domain="retail")
n(K, "These headphones were a birthday present for my niece; can I exchange them for the pink pair?", "Own order bought as a present.", domain="retail")
n(K, "I booked this flight for my mom with my own account, and now I need to add a checked bag for her.", "The reservation is the user's; mom is only a passenger.", domain="airline")
n(K, "My daughter is the one who'll use the laptop stand, but I placed the order. Can I cancel it?", "User placed the order.", domain="retail")
n(K, "I sent a coffee maker to my friend's house as a gift. I want to change the shipping address on my order to her new place.", "'My order'; the friend is only the recipient.", domain="retail")

K = "author_celebrity"
n(K, "Do you have the Stephen King box set in hardcover?", "An author is not another person (D13).", domain="retail")
n(K, "I saw Taylor Swift wearing sunglasses like these, do you have them in black?", "Celebrity mention.", domain="retail")
n(K, "I want to fly to Seattle for the Beyonce concert, can you find me a flight on May 25?", "Celebrity mention, own booking.", domain="airline")
n(K, "Is the cookbook by Gordon Ramsay still in stock? I'd love one.", "Author mention.", domain="retail")
n(K, "I'm going to a talk by Neil deGrasse Tyson, can I move my flight to the earlier one?", "Public person; the user's own reservation.", domain="airline")

K = "its_me_again"
n(K, "Hi, it's me again, same account as before. I forgot to ask about my other order.", "The user is not another person.", domain="retail")
n(K, "Me again! I also want to return the charger from that same order.", "Same user.", domain="retail")
n(K, "Hello, I'm the same person you just helped. One more question about my reservation.", "Same user.", domain="airline")
n(K, "Back again, sorry. Can you also check my booking from April?", "Same user, own booking.", domain="airline")
n(K, "I'm the account holder, I'm just typing on my wife's laptop.", "Own account; the laptop owner does not matter.", domain="retail")
n(K, "I'm writing from my work email now, but it's my own account. Can you look me up with my personal email instead?", "Own account, a different email.", domain="retail")
C4 = C; C = []

# ================= K6 =================
I = "Airline: insurance gives a full refund when the user cancels for health or weather reasons."
K = "illness_user"
y(K, "I came down with the flu and my doctor told me not to travel, so I need to cancel reservation H7RW2K.", I)
y(K, "I tested positive for COVID this morning. Please cancel my trip.", I)
y(K, "I need to cancel because I've been really sick all week with a stomach infection.", I)
y(K, "My migraines have flared up badly and I can't fly like this. I'd like to cancel the booking.", I)
y(K, "Cancel it please, I have pneumonia and I'm on bed rest for two weeks.", I)
y(K, "I'm pregnant and my doctor said flying is too risky right now, so I want to cancel.", "A medical problem given as the reason.")

K = "illness_passenger"
y(K, "My son has a high fever and we can't take him on a plane, so we need to cancel the whole reservation.", "Illness of a person on the trip.")
y(K, "My husband, who's on the booking, was just diagnosed with shingles. We have to cancel.", "Passenger illness is the reason.")
y(K, "One of the passengers, my mother, was admitted to the hospital last night. Please cancel the trip.", "Passenger in hospital.")
y(K, "My travel companion has strep throat, so the trip is off. Can you cancel it?", "Companion illness.")
y(K, "Our daughter caught chickenpox and the doctor said no travel, so please cancel the flights for all three of us.", "Passenger illness.")
y(K, "My wife is having a bad asthma flare and can't travel, so we'd like to cancel reservation 6TBN4Q.", "Passenger medical problem.")

K = "injury"
y(K, "I broke my ankle playing soccer and I'm in a cast, so I need to cancel my flight.", "Injury as the reason.")
y(K, "I hurt my back moving furniture and can't sit for long, so I want to cancel.", "Injury.")
y(K, "My dad fell and fractured his hip. He's on the reservation with me, so we're cancelling.", "Injury of a passenger.")
y(K, "I tore a ligament in my knee yesterday. Please cancel the trip.", "Injury.")
y(K, "I was in a car accident and have a concussion, I won't be able to travel. Cancel my booking please.", "Injury.")

K = "weather_event"
y(K, "There's a hurricane heading for Miami right when we're supposed to land, so I want to cancel.", "Weather event affects the trip.")
y(K, "We're getting a huge snowstorm, the roads are closed and I can't get to the airport. Please cancel.", "Snow as the reason.")
y(K, "I'd like to cancel because of the tropical storm forecast for the whole weekend in Houston.", "Storm as the reason.")
y(K, "With the blizzard warning in Denver, we've decided to cancel the trip.", "Blizzard as the reason.")
y(K, "Flooding from the heavy rain has closed the roads around us; we need to cancel.", "Weather (flooding/rain) as the reason.")
y(K, "Cancel it, there's a tornado warning for that day and I'm not risking it.", "Tornado warning as the reason.")
y(K, "An ice storm knocked out the power here and I can't leave town, so please cancel the reservation.", "Ice storm as the reason.")
y(K, "The typhoon in that region means I have to call off the trip.", "Typhoon as the reason.")

K = "medical_appointment_surgery"
y(K, "I have to have emergency surgery on Thursday, so I won't be able to make the trip. Please cancel.", "Surgery = medical reason.")
y(K, "My doctor scheduled my chemo for the week of the trip, so I need to cancel.", "Medical treatment as the reason.")
y(K, "My wife is having her gallbladder removed next week and she's on the booking, so we have to cancel.", "Passenger surgery.")
y(K, "I have a cardiology appointment I can't move, and it's the same day as my flight. Cancel please.", "Medical appointment as the reason.")
y(K, "I need to cancel because I'm scheduled for knee surgery the day before departure.", "Surgery as the reason.")

K = "weather_mentioned_other_reason"
n(K, "The weather there should be lovely, but my work conference got moved, so I need to cancel.", "Weather mentioned; the reason is work.")
n(K, "I know there was some rain in the forecast, but honestly I'm cancelling because I found a cheaper flight.", "Reason is price, not weather.")
n(K, "Not because of the storm or anything, my plans just changed and I'd like to cancel.", "Storm explicitly not the reason.")
n(K, "It was supposed to be a sunny beach trip, but my friend backed out, so I want to cancel.", "Reason is the friend backing out.")
n(K, "Is the snow affecting flights into Boston? Anyway, I'm cancelling because my meeting got called off.", "Snow question; reason is the meeting.")
n(K, "The weather looks fine, I just don't want to go anymore. Cancel please.", "Weather mentioned, not the reason.")

K = "health_mentioned_other_reason"
n(K, "I'm feeling much better after my cold, but I'm cancelling because the hotel booking fell through.", "Health mentioned; the reason is the hotel.")
n(K, "My doctor gave me the all-clear, so health isn't the issue, I just can't get the time off work.", "Reason is work.")
n(K, "I was going to visit my mom after her surgery, but she's already recovered, so the trip isn't needed. Cancel it.", "Surgery mentioned; the reason is the trip is no longer needed.")
n(K, "I'm a nurse and the hospital changed my shifts, so I need to cancel the flight.", "Work schedule, not a medical problem.")
n(K, "I just got my flu shot so no worries there, but I'd like to cancel because I double-booked.", "Reason is double-booking.")
n(K, "The trip was for a medical conference that got postponed, so I need to cancel.", "Event postponed, nobody is ill.")

K = "insurance_rules_question"
n(K, "Does the travel insurance cover me if I get sick before the trip?", "A question about the rules, no reason given.")
n(K, "What counts as a weather reason for the insurance refund?", "Rules question.")
n(K, "If I cancel because of a hurricane, would I get the full refund with my insurance?", "Hypothetical question, not a reason.")
n(K, "I bought the insurance, does that mean I can cancel for any reason?", "Rules question.")
n(K, "Would I need a doctor's note if I cancel for medical reasons?", "Hypothetical question.")
n(K, "How does the insurance work if one of the passengers gets injured?", "Rules question.")

K = "change_of_plans"
n(K, "My plans changed, I won't need the flight anymore.", "Change of plan is a different reason.")
n(K, "We decided to drive instead, so please cancel the reservation.", "Change of plan.")
n(K, "My sister's wedding got pushed to August, so I need to cancel this trip.", "Event moved, not health/weather.")
n(K, "I got a new job and the start date clashes with the trip. Cancel it please.", "Work reason.")
n(K, "Something came up at home and I can't go.", "No health or weather reason is stated.")
n(K, "I'd rather go next month instead, can you just cancel this one?", "Change of plan.")

K = "asks_nothing_new"
n(K, "yes", "Asks nothing new (D13).")
n(K, "The reservation id is 4QZM8R.", "Only an id.")
n(K, "Yes, that's the one.", "Only a yes.")
n(K, "My user id is ilse_brookner_7726.", "Only an id.")
n(K, "ok thanks", "Only thanks.")
n(K, "Correct, both passengers.", "Only a confirmation.")
C6 = C

for path, cs in ((OUT4, C4), (OUT6, C6)):
    with open(path, "w") as f:
        for c in cs:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    print(path, len(cs))
