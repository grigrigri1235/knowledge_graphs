import json, os

OUT = "/home/azureuser/code_projects/predicate_correctness/output/eval_v4/cases"
os.makedirs(OUT, exist_ok=True)

# ---------------- K7v4: a reason for cancelling the reservation ----------------
K7_W_REASON = "cancel needs a reason (change of plan, airline cancelled flight, or other reasons)"
K7 = []
def k7(exp, kind, a, why):
    K7.append(dict(A=a, expect=exp, kind=kind, why=why))

for a, why in [
    ("I need to cancel reservation QX7T2M. My plans changed and I'm no longer going to Denver.", "change of plan is a listed policy reason"),
    ("My conference got moved to next month, so I won't need this trip. Please cancel it.", "moved event = change of plan"),
    ("We decided to stay home for the holidays instead, so please cancel the booking.", "deciding not to go = change of plan"),
    ("Our wedding got postponed, so the trip is off. I'd like to cancel 8KQ2WD.", "postponed event = change of plan"),
    ("The airline cancelled my flight on May 18, so I want to cancel the whole reservation.", "airline cancelled flight is a listed policy reason"),
    ("You guys cancelled my outbound flight, so there's no point keeping this booking. Cancel it.", "airline cancelled flight reason"),
    ("I got an email saying my connecting flight was cancelled by the airline. I want to cancel the reservation.", "airline cancelled flight reason"),
    ("Since your airline scrapped the 7am flight, please cancel my trip ZK3P9A.", "airline cancelled flight in other words"),
    ("My mother is in the hospital and I can't travel, please cancel reservation M4RJ7V.", "health problem = other reason"),
    ("There's a hurricane forecast for Miami that week, so I'd like to cancel.", "weather = other reason"),
    ("I found a much cheaper fare on another airline, so I want to cancel this one.", "price = other reason"),
    ("My visa didn't come through in time, so I have to cancel T9WLQ2.", "visa issue = other reason"),
]:
    k7("yes", "policy reason (change of plan / airline cancelled / other)", a, why + "; " + K7_W_REASON)

for a, why in [
    ("Change of plans.", "short answer to 'why?' naming change of plan"),
    ("Airline cancelled the flight.", "short answer naming airline cancellation"),
    ("Personal reasons.", "short answer; any reason counts (other reasons)"),
    ("My plans changed.", "short answer naming change of plan"),
    ("I'm sick.", "short answer giving a health reason"),
    ("Work conflict.", "short answer giving a work reason"),
    ("Found a cheaper option.", "short answer giving a price reason"),
    ("Family emergency.", "short answer giving an other reason"),
]:
    k7("yes", "short answer to 'why?'", a, why + "; spec: a short answer to the reason question counts")

for a, why in [
    ("Hi, I'm zephyr_quill_8104. I booked a round trip to Seattle, reservation B2HX6N, but my company called off the offsite, so I'd like to cancel it and know where the refund goes.", "reason (offsite called off) inside a request with ids and a refund question"),
    ("Can you look up J7PZ4K? Both passengers are on it. My son broke his leg last weekend, so none of us are flying. I want to cancel everything.", "injury reason inside a longer cancel request"),
    ("Hello. I have two reservations, R3VD8F and W6NC2Y. The second one I need to cancel because the event I was flying to got called off. The first one stays.", "reason given for one of two reservations"),
    ("I booked this trip on impulse yesterday and realized I can't take the time off work. Please cancel H5QM9T. I think I'm still within 24 hours?", "can't get time off = change of plan, with a 24h question"),
    ("My flight from Boston on May 20 was cancelled by you, and the rebooking options don't work for me. I'd rather just cancel the reservation and get my money back.", "airline cancelled flight inside a longer request"),
    ("Hey, quick one: we're not going to Phoenix after all because my sister moved her graduation, so cancel reservation D8XK3L, user id orla_vantrees_2290.", "change of plan reason mixed with ids"),
    ("I'd like to cancel my business class booking N2FJ7W. The meeting it was for was moved to a video call, so I don't need to fly.", "reason after the request: meeting moved online"),
    ("There's a snowstorm expected in Chicago on the day of my connection and I don't want to risk being stranded. Please cancel P4TB9Q; I did buy insurance.", "weather reason inside a request mentioning insurance"),
    ("Good afternoon. I need to cancel V7GL2S for me and my husband. He just started a new job and can't get the days off.", "work reason for the trip being off"),
    ("Hi there, I have a one-way to Atlanta next Friday. My client meeting got cancelled so I don't need to go anymore. Can you cancel it?", "reason (meeting cancelled) inside a polite request"),
]:
    k7("yes", "reason inside a longer request", a, why + "; any reason counts")

