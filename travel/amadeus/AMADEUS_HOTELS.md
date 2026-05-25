# Amadeus Hotel API Integration

Last updated: 2026-02-22

**⚠️ DEPRECATION WARNING:** Amadeus developer APIs are being decommissioned starting March 2026, fully shut down by July 2026. This integration will stop working. Consider migrating to Duffel Stays (when account is activated) or another alternative.

## Working Configuration

**API Endpoint:** `https://api.amadeus.com`
**Authentication:** OAuth 2.0 client credentials

**Credentials:** stored in Ava/Mel instance-local tools-server or 1Password. Do not commit secrets.
- Client ID env: `AMADEUS_CLIENT_ID`
- Client Secret env: `AMADEUS_CLIENT_SECRET`
- Mel 1Password ref: item `Amadeus API`, fields `credential` and `Private API key`, vault `Alex-Mel`

## Two-Step Search Process

### Step 1: Get Access Token
```bash
CLIENT_ID="${AMADEUS_CLIENT_ID:?set AMADEUS_CLIENT_ID}"
CLIENT_SECRET="${AMADEUS_CLIENT_SECRET:?set AMADEUS_CLIENT_SECRET}"

curl -s -X POST "https://api.amadeus.com/v1/security/oauth2/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=client_credentials&client_id=$CLIENT_ID&client_secret=$CLIENT_SECRET"
# Returns: { "access_token": "...", "expires_in": 1800 }
```

### Step 2a: Find Hotels by Location
```bash
ACCESS_TOKEN="your_token_here"

curl -s -X GET "https://api.amadeus.com/v1/reference-data/locations/hotels/by-geocode?latitude=46.2375&longitude=6.1090&radius=5&radiusUnit=KM" \
  -H "Authorization: Bearer $ACCESS_TOKEN"
# Returns list of hotelIds: RTGVAEVE, RTGVAEPO, HLGVAAE7, etc.
```

### Step 2b: Get Hotel Offers
```bash
# Use hotel IDs from step 2a
HOTEL_IDS="RTGVAEVE,RTGVAEPO,HLGVAAE7"

curl -s -X GET "https://api.amadeus.com/v3/shopping/hotel-offers?hotelIds=${HOTEL_IDS}&checkInDate=2026-03-01&checkOutDate=2026-03-02&adults=2&roomQuantity=1" \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```

## Key Parameters

| Parameter | Description | Example |
|-----------|-------------|---------|
| `latitude` / `longitude` | Search center coordinates | 46.2375, 6.1090 (Geneva Airport) |
| `radius` | Search radius | 5 (with `radiusUnit=KM`) |
| `checkInDate` / `checkOutDate` | Stay dates | 2026-03-01, 2026-03-02 |
| `adults` | Number of guests | 2 |
| `roomQuantity` | Number of rooms | 1 |

## Response Fields

**Hotel info:**
- `hotel.name` - Property name
- `hotel.latitude` / `hotel.longitude` - Location
- `hotel.chainCode` - Brand (HL=Hilton, RT=ibis, etc.)

**Offer details:**
- `offers[0].price.total` - Total price
- `offers[0].price.currency` - CHF, EUR, etc.
- `offers[0].room.typeEstimated.bedType` - KING, DOUBLE, QUEEN, etc.
- `offers[0].boardType` - ROOM_ONLY, BREAKFAST_INCLUDED, etc.
- `offers[0].policies.cancellations` - Cancellation rules

## When to Use

**Use Amadeus Hotel API when:**
- Need hotel options for any destination
- Quick price comparison near airports/city centers
- Checking availability for specific dates
- Looking for specific room types (twin, king, etc.)

**Don't use when:**
- User has accommodation already (like Geneva apartment!)
- After July 2026 (API will be shut down)

## Migration Plan (Post-July 2026)

1. **Primary:** Duffel Stays (request account activation)
2. **Alternative:** Booking.com affiliate API
3. **Alternative:** RapidAPI hotel aggregators

## Test Search: Geneva Airport, March 1-2

**Results (within 5km):**
- Hilton Geneva - CHF 169 (King room)
- ibis Styles Palexpo - CHF 109 (Double)
- ibis budget Palexpo - CHF 109 (Double + bunk)
- ibis Genève Aéroport - CHF 110 (Double)
- Nash Pratik Hotel - CHF 89 (Queen)

All ~1-2km from airport, room-only rates.
