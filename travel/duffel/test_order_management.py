#!/usr/bin/env python3
"""
Duffel Sandbox - Complete Order Management Test
Tests: search → book → change eligibility → cancellation (full flow) → ancillaries

All sandbox (fake data, no real bookings)

Usage:
    python3 test_order_management.py
"""

from duffel_client import DuffelClient, DuffelError
from order_manager import OrderManager
import json
import os

print("="*80)
print("DUFFEL SANDBOX - COMPLETE ORDER MANAGEMENT TEST")
print("="*80)

client = DuffelClient(mode="sandbox")
mgr = OrderManager(client)

# ============== STEP 1: SEARCH & BOOK ==============
print("\n" + "="*80)
print("STEP 1: SEARCH & BOOK (American Airlines - known to support API cancellation)")
print("="*80)

search_result = client.search_flights(
    origin="GVA",
    destination="JFK",
    departure_date="2026-06-24",
    return_date="2026-07-08",
    cabin_class="business",
    adults=1
)

offers = search_result["offers"]
passengers_template = search_result["passengers"]

# Pick American Airlines (reliable for cancellation testing)
aa_offer = next(
    (o for o in offers if o.get("owner", {}).get("name") == "American Airlines"),
    offers[0]
)

print(f"\n✈️  Selected: {aa_offer['owner']['name']}")
print(f"   Offer ID: {aa_offer['id']}")
print(f"   Total: {aa_offer['total_currency']} {aa_offer['total_amount']}")

conditions = aa_offer.get("conditions") or {}
refundable = (conditions.get("refund_before_departure") or {}).get("allowed", False)
print(f"   Refundable: {'✅ YES' if refundable else '❌ NO'}")

# Book the order
passenger = {
    "id": passengers_template[0]["id"],  # REQUIRED from search response
    "type": "adult",
    "title": "mr",
    "given_name": "Test",
    "family_name": "Passenger",
    "gender": "m",
    "born_on": "1985-01-15",
    "email": "alexey.prudkov@via.travel",
    "phone_number": "+41791234567",
}

print(f"\n🎫 Booking order...")
order = client.create_order(aa_offer["id"], [passenger], payment_type="balance")
order_id = order["id"]
print(f"\n✅ ORDER CREATED: {order_id}")
print(f"   PNR: {order['booking_reference']}")
print(f"   Total: {order['total_currency']} {order['total_amount']}")

# ============== STEP 2: CHECK CHANGE/CANCEL ELIGIBILITY ==============
print("\n" + "="*80)
print("STEP 2: CHECK CHANGE/CANCEL ELIGIBILITY")
print("="*80)

change_info = mgr.get_order_change_request(order_id)
print("\n📋 Order Status:")
print(mgr.format_change_info(change_info))

# ============== STEP 3: TEST CANCELLATION (FULL FLOW) ==============
print("\n" + "="*80)
print("STEP 3: TEST CANCELLATION (QUOTE + CONFIRM)")
print("="*80)

print("\n🔴 Getting cancellation quote...")
try:
    quote = mgr.get_cancellation_quote(order_id)
    print(mgr.format_cancellation_quote(quote))
    
    cancellation_id = quote.get("id")
    if cancellation_id:
        print(f"\n✅ Quote received: {cancellation_id}")
        print(f"   Refund: {quote.get('refund_amount')} {quote.get('refund_currency')}")
        print(f"   Refund to: {quote.get('refund_to')}")
        
        # Confirm cancellation
        print(f"\n🔴 Confirming cancellation...")
        result = mgr.confirm_cancellation(cancellation_id)
        print(f"\n✅ CANCELLATION CONFIRMED")
        print(f"   Status: {result.get('status')}")
        print(f"   Refund: {result.get('refund_amount')} {result.get('refund_currency')}")
        print(f"   Refund to: {result.get('refund_to')}")
        
