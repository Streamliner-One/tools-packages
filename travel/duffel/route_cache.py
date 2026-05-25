#!/usr/bin/env python3
"""
Route Intelligence Cache v2
Hybrid approach: OpenFlights (world truth) + Duffel (inventory truth)
Cache is advisory hints only, never filters results.

Data source: https://github.com/jpatokal/openflights/master/data/routes.dat
Format: AirlineIATA,AirlineID,OriginIATA,OriginID,DestIATA,DestID,Codeshare,Stops,Equipment
"""

import os
import json
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

# Configuration
OPENFLIGHTS_ROUTES_URL = "https://raw.githubusercontent.com/jpatokal/openflights/master/data/routes.dat"
CACHE_FILE = Path(__file__).parent / "route_cache.json"
CACHE_TTL_DAYS = 30  # Duffel-learned data expires after 30 days

# Common airline IATA codes to names mapping
AIRLINE_NAMES = {
    "VY": "Vueling",
    "AZ": "ITA Airways",
    "BA": "British Airways",
    "AA": "American Airlines",
    "LH": "Lufthansa",
    "AF": "Air France",
    "KL": "KLM",
    "IB": "Iberia",
    "FR": "Ryanair",
    "U2": "easyJet",
    "LX": "SWISS",
    "OS": "Austrian Airlines",
    "SN": "Brussels Airlines",
    "TP": "TAP Air Portugal",
    "SK": "SAS",
    "AY": "Finnair",
    "DL": "Delta Air Lines",
    "UA": "United Airlines",
    "VS": "Virgin Atlantic",
    "EK": "Emirates",
    "QR": "Qatar Airways",
    "EY": "Etihad Airways",
    "TK": "Turkish Airlines",
    "SU": "Aeroflot",
    "LO": "LOT Polish Airlines",
    "OK": "Czech Airlines",
    "A3": "Aegean Airlines",
    "EN": "Air Dolomiti",
    "W6": "Wizz Air",
    "HV": "Transavia",
    "V7": "Volotea",
    "UX": "Air Europa",
    "I2": "Iberia Express",
    "NT": "Binter Canarias",
    "YW": "Air Nostrum",
    "X3": "TUI fly",
    "DE": "Condor",
    "4U": "Germanwings",
    "EW": "Eurowings",
}