for a, why in [
    ("Please cancel my reservation QX7T2M.", "request with id, no why"),
    ("I want to cancel my trip to Denver.", "names the trip, gives no why"),
    ("Can you cancel the whole booking for both passengers?", "scope of the cancel, no why"),
    ("Cancel it, please. All the flights on it.", "only 'cancel it'"),
    ("I'd like to cancel my upcoming flight. My user id is zephyr_quill_8104.", "cancel + user id, no why"),
    ("Hi, I need a cancellation on reservation 8KQ2WD, the round trip.", "cancel request with trip type, no why"),
    ("Just cancel the reservation, I don't want to move it to another date.", "refusing a change is not a reason for cancelling"),
    ("I'd like to go ahead and cancel the booking I made last week.", "booking date is not a reason"),
]:
    k7("no", "please cancel it", a, why + "; only saying 'cancel it' is no")

for a, why in [
    ("ZK3P9A", "id only"),
    ("It's reservation M4RJ7V.", "id only"),
    ("The flight is on May 21.", "date only"),
    ("My user id is orla_vantrees_2290.", "user id only"),
    ("The one departing May 19 from Newark.", "date and origin only"),
    ("T9WLQ2, booked on May 2.", "id and booking date only"),
    ("It's the second reservation on my profile, B2HX6N.", "id only"),
    ("The trip on the 25th of May.", "date only"),
]:
    k7("no", "id or date only", a, why + "; only an id or a date is no")

for a, why in [
    ("If I cancel, how much of my money will I get back?", "refund amount question"),
    ("Will the refund go back to my credit card or come as a certificate?", "refund method question"),
    ("How long does a refund take after cancelling?", "refund timing question"),
    ("Do I get a full refund if I cancel the economy booking?", "refund rule question"),
    ("Before you cancel, can you tell me if the gift card part is refunded too?", "refund question before cancel"),
    ("What happens to the travel certificate I used if the trip is cancelled?", "certificate refund question"),
    ("Is there a cancellation fee, or is it a full refund?", "fee question"),
]:
    k7("no", "question about refunds", a, why + "; a refund question gives no reason")

for a, why in [
    ("Yes.", "bare yes"),
    ("Yes, please cancel it.", "yes + cancel"),
    ("Yep, that's the right one.", "confirms the reservation only"),
    ("Yes, both passengers.", "yes + scope"),
    ("Correct, go ahead.", "go-ahead only"),
    ("Yes, I'm sure I want to cancel.", "certainty is not a reason"),
    ("Yes, cancel the whole trip.", "yes + scope"),
]:
    k7("no", "yes", a, why + "; only a yes is no")

# ---------------- K8v4: the user complains about a flight problem ----------------
K8 = []
def k8(exp, kind, a, why):
    K8.append(dict(A=a, expect=exp, kind=kind, why=why))

REF_C = "Refund rule: certificate if the user complains about cancelled flights"
REF_D = "Refund rule: certificate if the user complains about delayed flights"
for a in [
    "My flight to Orlando was cancelled and now I'm stuck at the airport with two kids. This is ridiculous.",
    "You cancelled my flight with no warning and I missed my sister's wedding.",
    "I just found out my 6am flight got cancelled. I'm really frustrated, I had a meeting to get to.",
    "Your airline cancelled my return flight and nobody even told me. Unacceptable.",
    "The flight on my reservation C9RW5H was cancelled and it's ruined my whole trip.",
    "I'm so upset. The first leg was cancelled and now I can't make my connection.",
    "That's the third time this year you've cancelled one of my flights. I'm fed up.",
    "My cancelled flight cost me a hotel night and a lost day of work.",
]:
    k8("yes", "cancelled complaint", a, REF_C + "; user says it was cancelled and it hurts them")
