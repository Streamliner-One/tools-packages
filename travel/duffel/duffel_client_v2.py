#!/usr/bin/env python3
"""
Duffel Flight Booking Client v2
With route intelligence, smart sorting by total travel time, and caching.

Usage:
    python duffel_client_v2.py search --origin VLC --destination ROM --date 2026-04-09 --mode live
"""

import os
import sys
import json
import requests
import argparse
from datetime import datetime, timedelta

DUFFEL_CACHE_TTL_SECONDS = 20 * 60
from typing import Optional, Dict, List, Any
from pathlib import Path

# Configuration
DUFFEL_API_BASE = "https://api.duffel.com"
DUFFEL_VERSION = "v2"
CREDENTIAL_LIVE = "duffel"
CREDENTIAL_SANDBOX = "duffel-1775151120476"

# Duffel fees (update here if they change)
DUFFEL_FEE_PERCENT = 0.01  # 1% of fare
DUFFEL_FEE_FIXED = 3.0     # $3 per order

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tools_server import get_api_key
from route_cache import RouteCache
from airline_cache import AirlineCache

# Initialize route cache
route_cache = RouteCache()


class DuffelError(Exception):
    def __init__(self, message: str, errors: Optional[List[Dict]] = None, status_code: Optional[int] = None):
        self.message = message
        self.errors = errors or []
        self.status_code = status_code
        super().__init__(self.message)