class RouteCache:
    """
    Manages route intelligence cache with TWO separate truth sources:
    
    1. world.* — OpenFlights data (immutable, refreshed monthly)
       - has_direct: True/False (does direct exist in real world?)
       - airlines: list of IATA codes (which airlines fly direct)
    
    2. duffel.* — Learned from Duffel searches (mutable, 30d TTL)
       - has_direct: True/False (did Duffel show directs last time?)
       - airlines: list of IATA codes (which airlines Duffel showed)
       - last_seen: ISO timestamp (when did we last search this route?)
    
    Advisory logic:
    - If world.has_direct=True but duffel.has_direct=False → warn user
    - Cache is hints only, never filters Duffel results
    """
    
    def __init__(self):
        self.cache_file = CACHE_FILE
        self.routes = {}  # {route_key: {"world": {...}, "duffel": {...}}}
        self.load()
    
    def load(self):
        """Load cache from disk"""
        if self.cache_file.exists():
            with open(self.cache_file) as f:
                data = json.load(f)
                self.routes = data.get("routes", {})
                print(f"✓ Loaded route cache: {len(self.routes)} routes")
        else:
            print("⚠️  No route cache found — will build on first download")
    
    def save(self):
        """Save cache to disk"""
        data = {
            "routes": self.routes,
            "last_updated": self._get_timestamp()
        }
        with open(self.cache_file, "w") as f:
            json.dump(data, f, indent=2)
        print(f"✓ Saved route cache: {len(self.routes)} routes")
    
    def _get_timestamp(self):
        return datetime.now().isoformat()
    
    def _is_duffel_expired(self, route_data: dict) -> bool:
        """Check if Duffel-learned data is expired (older than TTL)"""
        duffel = route_data.get("duffel", {})
        if not duffel or "last_seen" not in duffel:
            return True
        
        try:
            last_seen = datetime.fromisoformat(duffel["last_seen"])
            age = datetime.now() - last_seen
            return age.days > CACHE_TTL_DAYS
        except:
            return True
    
    def _airline_names(self, iata_codes: list) -> list:
        """Convert IATA codes to airline names"""
        names = []
        for code in iata_codes:
            name = AIRLINE_NAMES.get(code, code)  # Fallback to code if unknown
            names.append(name)
        return names
    
    def download_openflights(self):
        """Download and parse OpenFlights routes.dat — populates world.* data only"""
        print(f"📥 Downloading OpenFlights routes from {OPENFLIGHTS_ROUTES_URL}...")
        
        try:
            with urllib.request.urlopen(OPENFLIGHTS_ROUTES_URL, timeout=30) as response:
                lines = response.read().decode('utf-8').splitlines()
        except Exception as e:
            print(f"❌ Failed to download: {e}")
            return False
        
        print(f"✓ Downloaded {len(lines)} route entries")
        
        # Parse routes — populate world.* data
        direct_count = 0
        for line in lines:
            parts = line.split(',')
            if len(parts) < 8:
                continue
            
            airline_iata = parts[0]
            origin_iata = parts[2]
            dest_iata = parts[4]
            codeshare = parts[6]
            stops = parts[7]
            
            # Only direct flights (stops == "0"), skip codeshares
            if stops.strip() == "0" and origin_iata and dest_iata and not codeshare.strip():
                route_key = f"{origin_iata}-{dest_iata}"
                
                if route_key not in self.routes:
                    self.routes[route_key] = {
                        "world": {"has_direct": True, "airlines": []},
                        "duffel": {}
                    }
                
                # Add airline to world data (OpenFlights is authoritative)
                world = self.routes[route_key]["world"]
                if airline_iata and airline_iata not in world["airlines"]:
                    world["airlines"].append(airline_iata)
                    world["has_direct"] = True
                
                direct_count += 1
        
        print(f"✓ Parsed {direct_count} direct routes")
        self.save()
        return True
    
    def has_direct_world(self, origin: str, dest: str) -> bool:
        """Check if direct route exists in real world (OpenFlights)"""
        route_key = f"{origin}-{dest}"
        if route_key not in self.routes:
            return False
        return self.routes[route_key].get("world", {}).get("has_direct", False)
    
    def get_world_airlines(self, origin: str, dest: str) -> list:
        """Get airlines that operate direct route (OpenFlights)"""
        route_key = f"{origin}-{dest}"
        if route_key not in self.routes:
            return []
        return self.routes[route_key].get("world", {}).get("airlines", [])
    
    def has_direct_duffel(self, origin: str, dest: str) -> bool:
        """Check if Duffel showed directs last time we searched"""
        route_key = f"{origin}-{dest}"
        if route_key not in self.routes:
            return False
        
        route_data = self.routes[route_key]
        
        # Check if Duffel data is expired
        if self._is_duffel_expired(route_data):
            return False
        
        return route_data.get("duffel", {}).get("has_direct", False)
    
    def get_duffel_airlines(self, origin: str, dest: str) -> list:
        """Get airlines Duffel showed last time (if not expired)"""
        route_key = f"{origin}-{dest}"
        if route_key not in self.routes:
            return []
        
        route_data = self.routes[route_key]
        if self._is_duffel_expired(route_data):
            return []
        
        return route_data.get("duffel", {}).get("airlines", [])
    
    def cache_from_search(self, origin: str, dest: str, offers: list):
        """
        Cache Duffel search results — updates duffel.* data only.
        Never modifies world.* data (OpenFlights is authoritative).
        """
        if not offers:
            return
        
        route_key = f"{origin}-{dest}"
        
        # Analyze offers to see what Duffel showed
        duffel_has_direct = False
        duffel_airlines = set()
        
        for offer in offers:
            slices = offer.get("slices", [])
            if not slices:
                continue
            
            # Check if outbound has only 1 segment = direct
            outbound = slices[0]
            segments = outbound.get("segments", [])
            
            if len(segments) == 1:
                duffel_has_direct = True
                airline = segments[0].get("operating_carrier", {}).get("iata_code")
                if airline:
                    duffel_airlines.add(airline)
        
        # Initialize route if needed
        if route_key not in self.routes:
            self.routes[route_key] = {
                "world": {"has_direct": False, "airlines": []},
                "duffel": {}
            }
        
        # Update Duffel data only
        self.routes[route_key]["duffel"] = {
            "has_direct": duffel_has_direct,
            "airlines": list(duffel_airlines),
            "last_seen": self._get_timestamp()
        }
        
        self.save()
        
        direct_text = "has direct" if duffel_has_direct else "no direct"
        print(f"✓ Cached Duffel result for {origin}-{dest}: {direct_text}, {len(duffel_airlines)} airlines")
    
    def get_advisory(self, origin: str, dest: str) -> dict:
        """
        Get advisory message for route.
        
        Returns dict with:
        - show_advisory: True/False
        - message: Advisory text (if show_advisory=True)
        - world_airlines: Airlines from OpenFlights
        - duffel_airlines: Airlines from Duffel
        """
        route_key = f"{origin}-{dest}"
        
        world_has_direct = self.has_direct_world(origin, dest)
        world_airlines = self.get_world_airlines(origin, dest)
        duffel_has_direct = self.has_direct_duffel(origin, dest)
        duffel_airlines = self.get_duffel_airlines(origin, dest)
        
        # Advisory: world says direct exists, but Duffel didn't show it
        if world_has_direct and not duffel_has_direct:
            # Convert IATA codes to airline names for human-friendly message
            world_airline_names = self._airline_names(world_airlines)
            return {
                "show_advisory": True,
                "message": f"Direct flights may be available (not via Duffel). Check: {', '.join(world_airline_names)}",
                "world_airlines": world_airlines,
                "world_airline_names": world_airline_names,
                "duffel_airlines": duffel_airlines,
                "reason": "world_has_direct_but_duffel_doesnt"
            }
        
        # No advisory needed
        return {
            "show_advisory": False,
            "message": None,
            "world_airlines": world_airlines,
            "duffel_airlines": duffel_airlines,
            "reason": "no_conflict"
        }