for a in [
    "My flight has been delayed four hours and I'm going to miss my connection. This is terrible.",
    "The flight I'm on today is delayed again and I'm losing a full day of vacation.",
    "Your delay made me miss my daughter's recital. I'm very unhappy.",
    "We've been sitting at the gate for hours because the flight is delayed. This is awful service.",
    "My outbound flight got pushed back five hours and I'll miss my meeting. I'm not happy about it.",
    "The delay on my flight out of Las Vegas is ridiculous, I've been waiting since noon.",
    "I'm extremely frustrated that my flight on reservation 8KQ2WD is delayed and I'll arrive after midnight.",
    "My flight is running late again and it's messing up all my plans.",
]:
    k8("yes", "delayed complaint", a, REF_D + "; user says it is delayed and it hurts them")
for a in [
    "One flight was cancelled and the replacement was delayed three hours. Worst trip ever.",
    "First my flight got cancelled, then the one you moved me to is delayed. I'm exhausted and angry.",
    "Between the delay on the outbound and the cancellation of my return, this trip has been a nightmare.",
]:
    k8("yes", "both (cancelled and delayed)", a, "Refund rules for cancelled and delayed flights; both problems named as a complaint")
for a in [
    "my flight got cxld and now im stuck in denver, this is so annoying",
    "flight dleayed 3 hrs, gonna miss my connection, not ok",
    "Ur airline canceld my flite and i have no way home!!",
    "the flight is delayd agian and i'm missing my sons game",
    "my flght was cancelld last min, totally ruined my plans",
]:
    k8("yes", "typos", a, "Refund rules: a complaint about a cancelled/delayed flight still counts when misspelled")
for a in [
    "My flight was cancelled and I had to sleep at the airport. I want some kind of compensation for this.",
    "The delay made me miss a business dinner. What are you going to do to make it up to me?",
    "You cancelled my flight and I lost a hotel booking. I expect a voucher at least.",
    "My flight was delayed six hours. I'd like to change the reservation and get a certificate for the trouble.",
    "This cancelled flight wrecked my vacation. I want to be compensated.",
    "The flight delay cost me a whole day. Can I get a credit for that?",
]:
    k8("yes", "complaint + request for compensation", a, "Refund rules: complaint about the flight problem, plus an ask (the ask does not remove the complaint)")

for a in [
    "Is my flight to Orlando tomorrow on time?",
    "Can you check whether the flight on reservation ZK3P9A is delayed?",
    "I heard there might be storms. What's the status of my 3pm flight?",
    "Has my return flight on May 20 been cancelled, or is it still scheduled?",
    "What time is my flight departing now? I want to know if anything changed.",
    "Could you tell me if my connecting flight is still running?",
    "Is the flight I'm booked on today in the air yet?",
    "Is there any delay expected on my flight out of Phoenix?",
]:
    k8("no", "status question", a, "only asking about a flight's status is no; no complaint")
for a in [
    "I'd like to move my flight to a day later, please.",
    "Please cancel reservation M4RJ7V, my plans changed.",
    "Can I switch both flights to the morning departures?",
    "I want to upgrade my reservation to business class.",
    "My meeting moved, so I need to change my flight to Thursday.",
    "I'd like to cancel my trip because I'm not feeling well.",
    "Can you change my return flight to an earlier one on the same day?",
    "Please cancel the flight; I got a better deal on another airline.",
]:
    k8("no", "change / cancel request without a complaint", a, "only asking to change or cancel a booking is no; the flight itself had no problem")
for a in [
    "The seat I got was broken and wouldn't recline the whole flight. Really disappointing.",
    "The food on my last flight was terrible, I couldn't eat any of it.",
    "The agent I spoke to yesterday was rude and hung up on me.",
    "I'm upset that I was charged $50 for a bag I thought was free.",
    "Your website kept crashing while I was trying to book. Very frustrating.",
    "My suitcase came out damaged and the handle was torn off.",
    "I was put in a middle seat even though I picked a window. Not happy.",
]:
    k8("no", "complaint about something else (seat, food, agent)", a, "complaint, but not that the flight was delayed or cancelled")
for a in [
    "Yes.",
    "It's QX7T2M.",
    "My user id is zephyr_quill_8104.",
    "Thanks.",
    "Two passengers.",
    "The one on May 17.",
    "Okay, go ahead.",
]:
    k8("no", "asks nothing new", a, "D13 default: a message that only gives an id, a choice, a thank-you or a yes is no")

