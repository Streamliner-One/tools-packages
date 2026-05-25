#!/usr/bin/env python3
"""
Flexible Flight Search Engine
Smart search with airline-aware strategy, date flexibility, and result ranking.

Algorithm:
  1. Search round-trip on exact dates
  2. Search each leg one-way on exact dates
  3. If a leg has poor results, search +/-N days for that leg
  4. Build results matrix, rank combinations

Ranking: Direct > Travel time > Stops > Price
"""

import sys
import os
from datetime import datetime, timedelta
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from duffel_client import DuffelClient, DuffelError
from route_cache import RouteCache
from airline_cache import AirlineCache


def _parse_duration(slices: list) -> int:
    """Total travel minutes across all slices (excludes time at destination)."""
    total = 0
    for sl in slices:
        segs = sl.get("segments", [])
        if not segs:
            continue
        try:
            dep = datetime.fromisoformat(segs[0]["departing_at"])
            arr = datetime.fromisoformat(segs[-1]["arriving_at"])
            total += int((arr - dep).total_seconds() / 60)
        except (KeyError, ValueError):
            total += 99999
    return total


def _count_stops(slices: list) -> int:
    return sum(max(0, len(sl.get("segments", [])) - 1) for sl in slices)


def _is_direct(slices: list) -> bool:
    """True if every slice has exactly 1 segment."""
    return all(len(sl.get("segments", [])) == 1 for sl in slices)


def _offer_sort_key(offer: dict) -> tuple:
    """Ranking: direct first, then travel time, then stops, then price."""
    slices = offer.get("slices", [])
    direct = 0 if _is_direct(slices) else 1
    duration = _parse_duration(slices)
    stops = _count_stops(slices)
    price = float(offer.get("total_amount", "999999"))
    return (direct, duration, stops, price)


def _shift_date(date_str: str, days: int) -> str:
    dt = datetime.strptime(date_str, "%Y-%m-%d") + timedelta(days=days)
    return dt.strftime("%Y-%m-%d")


