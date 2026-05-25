#!/usr/bin/env python3
"""
Duffel Order Manager
Cancellations, changes, and order lifecycle management.
"""

from datetime import datetime
from typing import Dict, Optional

CURRENCY_SYMBOLS = {"EUR": "€", "GBP": "£", "USD": "$", "CHF": "CHF"}


def _sym(currency: str) -> str:
    return CURRENCY_SYMBOLS.get(currency, currency)


class OrderManager:
    def __init__(self, client):
        """Initialize with a DuffelClient instance."""
        self.client = client

    def get_cancellation_quote(self, order_id: str) -> Dict:
        """
        Create a pending cancellation to get a refund quote.
        Does NOT confirm — just returns the quote with expiry.
        """
        payload = {"data": {"order_id": order_id}}
        result = self.client._request("POST", "/air/order_cancellations", payload)
        return result.get("data", {})

    def format_cancellation_quote(self, cancellation: Dict) -> str:
        """Format cancellation quote for client presentation."""
        refund_amount = cancellation.get("refund_amount", "0.00")
        refund_currency = cancellation.get("refund_currency", "EUR")
        refund_to = cancellation.get("refund_to", "unknown")
        expires_at = cancellation.get("expires_at", "")
        cancellation_id = cancellation.get("id", "?")

        sym = _sym(refund_currency)

        # Format expiry
        expiry_display = expires_at
        if expires_at:
            try:
                dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
                expiry_display = dt.strftime("%d %b %Y at %H:%M")
            except (ValueError, AttributeError):
                pass

        refund_to_display = {
            "balance": "Duffel balance",
            "original_form_of_payment": "Original payment method",
            "voucher": "Airline voucher",
            "awaiting_airline": "Pending airline confirmation",
        }.get(refund_to, refund_to)

        lines = [
            "🔴 CANCELLATION QUOTE",
            f"Refund amount: {sym}{refund_amount}",
            f"Refund to: {refund_to_display}",
            f"Quote expires: {expiry_display}",
            "",
            f"To confirm cancellation, use: cancel --order-id <order_id> --confirm {cancellation_id}",
        ]
        return "\n".join(lines)

    def confirm_cancellation(self, cancellation_id: str) -> Dict:
        """Actually confirm and execute the cancellation."""
        result = self.client._request(
            "POST", f"/air/order_cancellations/{cancellation_id}/actions/confirm"
        )
        return result.get("data", {})

    def get_order_change_request(self, order_id: str) -> Dict:
        """
        Check if order supports changes by inspecting order conditions.
        Returns summary of what can be changed.
        """
        order = self.client.get_order(order_id)
        slices = order.get("slices", [])
        conditions = order.get("conditions") or {}

        change_info = {
            "order_id": order_id,
            "status": order.get("status", "unknown"),
            "conditions": conditions,
            "slices": [],
        }

        for i, sl in enumerate(slices):
            origin = sl.get("origin", {}).get("iata_code", "?")
            dest = sl.get("destination", {}).get("iata_code", "?")
            sl_conditions = sl.get("conditions", {})
            changeable = sl_conditions.get("change_before_departure")

            change_info["slices"].append({
                "index": i,
                "route": f"{origin} → {dest}",
                "change_specified": changeable is not None,
                "changeable": bool((changeable or {}).get("allowed", False)),
                "change_conditions": changeable or {},
            })

        return change_info

    def format_change_info(self, change_info: Dict) -> str:
        """Format change info for client presentation."""
        lines = [
            f"📋 ORDER CHANGE INFO — {change_info['order_id']}",
            f"Status: {change_info['status']}",
            "",
        ]

        conditions = change_info.get("conditions", {})
        if conditions:
            refund = conditions.get("refund_before_departure")
            if refund is None:
                lines.append("Refund: Needs airline confirmation")
            else:
                allowed = refund.get("allowed", False)
                penalty = refund.get("penalty_amount")
                penalty_cur = refund.get("penalty_currency", "EUR")
                if allowed:
                    if penalty and float(penalty) > 0:
                        lines.append(f"Refund: Allowed (penalty: {_sym(penalty_cur)}{penalty})")
                    else:
                        lines.append("Refund: Allowed (no penalty)")
                else:
                    lines.append("Refund: Not allowed")

        for sl in change_info.get("slices", []):
            if not sl.get("change_specified", True):
                status = "Needs airline confirmation"
            else:
                status = "✅ Changeable" if sl["changeable"] else "❌ Not changeable"
            lines.append(f"  Slice {sl['index'] + 1}: {sl['route']} — {status}")
            if sl["changeable"] and sl["change_conditions"]:
                penalty = sl["change_conditions"].get("penalty_amount")
                if penalty:
                    cur = sl["change_conditions"].get("penalty_currency", "EUR")
                    lines.append(f"    Change fee: {_sym(cur)}{penalty}")

        return "\n".join(lines)
