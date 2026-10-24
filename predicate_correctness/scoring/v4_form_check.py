#!/usr/bin/env python3
"""Tracker v4, part P1: the K2-style FORM CHECK, DATABASE ONLY ($0, no network, stdlib only).

The main idea in plain words: every form a v4 code line accepts must be backed by the tau-bench v1 DATABASE, by a
line of the policy wiki, or by a generic reason that needs no data. This script counts the forms that really occur in
the v1 databases and writes, for every v4 form decision, its basis and whether it changed.

Purity (docs/planning/tracker_v4/overview.md section 3: "we learned nothing about which action is right or wrong"):
this script reads ONLY
  ~/opt/tau-bench-59a200c/tau_bench/envs/{retail,airline}/data/*.json   (the v1 databases)
  ~/opt/tau-bench-59a200c/tau_bench/envs/{retail,airline}/wiki.md       (the policy text, cited by line number)
Every read goes through _read(), which refuses any other path. No task file, no user instruction, no expected
action, no conversation, no split file is read. tests/test_v4_form_check.py checks this by a source scan and by a
run that records every file opened.

An earlier version also counted the user-simulator task texts and their expected actions; that part was removed
(it leaked task knowledge into v4 form decisions), and so was the retail dev-20 overlap section (dev-20 is dropped
from the plan). The section "decisions, DB-only" of form_check.md re-bases every v4 form decision on DB / wiki /
generic reasons only.

Plan: docs/planning/tracker_v4/overview.md section 6 rule 8; predicate_table.md "K2-style check" column.
Writes predicate_correctness/output/eval_v4/form_check.md and form_check.json.
Run: PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1 python3 -B scoring/v4_form_check.py
"""
import hashlib
import json
import os
import re
from collections import Counter, defaultdict

TB = os.path.realpath(os.path.expanduser("~/opt/tau-bench-59a200c/tau_bench/envs"))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "output", "eval_v4")
OUT_MD = os.path.join(OUT_DIR, "form_check.md")
OUT_JSON = os.path.join(OUT_DIR, "form_check.json")
DOMAINS = ("retail", "airline")
DB_FILES = {"retail": ("users", "orders", "products"), "airline": ("users", "reservations", "flights")}
# the only paths this script may read: envs/<domain>/data/<name>.json and envs/<domain>/wiki.md
ALLOWED_READ = re.compile(r"^(retail|airline)/(data/[a-z_]+\.json|wiki\.md)$")

READ_LOG = []      # (relative path, sha256) of every file read, in order


def _read(rel):
    """Read one allowed input file (bytes). Anything that is not a DB json or a wiki.md is refused."""
    if not ALLOWED_READ.match(rel):
        raise PermissionError(f"v4_form_check reads only the DB json files and wiki.md, not {rel!r}")
    path = os.path.realpath(os.path.join(TB, rel))
    if os.path.relpath(path, TB) != rel:
        raise PermissionError(f"path escapes the tau-bench envs folder: {rel!r}")
    with open(path, "rb") as f:
        data = f.read()
    READ_LOG.append((rel, hashlib.sha256(data).hexdigest()))
    return data


def load(dom, name):
    if name not in DB_FILES[dom]:
        raise PermissionError(f"not a v1 database file: {dom}/{name}")
    return json.loads(_read(f"{dom}/data/{name}.json").decode("utf-8"))


WIKI = {}          # domain -> list of lines


def wiki_line(dom, needle):
    """'retail wiki.md:39' for the first wiki line that contains `needle` (case-insensitive); fails loudly."""
    if dom not in WIKI:
        WIKI[dom] = _read(f"{dom}/wiki.md").decode("utf-8").splitlines()
    for i, ln in enumerate(WIKI[dom], 1):
        if needle.lower() in ln.lower():
            return f"{dom} wiki.md:{i} (\"{needle}\")"
    raise SystemExit(f"wiki line not found: {dom}: {needle!r}")


# ----------------------------------------------------------------------------------------------- helpers
def pct(a, b):
    return f"{a} of {b} ({100.0 * a / b:.1f} %)" if b else f"{a} of 0"


def top(counter, n=8):
    return ", ".join(f"{k} {v}" for k, v in counter.most_common(n))


ROWS = []  # (section, kind, forms, count, decision, note)


def row(section, kind, forms, count, decision, note=""):
    ROWS.append((section, kind, forms, count, decision, note))


NUM = {}  # flat numbers for the json


def four_forms(pm):
    """4-digit forms of one payment method: the id's last 4 digits, a card's last_four."""
    out = []
    m = re.search(r"(\d+)$", pm["id"])
    if m:
        out.append(m.group(1)[-4:])
    if pm.get("last_four"):
        out.append(pm["last_four"])
    return out