class FlexibleSearch:
    """Intelligent flight search with airline classification and date flexibility."""

    def __init__(self, mode: str = "live"):
        self.client = DuffelClient(mode=mode)
        self.route_cache = RouteCache()
        self.airline_cache = AirlineCache()

    def _search_raw(self, origin: str, destination: str, departure_date: str,
                    return_date: Optional[str] = None, cabin_class: str = "economy",
                    adults: int = 1) -> list:
        """Run a single Duffel search and return offers list."""
        try:
            result = self.client.search_flights(
                origin=origin,
                destination=destination,
                departure_date=departure_date,
                return_date=return_date,
                cabin_class=cabin_class,
                adults=adults
            )
            offers = result.get("offers", [])
            # Learn airlines from results
            self.airline_cache.learn_from_offers(offers)
            # Cache route intelligence
            self.route_cache.cache_from_search(origin, destination, offers)
            return offers
        except DuffelError as e:
            print(f"Search failed ({origin}->{destination} {departure_date}): {e.message}", file=sys.stderr)
            return []

    def _has_directs(self, offers: list) -> bool:
        return any(_is_direct(o.get("slices", [])) for o in offers)

    def _best_offer(self, offers: list) -> Optional[dict]:
        if not offers:
            return None
        return min(offers, key=_offer_sort_key)

    def _direct_offers(self, offers: list) -> list:
        return [o for o in offers if _is_direct(o.get("slices", []))]

    def search(self, origin: str, destination: str, departure_date: str,
               return_date: Optional[str] = None, cabin_class: str = "economy",
               adults: int = 1, flexibility: int = 1) -> dict:
        """
        Run the full smart search algorithm.

        Returns a results dict with:
          - roundtrip: best round-trip offer (if return_date given)
          - outbound_ow: best one-way outbound
          - return_ow: best one-way return
          - best_combo: cheapest combination (RT or OW+OW)
          - flex_outbound: {date: best_offer} for flexible outbound dates
          - flex_return: {date: best_offer} for flexible return dates
          - best_flex_combo: best flexible combination
          - advisory: route advisory from cache
          - date_matrix: which dates have directs
        """
        results = {
            "origin": origin,
            "destination": destination,
            "departure_date": departure_date,
            "return_date": return_date,
            "roundtrip": None,
            "roundtrip_offers": [],
            "outbound_ow": None,
            "outbound_ow_offers": [],
            "return_ow": None,
            "return_ow_offers": [],
            "best_combo": None,
            "combo_type": None,
            "flex_outbound": {},
            "flex_return": {},
            "best_flex_combo": None,
            "flex_combo_type": None,
            "advisory": None,
            "date_matrix": {},
        }

        # Advisory
        results["advisory"] = self.route_cache.get_advisory(origin, destination)

        # --- Step 1: Round-trip search on exact dates ---
        rt_offers = []
        if return_date:
            print(f"\n[Step 1] Round-trip: {origin}->{destination} {departure_date} / {return_date}", file=sys.stderr)
            rt_offers = self._search_raw(origin, destination, departure_date, return_date, cabin_class, adults)
            rt_offers.sort(key=_offer_sort_key)
            results["roundtrip_offers"] = rt_offers
            results["roundtrip"] = self._best_offer(rt_offers)

        # --- Step 2: One-way searches on exact dates ---
        print(f"\n[Step 2a] One-way outbound: {origin}->{destination} {departure_date}", file=sys.stderr)
        ow_out_offers = self._search_raw(origin, destination, departure_date, cabin_class=cabin_class, adults=adults)
        ow_out_offers.sort(key=_offer_sort_key)
        results["outbound_ow_offers"] = ow_out_offers
        results["outbound_ow"] = self._best_offer(ow_out_offers)

        ow_ret_offers = []
        if return_date:
            print(f"\n[Step 2b] One-way return: {destination}->{origin} {return_date}", file=sys.stderr)
            ow_ret_offers = self._search_raw(destination, origin, return_date, cabin_class=cabin_class, adults=adults)
            ow_ret_offers.sort(key=_offer_sort_key)
            results["return_ow_offers"] = ow_ret_offers
            results["return_ow"] = self._best_offer(ow_ret_offers)

        # Record exact-date matrix entries
        results["date_matrix"][departure_date] = {
            "outbound_direct": self._has_directs(ow_out_offers),
            "outbound_count": len(ow_out_offers),
        }
        if return_date:
            results["date_matrix"][return_date] = {
                "return_direct": self._has_directs(ow_ret_offers),
                "return_count": len(ow_ret_offers),
            }

        # --- Step 3: Flexible date searches if results are poor ---
        if flexibility > 0:
            # Check outbound
            outbound_poor = not self._has_directs(ow_out_offers)
            if outbound_poor:
                print(f"\n[Step 3a] Flex outbound: no directs on {departure_date}, searching +/-{flexibility} days", file=sys.stderr)
            for delta in range(-flexibility, flexibility + 1):
                if delta == 0:
                    continue
                flex_date = _shift_date(departure_date, delta)

                if outbound_poor:
                    flex_offers = self._search_raw(origin, destination, flex_date, cabin_class=cabin_class, adults=adults)
                    if flex_offers:
                        flex_offers.sort(key=_offer_sort_key)
                        results["flex_outbound"][flex_date] = {
                            "best": self._best_offer(flex_offers),
                            "has_direct": self._has_directs(flex_offers),
                            "count": len(flex_offers),
                        }
                        results["date_matrix"][flex_date] = {
                            "outbound_direct": self._has_directs(flex_offers),
                            "outbound_count": len(flex_offers),
                        }

            # Check return
            if return_date:
                return_poor = not self._has_directs(ow_ret_offers)
                if return_poor:
                    print(f"\n[Step 3b] Flex return: no directs on {return_date}, searching +/-{flexibility} days", file=sys.stderr)
                for delta in range(-flexibility, flexibility + 1):
                    if delta == 0:
                        continue
                    flex_date = _shift_date(return_date, delta)

                    if return_poor:
                        flex_offers = self._search_raw(destination, origin, flex_date, cabin_class=cabin_class, adults=adults)
                        if flex_offers:
                            flex_offers.sort(key=_offer_sort_key)
                            results["flex_return"][flex_date] = {
                                "best": self._best_offer(flex_offers),
                                "has_direct": self._has_directs(flex_offers),
                                "count": len(flex_offers),
                            }
                            results["date_matrix"][flex_date] = {
                                "return_direct": self._has_directs(flex_offers),
                                "return_count": len(flex_offers),
                            }

        # --- Step 4: Build best combination ---
        results["best_combo"], results["combo_type"] = self._pick_best_combo(results)
        results["best_flex_combo"], results["flex_combo_type"] = self._pick_best_flex_combo(results)

        return results

    def _pick_best_combo(self, results: dict) -> tuple:
        """Compare round-trip vs sum of one-ways on exact dates."""
        rt = results.get("roundtrip")
        ow_out = results.get("outbound_ow")
        ow_ret = results.get("return_ow")

        rt_price = float(rt["total_amount"]) if rt else None
        ow_total = None
        if ow_out:
            ow_out_price = float(ow_out["total_amount"])
            if ow_ret:
                ow_ret_price = float(ow_ret["total_amount"])
                ow_total = ow_out_price + ow_ret_price
            else:
                # One-way only (no return date)
                return (ow_out, "one_way")

        if rt_price is not None and ow_total is not None:
            # Check airline type — legacy carriers favor round-trip
            rt_iata = rt.get("owner", {}).get("iata_code", "")
            if self.airline_cache.is_legacy(rt_iata) and rt_price <= ow_total * 1.05:
                # Legacy: prefer RT even if up to 5% more (better flexibility usually)
                return (rt, "roundtrip_legacy")
            if rt_price <= ow_total:
                return (rt, "roundtrip")
            return ({"_synthetic": True, "outbound": ow_out, "return": ow_ret,
                      "total_amount": str(ow_total), "total_currency": ow_out.get("total_currency", "EUR")},
                     "two_one_ways")
        elif rt_price is not None:
            return (rt, "roundtrip")
        elif ow_out:
            return (ow_out, "one_way")
        return (None, None)

    def _pick_best_flex_combo(self, results: dict) -> tuple:
        """Find best combination across flexible dates."""
        best = results.get("best_combo")
        best_price = float(best["total_amount"]) if best else 999999
        best_type = results.get("combo_type")

        # Check flex outbound options paired with exact return
        ow_ret = results.get("return_ow")
        for date, info in results.get("flex_outbound", {}).items():
            flex_out = info.get("best")
            if not flex_out:
                continue
            out_price = float(flex_out["total_amount"])
            if ow_ret:
                combo_price = out_price + float(ow_ret["total_amount"])
                if combo_price < best_price:
                    best_price = combo_price
                    best = {"_synthetic": True, "outbound": flex_out, "return": ow_ret,
                            "outbound_date": date, "return_date": results["return_date"],
                            "total_amount": str(combo_price), "total_currency": flex_out.get("total_currency", "EUR")}
                    best_type = f"flex_outbound_{date}"

        # Check exact outbound paired with flex return
        ow_out = results.get("outbound_ow")
        for date, info in results.get("flex_return", {}).items():
            flex_ret = info.get("best")
            if not flex_ret or not ow_out:
                continue
            combo_price = float(ow_out["total_amount"]) + float(flex_ret["total_amount"])
            if combo_price < best_price:
                best_price = combo_price
                best = {"_synthetic": True, "outbound": ow_out, "return": flex_ret,
                        "outbound_date": results["departure_date"], "return_date": date,
                        "total_amount": str(combo_price), "total_currency": ow_out.get("total_currency", "EUR")}
                best_type = f"flex_return_{date}"

        # Check flex outbound paired with flex return
        for out_date, out_info in results.get("flex_outbound", {}).items():
            flex_out = out_info.get("best")
            if not flex_out:
                continue
            for ret_date, ret_info in results.get("flex_return", {}).items():
                flex_ret = ret_info.get("best")
                if not flex_ret:
                    continue
                combo_price = float(flex_out["total_amount"]) + float(flex_ret["total_amount"])
                if combo_price < best_price:
                    best_price = combo_price
                    best = {"_synthetic": True, "outbound": flex_out, "return": flex_ret,
                            "outbound_date": out_date, "return_date": ret_date,
                            "total_amount": str(combo_price), "total_currency": flex_out.get("total_currency", "EUR")}
                    best_type = f"flex_{out_date}_{ret_date}"

        return (best, best_type)


