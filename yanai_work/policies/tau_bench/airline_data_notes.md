# τ-bench v1 airline: data formats that predicates depend on

Source: `sierra-research/tau-bench` @ `59a200c` (read-only clone at `~/refs/tau-bench`), files `tau_bench/envs/airline/data/{users,reservations,flights}.json` and `tools/*.py`. Counts come from the data files. Tool line numbers refer to that commit. See also `airline_tools.json`.

## What the agent can see

Predicates may only use **tool arguments and tool outputs in the trajectory**, never the DB directly. Each tool exposes the following:

| Tool | Output | Contains |
|---|---|---|
| `get_user_details(user_id)` | JSON user record | **No `user_id` key**: associate it with the call argument. |
| `get_reservation_details(reservation_id)` | JSON reservation record | Has `reservation_id` and `user_id`. **No flight status.** |
| `search_direct_flight(origin, destination, date)` | JSON list of flights | **Only flights whose status on `date` is `available`** (`search_direct_flight.py:15-18`). Each item has the flight fields plus that date's `status`, `available_seats` and `prices`, but **no `date` key**: associate it with the call argument. |
| `search_onestop_flight(origin, destination, date)` | JSON list of `[leg1, leg2]` pairs | Only pairs where both legs are `available`. Each leg carries its own `date` key. |
| `book_reservation`, `cancel_reservation`, `update_reservation_*` | JSON reservation record after the write | Same shape as `get_reservation_details`, the latest state. |
| `send_certificate` | Plain text: `"Certificate certificate_<id> added to user <user_id> with amount <amount>."` | |
| Any tool on failure | A string starting with `"Error: "` | No state change. |

**Consequence (important).** No v1 airline tool exposes a flight status other than `available`. Two facts are therefore **not observable from tool outputs**:
- whether the airline *cancelled* a flight;
- whether a flight on the current date has *departed*.