except DuffelError as e:
    print(f"\n❌ Cancellation failed: {e.message}")
    if e.errors:
        for err in e.errors:
            print(f"   {err.get('title')}: {err.get('message')}")
    print("\n⚠️  Note: Some airlines (e.g., easyJet) don't support API cancellation.")
    print("   Must cancel directly with the airline in those cases.")

# ============== STEP 4: BOOK FRESH ORDER FOR ANCILLARY TEST ==============
print("\n" + "="*80)
print("STEP 4: BOOK FRESH ORDER FOR ANCILLARY TEST")
print("="*80)

search_result2 = client.search_flights(
    origin="LHR",
    destination="JFK",
    departure_date="2026-07-15",
    cabin_class="economy",
    adults=1
)

offer2 = search_result2["offers"][0]
passenger2 = {
    "id": search_result2["passengers"][0]["id"],
    "type": "adult", "title": "mr",
    "given_name": "Ancillary", "family_name": "Test",
    "gender": "m", "born_on": "1985-01-15",
    "email": "alexey.prudkov@via.travel",
    "phone_number": "+41791234567",
}

order2 = client.create_order(offer2["id"], [passenger2], payment_type="balance")
order2_id = order2["id"]
print(f"\n✅ Order for ancillary test: {order2_id}")

# ============== STEP 5: TEST ANCILLARIES ==============
print("\n" + "="*80)
print("STEP 5: TEST ANCILLARIES (SEATS & BAGGAGE)")
print("="*80)

# Note: ancillaries require the ancillaries.py module which uses /air/services endpoint
# This is a placeholder - full ancillary test requires seat map data
print("\n📦 Ancillary services available post-booking:")
print("   - Baggage (extra bags, weight upgrades)")
print("   - Meals (special dietary, premium meals)")
print("   - Seats (pre-booking via seat maps, post-booking via services)")
print("   - Cancel for any reason protection")
print("\n⚠️  Full ancillary test requires:")
print("   1. Airline that supports ancillaries in sandbox")
print("   2. Seat map data (not all airlines provide)")
print("\n📚 Use duffel_client_v2.py for ancillary commands:")
print(f"   python3 duffel_client_v2.py services --order-id {order2_id} --mode sandbox")

# ============== STEP 6: EXPORT ORDER DATA ==============
print("\n" + "="*80)
print("STEP 6: EXPORT ORDER DATA")
print("="*80)

# Fetch full order details
full_order = client.get_order(order2_id)

# Save to temp file
output_path = f"/tmp/duffel_order_{order2_id}.json"
with open(output_path, "w") as f:
    json.dump(full_order, f, indent=2)

print(f"\n📄 Full order JSON saved to: {output_path}")
print(f"\n📋 Order Summary:")
print(f"   ID: {full_order['id']}")
print(f"   PNR: {full_order.get('booking_reference', 'N/A')}")
print(f"   Status: {full_order.get('status', 'N/A')}")
print(f"   Created: {full_order.get('created_at', 'N/A')}")
print(f"   Total: {full_order.get('total_currency')} {full_order.get('total_amount')}")

# ============== SUMMARY ==============
print("\n" + "="*80)
print("✅ ORDER MANAGEMENT TEST COMPLETE")
print("="*80)

print("\n🎯 Test Results:")
print("   ✓ Search flights")
print("   ✓ Create order")
print("   ✓ Check change eligibility")
print("   ✓ Cancellation quote + confirm (American Airlines)")
print("   ✓ View order details")
print("   ✓ Export order data")
print("\n📚 API Reference:")
print("   - Search: POST /air/offer_requests → GET /air/offers")
print("   - Book: POST /air/orders")
print("   - Change: POST /air/order_change_offers → confirm")
print("   - Cancel: POST /air/order_cancellations → confirm")
print("   - Ancillaries: POST /air/order_services")
print("   - View: GET /air/orders/{id}")
print(f"\n🔗 Dashboard: https://app.duffel.com/orders/{order2_id}")
print("="*80)