# ---------------- K10v4: the user explicitly asks for compensation ----------------
K10 = []
def k10(exp, kind, a, why):
    K10.append(dict(A=a, expect=exp, kind=kind, why=why))

R10 = "Refund rule: do not offer unless the user explicitly asks for some compensation"
for a in [
    "I want compensation for the cancelled flight.",
    "I'm requesting compensation for the delay.",
    "I think I deserve to be compensated for this mess.",
    "Please compensate me for the missed connection.",
    "Is there any compensation for my cancelled flight? I'd like it.",
    "I demand some compensation, this is unacceptable.",
    "I'd like to file for compensation for the five-hour delay.",
    "Given what happened, I expect to be compensated.",
]:
    k10("yes", "\"I want compensation\"", a, R10 + "; the word compensation is asked for")
for a in [
    "What are you going to give me for this?",
    "So what do I get for all this trouble?",
    "What will you do to make this right for me?",
    "How are you going to make it up to me?",
    "Surely you can offer me something for ruining my trip?",
    "What can you give me to make up for the delay?",
]:
    k10("yes", "\"what will you give me for this\"", a, R10 + "; asks to be given something to make up for a problem")
for a in [
    "Can I get a travel voucher for the cancellation?",
    "I'd like a certificate for the inconvenience.",
    "Please give me some credit toward a future flight.",
    "Can you send me a travel certificate for both passengers?",
    "I want a voucher for my next trip because of the delay.",
    "Could you add some credit to my account for this?",
    "At minimum I'd like a certificate to use next time.",
    "Is a flight credit possible for what happened? I'd like one.",
]:
    k10("yes", "voucher / credit / certificate ask", a, R10 + "; voucher, credit or certificate is compensation")
for a in [
    "I want $200 for the trouble this delay caused me.",
    "Will you pay for the hotel I had to book because of the cancellation?",
    "I expect cash compensation for the missed day of work.",
    "Please reimburse my taxi and meals from the delay.",
    "On top of the refund, I'd like some money for the hassle.",
    "Can you pay me back for the rental car I lost because of the delay?",
    "Send me $100 for the inconvenience, please.",
    "I want to be paid for the night I spent at the airport.",
]:
    k10("yes", "money ask", a, R10 + "; money to make up for a problem (not a refund of the booking)")

for a in [
    "My flight was cancelled, so please refund my ticket.",
    "Since you cancelled the flight, I want a full refund of the reservation.",
    "Cancel the booking and refund me to my credit card.",
    "Can I get my money back for the cancelled trip?",
    "I'd like the refund for reservation QX7T2M sent to my original card.",
    "When will I get my refund for the cancelled reservation?",
    "Please make sure the gift card I paid with gets refunded.",
    "Refund the whole booking, I'm not flying.",
]:
    k10("no", "refund of a cancelled booking", a, "asking only to refund a booking is no (refund goes to original payment, not compensation)")
for a in [
    "Please put me on the next available flight to Denver.",
    "Can you rebook me on the evening flight instead?",
    "I'd like to change my return to May 22.",
    "Switch me to the nonstop, please.",
    "Can you move both passengers to a later flight because of the delay?",
    "Upgrade me to business for the rest of the trip, I'll pay the difference.",
    "Change the flight to the morning one so I can make my meeting.",
    "Please add one checked bag to my reservation.",
]:
    k10("no", "change request", a, "asking only to change a booking is no")
for a in [
    "My flight was delayed for five hours and I missed my meeting.",
    "You cancelled my flight and I'm stuck in Chicago.",
    "This is the worst airline experience I've ever had.",
    "The delay ruined our anniversary dinner.",
    "I'm really upset that nobody told me the flight was cancelled.",
    "I've been waiting at the gate since 6am.",
    "This is the second cancellation this month.",
]:
    k10("no", "complaint without an ask", a, R10 + "; a complaint alone is not an explicit ask")
for a in [
    "Yes.",
    "It's ZK3P9A.",
    "Two passengers.",
    "My user id is orla_vantrees_2290.",
    "Thank you.",
    "The flight on May 18.",
    "I'm a gold member, if that matters.",
]:
    k10("no", "asks nothing new", a, "D13 default: a message that only gives an id, a date, a fact or a thank-you is no")