class DuffelClient:
    def __init__(self, api_key: Optional[str] = None, mode: str = "sandbox"):
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
        print(f"🔑 Duffel Client [{mode_display}] - Key: {key_preview}", file=sys.stderr)
    
    def _get_credentials(self, mode: str = "sandbox") -> str:
        try:
            cred_id = CREDENTIAL_SANDBOX if mode == "sandbox" else CREDENTIAL_LIVE
            api_key = get_api_key(cred_id)
            key_preview = f"{api_key[:12]}...{api_key[-4:]}"
            mode_display = "LIVE" if api_key.startswith("duffel_live_") else "SANDBOX"
            print(f"✓ Fetched Duffel key [{mode_display}]: {key_preview}", file=sys.stderr)
            return api_key
        except Exception as e:
            env_key = os.environ.get("DUFFEL_API_KEY")
            if env_key:
                return env_key
            raise DuffelError(f"Could not fetch Duffel API key.", status_code=0)
    
    def calculate_final_price(
        self,
        base_price: float,
        markup_percent: float = 0.0,
        booking_fee: float = 0.0,
        currency: str = "USD",
    ) -> float:
        """Calculate final client price including Duffel fees + optional markup or booking fee.

        Two billing modes:
          - Percentage markup (expensive fares, e.g. business class):
              markup_percent = 3.0 to 5.0 → adds % of base on top of Duffel fees
          - Flat booking fee (cheap fares, e.g. budget airlines):
              booking_fee = 50.0 → adds fixed €/CHF/USD amount regardless of fare
          Both can be combined, though typically one or the other is used.

        Formula:
          your_cost    = base + (base × DUFFEL_FEE_PERCENT) + DUFFEL_FEE_FIXED
          client_price = your_cost + (base × markup%) + booking_fee
        """
        duffel_fee = (base_price * DUFFEL_FEE_PERCENT) + DUFFEL_FEE_FIXED
        your_cost = base_price + duffel_fee
        markup_amount = base_price * (markup_percent / 100.0)
        return your_cost + markup_amount + booking_fee

    def calculate_service_fee(self, base_price: float, floor: float = 100.0) -> float:
        """Calculate the non-refundable service fee shown to clients.

        = Duffel exposure (1% + $3) + your floor, rounded UP to next $25.
        This is what the client keeps paying if they cancel a refundable fare.

        Args:
            base_price: fare total_amount from Duffel API
            floor: minimum service fee before rounding (default $100)
        """
        duffel_exposure = (base_price * DUFFEL_FEE_PERCENT) + DUFFEL_FEE_FIXED
        raw = duffel_exposure + floor
        # Round up to next $25
        import math
        return math.ceil(raw / 25) * 25
    
    def _request(self, method: str, path: str, data: Optional[Dict] = None) -> Any:
        url = f"{self.base_url}{path}"
        try:
            if method.upper() == "GET":
                resp = self.session.get(url, params=data, timeout=60)
            else:
                resp = self.session.post(url, json=data, timeout=60)
            
            if resp.status_code >= 400:
                try:
                    error_data = resp.json()
                    errors = error_data.get("errors", [])
                    error_msg = errors[0].get("message", "Unknown error") if errors else resp.text
                    raise DuffelError(f"Duffel API Error ({resp.status_code}): {error_msg}", errors=errors, status_code=resp.status_code)
                except json.JSONDecodeError:
                    raise DuffelError(f"Duffel API Error ({resp.status_code}): {resp.text[:200]}", status_code=resp.status_code)
            
            return resp.json()
        except requests.exceptions.Timeout:
            raise DuffelError("Duffel API request timed out (60s)", status_code=0)
        except DuffelError:
            raise
        except Exception as e:
            raise DuffelError(f"Unexpected error: {e}", status_code=0)
    
    def _calc_total_duration_minutes(self, slices: List[Dict]) -> int:
        """
        Calculate total travel time in minutes.
        For round trips: sum of outbound + return durations (excludes days at destination)
        For one-way: first departure to last arrival
        """
        if not slices or not slices[0].get("segments"):
            return 99999
        
        total_minutes = 0
        
        for slice in slices:
            slice_min = self._slice_duration_minutes(slice)
            if slice_min > 0:
                total_minutes += slice_min
        
        return total_minutes if total_minutes > 0 else 99999
    
    def _calc_max_layover_minutes(self, slices: List[Dict]) -> int:
        """Calculate maximum layover time across all slices"""
        max_layover = 0
        for slice in slices:
            segments = slice.get("segments", [])
            for i in range(len(segments) - 1):
                arr = segments[i]["arriving_at"]
                next_dep = segments[i+1]["departing_at"]
                try:
                    arr_dt = datetime.fromisoformat(arr)
                    next_dt = datetime.fromisoformat(next_dep)
                    layover = int((next_dt - arr_dt).total_seconds() / 60)
                    max_layover = max(max_layover, layover)
                except:
                    pass
        return max_layover
    
    def _count_stops(self, slices: List[Dict]) -> int:
        """Count total stops (segments - 1 per slice, summed)"""
        total = 0
        for slice in slices:
            segments = slice.get("segments", [])
            total += max(0, len(segments) - 1)
        return total
    
    def search_flights(self, origin: str, destination: str, departure_date: str,
                       return_date: Optional[str] = None, cabin_class: str = "economy",
                       adults: int = 1, sort_by: str = "duration") -> Dict:
        """
        Search flights with smart sorting.
        
        Args:
            sort_by: "duration" (default, best first) or "price"
        """
        slices = [{"origin": origin, "destination": destination, "departure_date": departure_date}]
        if return_date:
            slices.append({"origin": destination, "destination": origin, "departure_date": return_date})
        
        passengers = [{"type": "adult"} for _ in range(adults)]
        
        # Create offer request
        print(f"🔍 Searching {origin} → {destination}...", file=sys.stderr)
        payload = {"data": {"slices": slices, "passengers": passengers, "cabin_class": cabin_class}}
        # Use return_offers=true to get ALL offers inline (avoids 50-offer GET pagination cap)
        result = self._request("POST", "/air/offer_requests?return_offers=true", payload)
        offer_request = result.get("data", {})
        offer_request_id = offer_request.get("id")
        
        # Offers are inline from return_offers=true (1000+ vs 50 cap on GET /air/offers)
        offers = offer_request.get("offers", [])
        
        # Cache Duffel search results FIRST, then get advisory based on fresh cache
        route_cache.cache_from_search(origin, destination, offers)
        advisory = route_cache.get_advisory(origin, destination)
        
        # Show advisory AFTER search if there's a conflict
        if advisory["show_advisory"]:
            print(f"\n⚠️  ADVISORY: {advisory['message']}", file=sys.stderr)
            # Show the actual airlines Duffel returned, not just the first offer
            duffel_airlines = sorted(set(
                o.get("owner", {}).get("name", "")
                for o in offers if o.get("owner", {}).get("name")
            ))
            airlines_str = ", ".join(duffel_airlines[:3]) + ("…" if len(duffel_airlines) > 3 else "")
            print(f"   Duffel returned: {airlines_str or 'Unknown'}\n", file=sys.stderr)
        
        # Enrich offers with calculated fields
        for offer in offers:
            slices_data = offer.get("slices", [])
            offer["_total_duration_min"] = self._calc_total_duration_minutes(slices_data)
            offer["_max_layover_min"] = self._calc_max_layover_minutes(slices_data)
            offer["_total_stops"] = self._count_stops(slices_data)
        
        # Sort by total duration (Skyscanner style)
        if sort_by == "duration":
            offers.sort(key=lambda x: (x["_total_stops"], x["_total_duration_min"], float(x.get("total_amount", 999999))))
        else:
            offers.sort(key=lambda x: float(x.get("total_amount", 999999)))
        
        # Get passenger IDs from offer request
        passengers_with_ids = offer_request.get("passengers", [])
        
        # Check if Duffel showed directs
        duffel_has_direct = any(
            len(o.get("slices", [{}])[0].get("segments", [])) == 1
            for o in offers if o.get("slices")
        )
        
        return {
            "offers": offers,
            "passengers": passengers_with_ids,
            "offer_request_id": offer_request_id,
            "route_intelligence": {
                "advisory": advisory,
                "duffel_shows_direct": duffel_has_direct
            }
        }
    
    def _parse_iso_duration(self, duration: str) -> int:
        """Parse ISO 8601 duration (e.g. PT8H50M, PT2H10M, PT45M) to minutes."""
        import re
        if not duration:
            return 0
        m = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?', duration)
        if not m:
            return 0
        hours = int(m.group(1) or 0)
        minutes = int(m.group(2) or 0)
        return hours * 60 + minutes

    def _slice_duration_minutes(self, slice: Dict) -> int:
        """Duration for a single slice — use Duffel's provided duration field (timezone-correct)."""
        duration = slice.get("duration")
        if duration:
            return self._parse_iso_duration(duration)
        # Fallback: sum segment durations
        total = 0
        for seg in slice.get("segments", []):
            total += self._parse_iso_duration(seg.get("duration", ""))
        return total if total > 0 else 0
    
    def _format_time(self, iso_string: str) -> str:
        """Format ISO timestamp as HH:MM"""
        try:
            dt = datetime.fromisoformat(iso_string)
            return dt.strftime("%H:%M")
        except:
            return "??:??"
    
    def _format_date(self, iso_string: str, weekday: bool = False) -> str:
        """Format ISO timestamp as DD MMM, optionally with weekday prefix (Mon 15 Apr)"""
        try:
            dt = datetime.fromisoformat(iso_string)
            if weekday:
                return dt.strftime("%a %d %b")
            return dt.strftime("%d %b")
        except:
            return "?? ???"
    
    def _leg_info(self, sl: Dict):
        """Extract common leg data from a slice for formatting."""
        segments = sl.get("segments", [])
        if not segments:
            return None
        first_seg, last_seg = segments[0], segments[-1]
        dep_time = self._format_time(first_seg.get("departing_at", ""))
        arr_time = self._format_time(last_seg.get("arriving_at", ""))
        dep_date = self._format_date(first_seg.get("departing_at", ""), weekday=True)
        origin_code = sl.get("origin", {}).get("iata_code", "???")
        origin_name = sl.get("origin", {}).get("name", "")
        dest_code = sl.get("destination", {}).get("iata_code", "???")
        dest_name = sl.get("destination", {}).get("name", "")
        duration_min = self._slice_duration_minutes(sl)
        dur_h, dur_m = duration_min // 60, duration_min % 60
        stops = len(segments) - 1
        stops_text = "nonstop" if stops == 0 else f"{stops} stop" if stops == 1 else f"{stops} stops"
        # Flight numbers: one per segment, e.g. ["W6 1234", "VY 8052"]
        flight_numbers = []
        for seg in segments:
            carrier = seg.get("operating_carrier", seg.get("marketing_carrier", {}))
            iata = carrier.get("iata_code", "")
            num = seg.get("operating_carrier_flight_number") or seg.get("marketing_carrier_flight_number", "")
            if iata and num:
                flight_numbers.append(f"{iata}{num}")
        layovers = []
        for j in range(len(segments) - 1):
            via_code = segments[j].get("destination", {}).get("iata_code", "?")
            try:
                arr_dt = datetime.fromisoformat(segments[j]["arriving_at"])
                dep_dt = datetime.fromisoformat(segments[j+1]["departing_at"])
                lay_min = int((dep_dt - arr_dt).total_seconds() / 60)
                layovers.append(f"{via_code} {lay_min//60}h{lay_min%60:02d}m layover")
            except:
                layovers.append(via_code)
        return {
            "dep_time": dep_time, "arr_time": arr_time, "dep_date": dep_date,
            "origin_code": origin_code, "origin_name": origin_name,
            "dest_code": dest_code, "dest_name": dest_name,
            "dur_h": dur_h, "dur_m": dur_m, "stops_text": stops_text,
            "flight_numbers": flight_numbers,
            "layovers": layovers,
        }

    # ── Fare Conditions Helpers ──────────────────────────────────────────────

    def _offer_conditions(self, offer: Dict) -> Dict:
        """Extract structured fare conditions from an offer."""
        conds = offer.get("conditions") or {}
        chg_raw = conds.get("change_before_departure")
        ref_raw = conds.get("refund_before_departure")
        chg = chg_raw or {}
        ref = ref_raw or {}
        # Baggage from first slice, first segment, first passenger
        bags_checked = 0
        bags_carry = 0
        for sl in offer.get("slices", []):
            for seg in sl.get("segments", []):
                for pax in seg.get("passengers", []):
                    for bag in pax.get("baggages", []):
                        qty = bag.get("quantity", 0)
                        if bag.get("type") == "checked":
                            bags_checked = max(bags_checked, qty)
                        elif bag.get("type") == "carry_on":
                            bags_carry = max(bags_carry, qty)
                    break  # only first pax per segment
                break  # only first segment per slice
            break  # only first slice
        return {
            "change_specified": chg_raw is not None,
            "changeable": chg.get("allowed", False),
            "change_penalty": chg.get("penalty_amount"),
            "change_currency": chg.get("penalty_currency"),
            "refund_specified": ref_raw is not None,
            "refundable": ref.get("allowed", False),
            "refund_penalty": ref.get("penalty_amount"),
            "bags_checked": bags_checked,
            "bags_carry": bags_carry,
        }

    def _fare_conditions_summary(self, conds: Dict) -> str:
        """One-line human-readable conditions summary."""
        parts = []
        # Bags
        if conds["bags_checked"] > 0:
            parts.append(f"🧳 {conds['bags_checked']}×23kg")
        else:
            parts.append("🧳 No bags")
        # Changes
        if not conds.get("change_specified", True):
            parts.append("🔄 Changes: airline confirmation")
        elif conds["changeable"]:
            if conds["change_penalty"] and float(conds["change_penalty"]) > 0:
                cur = conds.get("change_currency", "")
                parts.append(f"🔄 Change: {cur} {float(conds['change_penalty']):.0f} fee")
            else:
                parts.append("🔄 Free changes")
        else:
            parts.append("❌ No changes")
        # Refund
        if not conds.get("refund_specified", True):
            parts.append("💸 Refund: airline confirmation")
        elif conds["refundable"]:
            if conds.get("refund_penalty") and float(conds["refund_penalty"]) > 0:
                cur = conds.get("change_currency", "")
                parts.append(f"💸 Refund: {cur} {float(conds['refund_penalty']):.0f} fee")
            else:
                parts.append("💸 Refundable")
        else:
            parts.append("❌ Non-refundable")
        return "  ".join(parts)

    def _matches_profile(self, conds: Dict, profile: str) -> bool:
        """Check if offer conditions match the requested profile."""
        if profile == "light":
            return True  # everything passes
        if profile == "standard":
            return conds["bags_checked"] >= 1
        if profile == "flex":
            return conds["bags_checked"] >= 1 and conds["changeable"]
        if profile == "full-flex":
            return conds["bags_checked"] >= 1 and conds["changeable"] and conds["refundable"]
        return True

    def _itinerary_key(self, offer: Dict) -> str:
        """Build a unique key for a flight itinerary (ignoring fare/price)."""
        parts = []
        for sl in offer.get("slices", []):
            for seg in sl.get("segments", []):
                carrier = seg.get("operating_carrier", seg.get("marketing_carrier", {}))
                iata = carrier.get("iata_code", "")
                num = seg.get("operating_carrier_flight_number") or seg.get("marketing_carrier_flight_number", "")
                dep = (seg.get("departing_at") or "")[:16]
                parts.append(f"{iata}{num}@{dep}")
        return "|".join(parts)

    def group_offers_by_itinerary(self, offers: List[Dict], profile: str = "light") -> List[Dict]:
        """
        Group offers by unique flight combination.
        Returns list of groups, each with:
          - 'cheapest': cheapest offer matching profile
          - 'all': all offers for this itinerary sorted by price
          - 'key': itinerary key
          - 'profile_match': True if any fare in group matches profile
        """
        from collections import defaultdict
        groups: Dict[str, List] = defaultdict(list)
        for offer in offers:
            key = self._itinerary_key(offer)
            groups[key].append(offer)

        result = []
        for key, group in groups.items():
            group_sorted = sorted(group, key=lambda x: float(x.get("total_amount", 999999)))
            # Find cheapest that matches profile
            matching = [o for o in group_sorted if self._matches_profile(self._offer_conditions(o), profile)]
            if not matching:
                continue  # skip entire itinerary if no fare matches profile
            result.append({
                "key": key,
                "cheapest": matching[0],
                "all": group_sorted,
                "profile_match": True,
                "variant_count": len(group_sorted),
                "matching_count": len(matching),
            })

        # Sort groups by cheapest matching fare price
        result.sort(key=lambda g: float(g["cheapest"].get("total_amount", 999999)))
        return result

    def format_grouped_search(
        self, offers: List[Dict], profile: str = "light",
        markup: float = 0.0, booking_fee: float = 0.0,
        service_floor: float = 100.0, show_service_fee: bool = True,
        limit: int = 10,
    ) -> str:
        """
        Phase 1 output: one block per unique itinerary, cheapest fare matching profile,
        with conditions summary and variant count.
        """
        groups = self.group_offers_by_itinerary(offers, profile)
        if not groups:
            return f"  No offers found matching profile '{profile}'."

        lines = []
        for i, group in enumerate(groups[:limit], 1):
            offer = group["cheapest"]
            conds = self._offer_conditions(offer)
            base = float(offer.get("total_amount", 0))
            client_price = self.calculate_final_price(base, markup * 100, booking_fee)
            currency = offer.get("total_currency", "USD")
            airline = offer.get("owner", {}).get("name", "Unknown")

            # Fare brand from first slice
            fare_brand = offer.get("slices", [{}])[0].get("fare_brand_name", "")
            cabin_raw = ""
            segs = (offer.get("slices") or [{}])[0].get("segments") or [{}]
            pax_list = segs[0].get("passengers", []) if segs else []
            if pax_list:
                cabin_raw = pax_list[0].get("cabin_class_marketing_name", "") or pax_list[0].get("cabin_class", "")
            cabin_str = cabin_raw.title() if cabin_raw else ""
            if cabin_str and fare_brand and cabin_str.lower() in fare_brand.lower():
                tier_str = fare_brand
            elif cabin_str and fare_brand:
                tier_str = f"{cabin_str} · {fare_brand}"
            else:
                tier_str = cabin_str or fare_brand or ""

            lines.append("─" * 32)
            lines.append(f"Option {i}  {airline}  {currency} {client_price:.0f}")
            if tier_str:
                lines.append(f"[{tier_str}]")
            lines.append("─" * 32)

            for j, sl in enumerate(offer.get("slices", [])):
                segments = sl.get("segments", [])
                if not segments:
                    continue
                direction = "OUT" if j == 0 else "RET"
                dep_date = self._format_date(segments[0].get("departing_at", ""), weekday=True)
                lines.append(f"{direction} {dep_date}")
                for k, seg in enumerate(segments):
                    carrier = seg.get("operating_carrier", seg.get("marketing_carrier", {}))
                    iata = carrier.get("iata_code", "")
                    num = seg.get("operating_carrier_flight_number") or seg.get("marketing_carrier_flight_number", "")
                    fn = f"{iata}{num}" if iata and num else "??"
                    orig = seg.get("origin", {}).get("iata_code", "?")
                    dest = seg.get("destination", {}).get("iata_code", "?")
                    dep_t = self._format_time(seg.get("departing_at", ""))
                    arr_t = self._format_time(seg.get("arriving_at", ""))
                    overnight = ""
                    dep_d = seg.get("departing_at", "")[:10]
                    arr_d = seg.get("arriving_at", "")[:10]
                    if arr_d and dep_d and arr_d > dep_d:
                        overnight = " (+1)"
                    try:
                        seg_min = int((datetime.fromisoformat(seg["arriving_at"]) - datetime.fromisoformat(seg["departing_at"])).total_seconds() / 60)
                        seg_dur = f"{seg_min//60}h{seg_min%60:02d}m"
                    except:
                        seg_dur = ""
                    lines.append(f"{fn}  {orig} {dep_t} → {dest} {arr_t}{overnight}  {seg_dur}")
                    if k < len(segments) - 1:
                        try:
                            lay_min = int((datetime.fromisoformat(segments[k+1]["departing_at"]) - datetime.fromisoformat(seg["arriving_at"])).total_seconds() / 60)
                            lay_str = f"{lay_min//60}h{lay_min%60:02d}m"
                        except:
                            lay_str = "?"
                        lines.append(f"  ┄ {dest} layover {lay_str}")
                total_min = self._slice_duration_minutes(sl)
                lines.append(f"Total: {total_min//60}h{total_min%60:02d}m")
                lines.append("")

        if len(groups) > limit:
            lines.append(f"... and {len(groups) - limit} more itineraries")
        return "\n".join(lines)

    def format_expand(
        self, offers: List[Dict], group_index: int,
        markup: float = 0.0, booking_fee: float = 0.0,
        service_floor: float = 100.0, show_service_fee: bool = True,
        profile: str = "light",
    ) -> str:
        """
        Phase 2: fare expansion table for itinerary N (1-based index from grouped search).
        Shows all fare variants side by side with conditions.
        """
        groups = self.group_offers_by_itinerary(offers, "light")  # always all fares for expansion
        if group_index < 1 or group_index > len(groups):
            return f"  ❌ No itinerary #{group_index}. Run search first to see available options."

        group = groups[group_index - 1]
        all_fares = group["all"]

        best = all_fares[0]
        airline = best.get("owner", {}).get("name", "Unknown")
        currency = best.get("total_currency", "USD")
        lines = ["─" * 32, f"Option {group_index} fares  {airline}", "─" * 32, ""]

        for j, sl in enumerate(best.get("slices", [])):
            segments = sl.get("segments", [])
            if not segments:
                continue
            direction = "OUT" if j == 0 else "RET"
            dep_date = self._format_date(segments[0].get("departing_at", ""), weekday=True)
            lines.append(f"{direction} {dep_date}")
            for k, seg in enumerate(segments):
                carrier = seg.get("operating_carrier", seg.get("marketing_carrier", {}))
                iata = carrier.get("iata_code", "")
                num = seg.get("operating_carrier_flight_number") or seg.get("marketing_carrier_flight_number", "")
                fn = f"{iata}{num}" if iata and num else "??"
                orig_obj = seg.get("origin", {})
                dest_obj = seg.get("destination", {})
                orig = orig_obj.get("iata_code", "?")
                dest = dest_obj.get("iata_code", "?")
                orig_name = (orig_obj.get("name") or "").split(",")[0].strip()
                dest_name = (dest_obj.get("name") or "").split(",")[0].strip()
                dep_t = self._format_time(seg.get("departing_at", ""))
                arr_t = self._format_time(seg.get("arriving_at", ""))
                try:
                    seg_min = int((datetime.fromisoformat(seg["arriving_at"]) - datetime.fromisoformat(seg["departing_at"])).total_seconds() / 60)
                    seg_dur = f"{seg_min//60}h{seg_min%60:02d}m"
                except:
                    seg_dur = ""
                lines.append(f"✈ {fn} {orig} {dep_t} → {dest} {arr_t} {seg_dur}")
                if orig_name or dest_name:
                    lines.append(f"{orig_name} → {dest_name}")
                if k < len(segments) - 1:
                    try:
                        lay_min = int((datetime.fromisoformat(segments[k+1]["departing_at"]) - datetime.fromisoformat(seg["arriving_at"])).total_seconds() / 60)
                        lay_str = f"{lay_min//60}h{lay_min%60:02d}m"
                    except:
                        lay_str = "?"
                    lines.append(f"┄ {dest} layover {lay_str}")
            total_min = self._slice_duration_minutes(sl)
            lines.append(f"Total: {total_min//60}h{total_min%60:02d}m")
            lines.append("")

        for fi, o in enumerate(all_fares, 1):
            sl0 = (o.get("slices") or [{}])[0]
            fb = sl0.get("fare_brand_name", "—")
            base = float(o.get("total_amount", 0))
            price = self.calculate_final_price(base, markup * 100, booking_fee)
            c = self._offer_conditions(o)
            sf = self.calculate_service_fee(base, service_floor)

            first_seg = (sl0.get("segments") or [{}])[0]
            pax_list = first_seg.get("passengers", []) if first_seg else []
            cabin_raw = ""
            if pax_list:
                cabin_raw = pax_list[0].get("cabin_class_marketing_name", "") or pax_list[0].get("cabin_class", "")
            cabin_str = cabin_raw.title() if cabin_raw else ""
            if cabin_str and fb and cabin_str.lower() in fb.lower():
                tier_str = fb
            elif cabin_str and fb:
                tier_str = f"{cabin_str} · {fb}"
            else:
                tier_str = cabin_str or fb or "—"

            if c["bags_checked"] > 0:
                bags = f"{c['bags_checked']} checked"
            else:
                bags = "No checked bag"
            if c["bags_carry"] > 0:
                bags += " + carry-on"

            if not c.get("change_specified", True):
                changes = "Needs airline confirmation"
            elif c["changeable"]:
                if c["change_penalty"] and float(c["change_penalty"]) > 0:
                    cur = c.get("change_currency", "")
                    changes = f"Allowed with fee {cur} {float(c['change_penalty']):.0f}"
                else:
                    changes = "Allowed"
            else:
                changes = "Not allowed"

            if not c.get("refund_specified", True):
                refunds = "Needs airline confirmation"
            elif c["refundable"]:
                if c.get("refund_penalty") and float(c["refund_penalty"]) > 0:
                    refunds = "Partial refund"
                else:
                    refunds = "Refundable"
            else:
                refunds = "Non-refundable"

            cancel = f"{currency} {sf:.0f}" if show_service_fee else "—"

            lines.append("─" * 42)
            lines.append(f"Tier {fi} — {tier_str}")
            lines.append(f"Price  : {currency} {price:.0f}")
            lines.append(f"Bags   : {bags}")
            lines.append(f"Changes: {changes}")
            lines.append(f"Refund : {refunds}")
            if show_service_fee:
                lines.append(f"Cancel : {cancel}")
            lines.append(f"ID     : {o.get('id', '')}")
            lines.append("")

        return "\n".join(lines)

    def format_offer_compact(self, offer: Dict, markup: float = 0.0, booking_fee: float = 0.0,
                              service_floor: float = 100.0, show_service_fee: bool = True) -> str:
        """Compact one-liner per leg — for scanning multiple options in a list."""
        airline = offer.get("owner", {}).get("name", "Unknown")
        base = float(offer.get("total_amount", 0))
        client_price = self.calculate_final_price(base, markup * 100, booking_fee)
        currency = offer.get("total_currency", "USD")
        fee_str = ""
        if show_service_fee:
            sf = self.calculate_service_fee(base, service_floor)
            fee_str = f"  |  Service fee: {currency} {sf:.0f} — non-refundable"
        # Fare brand from first slice
        sl0 = (offer.get("slices") or [{}])[0]
        fare_brand = sl0.get("fare_brand_name", "")
        cabin_raw = ""
        segs0 = sl0.get("segments") or [{}]
        pax_list = segs0[0].get("passengers", []) if segs0 else []
        if pax_list:
            cabin_raw = pax_list[0].get("cabin_class_marketing_name", "") or pax_list[0].get("cabin_class", "")
        cabin_str = cabin_raw.title() if cabin_raw else ""
        if cabin_str and fare_brand and cabin_str.lower() in fare_brand.lower():
            tier_str = fare_brand
        elif cabin_str and fare_brand:
            tier_str = f"{cabin_str} · {fare_brand}"
        else:
            tier_str = cabin_str or fare_brand or ""
        lines = [f"✈️ {airline}  {currency} {client_price:.0f}"]
        if tier_str:
            lines.append(f"   [{tier_str}]")
        if fee_str:
            lines.append(f"  {fee_str.strip()}")
        for i, sl in enumerate(offer.get("slices", [])):
            segs = sl.get("segments", [])
            direction = "OUT" if i == 0 else "RET"
            if len(segs) == 1:
                seg = segs[0]
                carrier = seg.get("operating_carrier", seg.get("marketing_carrier", {}))
                iata = carrier.get("iata_code", "")
                num = seg.get("operating_carrier_flight_number") or seg.get("marketing_carrier_flight_number", "")
                fn = f"{iata}{num}"
                orig = sl.get("origin", {}).get("iata_code", "?")
                dest = sl.get("destination", {}).get("iata_code", "?")
                dep_t = self._format_time(seg.get("departing_at", ""))
                arr_t = self._format_time(seg.get("arriving_at", ""))
                dep_date = self._format_date(seg.get("departing_at", ""), weekday=True)
                try:
                    dur_min = int((datetime.fromisoformat(seg["arriving_at"]) - datetime.fromisoformat(seg["departing_at"])).total_seconds() / 60)
                    dur_str = f"{dur_min//60}h{dur_min%60:02d}m"
                except:
                    dur_str = ""
                lines.append(f"  {direction} {fn}  {orig} {dep_t} → {dest} {arr_t}  {dur_str}  {dep_date}")
            else:
                # Connecting: one line per segment + layover + total
                try:
                    total_dep = datetime.fromisoformat(segs[0]["departing_at"])
                    total_arr = datetime.fromisoformat(segs[-1]["arriving_at"])
                    total_min = int((total_arr - total_dep).total_seconds() / 60)
                    total_str = f"{total_min//60}h{total_min%60:02d}m"
                except:
                    total_str = ""
                for j, seg in enumerate(segs):
                    carrier = seg.get("operating_carrier", seg.get("marketing_carrier", {}))
                    iata = carrier.get("iata_code", "")
                    num = seg.get("operating_carrier_flight_number") or seg.get("marketing_carrier_flight_number", "")
                    fn = f"{iata}{num}"
                    orig = seg.get("origin", {}).get("iata_code", "?")
                    dest = seg.get("destination", {}).get("iata_code", "?")
                    dep_t = self._format_time(seg.get("departing_at", ""))
                    arr_t = self._format_time(seg.get("arriving_at", ""))
                    try:
                        seg_min = int((datetime.fromisoformat(seg["arriving_at"]) - datetime.fromisoformat(seg["departing_at"])).total_seconds() / 60)
                        seg_dur = f"{seg_min//60}h{seg_min%60:02d}m"
                    except:
                        seg_dur = ""
                    lbl = direction if j == 0 else "   "
                    lines.append(f"  {lbl} {fn}  {orig} {dep_t} → {dest} {arr_t}  {seg_dur}")
                    if j < len(segs) - 1:
                        try:
                            lay_min = int((datetime.fromisoformat(segs[j+1]["departing_at"]) - datetime.fromisoformat(seg["arriving_at"])).total_seconds() / 60)
                            lay_str = f"{lay_min//60}h{lay_min%60:02d}m"
                        except:
                            lay_str = "?"
                        lines.append(f"       {dest} layover {lay_str}")
                if total_str:
                    lines.append(f"       Total: {total_str}")
        lines.append(f"  ID: {offer.get('id')}")
        return "\n".join(lines)

    def format_offer_full(self, offer: Dict, markup: float = 0.0, booking_fee: float = 0.0,
                          service_floor: float = 100.0, show_service_fee: bool = True) -> str:
        """Full presentation — each flight leg on its own line, layovers shown between legs."""
        airline = offer.get("owner", {}).get("name", "Unknown")
        base = float(offer.get("total_amount", 0))
        client_price = self.calculate_final_price(base, markup * 100, booking_fee)
        currency = offer.get("total_currency", "USD")
        # Fare label from first slice
        sl0 = (offer.get("slices") or [{}])[0]
        fare_brand = sl0.get("fare_brand_name", "")
        cabin_raw = ""
        segs0 = sl0.get("segments") or [{}]
        pax_list = segs0[0].get("passengers", []) if segs0 else []
        if pax_list:
            cabin_raw = pax_list[0].get("cabin_class_marketing_name", "") or pax_list[0].get("cabin_class", "")
        cabin_str = cabin_raw.title() if cabin_raw else ""
        if cabin_str and fare_brand and cabin_str.lower() in fare_brand.lower():
            tier_str = fare_brand
        elif cabin_str and fare_brand:
            tier_str = f"{cabin_str} · {fare_brand}"
        else:
            tier_str = cabin_str or fare_brand or ""

        header = f"✈️ {airline} {currency} {client_price:.0f}"
        if tier_str:
            header += f" [{tier_str}]"
        lines = [header, ""]

        for i, sl in enumerate(offer.get("slices", [])):
            segments = sl.get("segments", [])
            if not segments:
                continue
            direction = "OUTBOUND" if i == 0 else "RETURN"
            total_min = self._slice_duration_minutes(sl)
            stops = len(segments) - 1
            stops_label = "nonstop" if stops == 0 else f"{stops} stop" if stops == 1 else f"{stops} stops"
            dep_date = self._format_date(segments[0].get("departing_at", ""), weekday=True)
            lines.append(f" {direction} {dep_date} ({total_min//60}h{total_min%60:02d}m total, {stops_label})")

            for j, seg in enumerate(segments):
                carrier = seg.get("operating_carrier", seg.get("marketing_carrier", {}))
                iata = carrier.get("iata_code", "")
                num = seg.get("operating_carrier_flight_number") or seg.get("marketing_carrier_flight_number", "")
                fn = f"{iata}{num}" if iata and num else "??"

                orig = seg.get("origin", {})
                dest = seg.get("destination", {})
                orig_code = orig.get("iata_code", "???")
                orig_name = (orig.get("name") or "").split(",")[0].strip()
                dest_code = dest.get("iata_code", "???")
                dest_name = (dest.get("name") or "").split(",")[0].strip()
                dep_t = self._format_time(seg.get("departing_at", ""))
                arr_t = self._format_time(seg.get("arriving_at", ""))
                dep_d = self._format_date(seg.get("departing_at", ""))
                arr_d = self._format_date(seg.get("arriving_at", ""))
                seg_dur_raw = self._parse_iso_duration(seg.get("duration", ""))
                seg_dur = f"{seg_dur_raw//60}h{seg_dur_raw%60:02d}m" if seg_dur_raw else ""

                # Show date on segment if it differs from slice departure date (overnight layover)
                date_str = f" {dep_d}" if j > 0 else ""
                # Flag next-day arrival
                try:
                    dep_day = datetime.fromisoformat(seg["departing_at"]).date()
                    arr_day = datetime.fromisoformat(seg["arriving_at"]).date()
                    day_diff = (arr_day - dep_day).days
                    arr_note = f" (+{day_diff})" if day_diff > 0 else ""
                except:
                    arr_note = ""
                lines.append(f" ✈ {fn} {orig_code} {dep_t}{date_str} → {dest_code} {arr_t}{arr_note} {seg_dur}")
                if orig_name or dest_name:
                    lines.append(f" {orig_name} → {dest_name}")

                if j < len(segments) - 1:
                    try:
                        lay_min = int((
                            datetime.fromisoformat(segments[j+1]["departing_at"]) -
                            datetime.fromisoformat(seg["arriving_at"])
                        ).total_seconds() / 60)
                        lay_str = f"{lay_min//60}h{lay_min%60:02d}m"
                    except:
                        lay_str = "?"
                    lines.append(f" ┄ {dest_code} layover {lay_str}")

            lines.append("")
        lines.append(f" ID: {offer.get('id')}")
        return "\n".join(lines)

    def format_by_airline(self, offers: List[Dict], markup: float = 0.0, booking_fee: float = 0.0,
                          service_floor: float = 100.0, show_service_fee: bool = True) -> str:
        """One block per bookable combination — Skyscanner style. Each block = one ticket."""
        from collections import defaultdict

        # Filter nonstop only — if none exist, fall back gracefully to all offers
        nonstop = [o for o in offers if all(len(sl.get("segments", [])) == 1 for sl in o.get("slices", []))]
        if not nonstop:
            # No directs on this route — render top 10 with compact format and a note
            note = "  ℹ️  No nonstop options — showing connections:\n\n"
            rows = []
            for i, offer in enumerate(offers[:10], 1):
                rows.append(f"{i}.")
                rows.append(self.format_offer_full(offer, markup, booking_fee, service_floor, show_service_fee))
            return note + "\n".join(rows)

        def leg_data(sl):
            segs = sl.get("segments", [])
            if not segs:
                return {}
            seg, last = segs[0], segs[-1]
            carrier = seg.get("operating_carrier", seg.get("marketing_carrier", {}))
            op_iata = carrier.get("iata_code", "")
            fn = seg.get("operating_carrier_flight_number") or seg.get("marketing_carrier_flight_number", "")
            op_name = carrier.get("name", "")
            dep = seg.get("departing_at", "")
            arr = last.get("arriving_at", "")
            dur_min = 0
            try:
                dur_min = int((datetime.fromisoformat(arr) - datetime.fromisoformat(dep)).total_seconds() / 60)
            except:
                pass
            return {
                "fn": f"{op_iata}{fn}", "op_name": op_name,
                "dep": dep, "arr": arr,
                "dep_time": dep[11:16], "arr_time": arr[11:16],
                "dep_date": self._format_date(dep, weekday=True),
                "origin": sl.get("origin", {}).get("iata_code", "?"),
                "dest": sl.get("destination", {}).get("iata_code", "?"),
                "dur_h": dur_min // 60, "dur_m": dur_min % 60,
            }

        # Build one entry per offer (= one bookable combination)
        combos = []
        for o in nonstop:
            slices = o.get("slices", [])
            if len(slices) < 2:
                continue
            airline = o.get("owner", {}).get("name", "Unknown")
            out = leg_data(slices[0])
            ret = leg_data(slices[1])
            combos.append({
                "airline": airline,
                "out": out, "ret": ret,
                "price": float(o.get("total_amount", 0)),
                "currency": o.get("total_currency", "USD"),
                "id": o.get("id"),
            })

        # Deduplicate: keep cheapest per (airline, out_fn, ret_fn)
        seen = {}
        for c in combos:
            key = (c["airline"], c["out"].get("fn"), c["ret"].get("fn"))
            if key not in seen or c["price"] < seen[key]["price"]:
                seen[key] = c

        # Sort by price
        unique = sorted(seen.values(), key=lambda x: x["price"])

        lines = []
        for i, c in enumerate(unique, 1):
            airline = c["airline"]
            out, ret = c["out"], c["ret"]
            # Convert markup from decimal (0.05) to percentage (5.0) for calculate_final_price
            client_price = self.calculate_final_price(c["price"], markup * 100, booking_fee)
            currency = c["currency"]

            # Operator note if different from selling airline
            op_note = ""
            op_names = set(filter(None, [out.get("op_name"), ret.get("op_name")]))
            op_names.discard(airline)
            if len(op_names) == 1:
                op_note = f"  (operated by {op_names.pop()})"

            lines.append(f"{'─'*52}")
            lines.append(f"  Option {i}   {airline}{op_note}   {currency} {client_price:.0f}")
            if show_service_fee:
                sf = self.calculate_service_fee(c["price"], service_floor)
                lines.append(f"  Service fee: {currency} {sf:.0f} — non-refundable")
            lines.append(f"{'─'*52}")
            lines.append(f"  OUT  {out['fn']}   {out['origin']} {out['dep_time']} → {out['dest']} {out['arr_time']}   {out['dur_h']}h{out['dur_m']:02d}m  {out['dep_date']}")
            lines.append(f"  RET  {ret['fn']}   {ret['origin']} {ret['dep_time']} → {ret['dest']} {ret['arr_time']}   {ret['dur_h']}h{ret['dur_m']:02d}m  {ret['dep_date']}")
            lines.append(f"  [ID: {c['id']}]")
            lines.append("")

        return "\n".join(lines)

    # Keep old name as alias pointing to compact for backwards compat
    def format_offer_detailed(self, offer: Dict, markup: float = 0.03) -> str:
        return self.format_offer_compact(offer, markup)
    
    def format_offer(self, offer: Dict, show_times: bool = True) -> str:
        """Format offer with separate outbound/return durations (legacy)"""
        airline = offer.get("owner", {}).get("name", "Unknown")
        total = f"{offer.get('total_amount')} {offer.get('total_currency')}"
        
        slices = offer.get("slices", [])
        
        # Calculate per-slice durations and stops
        slice_info = []
        for i, slice in enumerate(slices):
            duration_min = self._slice_duration_minutes(slice)
            duration_h = duration_min // 60
            duration_m = duration_min % 60
            segments = slice.get("segments", [])
            stops = max(0, len(segments) - 1)
            
            origin = slice.get("origin", {}).get("iata_code", "???")
            dest = slice.get("destination", {}).get("iata_code", "???")
            direction = "Outbound" if i == 0 else "Return"
            
            stops_text = f"{stops} stop" if stops == 1 else f"{stops} stops" if stops > 1 else "direct"
            slice_info.append(f"{direction}: {duration_h}h{duration_m:02d}m ({stops_text}) {origin}→{dest}")
        
        # Max layover warning
        max_layover = offer.get("_max_layover_min", 0)
        layover_warning = ""
        if max_layover > 240:
            layover_warning = f" ⚠️ long layover ({max_layover//60}h{max_layover%60}m)"
        
        return f"✈️ {airline} | {total}{layover_warning} | {' | '.join(slice_info)} | ID: {offer.get('id')}"
    
    def create_order(self, offer_id: str, passengers: List[Dict], payment_type: str = "balance", metadata: Optional[Dict] = None) -> Dict:
        print(f"🎫 Creating order...", file=sys.stderr)
        for i, pax in enumerate(passengers):
            self._validate_passenger(pax, index=i, require_id=True)
        
        offer = self._get_offer(offer_id)
        total_amount = offer.get("total_amount")
        total_currency = offer.get("total_currency")
        
        payload = {
            "data": {
                "selected_offers": [offer_id],
                "passengers": passengers,
                "payments": [{"type": payment_type, "amount": total_amount, "currency": total_currency}]
            }
        }
        if metadata:
            payload["data"]["metadata"] = metadata
        
        result = self._request("POST", "/air/orders", payload)
        order = result.get("data", {})
        print(f"✓ Order: {order.get('id')} | PNR: {order.get('booking_reference')}", file=sys.stderr)
        return order
    
    def _validate_passenger(self, passenger: Dict, index: int = 0, require_id: bool = False):
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
        result = self._request("GET", f"/air/offers/{offer_id}")
        return result.get("data", {})
    
    def get_order(self, order_id: str) -> Dict:
        result = self._request("GET", f"/air/orders/{order_id}")
        return result.get("data", {})
    
    def list_orders(self, limit: int = 50, **filters) -> List[Dict]:
        params = {"limit": limit, **filters}
        result = self._request("GET", "/air/orders", params)
        return result.get("data", [])


