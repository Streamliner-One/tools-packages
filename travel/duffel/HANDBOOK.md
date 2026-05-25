# Duffel Agent Handbook
*Internal reference for Mel. For user-facing docs see README.md.*

Last updated: 2026-04-16 (format consolidation — connecting flights, fare tiers, show subcommand)

---

## When to Use Duffel

**Use Duffel for all flight searches and bookings** (primary tool since 2026-04-03).
**Use Amadeus for hotels** (Duffel not used for hotel inventory).

### Fallback to Amadeus for flights when:
- Duffel returns 0 offers for the route
- Airline requires direct booking (Emirates EK, SWISS LX — book direct or via GDS)
- Client has specific loyalty/insurance reason to book via airline directly

---

## Keys & Mode

Keys fetched automatically via `tools_server.py`. Default: **live mode**.

```bash
# Explicit mode override
python3 duffel_client_v2.py search --origin VLC --destination PAR \
  --date 2026-04-10 --return-date 2026-04-16 --mode live

python3 duffel_client_v2.py search --origin VLC --destination JFK \
  --date 2026-06-24 --mode sandbox
```

| Key prefix | Environment |
|------------|------------|
| `duffel_live_...` | Live — real fares, real charges, real PNR |
| `duffel_test_...` | Sandbox — fake data, no charges, no emails |

---

## Quick Command Reference

```bash
cd ~/.openclaw/workspace/duffel

# Search (round-trip, live, by-airline block view, 3% markup — standard client default)
python3 duffel_client_v2.py search \
  --origin VLC --destination PAR \
  --date 2026-04-10 --return-date 2026-04-16 \
  --mode live --by-airline --markup 3

# Flags
#   --cabin economy|business|first    (default: economy)
#   --adults N                         (default: 1)
#   --sort price|duration              (default: duration)
#   --limit N                          (default: show all)
#   --markup FLOAT                     (default: 0.0 — personal cost)
#   --booking-fee FLOAT                (flat fee in offer currency, e.g. 50 for cheap flights)
#   --service-floor FLOAT              (min non-refundable service fee, default 100 — e.g. 200 for premium clients)
#   --no-service-fee                   (hide the service fee line — personal searches, trusted clients)
#   --full                             (full airport names + detailed legs)
#   --by-airline                       (Skyscanner-style: one block per bookable pair)
#   --profile light|standard|flex|full-flex  (fare filter: light=cheapest, standard=≥1 bag, flex=bag+changeable, full-flex=bag+changeable+refundable)
#   --grouped                          (Phase 1 view: group by unique itinerary, show cheapest matching fare per route)

# Smart search (flexible dates ±3 days)
python3 duffel_client_v2.py smart-search \
  --origin GVA --destination JFK --date 2026-06-24 --cabin business

# Book (basic)
python3 duffel_client_v2.py book <OFFER_ID>

# Book with frequent flyer number (Swiss Miles & More)
python3 duffel_client_v2.py book --offer-id <OFFER_ID> \
  --passenger '{"type":"adult","title":"mr","given_name":"Vasily",...}' \
  --loyalty LX:12345678

# Book with multiple programmes
python3 duffel_client_v2.py book --offer-id <OFFER_ID> \
  --passenger '...' \
  --loyalty LX:12345678,LH:987654321

# List orders
python3 duffel_client_v2.py orders

# Order details
python3 duffel_client_v2.py order <ORDER_ID>

# Seat map
python3 duffel_client_v2.py seats <ORDER_ID>

# Ancillary services
python3 duffel_client_v2.py services <ORDER_ID>

# Add a service
python3 duffel_client_v2.py add-service <ORDER_ID> <SERVICE_ID>

# Cancellation quote
python3 duffel_client_v2.py cancel <ORDER_ID>

# Confirm cancellation
python3 duffel_client_v2.py cancel <ORDER_ID> --confirm <CANCELLATION_QUOTE_ID>

# Phase 2: Expand fare options for itinerary N (after grouped search)
python3 duffel_client_v2.py expand \
  --origin VLC --destination JFK \
  --date 2026-04-10 --return-date 2026-04-15 \
  --group 1 --markup 5
```