# ---------------- K12v4: the agent's reply offers compensation ----------------
K12 = []
def k12(exp, kind, a, why):
    K12.append(dict(A=a, expect=exp, kind=kind, why=why))

R12 = "Refund rule: the agent can offer a certificate as a gesture"
for a in [
    "I'm sorry about the cancelled flight. Since you're a gold member, I can offer you a $100 travel certificate as a gesture.",
    "Because there are two passengers on the reservation, I can send you a certificate worth $200 for the cancellation.",
    "I've confirmed the delay. I can offer a $50 certificate for each passenger, $150 in total.",
    "As a gesture, I'll issue a $300 travel certificate to your account for the three passengers.",
    "Would you like me to send you a $100 certificate for the trouble?",
    "I can provide a $50 travel certificate since your flight was delayed and you've changed the reservation.",
    "I'm going to send a $200 certificate to your profile now to make up for the cancellation.",
    "Here's what I can do: a $150 certificate, usable on a future booking.",
]:
    k12("yes", "certificate offer with amount", a, R12 + " ($100 / $50 per passenger); an amount is named")
for a in [
    "I'm sorry for the disruption. I can offer you a travel certificate as a gesture of goodwill.",
    "Since you have travel insurance, you're eligible for a certificate for the cancelled flight. Shall I send it?",
    "I'd be happy to send you a certificate for the inconvenience.",
    "To make up for this, I'll issue a travel certificate to your account.",
    "You qualify for a gesture certificate; I can add it to your profile.",
    "Let me send you a certificate to apologize for the delay.",
]:
    k12("yes", "certificate offer without amount", a, R12 + "; offered with no amount still counts")
for a in [
    "I can give you a $100 voucher toward your next flight.",
    "I'll add a travel credit to your account for the trouble.",
    "As compensation, I can offer you a flight credit of $50.",
    "I can provide you with a voucher for a future trip to make up for this.",
    "We'd like to offer you some credit on your account for the delayed flight.",
    "I can put $100 of credit on your profile as a goodwill gesture.",
]:
    k12("yes", "voucher / credit wording", a, R12 + "; voucher or credit is the same kind of compensation")
for a in [
    "Once I change your flight, I'll send you $50 per passenger as a certificate.",
    "After the cancellation goes through, I can issue you a $100 certificate.",
    "If you'd like me to rebook you, I'll follow up with a certificate for the delay.",
    "Once you confirm the new flights, I'll send a $100 certificate for the two of you.",
    "When the change is complete, you'll also receive a travel certificate for your trouble.",
]:
    k12("yes", "conditional promise", a, "Refund rule (delayed): certificate after changing/cancelling; a promise counts as an offer")
for a in [
    "Thanks for waiting. I've checked reservation W6NC2Y: your May 18 flight from Boston to Atlanta was cancelled, and you're a silver member with two passengers on the booking. I can cancel the reservation for you, and the full amount will be refunded to your original payment method in 5 to 7 business days. In addition, I can offer a $200 travel certificate as a gesture for the cancellation. Would you like me to proceed with the cancellation?",
    "Here are the options on the same route: a 9:10am departure in economy at $214 and a 1:45pm departure at $198. The price difference would be charged to your gift card. Also, because your original flight was delayed and you have insurance, I'll send you a $50 certificate once the change is done. Which option do you prefer?",
    "I've updated your reservation to the 2:30pm flight on May 19 in economy, keeping your return the same. Your gift card was charged the $62 difference and your two checked bags carried over. Since you're a gold member and your original flight was delayed, I've also prepared a $100 certificate ($50 per passenger) that I'll send to your profile right away. Is there anything else you need?",
    "Let me summarize: reservation C9RW5H is a round trip in business for one passenger. The outbound on May 20 was cancelled by the airline, so you can cancel the whole booking for a full refund to your credit card in 5 to 7 business days. Because you fly business, I can also give you a $100 travel voucher for the trouble. Do you want to cancel, or would you rather I look at other flights first?",
    "I understand how stressful today has been. Here's where things stand: your flight is delayed by about three hours, and the departure gate hasn't changed. If you'd like to move to tomorrow morning's flight, I can do that in the same cabin. Once that change is made, I'll add a $50 credit to your account to make up for the delay.",
]:
    k12("yes", "offer inside a long reply", a, R12 + "; the offer is one sentence among refund / price / flight details")