def _fmt_airport(airport: dict) -> str:
    """Format airport with code + short name. E.g., 'ORY (Paris Orly)' or 'CDG (Paris CDG)'."""
    if not airport:
        return "?"
    iata = airport.get("iata_code", "?")
    name = airport.get("name", "")
    city = airport.get("city_name", "")
    
    if not name and not city:
        return iata
    
    # Build a short display name: prefer city + airport distinction
    # Strip "Airport" suffix for brevity
    short_name = name.replace(" Airport", "").replace(" International", "").strip()
    
    if city and short_name and city.lower() not in short_name.lower():
        # City not in name — show both: "EWR (Newark, New York)"
        return f"{iata} ({short_name})"
    elif short_name:
        return f"{iata} ({short_name})"
    elif city:
        return f"{iata} ({city})"
    else:
        return iata


def _extract_route(slices: list) -> str:
    """Extract actual airport route with human-readable names.
    E.g., 'VLC (Valencia) → ORY (Paris-Orly)' or 'VLC → FRA (Frankfurt) → CDG (Paris CDG)'."""
    parts = []
    for sl in slices:
        segs = sl.get("segments", [])
        if not segs:
            continue
        
        route = []
        for i, seg in enumerate(segs):
            origin = seg.get("origin") or {}
            dest = seg.get("destination") or {}
            if i == 0:
                route.append(_fmt_airport(origin))
            route.append(_fmt_airport(dest))
        
        parts.append(" → ".join(route))
    return " | ".join(parts)