---

## Pricing Model

### How Duffel fees work

Duffel's `total_amount` in API responses = **fare + airline taxes only**.
Their service fee (1% of fare + $3 fixed per order) is **billed separately to your Duffel Balance account** — it is NOT inside `total_amount`.

```
Your actual cost = total_amount + (total_amount × 1%) + $3
Client price     = your_actual_cost × (1 + markup%)
```

### Fee constants in duffel_client_v2.py

```python
DUFFEL_FEE_PERCENT = 0.01   # 1% of total_amount
DUFFEL_FEE_FIXED   = 3.0    # $3 per order (USD)
```

### Markup guide

Two billing modes — use whichever makes sense for the fare, but the applied pricing mode must always be visible in the offer workflow.

| Scenario | Command | Notes |
|----------|---------|-------|
| Personal use / cost check | `--markup 0` (default) | Shows actual cost — Duffel net + their fee |
| Standard client quote | `--markup 3` | Default commercial markup for normal client offers |
| Premium / complex client quote | `--markup 5` | Use for high-touch, complex, premium, or business itineraries |
| Cheap fare (budget airline, short-haul) | `--booking-fee 50` | Flat service fee; % on a €100 ticket is meaningless |
| Both combined | `--markup 3 --booking-fee 50` | Rare, only if intentionally justified |

**Policy context:**
- Personal / internal comparison: 0% markup
- Standard client quote: 3% markup
- Premium / complex client quote: 5% markup
- Cheap short-haul tickets may use a flat booking fee instead of relying only on percentage markup
- Never present a client offer without stating which pricing mode was applied

Never add margin to personal bookings unless you intentionally want that outcome.

### Non-refundable service fee line

Every search result shows a per-offer non-refundable service fee — what the client keeps paying if they cancel a refundable fare.

**Formula:** Duffel exposure (1% + $3) + your floor ($100) → rounded UP to next $25.

**Currency:** Your floor is always $100 USD equivalent. Display in whatever currency the client prefers — convert at day's rate. The math stays dollar-based internally.

```
# Default floor: $100
python3 duffel_client_v2.py search ... --markup 3
→ "Service fee: USD 125 — non-refundable"

# Premium client / higher floor
python3 duffel_client_v2.py search ... --service-floor 200
→ "Service fee: USD 225 — non-refundable"

# Hide for personal searches or trusted clients
python3 duffel_client_v2.py search ... --no-service-fee
```

**Reference table (floor $100):**

| Fare | Service fee shown |
|------|------------------|
| $279 (budget short-haul) | $125 |
| $1,600 (economy long-haul) | $125 |
| $5,300 (business long-haul) | $175 |
| $10,000 (first class) | $225 |

Label in output: `Service fee: USD X — non-refundable` — no word "penalty", no explanation needed.

### Example (Transavia VLC→PAR, Apr 10–16)

| | Amount |
|---|---|
| Duffel `total_amount` (API) | $279 |
| Your cost (+ Duffel 1% + $3) | $285 |
| Client price at 5% markup | $299 |
| Client price at 10% markup | $314 |

**Note:** Revolut ~0.8% cashback roughly offsets the fixed $3 fee on mid-range fares.

---

## Agent Workflow: Search → Display → Offer (CANONICAL — 2026-04-16, rev 2)

This is the single source of truth for flight search behavior and output. Do not improvise a third format.

---

### 1. Search

Primary command:

```bash
python3 duffel_client_v2.py search \
  --origin GVA --destination VLC --date 2026-04-29 \
  --mode live --sort duration --limit 10
```