def payment_counts(users, prefix):
    """Counts shared by both domains: kinds, id forms, cards, same brand / kind, 4-digit clashes, 5+ digits."""
    src, brand, id_forms = Counter(), Counter(), Counter()
    cards = []
    for uid, u in users.items():
        for pid, pm in u["payment_methods"].items():
            src[pm["source"]] += 1
            id_forms[re.sub(r"\d", "9", pid)] += 1
            if pm["source"] == "credit_card":
                cards.append((uid, pid, pm))
                brand[pm["brand"]] += 1
    per_user = defaultdict(list)
    for uid, pid, pm in cards:
        per_user[uid].append(pm)
    multi_kind = Counter()
    tail_clash = cross_clash = need5 = one_card = 0
    cross_examples = []
    for uid, u in users.items():
        pms = list(u["payment_methods"].values())
        for k, v in Counter(p["source"] for p in pms).items():
            if v >= 2:
                multi_kind[k] += 1
        if sum(1 for p in pms if p["source"] in ("credit_card", "gift_card")) == 1:
            one_card += 1
        if not pms:
            continue
        if max(Counter(p["id"][-4:] for p in pms).values()) >= 2:
            tail_clash += 1
        l4 = {p["last_four"] for p in pms if p["source"] == "credit_card"}
        hit = [p["id"] for p in pms if p["id"][-4:] in l4 and
               not (p["source"] == "credit_card" and p["id"][-4:] == p["last_four"])]
        if hit:
            cross_clash += 1
            cross_examples.append({"user": uid, "id": hit[0], "other_card_last_four": hit[0][-4:]})
        for p in pms:   # the id's 4-digit tail is also a 4-digit form of another method of the owner -> 5+ digits
            others = {f for q in pms if q["id"] != p["id"] for f in four_forms(q)}
            if p["id"][-4:] in others:
                need5 += 1
    NUM.update({
        f"{prefix}_methods": sum(src.values()), f"{prefix}_kinds": dict(src), f"{prefix}_cards": len(cards),
        f"{prefix}_card_holders": len(per_user),
        f"{prefix}_cards_id_ends_in_last_four": sum(pid.endswith(pm["last_four"]) for _, pid, pm in cards),
        f"{prefix}_id_forms": dict(id_forms), f"{prefix}_brands": dict(brand),
        f"{prefix}_same_brand_users": sum(1 for l in per_user.values()
                                          if max(Counter(p["brand"] for p in l).values()) >= 2),
        f"{prefix}_two_cards_users": sum(1 for l in per_user.values() if len(l) >= 2),
        f"{prefix}_same_last4_users": sum(1 for l in per_user.values()
                                          if max(Counter(p["last_four"] for p in l).values()) >= 2),
        f"{prefix}_multi_kind": dict(multi_kind), f"{prefix}_tail_clash": tail_clash,
        f"{prefix}_cross_clash": cross_clash, f"{prefix}_cross_clash_examples": cross_examples,
        f"{prefix}_methods_needing_5_digits": need5, f"{prefix}_users_one_card": one_card,
    })
    return src, brand, id_forms, multi_kind