def _extract_leg_route(slices: list, leg_index: int = 0) -> str:
    """Extract route for a specific leg (slice index)."""
    if leg_index >= len(slices):
        return "?"
    sl = slices[leg_index]
    segs = sl.get("segments", [])
    if not segs:
        return "?"
    
    route = []
    for i, seg in enumerate(segs):
        origin = seg.get("origin") or {}
        dest = seg.get("destination") or {}
        if i == 0:
            route.append(_fmt_airport(origin))
        route.append(_fmt_airport(dest))
    return " → ".join(route)


def format_offer_line(offer: dict, airline_cache: AirlineCache) -> str:
    """Format a single offer for CLI display."""
    if not offer:
        return "  (no results)"
    if offer.get("_synthetic"):
        out = offer.get("outbound", {})
        ret = offer.get("return", {})
        out_iata = out.get("owner", {}).get("iata_code", "?")
        ret_iata = ret.get("owner", {}).get("iata_code", "?")
        out_label = airline_cache.get_type_label(out_iata)
        ret_label = airline_cache.get_type_label(ret_iata)
        out_name = airline_cache.get_name(out_iata)
        ret_name = airline_cache.get_name(ret_iata)
        out_direct = "direct" if _is_direct(out.get("slices", [])) else f"{_count_stops(out.get('slices', []))} stop"
        ret_direct = "direct" if _is_direct(ret.get("slices", [])) else f"{_count_stops(ret.get('slices', []))} stop"
        out_route = _extract_route(out.get("slices", []))
        ret_route = _extract_route(ret.get("slices", []))
        return (f"  Out: {out_name} [{out_label}] {out.get('total_amount')} {out.get('total_currency', '')} ({out_direct}) {out_route}\n"
                f"  Ret: {ret_name} [{ret_label}] {ret.get('total_amount')} {ret.get('total_currency', '')} ({ret_direct}) {ret_route}\n"
                f"  Combined: {offer['total_amount']} {offer.get('total_currency', '')}")

    iata = offer.get("owner", {}).get("iata_code", "?")
    name = airline_cache.get_name(iata)
    label = airline_cache.get_type_label(iata)
    price = f"{offer.get('total_amount')} {offer.get('total_currency', '')}"
    slices = offer.get("slices", [])
    direct = "direct" if _is_direct(slices) else f"{_count_stops(slices)} stop(s)"
    
    # Show per-leg durations (not summed total)
    leg_durations = []
    for sl in slices:
        segs = sl.get("segments", [])
        if segs:
            try:
                dep_dt = datetime.fromisoformat(segs[0]["departing_at"])
                arr_dt = datetime.fromisoformat(segs[-1]["arriving_at"])
                mins = int((arr_dt - dep_dt).total_seconds() / 60)
                h, m = divmod(mins, 60)
                leg_durations.append(f"{h}h{m:02d}m")
            except (KeyError, ValueError):
                leg_durations.append("?")
    
    if len(leg_durations) == 1:
        duration_str = leg_durations[0]
    elif len(leg_durations) == 2:
        duration_str = f"out {leg_durations[0]} / ret {leg_durations[1]}"
    else:
        duration_str = " + ".join(leg_durations)
    
    # Extract actual airport route
    route = _extract_route(slices)
    
    return f"  {name} [{label}] | {price} | {direct} | {duration_str} | {route}"


