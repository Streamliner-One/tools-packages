#!/usr/bin/env python3
"""
Duffel Flight Booking Client
Reliable API client for searching, booking, and managing flights via Duffel API.

Usage:
    python duffel_client.py search --origin GVA --destination JFK --date 2026-06-24 --cabin business
    python duffel_client.py book --offer-id off_... --passenger "John Doe" --email john@example.com
    python duffel_client.py order --id ord_...

Safety:
    - Default mode is "sandbox" (fake data, safe testing)
    - Use --mode live for real bookings (requires explicit confirmation)
"""

import os
import sys
import json
import requests
import argparse
from datetime import datetime
from typing import Optional, Dict, List, Any
from pathlib import Path

# Configuration
DUFFEL_API_BASE = "https://api.duffel.com"
DUFFEL_VERSION = "v2"

# Credential IDs in Tools Server
CREDENTIAL_LIVE = "duffel"  # Duffel - PROD
CREDENTIAL_SANDBOX = "duffel-1775151120476"  # Duffel - SANDBOX

# Import tools server helper (curl-based, reliable)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tools_server import get_api_key


class DuffelError(Exception):
    """Custom exception for Duffel API errors"""
    def __init__(self, message: str, errors: Optional[List[Dict]] = None, status_code: Optional[int] = None):
        self.message = message
        self.errors = errors or []
        self.status_code = status_code
        super().__init__(self.message)