Mandatory search rules:
- Search Duffel first, sorted by duration unless a price-first sort is explicitly needed
- Include all offers, nonstop and connecting
- Show nonstop options first
- If no nonstop exists on the requested airline, do not stop, include best 1-stop connections
- Never conclude "carrier unavailable" from a nonstop-only check
- Fall back to Amadeus only if the carrier is absent from all Duffel results
- Every search caches the full offer list only for short follow-up detail views
- Duffel search cache TTL is exactly 20 minutes; after that, rerun the search and rebuild option numbers
- Before any booking/commitment step, always revalidate live and present the fresh itinerary/fare again

Useful flags:
- `--cabin business` or `--cabin first` to search premium cabins (default: economy)
- `--adults N` for multi-passenger searches (affects pricing and seat count)
- `--markup 0 --no-service-fee` for personal checks
- `--markup 3` for standard client quotes, `--markup 5` for premium/complex
- `--grouped --profile light|standard|flex|full-flex` for itinerary-first workflow

Multi-passenger example:
```bash
python3 duffel_client_v2.py search \
  --origin GVA --destination VLC --date 2026-04-29 \
  --adults 3 --cabin business --sort duration --limit 10
```

---

### 2. Display (list view)

Default Telegram presentation is a compact monospace code block. Use airport codes only.

**One option = one itinerary.** When the same flights appear in multiple fare tiers, show only the cheapest tier in the list. The other tiers surface in Part B when the user says "show me option X". This keeps the list scannable — easyJet appears once at $82, not three times at $82/$158/$324.

Canonical nonstop option:

```text
────────────────────────────────────────
Option 1  easyJet  USD 82  [Economy · Light]
────────────────────────────────────────
OUT U21371  GVA 18:10 → VLC 20:00  1h50m
```

Canonical connecting option:

```text
────────────────────────────────────────
Option 2  Swiss  USD 296  [Economy · Economy Light]
────────────────────────────────────────
OUT LX2819  GVA 20:00 → ZRH 20:55  0h55m
       ZRH layover 1h05m
    LX2146  ZRH 22:00 → VLC 00:05  2h05m
       Total: 4h05m
```

Canonical business cabin option (same layout, different cabin):

```text
────────────────────────────────────────
Option 3  Swiss  USD 832  [Business · Business Basic]
────────────────────────────────────────
OUT LX2819  GVA 20:00 → ZRH 20:55  0h55m
       ZRH layover 1h05m
    LX2146  ZRH 22:00 → VLC 00:05  2h05m
       Total: 4h05m
```

Mandatory list-view rules:
- **One option per unique itinerary** — show cheapest fare only; other tiers revealed in `show --option N`
- Wrap flight data in triple backticks for Telegram
- On chat surfaces, the actual fare/flight layout is always inside a fenced code block; never send aligned offer text as normal prose
- Separator is exactly 40 `─` chars
- Header line is: `Option N  Airline  CURRENCY price  [Cabin · Fare brand]`
- Cabin and branded fare name must always be shown
- Use `OUT` on the first segment only, continuation segments are indented
- Every connecting option must include both layover and total travel time
- Airport names do not appear in list view
- Summary prose goes outside the code block, below all options

---

### 3. Offer / detailed view (`show --option N`)

When the user says "show me option X", serve from cached search data only if the cache is still within the 20-minute TTL. If expired, rerun the search first and rebuild the numbered list before showing details.

Command:

```bash
python3 duffel_client_v2.py show --option 3 --mode live
```

Detailed view always has two parts.

#### Part A — full itinerary

```text
✈️ Lufthansa

 OUTBOUND Fri 24 Apr (7h20m total, 1 stop)
 ✈ LH1165 VLC 06:05 → FRA 08:40 2h35m
 Valencia Airport → Frankfurt am Main Airport
 ┄ FRA layover 2h35m
 ✈ LH1454 FRA 11:15 24 Apr → TIA 13:25 2h10m
 Frankfurt am Main Airport → Tirana International Airport

 RETURN Sat 25 Apr (9h25m total, 1 stop)
 ✈ LX1443 TIA 14:40 → ZRH 16:45 2h05m
 Tirana International Airport → Zurich Airport
 ┄ ZRH layover 5h10m
 ✈ LX2146 ZRH 21:55 25 Apr → VLC 00:05 (+1) 2h10m
 Zurich Airport → Valencia Airport
```