# ================================================================================================ retail DB
def retail_db():
    users, orders, products = load("retail", "users"), load("retail", "orders"), load("retail", "products")
    S = "retail DB"
    src, brand, id_forms, multi_kind = payment_counts(users, "retail")
    n = NUM
    row(S, "payment method kinds", top(src), f"{n['retail_methods']} methods, {len(users)} users", "all accepted")
    row(S, "payment id forms", top(id_forms), n["retail_methods"], "full id; 4+ ending digits of the id number",
        "every id = kind word + _ + 7 digits")
    row(S, "credit card: id ends in last four", "id tail vs `last_four`",
        pct(n["retail_cards_id_ends_in_last_four"], n["retail_cards"]), "both accepted",
        "the id digits and the last four are never the same number on one card")
    row(S, "card brands", top(brand), n["retail_cards"], "brand word optional")
    row(S, "users with 2+ cards", "", pct(n["retail_two_cards_users"], n["retail_card_holders"]) + " card holders",
        "-", f"2+ cards of one brand: {n['retail_same_brand_users']}; same last four twice: "
             f"{n['retail_same_last4_users']}")
    row(S, "users with 2+ of one kind", top(Counter(multi_kind)) or "none", f"{sum(multi_kind.values())} users",
        "kind / brand word alone only when it fits one method of the owner")
    row(S, "4-digit clashes inside one user", "same id tail twice; id tail = another card's last four",
        f"{n['retail_tail_clash']} users; {n['retail_cross_clash']} users", "a 4-digit form of 2 methods names neither",
        f"methods that need 5+ ending digits: {n['retail_methods_needing_5_digits']}")
    gc_bal = [pm.get("balance") for u in users.values() for pm in u["payment_methods"].values()
              if pm["source"] == "gift_card"]
    row(S, "gift card balance", f"min {min(gc_bal)}, max {max(gc_bal)}", len(gc_bal),
        "not an argument; '$N' names a gift card only when unique for the owner")
    # ---- order ids
    oid_forms = Counter(re.sub(r"\d", "9", o) for o in orders)
    status = Counter(o["status"] for o in orders.values())
    row(S, "order id", top(oid_forms), len(orders), "`#W1234567` or `W1234567`, any case", f"status: {top(status)}")
    n.update(retail_orders=len(orders), retail_order_id_forms=dict(oid_forms))
    # ---- item / product ids
    pids = set(products)
    iids = {iid for p in products.values() for iid in p["variants"]}
    row(S, "product id / item id", f"product id lengths {dict(Counter(len(x) for x in pids))}; item id lengths "
        f"{dict(Counter(len(x) for x in iids))}", f"{len(pids)} products, {len(iids)} items",
        "item id: yes; product id: not an argument", f"item ids that equal a product id: {len(pids & iids)}")
    n.update(retail_products=len(pids), retail_items=len(iids), retail_item_eq_product=len(pids & iids))
    # ---- items per order
    n_items = Counter(len(o["items"]) for o in orders.values())
    two_same_prod = two_same_item = word_clash = 0
    pairs = pair_clash = 0
    for o in orders.values():
        pc = Counter(it["product_id"] for it in o["items"])
        if max(pc.values()) >= 2:
            two_same_prod += 1
        if max(Counter(it["item_id"] for it in o["items"]).values()) >= 2:
            two_same_item += 1
        names = {it["product_id"]: it["name"] for it in o["items"]}
        words = {p: {w for w in re.findall(r"[a-z0-9]+", nm.lower()) if len(w) >= 3} for p, nm in names.items()}
        if any(words[a] & words[b] for a in words for b in words if a < b):
            word_clash += 1
        for p in words:
            pairs += 1
            if any(words[p] & words[q] for q in words if q != p):
                pair_clash += 1
    row(S, "items per order", top(n_items), len(orders), "-")
    row(S, "order with 2+ items of one product", "same product name twice", pct(two_same_prod, len(orders)),
        "name alone NOT enough there: item id or an option value only that item has",
        f"same item id twice: {two_same_item}; orders where two products share a name word: {word_clash} "
        f"({pair_clash} of {pairs} (order, product) pairs)")
    n.update(retail_orders_two_same_product=two_same_prod, retail_orders_same_item_twice=two_same_item,
             retail_orders_name_word_clash=word_clash, retail_order_product_pairs=pairs,
             retail_order_product_pairs_word_clash=pair_clash)
    # ---- option values
    opt_names = Counter()
    short_vals, three_vals, numeric_vals, yesno_vals = set(), set(), set(), set()
    cross_opt, cross_examples, substr_pairs, substr_examples = 0, [], 0, []
    diff_hist = Counter()
    for p in products.values():
        per_opt = defaultdict(set)
        for v in p["variants"].values():
            for k, val in v["options"].items():
                per_opt[k].add(str(val))
        for k in per_opt:
            opt_names[k] += 1
        owner = defaultdict(set)
        for k, vals in per_opt.items():
            for val in vals:
                owner[val.lower()].add(k)
                if len(val) <= 2:
                    short_vals.add(val)
                elif len(val) == 3:
                    three_vals.add(val)
                if re.fullmatch(r"[\d.]+", val):
                    numeric_vals.add(val)
                if val.lower() in ("yes", "no", "none", "true", "false"):
                    yesno_vals.add(val)
        clash = sorted(v for v, ks in owner.items() if len(ks) >= 2)
        if clash:
            cross_opt += 1
            cross_examples.append(f"{p['name']}: {clash[0]} ({'/'.join(sorted(owner[clash[0]]))})")
        for k, vals in per_opt.items():
            for a in sorted(vals):
                for b in sorted(vals):
                    if a != b and re.search(r"(?<![\w])" + re.escape(a.lower()) + r"(?![\w])", b.lower()):
                        substr_pairs += 1
                        if len(substr_examples) < 6:
                            substr_examples.append(f"{p['name']}.{k}: '{a}' in '{b}'")
        vs = list(p["variants"].values())
        for i in range(len(vs)):
            for j in range(i + 1, len(vs)):
                diff_hist[sum(1 for k in vs[i]["options"] if vs[i]["options"][k] != vs[j]["options"].get(k))] += 1
    row(S, "option names", f"{len(opt_names)} names; most common {top(opt_names, 6)}", f"{len(products)} products",
        "-")
    row(S, "short option values (<= 2 chars)", ", ".join(sorted(short_vals)), len(short_vals),
        "only with the option name within 3 words", "e.g. size 'S' / 'M' / '8' match ordinary words and numbers")
    row(S, "3-char option values", ", ".join(sorted(three_vals)), len(three_vals),
        "whole value, no option name needed (unless number-only or shared)", "")
    row(S, "number-only option values", ", ".join(sorted(numeric_vals, key=float)) or "none", len(numeric_vals),
        "only with the option name within 3 words")
    row(S, "yes / no option values", ", ".join(sorted(yesno_vals)) or "none", len(yesno_vals),
        "only with the option name within 3 words")
    row(S, "one value under 2+ option names in one product", "; ".join(cross_examples[:5]) or "none",
        f"{cross_opt} products", "only with the option name within 3 words")
    row(S, "value inside another value of the same option", "; ".join(substr_examples) or "none",
        f"{substr_pairs} pairs", "whole-value match", "'black' must not count inside 'black and white'")
    row(S, "variant pairs of one product: options that differ", top(diff_hist), sum(diff_hist.values()),
        "a new item: its id, or every changed option value")
    n.update(retail_short_values=len(short_vals), retail_three_char_values=len(three_vals),
             retail_numeric_values=len(numeric_vals), retail_yesno_values=len(yesno_vals),
             retail_cross_option_products=cross_opt, retail_value_substring_pairs=substr_pairs,
             retail_variant_pair_diffs=dict(diff_hist))
    # ---- addresses (users + orders)
    addrs = [u["address"] for u in users.values()] + [o["address"] for o in orders.values()]
    a2_empty = sum(1 for a in addrs if not a.get("address2"))
    a2_form = Counter(re.sub(r"\d+", "N", a["address2"]) for a in addrs if a.get("address2"))
    country = Counter(a["country"] for a in addrs)
    zip_form = Counter(re.sub(r"\d", "9", a["zip"]) for a in addrs)
    state_form = Counter("2 capitals" if re.fullmatch(r"[A-Z]{2}", a["state"]) else a["state"] for a in addrs)
    a1_form = Counter(re.sub(r"\d+", "N", a["address1"]).split()[0] for a in addrs)
    a1_suffix = Counter(a["address1"].split()[-1] for a in addrs)
    default_used = sum(1 for o in orders.values() if all(
        str(o["address"].get(k, "")) == str(users[o["user_id"]]["address"].get(k, ""))
        for k in ("address1", "address2", "city", "state", "zip")))
    na = f"{len(addrs)} addresses ({len(users)} users + {len(orders)} orders)"
    row(S, "address2", top(a2_form), f"{na}; empty {a2_empty}",
        "line 2 when it changes; Suite / Ste / Apt / Unit / # + the number, or the number right after line 1")
    row(S, "country", top(country), len(addrs), "dropped (no line)")
    row(S, "zip", top(zip_form), len(addrs), "the 5 digits", f"leading 0: {sum(a['zip'][0] == '0' for a in addrs)}")
    row(S, "state", top(state_form), len(addrs), "2-letter code or the full name")
    row(S, "address1 start / last word", f"{top(a1_form, 3)}; last word {top(a1_suffix, 6)}", len(addrs),
        "the street line; Street / St, Avenue / Ave ... both")
    row(S, "orders shipped to the user's default address", "", pct(default_used, len(orders)),
        "'your default address' when the call's address is the default")
    n.update(retail_addresses=len(addrs), retail_address2_empty=a2_empty, retail_address2_forms=dict(a2_form),
             retail_country=dict(country), retail_non_usa=sum(v for k, v in country.items() if k != "USA"),
             retail_zip_forms=dict(zip_form), retail_state_forms=dict(state_form),
             retail_orders_default_address=default_used)
    # ---- original payment method
    first = Counter(o["payment_history"][0]["payment_method_id"].rsplit("_", 1)[0]
                    for o in orders.values() if o["payment_history"])
    row(S, "original payment method (payment_history[0])", top(first), len(orders),
        "'the original payment method' when the call uses it")
    n["retail_original_kinds"] = dict(first)