class DuffelClient:
    """Duffel API client with robust error handling and logging"""
    
    def __init__(self, api_key: Optional[str] = None, mode: str = "sandbox"):
        """
        Initialize Duffel client.
        
        Args:
            api_key: Duffel API key (duffel_test_... or duffel_live_...)
            mode: "sandbox" (default, safe) or "live" (real bookings)
        """
        self.mode = mode
        self.api_key = api_key or self._get_credentials(mode)
        self.live = self.api_key.startswith("duffel_live_")
        
        self.base_url = DUFFEL_API_BASE
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Duffel-Version": DUFFEL_VERSION,
            "Accept": "application/json",
            "Accept-Encoding": "gzip"
        })
        
        mode_display = "⚠️ LIVE" if self.live else "✓ SANDBOX"
        key_preview = f"{self.api_key[:12]}...{self.api_key[-4:]}"
        print(f"🔑 Duffel Client initialized [{mode_display}] - Key: {key_preview}", file=sys.stderr)
    
    def _get_credentials(self, mode: str = "sandbox") -> str:
        """Fetch Duffel credentials from Tools Server using curl-based helper"""
        try:
            cred_id = CREDENTIAL_SANDBOX if mode == "sandbox" else CREDENTIAL_LIVE
            api_key = get_api_key(cred_id)
            
            key_preview = f"{api_key[:12]}...{api_key[-4:]}"
            mode_display = "LIVE" if api_key.startswith("duffel_live_") else "SANDBOX"
            print(f"✓ Fetched Duffel key [{mode_display}]: {key_preview}", file=sys.stderr)
            
            return api_key
            
        except Exception as e:
            print(f"⚠️  Failed to fetch credentials: {e}", file=sys.stderr)
            env_key = os.environ.get("DUFFEL_API_KEY")
            if env_key:
                print(f"⚠️  Using DUFFEL_API_KEY from environment", file=sys.stderr)
                return env_key
            raise DuffelError(
                f"Could not fetch Duffel API key. Ensure Tools Server is running.",
                status_code=0
            )
    
    def _request(self, method: str, path: str, data: Optional[Dict] = None, raw: bool = False) -> Any:
        """Make HTTP request to Duffel API with error handling"""
        url = f"{self.base_url}{path}"
        
        try:
            if method.upper() == "GET":
                resp = self.session.get(url, params=data, timeout=60)
            else:
                resp = self.session.post(url, json=data, timeout=60)
            
            # Handle response
            if resp.status_code >= 400:
                try:
                    error_data = resp.json()
                    errors = error_data.get("errors", [])
                    error_msg = errors[0].get("message", "Unknown error") if errors else resp.text
                    raise DuffelError(
                        f"Duffel API Error ({resp.status_code}): {error_msg}",
                        errors=errors,
                        status_code=resp.status_code
                    )
                except json.JSONDecodeError:
                    raise DuffelError(
                        f"Duffel API Error ({resp.status_code}): {resp.text[:200]}",
                        status_code=resp.status_code
                    )
            
            if raw:
                return resp  # Return raw response for debugging
            return resp.json()
            
        except requests.exceptions.Timeout:
            raise DuffelError("Duffel API request timed out (60s)", status_code=0)
        except requests.exceptions.ConnectionError as e:
            raise DuffelError(f"Connection error: {e}", status_code=0)
        except DuffelError:
            raise
        except Exception as e:
            raise DuffelError(f"Unexpected error: {e}", status_code=0)
    
    # ============== FLIGHT SEARCH ==============
    
    def create_offer_request(
        self,
        slices: List[Dict],
        passengers: List[Dict],
        cabin_class: str = "economy",
        return_offers: bool = True
    ) -> Dict:
        """Create an offer request and optionally fetch offers"""
        print(f"🔍 Creating offer request...", file=sys.stderr)
        
        payload = {
            "data": {
                "slices": slices,
                "passengers": passengers,
                "cabin_class": cabin_class
            }
        }
        
        result = self._request("POST", "/air/offer_requests", payload)
        offer_request = result.get("data", {})
        offer_request_id = offer_request.get("id")
        
        print(f"✓ Offer request: {offer_request_id}", file=sys.stderr)
        
        if return_offers and offer_request_id:
            return self.get_offers(offer_request_id)
        
        return offer_request
    
    def get_offers(self, offer_request_id: str) -> Dict:
        """Fetch offers for an offer request"""
        print(f"📦 Fetching offers...", file=sys.stderr)
        
        result = self._request("GET", "/air/offers", {"offer_request_id": offer_request_id})
        offers = result.get("data", [])
        
        print(f"✓ Found {len(offers)} offers", file=sys.stderr)
        
        return {
            "offer_request_id": offer_request_id,
            "offers": offers
        }
    
    def search_flights(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        return_date: Optional[str] = None,
        cabin_class: str = "business",
        adults: int = 1
    ) -> Dict:
        """
        Search flights (one-way or round-trip).
        
        Returns:
            Dict with 'offers' list and 'passengers' list (with IDs from offer request)
        """
        slices = [{"origin": origin, "destination": destination, "departure_date": departure_date}]
        if return_date:
            slices.append({"origin": destination, "destination": origin, "departure_date": return_date})
        
        passengers = [{"type": "adult"} for _ in range(adults)]
        
        # Create offer request and get response with passenger IDs
        print(f"🔍 Creating offer request...", file=sys.stderr)
        payload = {"data": {"slices": slices, "passengers": passengers, "cabin_class": cabin_class}}
        result = self._request("POST", "/air/offer_requests", payload)
        offer_request = result.get("data", {})
        offer_request_id = offer_request.get("id")
        
        # Extract passenger IDs from offer request response
        passengers_with_ids = offer_request.get("passengers", [])
        
        # Fetch offers
        offers_result = self.get_offers(offer_request_id)
        offers = offers_result.get("offers", [])
        
        # Sort by price
        offers.sort(key=lambda x: float(x.get("total_amount", "999999")))
        
        return {
            "offers": offers,
            "passengers": passengers_with_ids,
            "offer_request_id": offer_request_id
        }
    
    # ============== BOOKING ==============
    
    def create_order(
        self,
        offer_id: str,
        passengers: List[Dict],
        payment_type: str = "balance",
        metadata: Optional[Dict] = None
    ) -> Dict:
        """
        Create an order (book a flight).
        
        Args:
            offer_id: Offer ID to book
            passengers: List of passenger dicts with 'id' from offer request + other required fields
            payment_type: "balance", "card", etc.
            metadata: Optional metadata
        """
        print(f"🎫 Creating order...", file=sys.stderr)
        
        # Validate passenger data (each must have id from offer request)
        for i, pax in enumerate(passengers):
            self._validate_passenger(pax, index=i, require_id=True)
        
        # Get offer details to get exact amount
        offer = self._get_offer(offer_id)
        total_amount = offer.get("total_amount")
        total_currency = offer.get("total_currency")
        
        payload = {
            "data": {
                "selected_offers": [offer_id],
                "passengers": passengers,
                "payments": [
                    {
                        "type": payment_type,
                        "amount": total_amount,
                        "currency": total_currency
                    }
                ]
            }
        }
        
        if metadata:
            payload["data"]["metadata"] = metadata
        
        result = self._request("POST", "/air/orders", payload)
        order = result.get("data", {})
        
        print(f"✓ Order: {order.get('id')} | PNR: {order.get('booking_reference')}", file=sys.stderr)
        
        return order
    
    def _validate_passenger(self, passenger: Dict, index: int = 0, require_id: bool = False):
        """Validate passenger data before booking"""
        required = ["type", "title", "given_name", "family_name", "gender", "born_on", "email", "phone_number"]
        
        if require_id:
            required.insert(0, "id")
        
        for field in required:
            if field not in passenger:
                raise DuffelError(f"Passenger {index + 1} missing: {field}")
        
        if passenger.get("gender") not in ["m", "f"]:
            raise DuffelError(f"Passenger {index + 1} gender must be 'm' or 'f'")
        
        valid_titles = ["mr", "ms", "mrs", "miss", "dr", "prof"]
        if passenger.get("title") not in valid_titles:
            raise DuffelError(f"Passenger {index + 1} title must be one of {valid_titles}")
        
        if "@" not in passenger.get("email", ""):
            raise DuffelError(f"Passenger {index + 1} invalid email")
        
        if not passenger.get("phone_number", "").startswith("+"):
            raise DuffelError(f"Passenger {index + 1} phone must start with +")
    
    def _get_offer(self, offer_id: str) -> Dict:
        """Get offer details by ID"""
        result = self._request("GET", f"/air/offers/{offer_id}")
        return result.get("data", {})
    
    # ============== ORDER MANAGEMENT ==============
    
    def get_order(self, order_id: str) -> Dict:
        """Get order details"""
        result = self._request("GET", f"/air/orders/{order_id}")
        return result.get("data", {})
    
    def list_orders(self, limit: int = 50, **filters) -> List[Dict]:
        """List orders with optional filters"""
        params = {"limit": limit, **filters}
        result = self._request("GET", "/air/orders", params)
        return result.get("data", [])
    
    # ============== PAYMENT INTENTS ==============
    
    def create_payment_intent(self, amount: str, currency: str) -> Dict:
        """Create payment intent for customer payment collection"""
        print(f"💳 Creating payment intent...", file=sys.stderr)
        
        payload = {"data": {"amount": amount, "currency": currency}}
        result = self._request("POST", "/payments/payment_intents", payload)
        pi = result.get("data", {})
        
        print(f"✓ Payment intent: {pi.get('id')}", file=sys.stderr)
        return pi
    
    def confirm_payment_intent(self, payment_intent_id: str) -> Dict:
        """Confirm payment intent after card collection"""
        print(f"✅ Confirming payment intent...", file=sys.stderr)
        
        result = self._request("POST", f"/payments/payment_intents/{payment_intent_id}/actions/confirm")
        pi = result.get("data", {})
        
        print(f"✓ Payment confirmed: {pi.get('status')}", file=sys.stderr)
        return pi
    
    # ============== UTILITIES ==============
    
    def format_offer(self, offer: Dict) -> str:
        """Format an offer for display"""
        total = f"{offer.get('total_amount')} {offer.get('total_currency')}"
        airline = offer.get("owner", {}).get("name", "Unknown")
        
        slices_info = []
        for i, slice in enumerate(offer.get("slices", [])):
            origin = slice.get("origin", {}).get("iata_code", "???")
            dest = slice.get("destination", {}).get("iata_code", "???")
            direction = "Outbound" if i == 0 else "Return"
            slices_info.append(f"{direction}: {origin} → {dest}")
        
        return f"✈️ {airline} | Total: {total} | {' | '.join(slices_info)} | ID: {offer.get('id')}"