def print_results(results: dict, airline_cache: AirlineCache) -> None:
    """Print formatted smart search results."""
    origin = results["origin"]
    destination = results["destination"]
    dep = results["departure_date"]
    ret = results.get("return_date")

    print(f"\n{'='*70}")
    print(f"SMART SEARCH: {origin} -> {destination}")
    print(f"Dates: {dep}" + (f" / {ret}" if ret else " (one-way)"))
    print(f"{'='*70}")

    # Advisory
    advisory = results.get("advisory", {})
    if advisory and advisory.get("show_advisory"):
        print(f"\nADVISORY: {advisory['message']}")

    # Best exact-date option
    print(f"\n--- EXACT DATE RESULTS ---")
    if results.get("roundtrip"):
        rt = results["roundtrip"]
        print(f"\nBest round-trip:")
        print(format_offer_line(rt, airline_cache))

    if results.get("outbound_ow"):
        print(f"\nBest one-way outbound ({dep}):")
        print(format_offer_line(results["outbound_ow"], airline_cache))

    if results.get("return_ow"):
        print(f"\nBest one-way return ({ret}):")
        print(format_offer_line(results["return_ow"], airline_cache))

    # RT vs OW comparison
    combo = results.get("best_combo")
    combo_type = results.get("combo_type")
    if combo:
        print(f"\nBest exact-date combination ({combo_type}):")
        print(format_offer_line(combo, airline_cache))

    # Flexible results
    flex_combo = results.get("best_flex_combo")
    flex_type = results.get("flex_combo_type")
    if flex_combo and flex_type != combo_type:
        print(f"\n--- FLEXIBLE DATE RESULTS ---")
        print(f"\nBest flexible combination ({flex_type}):")
        print(format_offer_line(flex_combo, airline_cache))

    # Date matrix
    matrix = results.get("date_matrix", {})
    if matrix:
        print(f"\n--- DATE AVAILABILITY MATRIX ---")
        for date in sorted(matrix.keys()):
            info = matrix[date]
            parts = []
            if "outbound_direct" in info:
                d = "DIRECT" if info["outbound_direct"] else "connecting"
                parts.append(f"outbound: {d} ({info.get('outbound_count', 0)} offers)")
            if "return_direct" in info:
                d = "DIRECT" if info["return_direct"] else "connecting"
                parts.append(f"return: {d} ({info.get('return_count', 0)} offers)")
            print(f"  {date}: {' | '.join(parts)}")

    print(f"\n{'='*70}")