Rules:
- The detailed view always starts with the full itinerary block first, then the fare tiers block second
- The full itinerary block must be wrapped in a fenced code block on chat surfaces
- Airline name appears alone on the first line; fare family details belong in Part B
- Include outbound and return section headers with date, total duration, and stop count
- Each flight segment is followed by the airport full-name line
- Preserve explicit segment dates when they help clarify same-day/next-day/previous-day timing
- Layovers shown between segments using `┄`
- Do not put fare-tier labels in the itinerary block

#### Part B — all fare tiers for the same itinerary

Shown only when 2+ fare variants exist.

```text
────────────────────────────────────────────
FARE OPTIONS — Swiss (3 tiers)
────────────────────────────────────────────
Tier   : 1 — Economy Light
Price  : USD 296
Bags   : No checked bag + carry-on
Changes: Not allowed
Refund : Non-refundable
ID     : off_xxx

Tier   : 2 — Economy Classic
Price  : USD 342
Bags   : 1×23kg checked + carry-on
Changes: Free
Refund : Non-refundable
ID     : off_xxx

Tier   : 3 — Economy Flex
Price  : USD 489
Bags   : 1×23kg checked + carry-on
Changes: Free
Refund : Full refund ✓
ID     : off_xxx
```

Rules:
- Part B always follows Part A immediately; do not send fare tiers alone when showing option details
- The fare tier block must be wrapped in a fenced code block on chat surfaces
- Start with a divider/title line such as `FARE OPTIONS — Airline (N tiers)`
- Use colon-aligned labels
- Always show Bags, Changes, Refund
- Show offer ID per tier so any tier can be booked directly
- This replaces any need to re-run a search just to inspect fare conditions

---

### Command decision table

| Situation | Command |
|-----------|---------|
| Standard Telegram search | `search --sort duration --limit 10` |
| Personal cost check | `search --markup 0 --no-service-fee` |
| Client quote, standard | `search --markup 3` |
| Client quote, premium / complex | `search --markup 5` |
| Cheap short-haul client fare | `search --markup 3` and consider flat booking fee policy |
| Show chosen option | `show --option N` |
| Formal client-facing verbose output | `search --full` only when explicitly asked |
| Group itineraries then inspect fares | `search --grouped ...` then `expand --group N` |

Hard rules:
- Cached Duffel result sets expire after 20 minutes, with no aging state
- Never reuse expired option numbers; rerun the search instead
- Always revalidate live and present the fresh itinerary/fare again before booking or any final commitment
- Never improvise a hybrid layout
- List view is for scanning, detailed view is for decision-making
- `show --option N` is the standard answer to "show me option X" within the active 20-minute cache window
- Detailed view presentation is fixed: Part A full itinerary first, Part B fare tiers second
- Option numbers must stay anchored to the originating list; if search parameters or cabin change, explicitly say numbering has changed before reusing option labels
- Every offer must explicitly state the pricing mode used: markup 0%, 3%, or 5%, and whether a booking fee/service fee line is included

---

## Phase 1 / Phase 2 Workflow (Itinerary Grouping + Fare Expansion)

**Problem:** Duffel returns 50 offers — many are the same flights with different fare tiers. Showing all 50 is noise. Showing only cheapest hides critical conditions.

**Solution:** Two-phase display matching how travel agents actually work.

### Phase 1 — Itinerary selection (`--grouped`)

```bash
python3 duffel_client_v2.py search \
  --origin VLC --destination JFK \
  --date 2026-04-10 --return-date 2026-04-15 \
  --mode live --grouped --profile light --limit 5
```

Output: one block per unique flight combination, showing:
- Cheapest fare matching the profile
- Cabin class + fare brand (e.g. `Economy · Economy Light`)
- Conditions summary: bags, changes, refund status
- Non-refundable service fee exposure
- Variant count: `→ 2 other fare options available (use --expand 1)`

