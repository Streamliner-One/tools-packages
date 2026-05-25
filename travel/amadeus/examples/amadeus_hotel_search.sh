#!/bin/bash

# Get Amadeus Token
echo "Fetching Amadeus Auth Token..."
AMADEUS_TOKEN=$(curl -s -X POST https://api.amadeus.com/v1/security/oauth2/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=client_credentials&client_id=${AMADEUS_CLIENT_ID:?set AMADEUS_CLIENT_ID}&client_secret=${AMADEUS_CLIENT_SECRET:?set AMADEUS_CLIENT_SECRET}" | jq -r .access_token)

if [ "$AMADEUS_TOKEN" == "null" ] || [ -z "$AMADEUS_TOKEN" ]; then
    echo "Failed to get token."
    exit 1
fi

# Geneva Airport IATA is GVA
# Tomorrow's date
CHECK_IN=$(date -d "tomorrow" +%Y-%m-%d)
CHECK_OUT=$(date -d "tomorrow + 1 day" +%Y-%m-%d)

echo "Searching for hotels near GVA (within 5km) for $CHECK_IN to $CHECK_OUT..."

# Step 1: Find hotels by geocode (GVA coordinates: 46.2381° N, 6.1089° E)
# Or use the Hotel List API by cityCode/airportCode
curl -s -X GET "https://api.amadeus.com/v1/reference-data/locations/hotels/by-geocode?latitude=46.2381&longitude=6.1089&radius=5&radiusUnit=KM" \
  -H "Authorization: Bearer $AMADEUS_TOKEN" | jq -r '.data[0:5] | .[] | "Hotel: \(.name) (ID: \(.hotelId)) - Distance: \(.distance.value) \(.distance.unit)"'