for a in [
    "Your reservation has been cancelled. The full $412 will be refunded to your original credit card within 5 to 7 business days.",
    "Since the airline cancelled the flight, you'll get a full refund to your original payment methods.",
    "The refund for both passengers will go back to the gift card you used.",
    "I've processed the cancellation; you'll see the money back in 5 to 7 business days.",
    "Because you booked within the last 24 hours, the reservation can be cancelled for a full refund.",
    "The certificate you used to pay isn't refundable, but the credit card portion of $180 will be refunded.",
    "Your refund of $640 has been issued to your original payment method.",
    "I'll cancel it and refund you the full fare. Would you like me to proceed?",
]:
    k12("no", "refund", a, "Cancel rule: refund to original payment methods is a normal refund, not compensation")
for a in [
    "I'm sorry, but as a regular member flying economy without insurance, you're not eligible for a certificate.",
    "Unfortunately the policy doesn't allow compensation for this booking.",
    "I checked your profile, and I'm afraid I can't offer a voucher for the delay in this case.",
    "There's no compensation available, since your flight wasn't actually delayed or cancelled.",
    "I understand your frustration, but I'm unable to issue any certificate for basic economy without insurance.",
    "I'm sorry, a travel certificate isn't something I can provide for this reservation.",
]:
    k12("no", "\"not eligible\"", a, "Refund rule: do not compensate regular/no insurance/economy; saying not eligible is no")
for a in [
    "The new flights are $86 cheaper, so the difference will be refunded to your gift card.",
    "Upgrading to business will cost an extra $320 in total, charged to your credit card.",
    "Adding two checked bags is $100, since each extra bag is $50.",
    "Travel insurance is $30 per passenger, so $90 for the three of you.",
    "The fare difference of $45 will be credited back to your original card.",
    "You have two free checked bags as a silver economy passenger; a third bag is $50.",
]:
    k12("no", "price difference / fees", a, "price difference, bag fees ($50) and insurance ($30) are not compensation")
for a in [
    "I'm really sorry about the delay and the trouble it caused you.",
    "I apologize for the cancelled flight; I know how frustrating that is. Let me look at your options.",
    "I'm so sorry your trip was disrupted. Would you like me to find you a new flight?",
    "My apologies for the inconvenience. I've rebooked you on the 4pm flight.",
    "I'm sorry to hear that. I understand how stressful a missed connection can be.",
]:
    k12("no", "apology without offer", a, "an apology gives nothing extra; no certificate, voucher or credit")
for a in [
    "Our policy only allows a gesture certificate for silver or gold members, insured bookings or business cabin, after a confirmed cancelled or delayed flight. Let me first look up your reservation details.",
    "Cancellations are allowed within 24 hours of booking, if the airline cancelled the flight, or with insurance for health or weather reasons.",
    "For delayed flights, any gesture could only be considered after the reservation is changed or cancelled, and only for eligible members. I'll need to check your booking first.",
    "Travel insurance covers a full refund when you cancel for health or weather reasons.",
    "The remaining balance of a travel certificate isn't refundable, and only one certificate can be used per booking.",
]:
    k12("no", "explaining the policy rules without offering", a, "describing the rules is not offering or promising anything")


def write(name, rows, prefix):
    ny = sum(r["expect"] == "yes" for r in rows)
    nn = sum(r["expect"] == "no" for r in rows)
    assert ny == 30 and nn == 30, (name, ny, nn)
    with open(os.path.join(OUT, name), "w") as f:
        iy = inn = 0
        for r in rows:
            if r["expect"] == "yes":
                iy += 1; cid = f"{prefix}-y{iy:02d}"
            else:
                inn += 1; cid = f"{prefix}-n{inn:02d}"
            f.write(json.dumps({"id": cid, **r}, ensure_ascii=False) + "\n")

write("K7.jsonl", K7, "K7v4")
write("K8.jsonl", K8, "K8v4")
write("K10.jsonl", K10, "K10v4")
write("K12.jsonl", K12, "K12v4")
print("ok")