### Phase 2 — Fare expansion (`expand` subcommand)

Client says "I like itinerary #1, show me the better fares":

```bash
python3 duffel_client_v2.py expand \
  --origin VLC --destination JFK \
  --date 2026-04-10 --return-date 2026-04-15 \
  --mode live --group 1 --markup 5
```

Output: side-by-side fare table with:
- All fare tiers for that itinerary (Economy Light, Basic, Flex, etc.)
- Baggage allowance per tier
- Change fees (amount + currency)
- Refund policy
- Cancellation service fee per tier
- Offer ID for each tier

### Fare Profiles

Filter by minimum conditions:

| Profile | Requires | Use case |
|---------|----------|----------|
| `light` (default) | Nothing | Cheapest available — price-sensitive clients |
| `standard` | ≥1 checked bag | Normal travel — most clients default here |
| `flex` | ≥1 bag + changeable | Uncertain plans, business travel |
| `full-flex` | ≥1 bag + changeable + refundable | Maximum flexibility, premium clients |

**Example for Vasily (needs changeable + bag):**
```bash
# Phase 1: show only itineraries with flex fares
python3 duffel_client_v2.py search --origin GVA --destination DXB \
  --date 2026-05-01 --grouped --profile flex --markup 5

# Phase 2: expand the chosen itinerary to show all flex tiers
python3 duffel_client_v2.py expand --origin GVA --destination DXB \
  --date 2026-05-01 --group 1 --markup 5
```

**No results?** If `--profile full-flex` returns 0 itineraries, the route has no refundable fares on those dates. Either relax the profile or adjust dates.

---

## Booking Flow (Real Client Bookings)

1. **Search** — `--mode live --by-airline --markup 3` (standard); use `--markup 5` for premium/complex routes
2. **Present options** — direct flights first; use `--full` for client-facing output
3. **Confirm passenger details** — name as in passport, DOB (YYYY-MM-DD), gender (m/f), title, email, phone (with country code)
4. **Seat selection** — optional; check seat map first (`seats <ORDER_ID>`)
5. **Ancillaries** — optional; check services
6. **Book** — `book <OFFER_ID>`
7. **Confirmation** — send own branded WhatsApp confirmation: booking ref, route, dates, PNR, total paid
8. **Pre-flight** — handle check-in and boarding passes ~24h before departure

### Passenger data validation

Client must provide: given name, family name, title (mr/ms/mrs/miss/dr), gender (m/f), DOB, email, phone (+country code).

---

## Client Segmentation & Use Cases

| Client type | Booking approach | Notes |
|-------------|-----------------|-------|
| **Personal** (Alex) | Direct with airline if loyalty miles apply (EK Skywards); Duffel for speed/comparison | Revolut cashback ~0.8% |
| **Vasily / Nikolay** | Duffel with 5% markup | Coordination fee + refundable fares policy |
| **Via Travel B2B** | Intelligence tool for route/price consultancy | Most clients have own ticketing |

**Policy:** Book refundable fares; non-refundable coordination fees for clients.

---

## Client Communication Policy

- **Disable Duffel confirmation emails** in production dashboard (avoids confusion)
- **Send own confirmation** via WhatsApp: booking ref, route, dates, PNR, total paid
- **Boarding passes** — handled ~24h pre-flight
- **Refunds** — to Duffel Balance; timeline depends on airline

---

## Known Airline Limitations

