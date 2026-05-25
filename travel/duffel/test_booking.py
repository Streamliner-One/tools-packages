#!/usr/bin/env python3
"""
Duffel Sandbox Booking Test
Runs a full search → book cycle in sandbox mode.
Uses real passenger details but NO real money (sandbox only).

Usage:
    python3 test_booking.py
"""

import sys
import os
import json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from duffel_client import DuffelClient, DuffelError

client = DuffelClient(mode="sandbox")

print("=" * 50)
print("DUFFEL SANDBOX BOOKING TEST")
print("=" * 50)
print()

try:
    # Step 1: Search — always fresh so we get valid passenger IDs and non-expired offers
    print("🔍 Searching GVA → JFK round-trip, 24 Jun – 08 Jul 2026, business...")
    result = client.search_flights(
        origin="GVA",
        destination="JFK",
        departure_date="2026-06-24",
        return_date="2026-07-08",
        cabin_class="business",
        adults=1
    )

    offers = result["offers"]
    passengers_template = result["passengers"]

    print(f"   Found {len(offers)} offers")
    print(f"   Passenger template ID: {passengers_template[0]['id']}")
    print()

    # Step 2: Pick a reliable sandbox airline (AA or Iberia; LOT/SAS often 502)
    preferred = ["American Airlines", "Iberia", "British Airways", "Duffel Airways"]
    offer = next(
        (o for o in offers if o.get("owner", {}).get("name") in preferred),
        offers[0]
    )

    airline = offer.get("owner", {}).get("name", "?")
    total = offer.get("total_amount", "?")
    currency = offer.get("total_currency", "USD")
    conditions = offer.get("conditions") or {}
    refundable = (conditions.get("refund_before_departure") or {}).get("allowed", False)

    print(f"✈️  Selected: {airline}")
    print(f"   Offer ID: {offer['id']}")
    print(f"   Total: {currency} {total}")
    print(f"   Refundable: {'✅ YES' if refundable else '❌ NO'}")
    print()

    # Step 3: Book — passenger ID must come from search response
    passenger_id = passengers_template[0]["id"]

    passenger = {
        "id": passenger_id,        # REQUIRED: from search response
        "type": "adult",
        "title": "mr",
        "given_name": "Alexey",
        "family_name": "Prudkov",
        "gender": "m",
        "born_on": "1978-08-20",
        "email": "alexey.prudkov@via.travel",
        "phone_number": "+41791234567",
    }

    print(f"🎫 Booking for: {passenger['given_name']} {passenger['family_name']}")
    print(f"   Email: {passenger['email']}")
    print()

    order = client.create_order(
        offer_id=offer["id"],
        passengers=[passenger],
        payment_type="balance"
    )

    print("=" * 50)
    print("✅  ORDER CREATED")
    print("=" * 50)
    print(f"   Order ID  : {order.get('id')}")
    print(f"   PNR       : {order.get('booking_reference')}")
    print(f"   Total     : {order.get('total_currency')} {order.get('total_amount')}")
    print()

    for i, sl in enumerate(order.get("slices", [])):
        dep = sl["segments"][0]["departing_at"][:10] if sl.get("segments") else "?"
        org = sl.get("origin", {}).get("iata_code", "?")
        dst = sl.get("destination", {}).get("iata_code", "?")
        print(f"   Slice {i+1}: {org} → {dst} on {dep}")

    print()
    print("Note: sandbox — no email sent. In live mode with dashboard toggle ON,")
    print("      Duffel sends a confirmation to the passenger email.")

except DuffelError as e:
    print(f"❌ DuffelError: {e.message}")
    if e.errors:
        for err in e.errors:
            print(f"   {err.get('title')}: {err.get('message')}")
    sys.exit(1)
except Exception as e:
    import traceback
    print(f"❌ Error: {e}")
    traceback.print_exc()
    sys.exit(1)