# CLI usage
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Route Intelligence Cache Manager v2")
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # Download command
    download_parser = subparsers.add_parser("download", help="Download OpenFlights routes")
    
    # Check command
    check_parser = subparsers.add_parser("check", help="Check route intelligence")
    check_parser.add_argument("origin", help="Origin IATA code")
    check_parser.add_argument("dest", help="Destination IATA code")
    
    # Advisory command
    advisory_parser = subparsers.add_parser("advisory", help="Get advisory for route")
    advisory_parser.add_argument("origin", help="Origin IATA code")
    advisory_parser.add_argument("dest", help="Destination IATA code")
    
    # Stats command
    stats_parser = subparsers.add_parser("stats", help="Show cache statistics")
    
    args = parser.parse_args()
    
    cache = RouteCache()
    
    if args.command == "download":
        cache.download_openflights()
    elif args.command == "check":
        route_key = f"{args.origin}-{args.dest}"
        if route_key not in cache.routes:
            print(f"\nRoute: {args.origin} → {args.dest}")
            print("Not in cache")
        else:
            route_data = cache.routes[route_key]
            world = route_data.get("world", {})
            duffel = route_data.get("duffel", {})
            
            print(f"\nRoute: {args.origin} → {args.dest}")
            print(f"\nWorld (OpenFlights):")
            print(f"  Has direct: {world.get('has_direct', False)}")
            print(f"  Airlines: {', '.join(world.get('airlines', [])) or 'None'}")
            
            if duffel:
                print(f"\nDuffel (learned):")
                print(f"  Has direct: {duffel.get('has_direct', False)}")
                print(f"  Airlines: {', '.join(duffel.get('airlines', [])) or 'None'}")
                print(f"  Last seen: {duffel.get('last_seen', 'Unknown')}")
                if cache._is_duffel_expired(route_data):
                    print(f"  ⚠️  EXPIRED (older than {CACHE_TTL_DAYS} days)")
            else:
                print(f"\nDuffel (learned): No data yet")
    elif args.command == "advisory":
        advisory = cache.get_advisory(args.origin, args.dest)
        print(f"\nRoute: {args.origin} → {args.dest}")
        print(f"\nAdvisory: {'YES' if advisory['show_advisory'] else 'No'}")
        if advisory['show_advisory']:
            print(f"Message: {advisory['message']}")
        print(f"\nWorld airlines: {', '.join(advisory['world_airlines']) or 'None'}")
        print(f"Duffel airlines: {', '.join(advisory['duffel_airlines']) or 'None'}")
    elif args.command == "stats":
        print(f"\nRoute Cache Statistics:")
        print(f"  Total routes: {len(cache.routes)}")
        print(f"  Cache file: {cache.cache_file}")
        if cache.cache_file.exists():
            size_mb = cache.cache_file.stat().st_size / 1024 / 1024
            print(f"  File size: {size_mb:.2f} MB")
        
        # Count conflicts
        conflicts = sum(1 for r in cache.routes.values() 
                       if r.get("world", {}).get("has_direct") and 
                          not r.get("duffel", {}).get("has_direct"))
        print(f"  Routes with advisory (world≠duffel): {conflicts}")
    else:
        parser.print_help()