# ============== CLI ==============

def main():
    parser = argparse.ArgumentParser(description="Duffel Flight Booking Client")
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # Search command
    search_parser = subparsers.add_parser("search", help="Search flights")
    search_parser.add_argument("--origin", required=True, help="Origin airport")
    search_parser.add_argument("--destination", required=True, help="Destination airport")
    search_parser.add_argument("--date", required=True, help="Departure date (YYYY-MM-DD)")
    search_parser.add_argument("--return-date", help="Return date (YYYY-MM-DD)")
    search_parser.add_argument("--cabin", default="business", help="Cabin class")
    search_parser.add_argument("--adults", type=int, default=1, help="Number of adults")
    search_parser.add_argument("--mode", default="sandbox", choices=["sandbox", "live"], help="Mode")
    
    # Book command
    book_parser = subparsers.add_parser("book", help="Book a flight")
    book_parser.add_argument("--offer-id", required=True, help="Offer ID")
    book_parser.add_argument("--passenger", required=True, action="append", help="Passenger JSON")
    book_parser.add_argument("--payment", default="balance", help="Payment type")
    book_parser.add_argument("--mode", default="sandbox", choices=["sandbox", "live"], help="Mode")
    
    # Order command
    order_parser = subparsers.add_parser("order", help="Get order details")
    order_parser.add_argument("--id", required=True, help="Order ID")
    order_parser.add_argument("--mode", default="sandbox", choices=["sandbox", "live"], help="Mode")
    
    # List command
    list_parser = subparsers.add_parser("list", help="List orders")
    list_parser.add_argument("--limit", type=int, default=10, help="Max results")
    list_parser.add_argument("--mode", default="sandbox", choices=["sandbox", "live"], help="Mode")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(0)
    
    # Initialize client
    mode = getattr(args, 'mode', 'sandbox')
    if mode == "live":
        print(f"\n⚠️  WARNING: LIVE MODE - Real bookings will be made!\n", file=sys.stderr)
    
    try:
        client = DuffelClient(mode=mode)
    except DuffelError as e:
        print(f"❌ {e.message}", file=sys.stderr)
        sys.exit(1)
    
    # Execute command
    if args.command == "search":
        offers = client.search_flights(
            origin=args.origin,
            destination=args.destination,
            departure_date=args.date,
            return_date=args.return_date,
            cabin_class=args.cabin,
            adults=args.adults
        )
        
        print(f"\n{'='*60}")
        print(f"Found {len(offers)} offers")
        print(f"{'='*60}\n")
        
        for i, offer in enumerate(offers[:5], 1):
            print(f"{i}. {client.format_offer(offer)}")
    
    elif args.command == "book":
        # Parse passenger details from CLI
        passenger_details = [json.loads(p) for p in args.passenger]
        
        try:
            # Get the offer to extract passenger IDs
            offer = client._get_offer(args.offer_id)
            offer_passengers = offer.get("passengers", [])
            
            if len(offer_passengers) != len(passenger_details):
                raise DuffelError(f"Passenger count mismatch: offer has {len(offer_passengers)}, provided {len(passenger_details)}")
            
            # Merge passenger IDs from offer with provided details
            passengers = []
            for i, pax_detail in enumerate(passenger_details):
                pax_id = offer_passengers[i].get("id")
                if not pax_id:
                    raise DuffelError(f"Passenger {i+1} has no ID in offer")
                passengers.append({"id": pax_id, **pax_detail})
            
            order = client.create_order(
                offer_id=args.offer_id,
                passengers=passengers,
                payment_type=args.payment
            )
            print(f"\n✅ BOOKING CONFIRMED")
            print(f"   Order: {order.get('id')}")
            print(f"   PNR: {order.get('booking_reference')}")
            print(f"   Total: {order.get('total_amount')} {order.get('total_currency')}")
        except DuffelError as e:
            print(f"\n❌ Booking failed: {e.message}")
            if e.errors:
                for err in e.errors:
                    print(f"   - {err.get('title')}: {err.get('message')}")
            sys.exit(1)
    
    elif args.command == "order":
        order = client.get_order(args.id)
        print(json.dumps(order, indent=2))
    
    elif args.command == "list":
        orders = client.list_orders(limit=args.limit)
        print(f"\n{'='*60}")
        print(f"Recent Orders ({len(orders)} results)")
        print(f"{'='*60}\n")
        for order in orders:
            print(f"  {order.get('id')} | PNR: {order.get('booking_reference')} | {order.get('total_amount')} {order.get('total_currency')} | {order.get('status')}")


if __name__ == "__main__":
    main()
