#!/usr/bin/env python3
"""
Interactive End-to-End Booking Flow
Orchestrates search → seat selection → services → booking for Via Travel clients.

Usage:
    python booking_flow.py --origin GVA --destination JFK --date 2026-06-24 --return-date 2026-07-08 --cabin business --mode sandbox
"""

import sys
import os
import argparse
from typing import Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from duffel_client_v2 import DuffelClient, DuffelError
from ancillaries import AncillaryManager, _sym
from order_manager import OrderManager

MARKUP_PCT = 3.0

TEST_PASSENGER = {
    "type": "adult",
    "title": "mr",
    "given_name": "Test",
    "family_name": "Passenger",
    "gender": "m",
    "born_on": "1985-05-15",
    "email": "test@via.travel",
    "phone_number": "+41791234567",
}


def _apply_markup(amount: float) -> float:
    return amount * (1 + MARKUP_PCT / 100)


def _format_price(amount: float, currency: str, with_markup: bool = True) -> str:
    sym = _sym(currency)
    if with_markup:
        marked = _apply_markup(amount)
        return f"{sym}{amount:.2f} net → {sym}{marked:.2f} client ({MARKUP_PCT}% markup)"
    return f"{sym}{amount:.2f}"


def _slice_summary(sl: Dict) -> str:
    """One-line summary of a slice."""
    segs = sl.get("segments", [])
    if not segs:
        return "?"
    origin = segs[0].get("origin", {}).get("iata_code", "?")
    dest = segs[-1].get("destination", {}).get("iata_code", "?")
    stops = max(0, len(segs) - 1)
    stops_text = "direct" if stops == 0 else f"{stops} stop{'s' if stops > 1 else ''}"

    # Duration
    try:
        from datetime import datetime
        dep = datetime.fromisoformat(segs[0]["departing_at"])
        arr = datetime.fromisoformat(segs[-1]["arriving_at"])
        mins = int((arr - dep).total_seconds() / 60)
        h, m = divmod(mins, 60)
        duration = f"{h}h{m:02d}m"
    except (KeyError, ValueError):
        duration = "?"

    # Times
    try:
        dep_time = datetime.fromisoformat(segs[0]["departing_at"]).strftime("%H:%M")
        arr_time = datetime.fromisoformat(segs[-1]["arriving_at"]).strftime("%H:%M")
        times = f"{dep_time}–{arr_time}"
    except (KeyError, ValueError):
        times = ""

    carrier = segs[0].get("operating_carrier", {}).get("name", "") or segs[0].get("marketing_carrier", {}).get("name", "")
    flight_no = segs[0].get("marketing_carrier_flight_number", "")
    carrier_code = segs[0].get("marketing_carrier", {}).get("iata_code", "")

    return f"{origin} → {dest} | {carrier} {carrier_code}{flight_no} | {stops_text} | {duration} | {times}"


def _prompt(text: str) -> str:
    """Prompt user for input."""
    try:
        return input(f"\n{text} ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nAborted.")
        sys.exit(0)