Predicates about them are either `dialogue` (the user's claim) or date-based approximations. Data fact: cancelled statuses occur only on dates **before** 2024-05-15. All flights dated after 2024-05-15 are `available`.

## Current time and timestamps
- The wiki fixes now = **2024-05-15 15:00:00 EST** (config `policies/curated/airline_config.json`).
- `reservation.created_at` uses the format `YYYY-MM-DDTHH:MM:SS`, with no timezone; it is read as EST. The data ranges from `2024-04-30T01:31:26` to `2024-05-14T23:57:50`. 41 of 2000 reservations were created at or after `2024-05-14T15:00:00`, i.e. within 24 h of now. New bookings are stamped `"2024-05-15T15:00:00"` (`book_reservation.py:47`).
- Flight-segment `date` uses `YYYY-MM-DD`. Departure times appear only in flight records (`scheduled_departure_time_est`, `HH:MM:SS`), so the agent sees them only via search results.

## Flight status per date (`flights.json`, `dates.<date>.status`)

| Date vs. 2024-05-15 | Statuses observed (count) | Extra keys per status |
|---|---|---|
| earlier | `landed` 3827, `cancelled` 373 | landed: `actual_departure_time_est`, `actual_arrival_time_est` |
| same day | `landed` 155, `flying` 47, `on time` 57, `delayed` 41 | flying: `actual_departure_time_est`, `estimated_arrival_time_est`; on time/delayed: `estimated_*` |
| later | `available` 4500 | `available_seats{basic_economy,economy,business}`, `prices{…}` |

The wiki names only `available`, `delayed`, `on time` and `flying`; the data adds `landed` and `cancelled`. A segment in a past-dated reservation is either flown (`landed`) or `cancelled`. Same-day segments may or may not have departed.

## Reservation object
Keys: `reservation_id`, `user_id`, `origin`, `destination`, `flight_type`, `cabin`, `flights`, `passengers`, `payment_history`, `created_at`, `total_baggages`, `nonfree_baggages`, `insurance`.
- `reservation_id`: 6 upper-case alphanumerics (e.g. `4WQ150`). New bookings get `HATHAT`, `HATHAU`, `HATHAV` in turn (`book_reservation.py:30-35`).
- `flight_type ∈ {one_way, round_trip}` (1046 / 954). `cabin ∈ {basic_economy, economy, business}` (649 / 676 / 675). There is **one cabin per reservation**.
- `flights[]`: `{flight_number, date, origin, destination, price}`. `price` is per passenger, for the reservation's cabin.
- `passengers[]`: `{first_name, last_name, dob}`, 1–4 per reservation in the data (the wiki allows up to 5).
- `insurance ∈ {"yes", "no"}`.
- `total_baggages` and `nonfree_baggages` are **reservation-level totals**, not per passenger.
- `payment_history[]`: `{payment_id, amount}`. Updates append entries; a cancellation appends negative refunds.
- **`status`** exists only after `cancel_reservation`, which sets `"cancelled"` (`cancel_reservation.py:29`). Otherwise the key is absent.
- **Quirk: `cabin` is never updated.** `update_reservation_flights(…, cabin=X)` re-prices every segment at cabin X and charges the difference, but it never assigns `reservation["cabin"]` (`update_reservation_flights.py:76-86`). Every later reservation object, including the tool's own output, therefore still shows the **old** cabin. The τ-bench ground truth assumes the new cabin; for example, airline task 5 expects 0 non-free bags for a gold user after a basic-economy-to-economy upgrade. Predicates use the *effective cabin*: the `cabin` argument of the latest successful `update_reservation_flights` on that reservation (`agent/predicates/context.py:with_effective_cabin`). Before this fix, the firing analysis flagged 10 correct bag updates in reward-1 runs.

## User object
Keys: `name{first_name,last_name}`, `address{…}`, `email`, `dob`, `payment_methods{id→method}`, `saved_passengers[]`, `membership`, `reservations[]`.
- **Membership tiers:** `regular` 143, `silver` 182, `gold` 175.
- **User ids** look like `mia_li_3668`. `reservations` lists reservation ids; data consistency was checked (every reservation is listed by its owner).

## Payment methods
- Ids are `<source>_<digits>` with `source ∈ {credit_card, gift_card, certificate}`. The prefix always equals `source` in the data (credit_card 503, gift_card 516, certificate 467).
- `credit_card`: `{source, brand, last_four, id}`.
- `gift_card` and `certificate`: `{source, amount, id}`. **The balance field is `amount`** (retail uses `balance`).
- `book_reservation` deducts gift-card amounts, **deletes** a used certificate, and rejects any amount above the balance (`book_reservation.py:84-100`).
- `update_reservation_*` rejects certificates (`update_reservation_flights.py:69`, `update_reservation_baggages.py:27`).
- `send_certificate` adds `certificate_3221322`, `…323` or `…324`, whichever is free first.

## Prices the API computes itself
- `book_reservation`: total = Σ segment price(cabin) × passengers + 30 × passengers (if insured) + 50 × `nonfree_baggages`. The call is rejected unless Σ payment amounts equals this total exactly (`book_reservation.py:72-91`).
- `update_reservation_flights`: charges (new − old) fare × passengers. A kept segment keeps its old price **only if the cabin is unchanged**; on a cabin change every segment is re-priced and must be `available` (`update_reservation_flights.py:26-58`).
- `update_reservation_baggages`: charges 50 × max(0, new nonfree − old nonfree) (`update_reservation_baggages.py:22`).

## Recorded trajectories (B0.4)
`historical_trajectories/gpt-4o-airline.json` (200 runs, 50 tasks × 4 trials, reward 1: 84) and `sonnet-35-new-airline.json` (400 runs, 50 tasks × 8 trials, reward 1: 184).

Each run is `{task_id, reward, info, traj, trial}`. `traj` is an OpenAI-style message list:
- `system` (the wiki);
- `user`;
- `assistant` with `content` and optional `tool_calls[{id, function{name, arguments(JSON string)}}]`;
- `tool` with `{tool_call_id, name, content}`.

`info.task.actions` holds the ground-truth action sequence. The `traj` format is the one the predicate functions take (`agent/predicates/context.py`).
