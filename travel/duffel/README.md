# Duffel Flight Booking — Streamliner One

Agent-operated flight search and booking via [Duffel API](https://duffel.com/docs).  
All scripts live in `~/.openclaw/workspace/duffel/`.

---

## File Map

| File | Role |
|------|------|
| `duffel_client.py` | Core client — search, book, order management. **The booking engine.** |
| `duffel_client_v2.py` | Extended CLI with route intelligence, markup display, ancillary/cancel commands |
| `ancillaries.py` | Seat maps (pre-booking) and post-booking services (baggage, meals, etc.) |
| `order_manager.py` | Cancellation quotes and confirmation, change eligibility checks |
| `route_cache.py` | Caches known direct/connection routes from past searches |
| `route_cache.json` | Persisted route data (~34k routes) |
| `airline_cache.py` | Caches airline IATA codes and names |
| `airlines.json` | Persisted airline data |
| `flexible_search.py` | Multi-date search with date flexibility (±N days) |
| `tools_server.py` | Credential helper — fetches API keys from tools-config-server |
| `test_booking.py` | Sandbox end-to-end booking test (search → book → confirm) |
| `test_order_management.py` | Sandbox order lifecycle test (search → book → cancel/change) |

---

## Credentials

Stored in tools-config-server at `http://localhost:8080`.  
Both clients fetch them automatically on init — no manual key handling.

| Mode | Credential ID | Key prefix |
|------|--------------|------------|
| **Live** (real bookings) | `duffel` | `duffel_live_...` |
| **Sandbox** (safe testing) | `duffel-1775151120476` | `duffel_test_...` |

Default mode is `sandbox` unless `--mode live` is passed.

---

## The Most Important Rule About Booking

**Duffel order creation requires passenger IDs from the search response.**  
You cannot book from a stale offer ID alone. The correct flow is always:

```
search → get offers + passenger IDs → book using those IDs
```

`duffel_client.py` handles this automatically in `create_order()` via `_get_offer()`.  
Do NOT try to pass passenger details without the offer's `pas_...` ID — it will 422.

---

## Usage: duffel_client_v2.py (main CLI)

### Search
```bash
# Economy, sandbox (default)
python3 duffel_client_v2.py search --origin GVA --destination BCN --date 2026-05-10

# Business, live, with markup
python3 duffel_client_v2.py search --origin GVA --destination JFK --date 2026-06-24 \
    --return-date 2026-07-08 --cabin business --mode live --markup 3.0

# Sort by price instead of duration
python3 duffel_client_v2.py search --origin VLC --destination LHR --date 2026-05-15 \
    --mode live --sort price --limit 5
```

**Output:** numbered list with airline, total price, outbound/return durations, stops, markup price, offer ID.  
Route advisory shown when known direct routes exist that Duffel doesn't cover.

### Book

Booking via CLI (`book` subcommand) is **not recommended** for agent use.  
Use `test_booking.py` pattern or Python directly — the CLI `book` command requires
pre-fetching the offer to get passenger IDs, which is done automatically in Python.

For ad-hoc agent bookings, use this Python pattern:

```python
from duffel_client import DuffelClient

client = DuffelClient(mode="sandbox")  # or "live"
result = client.search_flights(
    origin="GVA", destination="JFK",
    departure_date="2026-06-24", return_date="2026-07-08",
    cabin_class="business", adults=1
)

offer = result["offers"][0]
passenger_id = result["passengers"][0]["id"]  # REQUIRED — from search response

order = client.create_order(
    offer_id=offer["id"],
    passengers=[{
        "id": passenger_id,       # from search, not made up
        "type": "adult",
        "title": "mr",            # mr / ms / mrs / miss / dr / prof
        "given_name": "Alexey",
        "family_name": "Prudkov",
        "gender": "m",            # m / f
        "born_on": "1978-08-20",  # YYYY-MM-DD
        "email": "alexey@example.com",
        "phone_number": "+41791234567",  # must start with +
    }],
    payment_type="balance"        # sandbox accepts "balance"
)
print(f"PNR: {order['booking_reference']}")
print(f"Order ID: {order['id']}")
```

### Get Order Details
```bash
python3 duffel_client_v2.py order --id ord_0000B4uh6DIFatu3lCgCZ6 --mode sandbox
```

### List Orders
```bash
python3 duffel_client_v2.py list --limit 10 --mode live
```

### Seat Maps (pre-booking, offer ID)
```bash
python3 duffel_client_v2.py seats --offer-id off_0000... --mode sandbox --max-rows 15
```
Note: seat maps only available for airlines that support it (American Airlines is reliable in sandbox).

### Post-Booking Services (order ID)
```bash
# List available extras (baggage, meals, cancel protection)
python3 duffel_client_v2.py services --order-id ord_0000... --mode sandbox

# Add a service
python3 duffel_client_v2.py add-service --order-id ord_0000... \
    --service-id svc_0000... --mode sandbox
```

### Cancellation
```bash
# Step 1: Get quote (safe — does not cancel yet)
python3 duffel_client_v2.py cancel --order-id ord_0000... --mode sandbox

# Step 2: Confirm cancellation (use cancellation ID from quote)
python3 duffel_client_v2.py cancel --order-id ord_0000... \
    --confirm ore_0000... --mode sandbox
```
⚠️ Not all airlines support API cancellation. easyJet returns 422 — must be cancelled directly with the airline. American Airlines, Iberia, British Airways: confirmed working.

### Smart Search (flexible dates)
```bash
python3 duffel_client_v2.py smart --origin GVA --destination JFK \
    --date 2026-06-24 --flexibility 2 --cabin business --mode live
```
Searches ±2 days around the target date, shows best direct options first.

---

## Passenger Validation Rules

The client validates these before every booking attempt:

| Field | Requirement |
|-------|-------------|
| `id` | Must come from search response `passengers[].id` |
| `type` | `adult`, `child`, or `infant_without_seat` |
| `title` | `mr`, `ms`, `mrs`, `miss`, `dr`, or `prof` |
| `gender` | `m` or `f` (not `male`/`female`) |
| `born_on` | `YYYY-MM-DD` |
| `phone_number` | Must start with `+` |
| `email` | Must contain `@` |

---

## Modes and Safety

| Flag | What happens |
|------|-------------|
| `--mode sandbox` | Fake bookings, fake money, safe to test. Some airlines return 502 (LOT is unreliable). |
| `--mode live` | Real bookings, real Duffel Balance charged. Requires Duffel Balance funded. |

In sandbox, **no emails are ever sent** — not from Duffel, not from airlines.  
In live mode with confirmation emails enabled (Duffel dashboard toggle): Duffel sends a booking confirmation to the passenger email.

**Duffel does NOT suppress airline emails.** Airlines that send their own confirmations (Iberia, easyJet, United, Singapore) will still send them independently.

---

## Limitations

- **Switzerland origin works fine** — GVA searches return live offers (verified 2026-04-03). The "seller country" restriction applies only to **Duffel Payments** (their card processor, 22 countries), which we don't use — we use Duffel Balance (bank transfer top-up, no country restrictions). No issue here.
- **No SWISS (LX) in Duffel** — not in their network. Book SWISS directly.
- **No Emirates (EK) in Duffel** — inactive, requires special approval.
- **Seat maps only work pre-booking** (offer ID). Post-booking seat assignment goes through services API.
- **Route cache** is advisory only — Duffel is the authoritative source for what's bookable.
- **API cancellation is airline-dependent** — not all airlines allow cancellation via Duffel API. easyJet, for example, returns 422 "This order cannot be cancelled through the API." American Airlines works. Always check cancellability via the quote endpoint before presenting cancellation as an option to clients.

## Tested Flows (Sandbox) — Verified 2026-04-03

| Flow | Airline | Result |
|------|---------|--------|
| Search + book | American Airlines | ✅ Works |
| Search + book | British Airways | ✅ Works |
| Search + book | easyJet | ✅ Works |
| Cancellation quote + confirm | American Airlines | ✅ Works — refund to Duffel balance |
| Cancellation via API | easyJet | ❌ 422 — not supported by airline |
| Change eligibility check | American Airlines | ✅ Works — shows per-slice changeability |
| Seat map | American Airlines | ✅ Works (when airline supports it) |

**Test log:**
```
Cancellation: ord_0000B4uis5ISjDdyoVAYdc (AA GVA-JFK round-trip)
  → Quote: $4119.56 refund to balance
  → Confirmed: ore_0000B4uis7JbDxk34biUgj
  → Status: refunded

Change check: ord_0000B4uisXogh03fGYSgkq (BA LHR-JFK)
  → Slice 1: LHR → JFK — ✅ Changeable
  → Refund: Not allowed (basic fare)
```

---

## Sandbox Test: Last Successful Booking

```
Route:     GVA → JFK → GVA (round-trip)
Dates:     2026-06-24 / 2026-07-08
Airline:   American Airlines (sandbox)
Order ID:  ord_0000B4uh6DIFatu3lCgCZ6
PNR:       24FUSF
Total:     USD 3,811.75
Passenger: Alexey Prudkov
Tested:    2026-04-03
```

---

## Common Errors

| Error | Cause | Fix |
|-------|-------|-----|
| `422 Field 'id' can't be blank` | Passenger missing `id` from search response | Always use `result["passengers"][0]["id"]` |
| `422 Field 'selected_offers' can't be blank` | Using old `offer_id` field instead of `selected_offers` | `create_order()` handles this — don't call `_request()` directly |
| `502 internal_error` | Airline sandbox unreliable (LOT, others) | Try American Airlines or Iberia |
| `401 Unauthorized` | Tools server not running or wrong credential ID | `openclaw gateway status`; check credential ID |
| `Offer expired` | Offers expire in ~30 min | Re-search and pick a fresh offer |