# ================================================================================================ airline DB
def airline_db():
    users, res, flights = load("airline", "users"), load("airline", "reservations"), load("airline", "flights")
    S = "airline DB"
    src, brand, id_forms, multi_kind = payment_counts(users, "airline")
    n = NUM
    row(S, "payment method kinds", top(src), f"{n['airline_methods']} methods, {len(users)} users", "all accepted")
    row(S, "payment id forms", top(id_forms), n["airline_methods"], "full id; 4+ ending digits of the id number")
    row(S, "credit card: id ends in last four", "id tail vs `last_four`",
        pct(n["airline_cards_id_ends_in_last_four"], n["airline_cards"]), "both accepted")
    row(S, "card brands", top(brand), n["airline_cards"], "brand word optional")
    row(S, "users with 2+ cards / 2+ of one brand", "",
        f"{n['airline_two_cards_users']} / {n['airline_same_brand_users']} users",
        "brand word alone only when it fits one card of the owner",
        f"same last four twice in one user: {n['airline_same_last4_users']}")
    row(S, "users with 2+ of one kind", top(Counter(multi_kind)), f"{sum(multi_kind.values())} users",
        "'the certificate' / 'gift card' alone only when the owner has one")
    row(S, "4-digit clashes inside one user", "same id tail twice; id tail = another card's last four",
        f"{n['airline_tail_clash']} users; {n['airline_cross_clash']} users",
        "a 4-digit form of 2 methods names neither",
        f"methods that need 5+ ending digits: {n['airline_methods_needing_5_digits']}")
    cert_amt = Counter(pm["amount"] for u in users.values() for pm in u["payment_methods"].values()
                       if pm["source"] == "certificate")
    cert_same = sum(1 for u in users.values() if any(
        v >= 2 for v in Counter(pm["amount"] for pm in u["payment_methods"].values()
                                if pm["source"] == "certificate").values()))
    row(S, "certificate amount", top(cert_amt, 6), sum(cert_amt.values()),
        "'$N certificate' only when unique for the owner; send_certificate: the amount",
        f"users with 2 certificates of one amount: {cert_same}")
    n.update(airline_cert_same_amount_users=cert_same)
    # ---- reservations
    rid_forms = Counter("6 chars [A-Z0-9]" if re.fullmatch(r"[A-Z0-9]{6}", r) else r for r in res)
    rid_letters = sum(1 for r in res if r.isalpha())
    row(S, "reservation id", top(rid_forms), len(res), "the 6 chars, any case, whole token",
        f"all digits: {sum(r.isdigit() for r in res)}; all letters: {rid_letters}")
    n.update(airline_reservations=len(res), airline_res_id_forms=dict(rid_forms), airline_res_letters_only=rid_letters)
    fn_forms = Counter(re.sub(r"\d", "9", f) for f in flights)
    tails = Counter(re.sub(r"^[A-Z]+", "", f) for f in flights)
    row(S, "flight number", top(fn_forms), len(flights), "'HAT170', 'HAT 170', 'flight 170', with its date",
        f"distinct digit tails: {len(tails)} of {len(flights)}")
    n.update(airline_flights=len(flights), airline_flight_forms=dict(fn_forms), airline_flight_tails=len(tails))
    date_forms, years = Counter(), Counter()
    two_on_date = same_fn_two_dates = 0
    for r in res.values():
        per_date = Counter(f["date"] for f in r["flights"])
        if per_date and max(per_date.values()) >= 2:
            two_on_date += 1
        fn_dates = defaultdict(set)
        for f in r["flights"]:
            date_forms[re.sub(r"\d", "9", f["date"])] += 1
            years[f["date"][:4]] += 1
            fn_dates[f["flight_number"]].add(f["date"])
        if any(len(d) >= 2 for d in fn_dates.values()):
            same_fn_two_dates += 1
    row(S, "flight date (reservations)", top(date_forms), sum(date_forms.values()), "any date form, year optional",
        f"years: {top(years)}; reservations with 2+ flights on one date: {two_on_date}; with one flight number on "
        f"2+ dates: {same_fn_two_dates}")
    n.update(airline_years=dict(years), airline_res_two_flights_one_date=two_on_date,
             airline_res_same_flight_two_dates=same_fn_two_dates)
    status = Counter(st["status"] for f in flights.values() for st in f["dates"].values())
    row(S, "flight status (flights DB)", top(status), sum(status.values()), "no line (DB state, not a call detail)")
    cabin = Counter(r["cabin"] for r in res.values())
    row(S, "cabin", top(cabin), len(res), "'basic economy' / 'economy' / 'business'",
        "DB spells `basic_economy`; 'economy' is inside 'basic economy': the longer is matched first")
    n["airline_cabins"] = dict(cabin)
    row(S, "flight type", top(Counter(r["flight_type"] for r in res.values())), len(res),
        "no line (implied by the flights)")
    row(S, "insurance", top(Counter(r["insurance"] for r in res.values())), len(res),
        "not a form: the tiny question K17")
    tb = Counter(r["total_baggages"] for r in res.values())
    nf = Counter(r["nonfree_baggages"] for r in res.values())
    row(S, "total bags", top(tb, 10), len(res), "the total when > 0; a bag change: the new total or the number added")
    row(S, "paid (nonfree) bags", top(nf, 10), len(res), "a line only when > 0 (book)",
        f"reservations with 0 paid: {nf.get(0, 0)}")
    n.update(airline_nonfree_zero=nf.get(0, 0))
    # ---- passengers
    kinds, n_pax = Counter(), Counter()
    dup_name = 0
    for r in res.values():
        u = users[r["user_id"]]
        me = (u["name"]["first_name"], u["name"]["last_name"])
        saved = {(p["first_name"], p["last_name"]) for p in u.get("saved_passengers", [])}
        n_pax[len(r["passengers"])] += 1
        names = Counter((p["first_name"].lower(), p["last_name"].lower()) for p in r["passengers"])
        if names and max(names.values()) >= 2:
            dup_name += 1
        for p in r["passengers"]:
            k = (p["first_name"], p["last_name"])
            kinds["user" if k == me else "saved passenger" if k in saved else "other"] += 1
    tot = sum(kinds.values())
    row(S, "reservation passengers", top(kinds), tot, "first + last name; the DOB only when it is the changed field",
        f"user or saved (DOB in DB): {pct(tot - kinds['other'], tot)}; passengers per reservation: {top(n_pax)}; "
        f"reservations with one name twice: {dup_name}")
    n.update(airline_pax_total=tot, airline_pax_other=kinds["other"], airline_res_dup_passenger_name=dup_name)
    row(S, "saved passengers per user", top(Counter(len(u.get("saved_passengers", [])) for u in users.values())),
        len(users), "-")
    addrs = [u["address"] for u in users.values()]
    row(S, "user address", f"address2 empty {sum(1 for a in addrs if not a.get('address2'))}; country "
        f"{top(Counter(a['country'] for a in addrs))}", len(users), "no line (not a write argument)")
    row(S, "membership", top(Counter(u["membership"] for u in users.values())), len(users),
        "no line (DB state, not a call detail)")


