# Hermes Travel Capability Parity Handoff — 2026-05-25

Safe export from Mel's current working travel-management material for Ava/Hermes parity. This branch intentionally contains source-controlled code/docs/examples only. It does not contain live credentials, local registries, booking PII, or Mel runtime state.

## Included paths

### Duffel
- `travel/duffel/HANDBOOK.md` — canonical agent workflow and presentation format.
- `travel/duffel/README.md` — file map, credential mode notes, tested sandbox flows.
- `travel/duffel/duffel_client.py` — core client.
- `travel/duffel/duffel_client_v2.py` — current primary CLI.
- `travel/duffel/tools_server.py` — credential helper pattern for a local tools-server.
- `travel/duffel/booking_flow.py`, `ancillaries.py`, `order_manager.py`, `flexible_search.py`, `route_cache.py`, `airline_cache.py` — support modules.
- `travel/duffel/test_booking.py`, `test_order_management.py` — sandbox lifecycle tests. Use with sandbox credentials only.
- `travel/duffel/route_cache.json`, `airlines.json` — advisory caches, not authoritative inventory.

### Amadeus
- `travel/amadeus/AMADEUS_HOTELS.md` — two-step hotel flow, sanitized auth notes, deprecation warning.
- `travel/amadeus/examples/amadeus_hotel_search.sh` — safe hotel-list smoke example.
- `travel/amadeus/examples/amadeus_hotel_pricing.sh` — safe hotel-offers smoke example.
- `travel/amadeus/examples/amadeus_hilton_rooms.sh` — safe single-property room/rate smoke example.

### Tools Server excerpts
- `travel/tools-server/schema.js` — current service package definitions including Amadeus and Duffel.
- `travel/tools-server/usage.js` — current call templates and agent notes.
- `travel/tools-server/router.json` — current intent-to-package routing.

## Current Duffel account/card/booking status

From Mel's current docs/state:
- Two Duffel credentials are expected:
  - live credential id: `duffel`, key prefix `duffel_live_...`.
  - sandbox credential id: `duffel-1775151120476`, key prefix `duffel_test_...`.
- Live mode means real fares, real charges, real PNR. Do not run booking commands without explicit human approval.
- Sandbox mode is safe for tests and fake bookings. No real charges and no passenger emails.
- Mel uses Duffel Balance, not Duffel Payments card processing. Prior note: Swiss seller-country restriction applies to Duffel Payments, not Duffel Balance.
- Known airline coverage limitations: no SWISS LX in Duffel; Emirates EK inactive / special approval required. Fall back to Amadeus/direct airline/GDS as appropriate.
- Tested sandbox flows documented in `travel/duffel/README.md` and `HANDBOOK.md`: search+book for AA/BA/easyJet; cancellation quote+confirm works for AA; easyJet API cancellation returns 422.
- This handoff does not assert current live Duffel balance or production activation beyond the credential presence pattern. Ava should verify in her own Duffel dashboard/tools-server health before live operations.

## Safe authentication model for Ava

Do not reuse Mel's live machine as a runtime dependency.

Ava should provision her own local tools-server and store instance-local credentials there:
- Duffel live: credential id `duffel`, field `apiKey`, source from Ava's 1Password item or Duffel dashboard.
- Duffel sandbox: credential id such as `duffel-sandbox` or Mel-compatible `duffel-1775151120476`, field `apiKey`.
- Amadeus: credential id `amadeus`, fields `clientId`, `clientSecret`, `environment` (`production` or `test`).
- Environment variables for standalone examples:
  - `AMADEUS_CLIENT_ID`
  - `AMADEUS_CLIENT_SECRET`
  - `DUFFEL_ACCESS_TOKEN` only if bypassing tools-server for one-off smoke tests.

1Password refs without secrets from Mel:
- Amadeus: vault `Alex-Mel`, item `Amadeus API`, fields `credential` and `Private API key`.
- Duffel: stored in tools-server credentials; use Ava's own vault/item naming when moving to Ava.

## First smoke command Ava should run

Install Python deps as needed (`requests`; `jq` for shell examples). Then start with a non-booking Duffel sandbox search:

```bash
cd travel/duffel
python3 duffel_client_v2.py search --origin GVA --destination BCN --date 2026-07-15 --mode sandbox --sort price --limit 5
```

This creates no booking and spends no money.

Then run a non-booking Amadeus hotel-list smoke:

```bash
cd travel/amadeus/examples
AMADEUS_CLIENT_ID=... AMADEUS_CLIENT_SECRET=... bash amadeus_hotel_search.sh
```

That only fetches hotel IDs near Geneva airport.

## How Ava should run her own local Tools Server + MCP sidecar

Recommended topology:
- Ava VPS runs its own OpenClaw/Gateway stack.
- Ava VPS runs its own tools-config-server bound to localhost or Tailscale only.
- Ava's agent reads its own generated `TOOLS.md` / `TOOLS-REFERENCE.md` from that instance.
- Ava runs her own MCP sidecars locally: Polycal, Persona, and Tools Server MCP/HTTP access. Mel's machine is reference knowledge only.

Install/run outline:

```bash
# Install repo
# https://github.com/Streamliner-One/tools
# Tools server repo
# https://github.com/Streamliner-One/tools-config-server

cd tools-server
npm install
node server.js --bind 127.0.0.1:8080 --password "$TOOLS_SERVER_PASSWORD" --data-dir "$HOME/.openclaw"
```

For production: run under systemd, bind to localhost/Tailscale, and put data under `~/.openclaw` or another instance-local path outside any public git tree. Do not put vaults, registry files, logs, certs, or generated TOOLS files inside release artifact paths.

MCP sidecar principle:
- Polycal/Persona should have local storage and local service credentials on Ava's VPS.
- Tools Server credentials should be local to Ava.
- Agents should call localhost/Tailscale services, not Mel's live machine.

## Source-controlled vs instance-local

Source-controlled:
- Travel clients and support modules.
- Handbooks, examples, schemas, validators, package definitions.
- Intent routing definitions that contain no secrets.
- Smoke scripts that do not create bookings or spend money.

Instance-local / never commit:
- `tools-registry.json`, `.health-cache.json`, generated `TOOLS.md`, generated `TOOLS-REFERENCE.md` if they contain local state.
- TLS certs/keys, server logs, cookie jars, OAuth tokens.
- Duffel/Amadeus keys, gateway tokens, 1Password exports.
- Obsidian vault contents and sync state.
- Passenger PII, live order details, booking references unless deliberately redacted for test docs.

## Known blockers before Hermes parity

- Need Ava-owned credential setup and health checks for Duffel + Amadeus.
- Need explicit no-spend guardrails around booking commands. Search/show/cancel-quote are safe; create-order/cancel-confirm are not safe without approval.
- Duffel coverage gaps: LX absent, EK inactive/special approval; direct airline/GDS fallback remains necessary.
- Amadeus developer APIs have a documented decommission window in current notes; hotel flow may need replacement by Duffel Stays or another hotel provider.
- Tools Server currently has first-class schema/usage entries for Duffel/Amadeus, but this handoff exports excerpts rather than a packaged `packages/duffel` / `packages/amadeus` directory in tools-packages. If Ava needs package-level installability, promote these into package definitions next.
- MCP parity requires Ava-local Polycal/Persona/Tools Server sidecars; do not make Ava call Mel's local services in production.
