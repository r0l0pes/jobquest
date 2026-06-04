"""Salary benchmarking lookup tool.

Provides fuzzy company name matching and city-filtered compensation data.
Works with a BYO-data JSON file (salary_data.json in PROJECT_ROOT).
If no data file exists, all operations return None silently.

Usage:
    lookup = SalaryLookup()
    result = lookup.lookup("Zalando", "Berlin")
    # Returns: {"company": "Zalando SE", "city": "Berlin", ...} or None
"""

import json
import re
from pathlib import Path
from difflib import SequenceMatcher


# Minimum similarity ratio for fuzzy matching (0.0 - 1.0)
FUZZY_THRESHOLD = 0.7

# Legal suffixes to strip when matching company names
LEGAL_SUFFIXES = [
    r"\s+(?:GmbH|SE|AG|BV|NV|Ltd|Limited|Inc|Corp|LLC|PLC|S\.A\.?|S\.p\.A\.?)$",
    r"\s+(?:GmbH & Co\. KG|GmbH & Co KG)$",
    r"\s+\([^)]*\)$",  # Parenthetical suffixes like "(Germany)"
]


class SalaryLookup:
    """Salary benchmarking lookup using a BYO-data JSON file."""

    def __init__(self, data_path: str | Path | None = None):
        """Initialize with optional custom data path.

        Args:
            data_path: Path to salary_data.json. Defaults to PROJECT_ROOT / salary_data.json.
        """
        if data_path is None:
            data_path = Path(__file__).parent.parent / "salary_data.json"
        self._data_path = Path(data_path)
        self._data = None

    def _load_data(self) -> dict | None:
        """Load salary data JSON file. Returns None if file doesn't exist."""
        if self._data is not None:
            return self._data

        if not self._data_path.exists():
            self._data = {}  # Cache empty result to avoid repeated fs checks
            return None

        try:
            with open(self._data_path, encoding="utf-8") as f:
                self._data = json.load(f)
            return self._data
        except (json.JSONDecodeError, OSError):
            return None

    def has_data(self) -> bool:
        """Check if salary data is available."""
        data = self._load_data()
        if data is None:
            return False
        companies = data.get("companies", [])
        return len(companies) > 0

    def _normalize(self, name: str) -> str:
        """Normalize a company name for matching: lowercase, strip legal suffixes."""
        name = name.strip().lower()
        for suffix_pattern in LEGAL_SUFFIXES:
            name = re.sub(suffix_pattern, "", name, flags=re.IGNORECASE)
        return name.strip()

    def _fuzzy_match(self, query_company: str, data_company: str) -> float:
        """Compute similarity ratio between two company names after normalization."""
        query_norm = self._normalize(query_company)
        data_norm = self._normalize(data_company)
        return SequenceMatcher(None, query_norm, data_norm).ratio()

    def lookup(self, company: str, city: str | None = None) -> dict | None:
        """Look up salary data for a company, optionally filtered by city.

        Args:
            company: Company name (e.g., "Zalando", "Delivery Hero SE")
            city: City name (e.g., "Berlin", "Munich"). Optional.

        Returns:
            Dict with company info + category indices, or None if not found.
        """
        data = self._load_data()
        if data is None:
            return None

        companies = data.get("companies", [])
        metadata = data.get("metadata", {})
        currency = metadata.get("currency", "EUR")
        index_label = metadata.get("index_label", "Index")
        baseline_desc = metadata.get("baseline_description", "")

        if not companies:
            return None

        # Find best fuzzy match
        best_match = None
        best_score = 0.0

        for entry in companies:
            entry_name = entry.get("company", "")
            score = self._fuzzy_match(company, entry_name)
            if score > best_score:
                best_score = score
                best_match = entry

        if best_match is None or best_score < FUZZY_THRESHOLD:
            return None

        result = {
            "company": best_match.get("company", ""),
            "matched_score": round(best_score, 2),
            "matched_query": company,
            "currency": currency,
            "index_label": index_label,
            "baseline_description": baseline_desc,
        }

        # City filter: if city is provided, only return if it matches
        categories = best_match.get("categories", {})
        entry_city = best_match.get("city", "")

        if city:
            city_match = self._fuzzy_match(city, entry_city) >= FUZZY_THRESHOLD
            if not city_match:
                return None  # City mismatch

        result["city"] = entry_city
        result["categories"] = categories

        return result

    def list_all(self) -> list[dict]:
        """Return all available salary entries (for debugging)."""
        data = self._load_data()
        if data is None:
            return []
        return data.get("companies", [])


def main():
    """Quick CLI test: look up a company name passed as argument."""
    import sys
    lookup = SalaryLookup()
    if len(sys.argv) < 2:
        print(f"Usage: python {sys.argv[0]} <company> [city]")
        print("Available entries:")
        for entry in lookup.list_all():
            print(f"  - {entry.get('company')} / {entry.get('city')}")
        return

    company = sys.argv[1]
    city = sys.argv[2] if len(sys.argv) > 2 else None
    result = lookup.lookup(company, city)
    if result:
        print(f"\nMatch found for '{company}'" + (f" in {city}" if city else "") + ":")
        print(f"  Company: {result['company']} (score: {result['matched_score']})")
        print(f"  Currency: {result['currency']}")
        print(f"  Categories:")
        for cat_name, cat_data in result.get("categories", {}).items():
            print(f"    {cat_name}: count={cat_data.get('count', '?')}, index={cat_data.get('index', '?')}")
    else:
        print(f"\nNo match found for '{company}'" + (f" in {city}" if city else "") + ".")


if __name__ == "__main__":
    main()
