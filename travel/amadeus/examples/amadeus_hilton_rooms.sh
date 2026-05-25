#!/bin/bash

AMADEUS_TOKEN=$(curl -s -X POST https://api.amadeus.com/v1/security/oauth2/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=client_credentials&client_id=${AMADEUS_CLIENT_ID:?set AMADEUS_CLIENT_ID}&client_secret=${AMADEUS_CLIENT_SECRET:?set AMADEUS_CLIENT_SECRET}" | jq -r .access_token)

CHECK_IN=$(date -d "tomorrow" +%Y-%m-%d)
CHECK_OUT=$(date -d "tomorrow + 1 day" +%Y-%m-%d)

# Hilton Geneva Hotel and Conference Centre ID is HLGVAAE7
# We set bestRateOnly=false to get ALL available rooms/rates, not just the cheapest one

curl -s -X GET "https://api.amadeus.com/v3/shopping/hotel-offers?hotelIds=HLGVAAE7&adults=1&checkInDate=$CHECK_IN&checkOutDate=$CHECK_OUT&roomQuantity=1&paymentPolicy=NONE&bestRateOnly=false" \
  -H "Authorization: Bearer $AMADEUS_TOKEN" | jq -r '
  if .data then 
    .data[0].offers[] | 
    "🛏️ Room: \(.room.typeEstimated.category // "Standard")\n" +
    "📝 Description: \(.room.description.text // "No description")\n" +
    "💰 Price: \(.price.total) \(.price.currency)\n" +
    "🎫 Rate Plan: \(.policies.paymentType // "Standard")\n" +
    "---"
  else 
    "Error or No availability" 
  end'

