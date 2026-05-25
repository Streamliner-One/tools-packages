#!/usr/bin/env python3
"""
Duffel Ancillaries Module
Seat maps (pre-booking) and services (post-booking): baggage, meals, cancel protection.
"""

import sys
from typing import Dict, List, Optional

CURRENCY_SYMBOLS = {"EUR": "€", "GBP": "£", "USD": "$", "CHF": "CHF"}


def _sym(currency: str) -> str:
    return CURRENCY_SYMBOLS.get(currency, currency)


class AncillaryManager:
    def __init__(self, client):
        """Initialize with a DuffelClient instance."""
        self.client = client

    def get_seat_map(self, offer_id: str) -> List[Dict]:
        """Get seat map for an offer. Returns per-segment seat maps."""
        result = self.client._request("GET", "/air/seat_maps", {"offer_id": offer_id})
        return result.get("data", [])

    def format_seat_map(self, seat_map_data: List[Dict], max_rows: int = 10) -> str:
        """Format seat map as ASCII art for Telegram/CLI display."""
        if not seat_map_data:
            return "No seat map available for this flight."

        lines = []
        total_available = 0
        min_price = None

        for sm in seat_map_data:
            # Segment header
            segment = sm.get("segment", {}) or {}
            origin = segment.get("origin", {}).get("iata_code", "?") if isinstance(segment.get("origin"), dict) else segment.get("origin", "?")
            dest = segment.get("destination", {}).get("iata_code", "?") if isinstance(segment.get("destination"), dict) else segment.get("destination", "?")
            carrier = segment.get("marketing_carrier", {}).get("name", "") if isinstance(segment.get("marketing_carrier"), dict) else ""
            flight_no = segment.get("marketing_carrier_flight_number", "")
            carrier_code = segment.get("marketing_carrier", {}).get("iata_code", "") if isinstance(segment.get("marketing_carrier"), dict) else ""

            header = f"✈️  SEGMENT: {origin} → {dest}"
            if carrier:
                header += f" ({carrier}, {carrier_code}{flight_no})"
            lines.append(header)
            lines.append("")

            cabins = sm.get("cabins", [])
            for cabin in cabins:
                cabin_class = (cabin.get("cabin_class") or "economy").upper()
                lines.append(f"{cabin_class} CLASS")

                rows = cabin.get("rows", [])
                if not rows:
                    lines.append("  No row data available.")
                    lines.append("")
                    continue

                # Determine column layout from first row with seats
                col_ids = []
                for row in rows:
                    for section in row.get("sections", []):
                        for el in section.get("elements", []):
                            if el.get("type") == "seat":
                                d = el.get("designator", "")
                                col_letter = d[-1] if d else ""
                                if col_letter and col_letter not in col_ids:
                                    col_ids.append(col_letter)
                    if col_ids:
                        break

                # Header row
                col_header = "Row  " + "  ".join(f"  {c}   " for c in col_ids)
                lines.append(col_header)

                shown = 0
                for row in rows:
                    if shown >= max_rows:
                        remaining = len(rows) - shown
                        lines.append(f"  ... {remaining} more rows")
                        break

                    # Build seat map for this row
                    row_seats = {}  # col_letter -> display string
                    row_num = ""
                    is_exit = False

                    for section in row.get("sections", []):
                        for el in section.get("elements", []):
                            if el.get("type") == "exit_row":
                                is_exit = True
                            if el.get("type") != "seat":
                                continue
                            designator = el.get("designator", "")
                            if not designator:
                                continue
                            row_num = designator[:-1]
                            col_letter = designator[-1]
                            services = el.get("available_services", [])

                            if services:
                                # Seat available — show cheapest price
                                prices = []
                                for svc in services:
                                    try:
                                        prices.append(float(svc.get("total_amount", "0")))
                                    except (ValueError, TypeError):
                                        pass
                                if prices:
                                    cheapest = min(prices)
                                    currency = services[0].get("total_currency", "EUR")
                                    sym = _sym(currency)
                                    row_seats[col_letter] = f"{sym}{cheapest:.0f}"
                                    total_available += 1
                                    if min_price is None or cheapest < min_price:
                                        min_price = cheapest
                                else:
                                    row_seats[col_letter] = "free"
                                    total_available += 1
                            else:
                                row_seats[col_letter] = "---"

                    if not row_num:
                        continue

                    # Format row
                    cells = []
                    for c in col_ids:
                        val = row_seats.get(c, "   ")
                        cells.append(f"[{val:^5s}]")

                    suffix = "  ← exit row" if is_exit else ""
                    lines.append(f"{row_num:>3s}  {'  '.join(cells)}{suffix}")
                    shown += 1

                lines.append("")

        # Summary
        lines.append("Legend: [$XX] = available at price | [---] = taken | [   ] = not a seat")
        if total_available > 0 and min_price is not None:
            lines.append(f"\n{total_available} seats available from {_sym('EUR')}{min_price:.0f}")
        elif total_available == 0:
            lines.append("\nNo bookable seats found in this map.")

        return "\n".join(lines)

    def get_available_services(self, order_id: str) -> Dict:
        """
        Get available ancillary services for a booked order.
        Returns dict grouped by type: {baggage: [...], meal: [...], ...}
        """
        result = self.client._request("GET", "/air/services", {"order_id": order_id})
        raw_services = result.get("data", [])

        grouped: Dict[str, list] = {}
        for svc in raw_services:
            svc_type = svc.get("type", "other")
            grouped.setdefault(svc_type, []).append(svc)

        return grouped

    def format_services(self, services: Dict) -> str:
        """Format services for client presentation."""
        if not services:
            return "No additional services available for this order."

        type_icons = {
            "baggage": "🧳 EXTRA BAGGAGE",
            "meal": "🍽️ MEALS",
            "cancel_for_any_reason": "🛡️ CANCEL FOR ANY REASON",
            "seat": "💺 SEAT SELECTION",
        }

        lines = []
        for svc_type, items in services.items():
            header = type_icons.get(svc_type, f"📦 {svc_type.upper()}")
            lines.append(header)

            for item in items:
                amount = item.get("total_amount", "?")
                currency = item.get("total_currency", "EUR")
                sym = _sym(currency)

                # Build description from metadata
                metadata = item.get("metadata", {}) or {}
                desc_parts = []

                if svc_type == "baggage":
                    weight = metadata.get("maximum_weight_kg")
                    if weight:
                        desc_parts.append(f"{weight}kg bag")
                    else:
                        desc_parts.append("Extra bag")
                elif svc_type == "meal":
                    meal_type = metadata.get("meal_type") or metadata.get("name") or "Meal"
                    desc_parts.append(meal_type)
                elif svc_type == "cancel_for_any_reason":
                    desc_parts.append("Full protection")
                else:
                    desc_parts.append(item.get("type", "Service"))

                # Segment info if available
                segment = item.get("segment_id", "")
                if segment:
                    desc_parts.append(f"(seg: {segment[:8]}…)")

                desc = " — ".join(filter(None, desc_parts)) if desc_parts else "Service"
                svc_id = item.get("id", "?")
                lines.append(f"  • {desc} — {sym}{amount}  [id: {svc_id}]")

            lines.append("")

        return "\n".join(lines)

    def add_services_to_order(self, order_id: str, service_ids: List[str],
                               payment_type: str = "balance", currency: str = "EUR") -> Dict:
        """
        Add selected services to a confirmed order.
        Fetches service prices first to calculate total payment amount.
        """
        # Get all available services to find prices
        all_services = self.client._request("GET", "/air/services", {"order_id": order_id})
        raw_services = all_services.get("data", [])

        # Build price lookup
        price_map = {}
        for svc in raw_services:
            price_map[svc["id"]] = {
                "amount": float(svc.get("total_amount", "0")),
                "currency": svc.get("total_currency", currency),
            }

        # Calculate total
        total = 0.0
        svc_currency = currency
        add_items = []
        for sid in service_ids:
            if sid in price_map:
                total += price_map[sid]["amount"]
                svc_currency = price_map[sid]["currency"]
            add_items.append({"id": sid, "quantity": 1})

        if not add_items:
            raise ValueError("No valid service IDs provided.")

        payload = {
            "data": {
                "add": add_items,
                "payment": {
                    "type": payment_type,
                    "currency": svc_currency,
                    "amount": f"{total:.2f}",
                },
            }
        }

        result = self.client._request("POST", f"/air/orders/{order_id}/services", payload)
        return result.get("data", {})