def run_booking_flow(origin: str, destination: str, departure_date: str,
                     return_date: Optional[str], cabin_class: str, mode: str) -> None:
    """Run the full interactive booking flow."""

    # Initialize client
    try:
        client = DuffelClient(mode=mode)
    except DuffelError as e:
        print(f"❌ {e.message}")
        sys.exit(1)

    anc = AncillaryManager(client)
    omgr = OrderManager(client)

    # ── Step 1: Search ──
    print(f"\n{'='*70}")
    print(f"FLIGHT SEARCH: {origin} → {destination}")
    print(f"Date: {departure_date}" + (f" / Return: {return_date}" if return_date else " (one-way)"))
    print(f"Cabin: {cabin_class} | Mode: {mode.upper()}")
    print(f"{'='*70}")

    try:
        result = client.search_flights(
            origin=origin, destination=destination,
            departure_date=departure_date, return_date=return_date,
            cabin_class=cabin_class, sort_by="duration",
        )
    except DuffelError as e:
        print(f"❌ Search failed: {e.message}")
        sys.exit(1)

    offers = result["offers"]
    if not offers:
        print("No flights found for this route/date.")
        sys.exit(0)

    # Show top 3
    top_n = min(3, len(offers))
    print(f"\nTop {top_n} options:\n")
    for i, offer in enumerate(offers[:top_n], 1):
        net = float(offer.get("total_amount", 0))
        cur = offer.get("total_currency", "EUR")
        airline = offer.get("owner", {}).get("name", "Unknown")

        print(f"  Option {i}: {airline} — {_format_price(net, cur)}")
        for j, sl in enumerate(offer.get("slices", [])):
            direction = "Outbound" if j == 0 else "Return"
            print(f"    {direction}: {_slice_summary(sl)}")
        print()

    # ── Step 2: Select offer ──
    choice = _prompt(f"Which option? (1-{top_n} or q to quit):")
    if choice.lower() == "q":
        print("Cancelled.")
        return
    try:
        idx = int(choice) - 1
        if idx < 0 or idx >= top_n:
            raise ValueError
    except ValueError:
        print("Invalid choice.")
        return

    selected_offer = offers[idx]
    offer_id = selected_offer["id"]
    net_fare = float(selected_offer.get("total_amount", 0))
    fare_currency = selected_offer.get("total_currency", "EUR")
    print(f"\n✓ Selected: {selected_offer.get('owner', {}).get('name')} — {_sym(fare_currency)}{net_fare:.2f}")

    # ── Step 3: Seat map ──
    selected_seats = []
    try:
        seat_data = anc.get_seat_map(offer_id)
        if seat_data:
            for sm in seat_data:
                cabins = sm.get("cabins", [])
                has_seats = any(
                    el.get("available_services")
                    for cab in cabins
                    for row in cab.get("rows", [])
                    for sec in row.get("sections", [])
                    for el in sec.get("elements", [])
                    if el.get("type") == "seat"
                )
                if has_seats:
                    print(anc.format_seat_map([sm], max_rows=8))

            seat_input = _prompt("Select seats? (e.g. 1A,2K or press Enter to skip):")
            if seat_input:
                selected_seats = [s.strip() for s in seat_input.split(",") if s.strip()]
                print(f"  Seats noted: {', '.join(selected_seats)}")
        else:
            print("\nSeat map not available for this flight.")
    except DuffelError:
        print("\nSeat map not available for this flight.")

    # ── Step 4: Show summary and confirm ──
    extras_cost = 0.0  # seat/service costs added post-booking

    print(f"\n{'='*70}")
    print("BOOKING SUMMARY")
    print(f"{'='*70}")
    print(f"Flight: {selected_offer.get('owner', {}).get('name', '?')}")
    for j, sl in enumerate(selected_offer.get("slices", [])):
        direction = "Outbound" if j == 0 else "Return"
        print(f"  {direction}: {_slice_summary(sl)}")
    if selected_seats:
        print(f"  Seats requested: {', '.join(selected_seats)}")
    print(f"\nFare: {_format_price(net_fare, fare_currency)}")
    client_total = _apply_markup(net_fare)
    print(f"Client total: {_sym(fare_currency)}{client_total:.2f}")
    print(f"\nPassenger: {TEST_PASSENGER['title'].upper()} {TEST_PASSENGER['given_name']} {TEST_PASSENGER['family_name']}")
    print(f"Payment: balance (sandbox)")

    confirm = _prompt("Confirm booking? (y/n):")
    if confirm.lower() != "y":
        print("Booking cancelled.")
        return

    # ── Step 5: Create order ──
    try:
        # Get passenger ID from offer
        offer_detail = client._get_offer(offer_id)
        offer_passengers = offer_detail.get("passengers", [])
        if not offer_passengers:
            print("❌ No passenger slots in offer.")
            return

        passenger = {"id": offer_passengers[0]["id"], **TEST_PASSENGER}
        order = client.create_order(
            offer_id=offer_id,
            passengers=[passenger],
            payment_type="balance",
        )
    except DuffelError as e:
        print(f"\n❌ Booking failed: {e.message}")
        if e.errors:
            for err in e.errors:
                print(f"   - {err.get('title', '')}: {err.get('message', '')}")
        return

    order_id = order.get("id", "?")
    pnr = order.get("booking_reference", "?")
    total_charged = order.get("total_amount", "?")
    total_cur = order.get("total_currency", fare_currency)

    print(f"\n{'='*70}")
    print("✅ BOOKING CONFIRMED")
    print(f"{'='*70}")
    print(f"  Order ID:  {order_id}")
    print(f"  PNR:       {pnr}")
    print(f"  Charged:   {_sym(total_cur)}{total_charged}")
    print(f"  Client price: {_sym(total_cur)}{_apply_markup(float(total_charged)):.2f} ({MARKUP_PCT}% markup)")

    # ── Step 6: Post-booking services ──
    try:
        services = anc.get_available_services(order_id)
        if services:
            print(f"\n--- AVAILABLE ADD-ONS ---")
            print(anc.format_services(services))

            svc_input = _prompt("Add any services? (comma-separated IDs, or Enter to skip):")
            if svc_input:
                svc_ids = [s.strip() for s in svc_input.split(",") if s.strip()]
                if svc_ids:
                    try:
                        add_result = anc.add_services_to_order(order_id, svc_ids)
                        print(f"✅ Services added to order {order_id}.")
                    except (DuffelError, ValueError) as e:
                        msg = e.message if hasattr(e, "message") else str(e)
                        print(f"⚠️  Could not add services: {msg}")
        else:
            print("\nNo additional services available for this booking.")
    except DuffelError:
        print("\nServices not available for this booking.")

    print(f"\nDone. Order {order_id} (PNR: {pnr}) is confirmed.")


def main():
    parser = argparse.ArgumentParser(description="Interactive Flight Booking Flow")
    parser.add_argument("--origin", required=True, help="Origin IATA code")
    parser.add_argument("--destination", required=True, help="Destination IATA code")
    parser.add_argument("--date", required=True, help="Departure date (YYYY-MM-DD)")
    parser.add_argument("--return-date", help="Return date (YYYY-MM-DD)")
    parser.add_argument("--cabin", default="economy", help="Cabin class")
    parser.add_argument("--adults", type=int, default=1, help="Number of adults")
    parser.add_argument("--mode", default="sandbox", choices=["sandbox", "live"], help="API mode")
    args = parser.parse_args()

    if args.mode == "live":
        print(f"\n⚠️  WARNING: LIVE MODE - Real bookings will be charged!\n", file=sys.stderr)

    run_booking_flow(
        origin=args.origin,
        destination=args.destination,
        departure_date=args.date,
        return_date=args.return_date,
        cabin_class=args.cabin,
        mode=args.mode,
    )


if __name__ == "__main__":
    main()