# ================================================================================================ decisions
def decisions():
    """Every v4 form decision with its basis: DB (a count above), wiki (a policy line) or generic (needs no data).
    `was` = where the decision came from before (old form-check row, or a code comment)."""
    n = NUM
    W = wiki_line
    D = []

    def d(did, decision, code, was, kind, basis, change="no"):
        D.append({"id": did, "decision": decision, "code": code, "was": was, "basis_kind": kind, "basis": basis,
                  "changes": change})

    LV, GA = "state_tracker/v4/listing_v4.py", "state_tracker/v4/helpers_go_ahead_v4.py"
    r_cards, a_cards = n["retail_cards"], n["airline_cards"]
    # ---- payment (D7)
    d("P1", "every payment kind (credit card, gift card, PayPal, certificate) is a payment line", f"{LV} _pay_line",
      "DB rows 'payment method kinds'", "DB",
      f"retail kinds {n['retail_kinds']}; airline kinds {n['airline_kinds']}; "
      f"{W('retail', 'Each payment method is either a gift card')}")
    d("P2", "the full payment id is accepted", f"{LV}:216 exact_payment_forms", "DB rows 'payment id forms'", "DB",
      f"every id is kind + '_' + 7 digits: retail {n['retail_id_forms']}, airline {n['airline_id_forms']}")
    d("P3", "4+ ending digits of the id number are accepted (also 5 and 6 digits)", f"{LV}:217-222",
      "DB rows 'payment id forms' + simulator rows 'every 4-digit number', 'payment id as named'", "DB + generic",
      "generic: the id is what the agent's own tool output shows, its ending digits are the short form of it; DB: "
      f"card ids ending in the card's last four: retail {n['retail_cards_id_ends_in_last_four']} of {r_cards}, "
      f"airline {n['airline_cards_id_ends_in_last_four']} of {a_cards}, so the id digits never collide with the "
      f"card's own last four; methods whose 4-digit tail fits another method of the owner (they need 5+ digits): "
      f"retail {n['retail_methods_needing_5_digits']}, airline {n['airline_methods_needing_5_digits']}")
    d("P4", "a card's last four is accepted, brand word optional", f"{LV}:202-203, 238-242",
      "DB rows 'credit card: id ends in last four', 'card brands'", "DB",
      f"every card has `last_four` (retail {r_cards}, airline {a_cards} cards); brands retail {n['retail_brands']}, "
      f"airline {n['airline_brands']}")
    d("P5", "a 4-digit number that is a 4-digit form of 2 of the owner's methods names neither (unless a brand word "
      "next to it picks one)", f"{LV}:221-222; {GA}:18-22 (form_map_v4, methods_named_v4, 246-318)", "DB rows '4-digit clashes' + code comment "
      f"{GA}:18 'after the v1 form check'", "DB",
      f"users with such a clash: retail {n['retail_tail_clash']} (same tail) / {n['retail_cross_clash']} (tail = "
      f"another card's last four), airline {n['airline_tail_clash']} / {n['airline_cross_clash']}; retail example "
      f"{n['retail_cross_clash_examples'][:1]}")
    d("P6", "kind word / brand word / 'the card' / the balance name a method only when they fit one method of the "
      "owner (per user, at run time)", "state_tracker/v3/message_view.py _unique_word_forms (used by "
      f"{LV}:223)", "DB rows 'users with 2+ of one kind', 'users with 2+ cards of one brand' + simulator row "
      "'brand only: retail yes, airline no'", "DB",
      f"same-brand card users: retail {n['retail_same_brand_users']}, airline {n['airline_same_brand_users']}; 2+ of "
      f"one kind: retail {n['retail_multi_kind']}, airline {n['airline_multi_kind']}; users with exactly one card: "
      f"retail {n['retail_users_one_card']}, airline {n['airline_users_one_card']}; 2 certificates of one amount: "
      f"{n['airline_cert_same_amount_users']}. The check is per user, so the domain split ('retail yes, airline no') "
      "follows from the DB and needs no per-domain rule")
    d("P7", "a brand word next to the digits that is not the card's brand is a clash, not a match; negation ('not "
      "the Mastercard') does not count", f"{LV}:236-242; {GA}:320-356 (brand_mismatch_v4, _payment_clash)", "lesson L1 (generic)", "generic",
      "a wrong brand next to the digits names a different card; a negated mention is not a choice")
    d("P8", "'the original payment method' when the call's method is payment_history[0]", f"{LV}:183-188, 248-251",
      "DB row 'original payment method'", "wiki",
      f"{W('retail', 'refunded via the original payment method')}; "
      f"{W('retail', 'must either go to the original payment method')}; "
      f"{W('airline', 'original payment methods')}; DB kinds of payment_history[0]: {n['retail_original_kinds']}")
    d("P9", "airline booking with 2+ methods: each method with its amount", f"{LV}:623-626, 434-439",
      "predicate_table book row", "wiki",
      f"{W('airline', 'at most one travel certificate, at most one credit card')} (a split payment has amounts)")
    # ---- retail objects / items
    d("R1", "order id: '#W1234567' or 'W1234567', any case; also by D6 (newest order id named)",
      f"{LV}:418-421, 739-740", "DB row 'order id' + simulator row 'order id as named'", "DB + generic",
      f"order ids {n['retail_order_id_forms']} (all '#W' + 7 digits); generic: the '#' and the case carry no meaning")
    d("R2", "item id accepted; product id is not a line", f"{LV}:458, 720", "DB row 'product id / item id'",
      "DB + generic", f"{n['retail_items']} item ids, {n['retail_products']} product ids, item ids equal to a product "
      f"id: {n['retail_item_eq_product']}; generic: the tools take item ids, not product ids")
    d("R3", "old item: the product name, or a word of it that names no other product of the order", f"{LV}:467-475",
      "DB row 'order with 2+ items of one product' (word clash note)", "DB",
      f"(order, product) pairs whose name shares a word with another product of the order: "
      f"{n['retail_order_product_pairs_word_clash']} of {n['retail_order_product_pairs']}, so the word must be unique "
      "in the order (checked per order at run time)")
    d("R4", "old item when the order has 2+ items of that product and the call does not take all: item id or an "
      "option value only that item has", f"{LV}:453-466", "DB row 'order with 2+ items of one product' + simulator "
      "row 'items in expected writes'", "DB",
      f"orders with 2+ items of one product: {n['retail_orders_two_same_product']} of {n['retail_orders']} (same item "
      f"id twice: {n['retail_orders_same_item_twice']}); there the name names 2 items")
    d("R5", "return: 'all the items' / 'the whole order' when the call returns every item", f"{LV}:570-573, 285-287",
      "predicate_table retail row", "wiki + generic",
      f"{W('retail', 'the list of items to be returned')}; generic: 'all' names every item exactly")
    d("R6", "new item: its id, or every changed option value (whole value)", f"{LV}:482-504, 778-782",
      "DB row 'variant pairs'", "DB", f"variant pairs by number of differing options: {n['retail_variant_pair_diffs']}"
      "; the new item is fixed by the product (same as the old) plus every changed value")
    d("R7", "option values match as whole values ('black' not inside 'black and white')", f"{LV}:115-122; {GA}:18-22, 276-277 (_outer_spans)",
      f"DB row 'value inside another value' + code comment {GA}:18-22", "DB",
      f"value pairs where one is a whole word inside another of the same option: {n['retail_value_substring_pairs']}")
    d("R8", "a value of <= 2 characters needs its option name within 3 words", f"{LV}:376", "DB row 'short option "
      "values'", "DB + generic", f"{n['retail_short_values']} such values in the DB; generic: 1-2 character tokens "
      f"('S', 'M', '8') occur as ordinary words and numbers. 3-character values ({n['retail_three_char_values']}, "
      "e.g. colour words) are whole words and need no option name. Note: predicate_table.md says '<= 3 characters'; "
      "the code and this check say <= 2 (code unchanged)")
    d("R9", "a number-only value needs its option name within 3 words", f"{LV}:376", "DB row 'number-only option "
      "values'", "DB + generic", f"{n['retail_numeric_values']} number-only values; generic: a bare number also "
      "matches prices, quantities and ids")
    d("R10", "a yes / no / none value needs its option name within 3 words", f"{LV}:376",
      "DB row 'yes / no option values'", "DB + generic", f"{n['retail_yesno_values']} such values; generic: 'yes' and "
      "'no' are reply words")
    d("R11", "a value used under 2+ option names of one product needs its own option name", f"{LV}:377-381",
      "DB row 'one value under 2+ option names'", "DB",
      f"products with one value under 2+ option names: {n['retail_cross_option_products']}")
    # ---- retail address
    d("A1", "country dropped (no line)", f"{LV}:73", f"DB row 'country' + code comment {LV}:73", "DB",
      f"country over {n['retail_addresses']} addresses (users + orders): {n['retail_country']}; non-USA "
      f"{n['retail_non_usa']}")
    d("A2", "address2: line 2 when it changes; 'Suite / Ste / Apt / Unit / #' + the number, or the number right after "
      "line 1", f"{LV}:294, 335-347", "DB row 'address2'", "DB + generic",
      f"address2 forms {n['retail_address2_forms']}, empty {n['retail_address2_empty']}; generic: the other unit "
      "words are common spellings of the same unit and still need the same number")
    d("A3", "zip: the 5 digits, not inside another number", f"{LV}:356-357", "DB row 'zip'", "DB",
      f"zip forms {n['retail_zip_forms']}")
    d("A4", "state: the 2-letter code or the full name", f"{LV}:295-305, 350-355", "DB row 'state'", "DB + generic",
      f"state forms {n['retail_state_forms']}; generic: the full state name is the same state")
    d("A5", "address1: the street line; suffix words and their abbreviations both count (Street / St ...)",
      f"{LV}:290-293, 319-327", "DB row 'address1'", "DB + generic", "DB street lines are 'N Name Suffix'; generic: "
      "the abbreviation names the same street")
    d("A6", "'your default address' when the call's address equals the user's default", f"{LV}:288-289, 510-528",
      "predicate_table retail row", "DB + wiki", f"orders shipped to the default address: "
      f"{n['retail_orders_default_address']} of {n['retail_orders']}; {W('retail', 'modify their default user address')}")
    d("A7", "an unchanged address field needs no line", f"{LV}:517-518", "predicate_table retail row", "generic",
      "the user is asked to confirm a change; an unchanged field changes nothing")
    # ---- airline
    d("F1", "reservation id: the 6 characters, any case, whole token; also by D6", f"{LV}:424-425, 741-742",
      "DB row 'reservation id'", "DB", f"reservation id forms {n['airline_res_id_forms']}; letters-only ids "
      f"{n['airline_res_letters_only']} (matched as a whole token, so no inner-word hit)")
    d("F2", "flight: 'HAT170', 'HAT 170', 'flight 170', each with its date", f"{LV}:578-587, 698-707",
      "DB rows 'flight number', 'flight date'", "DB + generic",
      f"flight numbers {n['airline_flight_forms']}; distinct digit tails {n['airline_flight_tails']} of "
      f"{n['airline_flights']} (so '170' alone names one flight); reservations with one flight number on 2+ dates: "
      f"{n['airline_res_same_flight_two_dates']}, with 2+ flights on one date: "
      f"{n['airline_res_two_flights_one_date']} (the date is part of the line)")
    d("F3", "dates: any common format, year optional", f"{LV}:586, 707; message_view.text_names_date",
      "DB row 'flight date' + simulator row 'date forms'", "generic + DB",
      f"generic: a date in any common format names the same day; DB years {n['airline_years']} (one year, so the year "
      "adds nothing)")
    d("F4", "cabin: 'basic economy' / 'economy' / 'business'; 'economy' is not matched inside 'basic economy'; flight "
      "change: only when it differs", f"{LV}:590-592, 692-716, 655-656", "DB row 'cabin'", "DB + generic",
      f"cabins {n['airline_cabins']}; generic: 'economy' is a word of 'basic economy'")
    d("F5", "passenger: first + last name; the date of birth only when it is the changed field", f"{LV}:595-605, 669-674",
      "DB row 'reservation passengers' + simulator row 'booking passengers'", "DB + wiki",
      f"reservations with one passenger name twice: {n['airline_res_dup_passenger_name']} of "
      f"{n['airline_reservations']} (elsewhere first + last name picks one passenger; a change that keeps the name "
      "lists the date of birth, so those few still name the changed passenger); passengers who are not the user or a "
      f"saved passenger: {n['airline_pax_other']} of {n['airline_pax_total']}; "
      f"{W('airline', 'collect the first name, last name, and date of birth')} (collecting, not listing)")
    d("F6", "bags: the total when > 0 (book); a bag change: the new total or the number added", f"{LV}:627-631, 659-666",
      "DB row 'total bags'", "generic", "the total and the number added both state the same change")
    d("F7", "paid bags: a line only when > 0 (book), as the number with a paid word or the $ amount; a bag change "
      "names the payment method only when it costs money", f"{LV}:632-635, 667-668", "DB row 'paid bags'",
      "DB + wiki", f"reservations with 0 paid bags: {n['airline_nonfree_zero']} of {n['airline_reservations']}; "
      f"{W('airline', 'Each extra baggage is 50 dollars')}")
    d("F8", "certificate amount: '$N' (send_certificate)", f"{LV}:640-644", "DB row 'certificate amount'", "wiki",
      f"{W('airline', 'with the amount being $100 times the number of passengers')}")
    d("F9", "no line for flight type, flight status, membership, user address, unchanged flights / passengers",
      f"{LV}:614-675", "DB rows 'flight type', 'flight status', 'membership', 'user address'", "generic",
      "they are not arguments of the call, or they do not change")
    d("F10", "insurance (book): the tiny question K17, not a form", f"{LV}:636-638", "DB row 'insurance'", "generic",
      "not a string form; decided by K17")
    # ---- code comments that cited the form check
    d("C1", "comment: forms 'counted on the v1 data' -> now 'the DB-only form check'", f"{LV}:6",
      "code comment", "comment", "points to output/eval_v4/form_check.md, section 'decisions, DB-only'", "comment only")
    d("C2", "comment: ambiguity rule 'after the v1 form check' -> now 'the DB-only form check'", f"{GA}:18",
      "code comment", "comment", "the rule is P5 + P6 above (DB counts)", "comment only")
    d("C3", "comment: test docstring 'form-check traps' -> DB-only form check", "tests/test_v4_listing.py:6",
      "code comment", "comment", "the traps are DB facts (P5, R4, R7, R8, F1)", "comment only")
    return D