def main():
    parser = argparse.ArgumentParser(description="Duffel Flight Booking Client v2")
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    search_parser = subparsers.add_parser("search", help="Search flights")
    search_parser.add_argument("--origin", required=True)
    search_parser.add_argument("--destination", required=True)
    search_parser.add_argument("--date", required=True)
    search_parser.add_argument("--return-date")
    search_parser.add_argument("--cabin", default="economy")
    search_parser.add_argument("--adults", type=int, default=1)
    search_parser.add_argument("--sort", default="duration", choices=["duration", "price"])
    search_parser.add_argument("--full", action="store_true", help="Show full format with airport names (default: compact list)")
    search_parser.add_argument("--by-airline", action="store_true", help="Group nonstop results by airline — one block per carrier")
    search_parser.add_argument("--mode", default="live", choices=["sandbox", "live"])
    search_parser.add_argument("--limit", type=int, default=10, help="Max offers to show")
    search_parser.add_argument("--markup", type=float, default=0.0,
        help="Markup %% of base fare (default 0.0; use 3-5 for client bookings on expensive fares)")
    search_parser.add_argument("--booking-fee", type=float, default=0.0,
        help="Flat booking fee in offer currency (default 0.0; use e.g. 50 for cheap/budget flights)")
    search_parser.add_argument("--service-floor", type=float, default=100.0,
        help="Your minimum non-refundable service fee in USD (default 100; e.g. 200 for premium clients)")
    search_parser.add_argument("--no-service-fee", action="store_true",
        help="Hide the service fee line from output (e.g. personal searches, trusted clients)")
    search_parser.add_argument("--profile", default="light",
        choices=["light", "standard", "flex", "full-flex"],
        help="Fare profile filter: light=cheapest anything, standard=must have ≥1 bag, flex=bag+changeable, full-flex=bag+changeable+refundable")
    search_parser.add_argument("--grouped", action="store_true",
        help="Group by unique itinerary (Phase 1 view) — one block per flight combo, cheapest fare shown")

    book_parser = subparsers.add_parser("book", help="Book a flight")
    book_parser.add_argument("--offer-id", required=True)
    book_parser.add_argument("--passenger", required=True, action="append")
    book_parser.add_argument("--payment", default="balance")
    book_parser.add_argument("--mode", default="live", choices=["sandbox", "live"])
    book_parser.add_argument("--loyalty", action="append", help="Frequent flyer per passenger: IATA_CODE:ACCOUNT_NUMBER (e.g. LX:12345678). Repeat flag for each passenger in order. Comma-separate multiple programmes for one passenger (e.g. LX:123,LH:456).")
    
    order_parser = subparsers.add_parser("order", help="Get order details")
    order_parser.add_argument("--id", required=True)
    order_parser.add_argument("--mode", default="live", choices=["sandbox", "live"])
    
    list_parser = subparsers.add_parser("list", help="List orders")
    list_parser.add_argument("--limit", type=int, default=10)
    list_parser.add_argument("--mode", default="live", choices=["sandbox", "live"])

    seats_parser = subparsers.add_parser("seats", help="Show seat map for an offer")
    seats_parser.add_argument("--offer-id", required=True)
    seats_parser.add_argument("--mode", default="live", choices=["sandbox", "live"])
    seats_parser.add_argument("--max-rows", type=int, default=10, help="Max rows to display")

    services_parser = subparsers.add_parser("services", help="List available services for a booked order")
    services_parser.add_argument("--order-id", required=True)
    services_parser.add_argument("--mode", default="live", choices=["sandbox", "live"])

    add_svc_parser = subparsers.add_parser("add-service", help="Add services to an order")
    add_svc_parser.add_argument("--order-id", required=True)
    add_svc_parser.add_argument("--service-id", required=True, action="append", help="Service ID (repeatable)")
    add_svc_parser.add_argument("--mode", default="live", choices=["sandbox", "live"])

    cancel_parser = subparsers.add_parser("cancel", help="Get cancellation quote or confirm cancellation")
    cancel_parser.add_argument("--order-id", required=True)
    cancel_parser.add_argument("--confirm", help="Cancellation ID to confirm (omit for quote only)")
    cancel_parser.add_argument("--mode", default="live", choices=["sandbox", "live"])

    expand_parser = subparsers.add_parser("expand", help="Show all fare variants for itinerary N from a grouped search")
    expand_parser.add_argument("--origin", required=True)
    expand_parser.add_argument("--destination", required=True)
    expand_parser.add_argument("--date", required=True)
    expand_parser.add_argument("--return-date")
    expand_parser.add_argument("--cabin", default="economy")
    expand_parser.add_argument("--adults", type=int, default=1)
    expand_parser.add_argument("--group", type=int, required=True, help="Itinerary number from grouped search (1-based)")
    expand_parser.add_argument("--markup", type=float, default=0.0)
    expand_parser.add_argument("--booking-fee", type=float, default=0.0)
    expand_parser.add_argument("--service-floor", type=float, default=100.0)
    expand_parser.add_argument("--mode", default="live", choices=["sandbox", "live"])

    show_parser = subparsers.add_parser("show", help="Zoom into option N from last search (full format with airport names)")
    show_parser.add_argument("--option", type=int, required=True, help="Option number from last search (1-based)")
    show_parser.add_argument("--markup", type=float, default=None, help="Override markup from cached search")
    show_parser.add_argument("--no-service-fee", action="store_true")
    show_parser.add_argument("--mode", default="live", choices=["sandbox", "live"])

    smart_parser = subparsers.add_parser("smart", help="Smart search with airline awareness and date flexibility")
    smart_parser.add_argument("--origin", required=True)
    smart_parser.add_argument("--destination", required=True)
    smart_parser.add_argument("--date", required=True, help="Departure date (YYYY-MM-DD)")
    smart_parser.add_argument("--return-date", help="Return date (YYYY-MM-DD)")
    smart_parser.add_argument("--cabin", default="economy")
    smart_parser.add_argument("--adults", type=int, default=1)
    smart_parser.add_argument("--flexibility", type=int, default=1, help="Days +/- to search if no directs")
    smart_parser.add_argument("--mode", default="live", choices=["sandbox", "live"])

    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(0)
    
    mode = getattr(args, 'mode', 'sandbox')
    if mode == "live":
        print(f"\n⚠️  WARNING: LIVE MODE - Real bookings!\n", file=sys.stderr)

    # Smart command uses its own client via FlexibleSearch
    if args.command == "smart":
        from flexible_search import FlexibleSearch, print_results
        searcher = FlexibleSearch(mode=mode)
        results = searcher.search(
            origin=args.origin,
            destination=args.destination,
            departure_date=args.date,
            return_date=args.return_date,
            cabin_class=args.cabin,
            adults=args.adults,
            flexibility=args.flexibility
        )
        print_results(results, searcher.airline_cache)
        return

    try:
        client = DuffelClient(mode=mode)
    except DuffelError as e:
        print(f"❌ {e.message}", file=sys.stderr)
        sys.exit(1)

    if args.command == "search":
        result = client.search_flights(
            origin=args.origin,
            destination=args.destination,
            departure_date=args.date,
            return_date=args.return_date,
            cabin_class=args.cabin,
            adults=args.adults,
            sort_by=args.sort
        )
        
        offers = result["offers"]
        route_intel = result["route_intelligence"]
        advisory = route_intel["advisory"]
        
        print(f"\n{'='*80}")
        print(f"SEARCH RESULTS: {args.origin} → {args.destination}")
        print(f"Sorted by: {args.sort.upper()}")
        print(f"{'='*80}\n")
        
        # Show advisory if applicable
        if advisory["show_advisory"]:
            print(f"⚠️  {advisory['message']}")
            print(f"   Duffel shows: {offers[0].get('owner', {}).get('name', 'Unknown')} connections\n")
        
        markup_pct = getattr(args, 'markup', 0.0)
        booking_fee = getattr(args, 'booking_fee', 0.0)
        service_floor = getattr(args, 'service_floor', 100.0)
        show_service_fee = not getattr(args, 'no_service_fee', False)
        limit = getattr(args, 'limit', 10)
        
        # Trade-off summary — cheapest and latest-departure outbound
        # No "best" label — client decides based on price vs schedule preference
        if len(offers) >= 2:
            def _out_info(o):
                sl = o.get("slices", [])
                if not sl:
                    return 999999, 999999, "--:--", "?"
                segs = sl[0].get("segments", [])
                if not segs:
                    return 999999, 999999, "--:--", "?"
                try:
                    first_dep = datetime.fromisoformat(segs[0]["departing_at"])
                    last_arr = datetime.fromisoformat(segs[-1]["arriving_at"])
                    dur_min = int((last_arr - first_dep).total_seconds() / 60)
                    dep_time = first_dep.strftime("%H:%M")
                    dep_hour = first_dep.hour * 60 + first_dep.minute
                    return dur_min, dep_hour, dep_time, segs[0].get("departing_at", "")
                except:
                    return 999999, 999999, "--:--", "?"

            cheapest = min(offers, key=lambda x: float(x.get("total_amount", 999999)))
            latest_dep = max(offers, key=lambda x: _out_info(x)[1])  # latest outbound departure

            cheap_price = client.calculate_final_price(float(cheapest.get("total_amount", 0)), markup_pct, booking_fee)
            cheap_dur, _, cheap_deptime, _ = _out_info(cheapest)

            late_price = client.calculate_final_price(float(latest_dep.get("total_amount", 0)), markup_pct, booking_fee)
            late_dur, _, late_deptime, _ = _out_info(latest_dep)

            print("📊 HIGHLIGHTS:")
            print(f"   💰 Cheapest:        ${cheap_price:.0f} — departs {cheap_deptime}, outbound {cheap_dur//60}h{cheap_dur%60:02d}m — {cheapest.get('owner', {}).get('name', 'Unknown')}")
            print(f"   🕐 Latest departure: ${late_price:.0f} — departs {late_deptime}, outbound {late_dur//60}h{late_dur%60:02d}m — {latest_dep.get('owner', {}).get('name', 'Unknown')}")
            print(f"   ({len(offers)} options total — sorted by {args.sort})")
            print()
        
        # Show results — four modes: grouped (Phase 1), by-airline blocks, full with names, compact list
        use_by_airline = getattr(args, 'by_airline', False)
        use_full = getattr(args, 'full', False)
        use_grouped = getattr(args, 'grouped', False)
        profile = getattr(args, 'profile', 'light')

        if use_grouped:
            groups = client.group_offers_by_itinerary(offers, profile)
            print(f"Profile: {profile.upper()}  |  {len(groups)} unique itineraries found (from {len(offers)} offers)\n")
            print(client.format_grouped_search(offers, profile, markup_pct/100, booking_fee, service_floor, show_service_fee, limit))
        elif use_by_airline:
            print(client.format_by_airline(offers, markup_pct/100, booking_fee, service_floor, show_service_fee))
        else:
            for i, offer in enumerate(offers[:limit], 1):
                if use_full:
                    print(f"{i}.")
                    print(client.format_offer_full(offer, markup_pct/100, booking_fee, service_floor, show_service_fee))
                    print()
                else:
                    print(f"{i}.")
                    print(client.format_offer_compact(offer, markup_pct/100, booking_fee, service_floor, show_service_fee))
                    print()
            if len(offers) > limit:
                print(f"\n... and {len(offers) - limit} more options")

        # Always cache full offer list for instant zoom (show subcommand)
        cache = {
            "cached_at": datetime.utcnow().isoformat(),
            "origin": args.origin,
            "destination": args.destination,
            "date": args.date,
            "return_date": getattr(args, "return_date", None),
            "cabin": getattr(args, "cabin", "economy"),
            "markup": markup_pct,
            "booking_fee": booking_fee,
            "service_floor": service_floor,
            "offers": offers
        }
        with open("/tmp/duffel_last_search.json", "w") as f:
            json.dump(cache, f)
        print(f"\n💾 {len(offers)} offers cached for 20 minutes — use `show --option N` to zoom in on any option.", file=sys.stderr)
    
    elif args.command == "book":
        passenger_details = [json.loads(p) for p in args.passenger]
        try:
            offer = client._get_offer(args.offer_id)
            offer_passengers = offer.get("passengers", [])
            
            if len(offer_passengers) != len(passenger_details):
                raise DuffelError(f"Passenger count mismatch")
            
            # Parse loyalty programmes per passenger: --loyalty LX:123,LH:456 --loyalty "" --loyalty UA:789
            # Each --loyalty entry corresponds to passenger N (by position). Empty string = no loyalty for that pax.
            loyalty_per_pax = []
            raw_loyalties = getattr(args, "loyalty", None) or []
            for raw in raw_loyalties:
                accounts = []
                for entry in (raw or "").split(","):
                    parts = entry.strip().split(":", 1)
                    if len(parts) == 2 and parts[0] and parts[1]:
                        accounts.append({"airline_iata_code": parts[0].upper(), "account_number": parts[1]})
                loyalty_per_pax.append(accounts)

            passengers = []
            for i, pax_detail in enumerate(passenger_details):
                pax_id = offer_passengers[i].get("id")
                if not pax_id:
                    raise DuffelError(f"Passenger {i+1} has no ID in offer")
                pax = {"id": pax_id, **pax_detail}
                if i < len(loyalty_per_pax) and loyalty_per_pax[i]:
                    pax["loyalty_programme_accounts"] = loyalty_per_pax[i]
                    loyalty_str = ', '.join(f'{l["airline_iata_code"]}:{l["account_number"]}' for l in loyalty_per_pax[i])
                    print(f"✈️  Pax {i+1} loyalty: {loyalty_str}", file=sys.stderr)
                passengers.append(pax)
            
            order = client.create_order(offer_id=args.offer_id, passengers=passengers, payment_type=args.payment)
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
    
    elif args.command == "show":
        try:
            with open("/tmp/duffel_last_search.json") as f:
                cache = json.load(f)
        except FileNotFoundError:
            print("❌ No cached search found. Run a search first.", file=sys.stderr)
            sys.exit(1)

        cached_at_raw = cache.get("cached_at")
        if not cached_at_raw:
            print("❌ Cached search has no timestamp. Run a fresh search first.", file=sys.stderr)
            sys.exit(1)
        try:
            cached_at = datetime.fromisoformat(cached_at_raw)
        except ValueError:
            print("❌ Cached search timestamp is invalid. Run a fresh search first.", file=sys.stderr)
            sys.exit(1)
        cache_age = (datetime.utcnow() - cached_at).total_seconds()
        if cache_age > DUFFEL_CACHE_TTL_SECONDS:
            print("❌ Cached search expired (>20 minutes). Run a fresh search first.", file=sys.stderr)
            sys.exit(1)

        offers = cache["offers"]
        n = args.option
        if n < 1 or n > len(offers):
            print(f"❌ Option {n} out of range (1–{len(offers)})", file=sys.stderr)
            sys.exit(1)
        offer = offers[n - 1]
        markup = args.markup if args.markup is not None else cache.get("markup", 0.0)
        booking_fee = cache.get("booking_fee", 0.0)
        service_floor = cache.get("service_floor", 100.0)
        show_service_fee = not getattr(args, "no_service_fee", False)

        # Show full itinerary detail for selected offer
        print(client.format_offer_full(offer, markup/100, booking_fee, service_floor, show_service_fee))

        # Find all fare variants for the same itinerary from the cache
        def _itin_key(o):
            """Fingerprint: flight numbers + departure times across all slices."""
            parts = []
            for sl in o.get("slices", []):
                for seg in sl.get("segments", []):
                    carrier = seg.get("operating_carrier", seg.get("marketing_carrier", {}))
                    iata = carrier.get("iata_code", "")
                    num = seg.get("operating_carrier_flight_number") or seg.get("marketing_carrier_flight_number", "")
                    dep = seg.get("departing_at", "")[:16]  # YYYY-MM-DDTHH:MM
                    parts.append(f"{iata}{num}@{dep}")
            return "|".join(parts)

        selected_key = _itin_key(offer)
        variants = [o for o in offers if _itin_key(o) == selected_key]
        variants.sort(key=lambda o: float(o.get("total_amount", 0)))

        if len(variants) > 1:
            airline_name = offer.get("owner", {}).get("name", "Unknown")
            print(f"\n{'─'*44}")
            print(f"FARE OPTIONS — {airline_name} ({len(variants)} tiers)")
            print(f"{'─'*44}")
            for fi, o in enumerate(variants, 1):
                sl0 = (o.get("slices") or [{}])[0]
                fb = sl0.get("fare_brand_name", "") or "—"
                base = float(o.get("total_amount", 0))
                price = client.calculate_final_price(base, markup/100 * 100, booking_fee)
                currency = o.get("total_currency", "USD")
                c = client._offer_conditions(o)
                sf = client.calculate_service_fee(base, service_floor)
                # Bags
                bags = (f"{c['bags_checked']}×23kg checked" if c["bags_checked"] > 0 else "No checked bag")
                if c["bags_carry"] > 0:
                    bags += " + carry-on"
                # Changes
                if not c.get("change_specified", True):
                    chg = "Needs airline confirmation"
                elif c["changeable"]:
                    cur = c.get("change_currency", "")
                    chg = (f"Fee {cur} {float(c['change_penalty']):.0f}" if c["change_penalty"] and float(c["change_penalty"]) > 0 else "Free")
                else:
                    chg = "Not allowed"
                # Refund
                if not c.get("refund_specified", True):
                    ref = "Needs airline confirmation"
                elif c["refundable"]:
                    ref = ("Partial (fee applies)" if c.get("refund_penalty") and float(c["refund_penalty"]) > 0 else "Full refund ✓")
                else:
                    ref = "Non-refundable"
                label_w = len("Changes")
                print(f"  {'Tier':<{label_w}}: {fi} — {fb}")
                print(f"  {'Price':<{label_w}}: {currency} {price:.0f}")
                print(f"  {'Bags':<{label_w}}: {bags}")
                print(f"  {'Changes':<{label_w}}: {chg}")
                print(f"  {'Refund':<{label_w}}: {ref}")
                if show_service_fee:
                    print(f"  {'Cancel':<{label_w}}: {currency} {sf:.0f} (non-refundable)")
                print(f"  {'ID':<{label_w}}: {o.get('id', '')}")
                print()

    elif args.command == "order":
        order = client.get_order(args.id)
        print(json.dumps(order, indent=2))
    
    elif args.command == "list":
        orders = client.list_orders(limit=args.limit)
        print(f"\n{'='*80}")
        print(f"Recent Orders ({len(orders)} results)")
        print(f"{'='*80}\n")
        for order in orders:
            print(f"  {order.get('id')} | PNR: {order.get('booking_reference')} | {order.get('total_amount')} {order.get('total_currency')} | {order.get('status')}")

    elif args.command == "seats":
        from ancillaries import AncillaryManager
        try:
            mgr = AncillaryManager(client)
            seat_data = mgr.get_seat_map(args.offer_id)
            print(mgr.format_seat_map(seat_data, max_rows=args.max_rows))
        except DuffelError as e:
            print(f"❌ {e.message}", file=sys.stderr)
            sys.exit(1)

    elif args.command == "services":
        from ancillaries import AncillaryManager
        try:
            mgr = AncillaryManager(client)
            services = mgr.get_available_services(args.order_id)
            print(mgr.format_services(services))
        except DuffelError as e:
            print(f"❌ {e.message}", file=sys.stderr)
            sys.exit(1)

    elif args.command == "add-service":
        from ancillaries import AncillaryManager
        try:
            mgr = AncillaryManager(client)
            result = mgr.add_services_to_order(args.order_id, args.service_id)
            print(f"✅ Services added successfully.")
            print(json.dumps(result, indent=2))
        except DuffelError as e:
            print(f"❌ {e.message}", file=sys.stderr)
            sys.exit(1)

    elif args.command == "expand":
        try:
            with open("/tmp/duffel_last_search.json") as f:
                cache = json.load(f)
        except FileNotFoundError:
            print("❌ No cached search found. Run a grouped search first.", file=sys.stderr)
            sys.exit(1)

        cached_at_raw = cache.get("cached_at")
        if not cached_at_raw:
            print("❌ Cached search has no timestamp. Run a fresh grouped search first.", file=sys.stderr)
            sys.exit(1)
        try:
            cached_at = datetime.fromisoformat(cached_at_raw)
        except ValueError:
            print("❌ Cached search timestamp is invalid. Run a fresh grouped search first.", file=sys.stderr)
            sys.exit(1)
        cache_age = (datetime.utcnow() - cached_at).total_seconds()
        if cache_age > DUFFEL_CACHE_TTL_SECONDS:
            print("❌ Cached grouped search expired (>20 minutes). Run a fresh grouped search first.", file=sys.stderr)
            sys.exit(1)

        offers = cache["offers"]
        markup_pct = getattr(args, 'markup', cache.get('markup', 0.0))
        booking_fee = getattr(args, 'booking_fee', cache.get('booking_fee', 0.0))
        service_floor = getattr(args, 'service_floor', cache.get('service_floor', 100.0))
        print(f"\n{'='*80}")
        print(f"FARE EXPANSION — Itinerary #{args.group}: {cache.get('origin', args.origin)} → {cache.get('destination', args.destination)}")
        print(f"{'='*80}\n")
        print(client.format_expand(offers, args.group, markup_pct/100, booking_fee, service_floor))

    elif args.command == "cancel":
        from order_manager import OrderManager
        try:
            mgr = OrderManager(client)
            if args.confirm:
                result = mgr.confirm_cancellation(args.confirm)
                print(f"✅ Cancellation confirmed.")
                print(f"   ID: {result.get('id')}")
                print(f"   Status: {result.get('status')}")
                refund = result.get("refund_amount", "0")
                cur = result.get("refund_currency", "EUR")
                sym = {"EUR": "€", "GBP": "£", "USD": "$", "CHF": "CHF"}.get(cur, cur)
                print(f"   Refund: {sym}{refund}")
            else:
                quote = mgr.get_cancellation_quote(args.order_id)
                print(mgr.format_cancellation_quote(quote))
        except DuffelError as e:
            print(f"❌ {e.message}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