| Airline | Status | Notes |
|---------|--------|-------|
| Emirates (EK) | ❌ Inactive in dashboard | Book direct. Skywards miles + ADIB Visa Infinite |
| SWISS (LX) | ❌ Inactive in dashboard | Book direct. Present in Duffel global list; activation pending |
| Air France (AF) | ❌ Inactive in dashboard | Requires airline activation request |
| KLM (KL) | ❌ Inactive in dashboard | Requires airline activation request |
| United (UA) | ❌ Inactive in dashboard | Requires airline activation request |
| easyJet (U2) | ⚠️ No API cancellations | 422 on cancel. Refund only per fare conditions manually |
| LOT Polish | ⚠️ Sandbox flaky | 502 errors in sandbox; live untested |
| Transavia France | ✅ Live tested | VLC→PAR confirmed, Apr 2026 |
| Iberia (operated by Vueling) | ✅ Live tested | VLC→PAR confirmed; Iberia sells, Vueling operates |
| American Airlines | ✅ Sandbox + seat maps | Best airline for sandbox testing including seats |

**Activate airlines**: Duffel dashboard → Airlines → toggle to active.

---

## Seat Maps

- Not all airlines expose seat maps via API. AA is most reliable for testing.
- Seat maps returned as JSON, parsed to ASCII for Telegram/CLI (Phase 1).
- Pillow-based image generator considered for future enhancement — deferred.
- React `@duffel/components` UI not suitable for agent/Telegram context.

---

## Ancillaries

Tested types: baggage, meals, cancellation protection, seat upgrades.
Fee structure: ~$2/service + $3 base order fee (modest relative to fares).
Access: `services <ORDER_ID>` lists available extras post-search.

---

## Sandbox vs Live Reference

| | Sandbox | Live |
|---|---------|------|
| Key prefix | `duffel_test_` | `duffel_live_` |
| Offers | Fake/test data | Real fares |
| Bookings | No charge | Real charge, real PNR |
| Emails | Never sent | Opt-in via dashboard |
| easyJet sandbox | Triggers real-style confirmation emails (preprod) | N/A |
| Reliable airlines | AA, Iberia, easyJet | All dashboard-activated airlines |
| Flaky airlines | LOT, SAS (502 errors) | N/A |

---

## Duffel Balance (Payment)

- **Primary**: Duffel Balance (top-up by bank transfer — no country restrictions)
- **Verified**: Revolut GB card (~0.8% cashback; offsets ~$3 fixed fee on mid-range fares)
- **Fallback**: Amex UAE
- **Avoid**: Duffel Payments card processor — Switzerland excluded from their 22-country list (irrelevant since we use Balance)

---

## Completed Sandbox Tests (2026-04-03)

| Test | Result |
|------|--------|
| VLC→PAR live search | ✅ Multiple airlines, correct pricing |
| GVA→JFK sandbox search | ✅ Offers returned |
| Full booking (AA, sandbox) | ✅ ord_0000B4uh6DIFatu3lCgCZ6, PNR 24FUSF, $3811.75 |
| Cancellation quote + confirm | ✅ Refund to Duffel Balance |
| Nullable conditions handling | ✅ Fixed in order_manager.py |
| Live GVA→DXB search | ✅ Turkish, flydubai, Ethiopian, Kuwait Airways |
| 5% markup client pricing | ✅ Verified math correct |
| Fare card colon alignment | ✅ Dynamic padding — all colons in same column |
| Mobile output format | ✅ Stacked cards, no tables — tested on Telegram mobile |
| Full Swiss LX22/23 fare expansion | ✅ 4 tiers returned (Basic → Flex), $5,739–$6,272 |
| Pagination bug fix | ✅ `?return_offers=true` returns full set (1,714 offers) |

---

## Pricing Validation Log

**2026-04-03**: Confirmed `total_amount` does NOT include Duffel service fee.
- `intended_total_amount` == `total_amount` (fee billed to account separately)
- Old code (3% markup only) was wrong — mixed Duffel fee and agent margin
- New code: `base + base×1% + $3 + base×markup%` — correct
- Transavia VLC→PAR: API $279 → your cost $285 → client (5%) $299

---

## File Map

