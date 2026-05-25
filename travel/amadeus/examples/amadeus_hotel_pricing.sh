#!/bin/bash

AMADEUS_TOKEN=$(curl -s -X POST https://api.amadeus.com/v1/security/oauth2/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=client_credentials&client_id=${AMADEUS_CLIENT_ID:?set AMADEUS_CLIENT_ID}&client_secret=${AMADEUS_CLIENT_SECRET:?set AMADEUS_CLIENT_SECRET}" | jq -r .access_token)

CHECK_IN=$(date -d "tomorrow" +%Y-%m-%d)
CHECK_OUT=$(date -d "tomorrow + 1 day" +%Y-%m-%d)

echo "Fetching exact pricing and availability for tomorrow night ($CHECK_IN to $CHECK_OUT) for 1 adult..."

# Checking pricing for the top 5 closest hotels from our previous step
curl -s -X GET "https://api.amadeus.com/v3/shopping/hotel-offers?hotelIds=RTGVAEVE,HLGVAAE7,RTGVAEPO,RTGVAVIO,WVGVA916&adults=1&checkInDate=$CHECK_IN&checkOutDate=$CHECK_OUT&roomQuantity=1&paymentPolicy=NONE&bestRateOnly=true" \
  -H "Authorization: Bearer $AMADEUS_TOKEN" | jq -r '
  if .data then 
    .data[] | 
    "Hotel: \(.hotel.name)\n" +
    "Available Room: \(.offers[0].room.typeEstimated.category // "Standard") - \(.offers[0].room.description.text // "No description")\n" +
    "Price: \(.offers[0].price.total) \(.offers[0].price.currency)\n" +
    "---"
  else 
    "Error or No availability" 
  end'