# ================================================================================================ main
def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    retail_db()
    airline_db()
    D = decisions()
    NUM["decisions"] = D
    NUM["inputs_sha256"] = dict(READ_LOG)
    kinds = Counter()
    for x in D:
        k = x["basis_kind"]
        kinds["comment" if k == "comment" else "generic" if k == "generic" else "DB / wiki"] += 1
    changed = [x for x in D if x["changes"] not in ("no", "comment only")]
    NUM["decision_counts"] = {"kept from DB / wiki": kinds["DB / wiki"], "kept as generic": kinds["generic"],
                              "comment only": kinds["comment"], "changed": len(changed)}
    with open(OUT_JSON, "w") as f:
        json.dump(NUM, f, indent=1, sort_keys=True)

    n = NUM
    L = ["# Tracker v4 P1: K2-style form check (tau-bench v1 database only, $0)", "",
         "Written by `predicate_correctness/scoring/v4_form_check.py` (stdlib, no network, no LLM). Numbers also in "
         "`form_check.json`.", "",
         "**Sources (the only files read):** " + ", ".join(f"`envs/{p}`" for p, _ in READ_LOG) + " under "
         "`~/opt/tau-bench-59a200c/tau_bench/`; sha256 in `form_check.json` (`inputs_sha256`). No task file, user "
         "instruction, expected action or conversation is read; `tests/test_v4_form_check.py` checks this.", "",
         "**Why DB only:** an earlier version also counted the user-simulator task texts and their expected actions "
         "(retail train, retail and airline test minus test-66, retail dev-20). That leaked task knowledge into the "
         "v4 form decisions (overview.md section 3). Those parts and the dev-20 overlap section are removed; every "
         "decision is re-based below on the database, the policy wiki, or a generic reason.", "",
         "**Main points**",
         f"- Cards: {n['retail_cards_id_ends_in_last_four']} of {n['retail_cards']} retail and "
         f"{n['airline_cards_id_ends_in_last_four']} of {n['airline_cards']} airline card ids end in the card's last "
         "four. So the id digits and the last four are always different numbers: accept both.",
         f"- Same-brand cards: {n['retail_same_brand_users']} retail users, {n['airline_same_brand_users']} airline "
         "users have 2+ cards of one brand. A brand word alone names a card only when the owner has one of that "
         "brand (checked per user).",
         f"- 4-digit clashes inside one user: retail {n['retail_tail_clash']} / {n['retail_cross_clash']}, airline "
         f"{n['airline_tail_clash']} / {n['airline_cross_clash']} users (same id tail / id tail = another card's last "
         f"four). Methods that need 5+ ending digits: retail {n['retail_methods_needing_5_digits']}, airline "
         f"{n['airline_methods_needing_5_digits']}.",
         f"- Orders with 2+ items of one product: {n['retail_orders_two_same_product']} of {n['retail_orders']}. "
         "There the product name alone does not pick the item.",
         f"- Short option values (<= 2 chars) {n['retail_short_values']}, number-only values "
         f"{n['retail_numeric_values']}, products with one value under 2+ option names "
         f"{n['retail_cross_option_products']}: these need the option name next to the value.",
         f"- Retail address2 empty: {n['retail_address2_empty']} of {n['retail_addresses']}; non-USA country: "
         f"{n['retail_non_usa']}. Dropping the country line loses nothing.",
         f"- Airline passengers who are not the user or a saved passenger: {n['airline_pax_other']} of "
         f"{n['airline_pax_total']}; paid bags 0 in {n['airline_nonfree_zero']} of {n['airline_reservations']} "
         "reservations."]
    for ex in n["retail_cross_clash_examples"] + n["airline_cross_clash_examples"]:
        L.append(f"- User {ex['user']}: the id {ex['id']} ends in {ex['other_card_last_four']}, which is also the last "
                 f"four of another of their cards. For this user 'ending in {ex['other_card_last_four']}' alone is "
                 "unclear.")
    L += ["", "## The table", "", "| where | value kind | forms that occur | count | v4 form decision | note |",
          "|---|---|---|---|---|---|"]
    esc = lambda s: str(s).replace("|", "/").replace("\n", " ")
    for r in ROWS:
        L.append("| " + " | ".join(esc(x) for x in r) + " |")
    c = n["decision_counts"]
    L += ["", "## Decisions, DB-only", "",
          "Every v4 form decision: the decision, where it is in the code, where it came from before, and its basis now "
          "(a DB count from the table above, a wiki line, or a generic reason that needs no data). The old "
          "simulator rows were not used to decide. Line numbers are those of the files at this check.", "",
          f"**Summary:** {len(D)} entries: {c['kept from DB / wiki']} kept from DB / wiki, {c['kept as generic']} kept "
          f"as generic, {c['comment only']} comment-only, **{c['changed']} changed**.", "",
          "| id | decision | code | before | basis kind | basis now | changes? |", "|---|---|---|---|---|---|---|"]
    for x in D:
        L.append("| " + " | ".join(esc(x[k]) for k in ("id", "decision", "code", "was", "basis_kind", "basis",
                                                          "changes")) + " |")
    L += ["", "Old table rows with no decision ('-': users with 2+ cards, items per order, option names, saved "
          "passengers per user) stay information only.", "",
          "## How to rerun", "```",
          "cd /home/azureuser/code_projects/predicate_correctness && PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1 "
          "/home/azureuser/miniconda3/bin/python3 -B scoring/v4_form_check.py", "```"]
    with open(OUT_MD, "w") as f:
        f.write("\n".join(L) + "\n")
    print("wrote", OUT_MD, OUT_JSON, "rows", len(ROWS), "decisions", len(D), "changed", c["changed"])


if __name__ == "__main__":
    main()