```
duffel/
├── HANDBOOK.md              ← this file (agent reference)
├── README.md                ← full documentation (user-facing)
├── duffel_client_v2.py      ← main CLI client (use this)
├── duffel_client.py         ← legacy v1 (deprecated)
├── ancillaries.py           ← seat maps + ancillary services
├── order_manager.py         ← cancellations + change tracking
├── booking_flow.py          ← orchestrated end-to-end flow
├── flexible_search.py       ← date-flexible smart search
├── route_cache.py           ← route caching layer
├── airline_cache.py         ← airline list + IATA classification
├── tools_server.py          ← credential fetcher
├── test_booking.py          ← sandbox booking tests
└── test_order_management.py ← sandbox order lifecycle tests
```

---

*TOOLS.md routing: `flight_price_lookup` → Duffel primary, Amadeus fallback*
*Hotels: `hotel_price_lookup` → Amadeus only*

---

## Business Model — Final Structure (2026-04-03)

### Pricing Model

**Every booking has two components:**

**1. Commission (3% markup — always)**
- Applied on every ticket regardless of cabin class or price
- Baked silently into the quoted fare — client never sees this line
- On expensive tickets (business, long-haul) this is the main earning
- On cheap tickets this is small but still included — the booking fee carries the floor

**2. Booking fee (non-refundable — always)**
- Formula: Duffel fee (~1% of fare + $3) + $100 your floor → rounded UP to nearest $25
- Your floor is always $100 USD equivalent; convert to client's preferred currency at day's rate
- Charged per ticket, per passenger — not per order or per group
- Non-refundable regardless of outcome (cancellation or completed travel)

**Reference table (floor $100):**

| Fare | Duffel fee | Booking fee shown |
|------|-----------|-------------------|
| ~$300 (budget short-haul) | ~$6 | $125 |
| ~$1,600 (economy long-haul) | ~$19 | $125 |
| ~$5,900 (business long-haul) | ~$62 | $175 |
| ~$10,000 (first class) | ~$103 | $225 |

**Currency:** Always calculate in USD internally. Present in client's preferred currency (CHF, EUR, USD) at day's rate.

---

### What happens on cancellation

- Booking fee: **kept** (non-refundable, always)
- Commission (3%): **lost** — it was baked into the fare price which gets refunded to client
- Net result on cancellation: booking fee only = covers Duffel costs + $100 your time
- Net result on completed travel: booking fee + full 3% commission

---

### Client segmentation

| Client type | How to present |
|-------------|----------------|
| Trusted (Vasily, Nikolay) | All-in price only. No separate fee line. "CHF 4,860 all-in, flex ticket." |
| New / one-off | Separate lines: ticket price + booking fee (non-refundable) + total |

---

### Multi-passenger bookings

- Search with `--adults N` → Duffel returns one offer with N passenger slots
- All passengers land on **one PNR**, one order, one confirmation
- Booking fee applies **per passenger** unless a family-specific waiver is intentionally used
- Children: Duffel supports `"type": "child"` with `age` field — same booking flow, separate passenger entry
- **Children must always be on the same PNR as their parents** — unaccompanied minor rules, parental consent requirements, and status seat selection (Gold members extending to companions) all require it. Never split a family booking with children.

### Loyalty programmes at booking

Loyalty is attached per-passenger at booking time via `--loyalty`:
```
--loyalty AIRLINE_IATA:MEMBERSHIP_NUMBER
```

The airline IATA code identifies the programme:
- `LX` → Swiss Miles & More
- `LH` → Lufthansa Miles & More
- `EK` → Emirates Skywards
- `UA` → United MileagePlus
- `AF` → Air France Flying Blue
- `BA` → British Airways Executive Club

`--loyalty` is positional: first flag = passenger 1, second flag = passenger 2. Use `""` for a passenger with no loyalty.

**Examples:**
```bash
--loyalty LX:12345678
--loyalty LX:12345678,LH:987654321
--loyalty "LX:<PASSENGER_1_MM_NUMBER>" \
--loyalty ""
```

### Passenger data required fields

Every `--passenger` JSON must include:
```
type, title, given_name, family_name, gender, born_on, email, phone_number
```
- `title`: mr / ms / mrs / miss / dr / prof
- `gender`: m / f
- `phone_number`: must start with `+`
- `email`: must include `@`
- Children: `"type": "child"` with `"age": N`

