#!/usr/bin/env python3
"""
Airline Classification Cache
Classifies airlines as legacy/lcc/hybrid to inform search strategy.
Learns unknown airlines from Duffel offer data automatically.
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

CACHE_FILE = Path(__file__).parent / "airlines.json"

# Types: legacy (round-trip usually cheaper), lcc (one-ways fine), hybrid (varies)
VALID_TYPES = {"legacy", "lcc", "hybrid"}


class AirlineCache:
    """Airline classification cache with auto-learning from Duffel offers."""

    def __init__(self):
        self.cache_file = CACHE_FILE
        self.airlines: dict = {}  # iata -> {name, type}
        self.learned: dict = {}   # iata -> {name, type, first_seen, source}
        self.load()

    def load(self) -> None:
        """Load airline data from disk."""
        if not self.cache_file.exists():
            print("WARNING: airlines.json not found, using empty cache", file=sys.stderr)
            return

        with open(self.cache_file, encoding="utf-8") as f:
            data = json.load(f)

        self.airlines = data.get("airlines", {})
        self.learned = data.get("learned", {})
        total = len(self.airlines) + len(self.learned)
        print(f"Loaded airline cache: {len(self.airlines)} known + {len(self.learned)} learned = {total} total", file=sys.stderr)

    def save(self) -> None:
        """Persist cache to disk."""
        data = {
            "airlines": self.airlines,
            "learned": self.learned,
            "last_updated": datetime.now().isoformat()
        }
        with open(self.cache_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def classify(self, iata_code: str) -> str:
        """
        Get airline type by IATA code.

        Returns: 'legacy', 'lcc', 'hybrid', or 'unknown'
        """
        if not iata_code:
            return "unknown"

        # Check hardcoded first
        if iata_code in self.airlines:
            return self.airlines[iata_code].get("type", "unknown")

        # Check learned
        if iata_code in self.learned:
            return self.learned[iata_code].get("type", "unknown")

        return "unknown"

    def get_name(self, iata_code: str) -> str:
        """Get airline name by IATA code."""
        if iata_code in self.airlines:
            return self.airlines[iata_code].get("name", iata_code)
        if iata_code in self.learned:
            return self.learned[iata_code].get("name", iata_code)
        return iata_code

    def is_legacy(self, iata_code: str) -> bool:
        return self.classify(iata_code) == "legacy"

    def is_lcc(self, iata_code: str) -> bool:
        return self.classify(iata_code) == "lcc"

    def prefers_roundtrip(self, iata_code: str) -> bool:
        """Legacy carriers typically price round-trips cheaper than 2x one-way."""
        return self.classify(iata_code) in ("legacy", "hybrid")

    def learn_from_offers(self, offers: list) -> list:
        """
        Extract airline info from Duffel offers and learn unknown carriers.

        Looks at owner.iata_code + owner.name on each offer.
        Returns list of newly learned IATA codes.
        """
        new_airlines = []

        for offer in offers:
            owner = offer.get("owner", {})
            iata = owner.get("iata_code")
            name = owner.get("name")

            if not iata:
                continue

            # Already known
            if iata in self.airlines or iata in self.learned:
                continue

            # New airline — default to hybrid (safest assumption)
            self.learned[iata] = {
                "name": name or iata,
                "type": "hybrid",
                "first_seen": datetime.now().isoformat(),
                "source": "duffel_offer"
            }
            new_airlines.append(iata)
            print(f"Learned new airline: {iata} ({name}) — classified as hybrid", file=sys.stderr)

        if new_airlines:
            self.save()

        return new_airlines

    def get_type_label(self, iata_code: str) -> str:
        """Human-readable label for display."""
        atype = self.classify(iata_code)
        labels = {
            "legacy": "Legacy",
            "lcc": "LCC",
            "hybrid": "Hybrid",
            "unknown": "?"
        }
        return labels.get(atype, "?")

    def all_airlines(self) -> dict:
        """Merge known + learned airlines."""
        merged = {}
        for iata, info in self.airlines.items():
            merged[iata] = info
        for iata, info in self.learned.items():
            if iata not in merged:
                merged[iata] = info
        return merged


if __name__ == "__main__":
    cache = AirlineCache()

    if len(sys.argv) > 1:
        code = sys.argv[1].upper()
        atype = cache.classify(code)
        name = cache.get_name(code)
        print(f"{code}: {name} ({atype})")
        print(f"  Prefers round-trip: {cache.prefers_roundtrip(code)}")
    else:
        print(f"\nAirline Cache Summary:")
        print(f"  Known airlines: {len(cache.airlines)}")
        print(f"  Learned airlines: {len(cache.learned)}")
        for atype in ["legacy", "lcc", "hybrid"]:
            codes = [k for k, v in cache.airlines.items() if v.get("type") == atype]
            print(f"  {atype}: {', '.join(sorted(codes))}")