**When to book separately (adults only, no status seat dependencies):**
- All passengers are independent adults
- No Gold/status member needs to extend seat selection to companions
- Genuine possibility of different travel dates known upfront

**When to keep on one PNR (mandatory):**
- Any child is traveling
- Status member + companions (Gold seat selection extends to same booking only)
- Passengers are confirmed traveling together

**If a post-booking split is needed (e.g. one passenger changes dates):**
- Duffel cannot split an existing order
- Option A: cancel whole order (if flex) → rebook separately (two booking fees)
- Option B: call airline directly → request PNR split → airline handles it operationally; Duffel order becomes stale but booking remains valid

**Example — Vasily + Olga:**
```bash
python3 duffel_client_v2.py book \
  --offer-id off_xxx \
  --passenger '{"given_name":"Vasily","family_name":"...","gender":"m",...}' \
  --passenger '{"given_name":"Olga","family_name":"...","gender":"f",...}' \
  --loyalty "LX:<VASILY_MM_NUMBER>" \
  --loyalty "" \
  --mode live
```

---

### Competitive position vs current agency

| | Current agency (Natalia) | Via Travel (Duffel) |
|---|---|---|
| Ticket price | Net + ~3-4% | Net + 3% (same or slightly less) |
| Booking fee | None stated | $100 floor (non-refundable) |
| Cancellation penalty | €150 flat | Booking fee only (already paid) |
| Changes | Free on flex | Free on flex |
| Payment | Bank transfer | Card (Revolut) or bank |
| Contact | Agency | Single point — Alex |

Client value proposition: same or lower fare price, one trusted contact, card payment option, loyalty numbers handled.


---

## Family Booking Policy Notes (2026-04-03)

**Always one PNR for families.** Same booking = group check-in, shared baggage allowance, seat selection as a unit, Gold status extending to all companions. Never split a family group across separate bookings.

**Post-booking splits:** If circumstances force a PNR split (e.g. one passenger changes dates), Duffel cannot do this — must go directly to the airline. Duffel order becomes stale but booking remains valid with the airline.

**Fee waiver for children (optional policy):**  
- Standard: booking fee per passenger, including children  
- Family discount option: charge booking fee for adults only, waive for children under 18  
- Rationale: children add no meaningful coordination overhead — same PNR, same seats, same check-in  
- Implementation: set `--booking-fee 0` for child passenger entries when applying this policy  

**General principle:** clients booking through a travel agency are already self-selected for service. Standard fees apply unless there's a specific relationship reason to adjust.


---

## Seat Selection Strategy for Families

### Option A — Free auto-assignment (families with children, no specific seat preference)

1. Book all passengers on one PNR (mandatory — airline family seating logic requires same booking)
2. Skip paid seat selection during booking
3. Airline auto-assigns adjacent seats at check-in, keeping children with parents
4. No ancillary fee charged

**Applicable to:** Emirates, Lufthansa, Swiss, British Airways, and most major carriers — children under 12-14 seated with at least one parent as standard policy, even on basic economy fares.

**Client talking point:** "We'll book you on one PNR — the airline will automatically seat your family together at no extra charge."

### Option B — Paid seat selection (control, preference, premium seats)

1. Book all passengers on one PNR
2. Pull seat map via Duffel seat maps API
3. Select specific seats (throne seats, bulkhead, exit row, etc.)
4. Add as ancillary to the order, charge client accordingly

**Use when:** Client wants specific seats (business throne seats, extra legroom, front of cabin), or when automatic assignment risk is too high on a busy flight.

### Decision guide

| Scenario | Recommended |
|----------|-------------|
| Family, economy, no preference | Option A — skip seat selection, save the fee |
| Family, economy, specific row/window wanted | Option B — worth paying for peace of mind |
| Business class, any passenger | Option B — seat choice matters at that price point |
| Vasily's bookings | Option B — throne seats, always |
