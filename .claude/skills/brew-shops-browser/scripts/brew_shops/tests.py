"""Semi-automated tests for brew shop parsers.

These tests fetch real data from shops and display results for manual review.

Run with:
  python -m brew_shops test              # Run all tests
  python -m brew_shops test quick        # Run quick tests (1 item per shop)
  python -m brew_shops test <shop_name>  # Run tests for specific shop
"""

from dataclasses import asdict
import json
from typing import Optional

from .base import ItemInfo
from .shops import (
    HomebeerParser,
    HomebrewingParser,
    SwiatSloduParser,
    BrowamatorParser,
    BrowarBizParser,
)


# Test URLs with expected values for validation
# Format: (url, expected_name_contains, expected_price_range, expected_availability)
# NOTE: URLs may become outdated as shops change their inventory

TEST_ITEMS = {
    "homebeer": [
        (
            "https://homebeer.pl/pl/p/Chmiel-Citra-USA-granulat/288",
            "Citra",
            (20, 100),  # price range PLN
            None,  # any availability
        ),
        (
            "https://homebeer.pl/pl/p/Drozdze-do-piwa-domowego-Fermentis-BE-256-Abbaye/179",
            "Fermentis",
            (10, 50),
            None,
        ),
        (
            "https://homebeer.pl/pl/p/WES-piwo-domowe-bursztynowe-PIWES-04-1%2C7kg/843",
            "WES",
            (30, 100),
            None,
        ),
        (
            "https://homebeer.pl/pl/p/Chmiel-Ksiazecy-granulat/1801",
            "Książęcy",
            (5, 50),
            None,
        ),
    ],
    "homebrewing": [
        # Test for the price parsing fix - should get main price, not shipping
        (
            "https://homebrewing.pl/chmiel-perle-100-g-p-90.html",
            "Perle",
            (10, 40),  # main price, not shipping (15.95)
            None,
        ),
        (
            "https://homebrewing.pl/chmiel-perle-50-g-p-92.html",
            "Perle",
            (5, 30),
            None,
        ),
        (
            "https://homebrewing.pl/chmiel-magnum-100g-polishhops-p-127.html",
            "Magnum",
            (10, 50),
            None,
        ),
        (
            "https://homebrewing.pl/chmiel-hallertauer-tradition-100-g-polishhops-p-77.html",
            "Hallertauer",
            (10, 50),
            None,
        ),
    ],
    "swiatslodu": [
        (
            "https://www.swiatslodu.pl/Slod-PILZNENSKI-5kg-Viking-Malt",
            "Pilzneński",
            (30, 80),
            None,
        ),
        (
            "https://www.swiatslodu.pl/slod-karmelowy-100ebc-1kg",
            "Karmelowy",
            (10, 40),
            None,
        ),
        (
            "https://www.swiatslodu.pl/slod-czekoladowy-800-ebc-viking-malt",
            "Czekoladowy",
            (10, 50),
            None,
        ),
        (
            "https://www.swiatslodu.pl/Slod-PALE-ALE-5kg-Viking-Malt",
            "Pale Ale",
            (30, 80),
            None,
        ),
    ],
    "browamator": [
        (
            "https://browamator.pl/chmiel-mosaic-usa-50-g-granulat/3-56-392",
            "Mosaic",
            (10, 40),
            None,
        ),
        (
            "https://browamator.pl/chmiel-centennial-usa-50-g-granulat/3-220-388",
            "Centennial",
            (10, 40),
            None,
        ),
        (
            "https://browamator.pl/chmiel-simcoe-usa-50-g-granulat/3-64-400",
            "Simcoe",
            (10, 40),
            None,
        ),
        (
            "https://browamator.pl/chmiel-sabro-usa-50-g-granulat/3-56-393",
            "Sabro",
            (10, 50),
            None,
        ),
    ],
    "browarbiz": [
        # Test for "na wyczerpaniu" availability detection
        (
            "https://www.browar.biz/centrumpiwowarstwa/chmiele/granulat/citra-us-2021-100-g",
            "Citra",
            (20, 40),  # should be ~27, not shipping price (13.79)
            "low_stock",  # "produkt na wyczerpaniu"
        ),
        # Test for thousand-separator price parsing (2 897,99)
        (
            "https://www.browar.biz/centrumpiwowarstwa/sprzet_zaawansowany/brew-monk-b50-wi-fi-brewing-system",
            "Brew Monk",
            (2500, 3500),  # ~2897 PLN, not 69.99 from related products
            "in_stock",
        ),
        (
            "https://www.browar.biz/centrumpiwowarstwa/chmiele/granulat/citra-us-2024-50-g",
            "Citra",
            (15, 35),
            None,
        ),
        (
            "https://www.browar.biz/centrumpiwowarstwa/drozdze/gorna_fermentacja/lallemand-lalbrew-verdant-ipa-11-g",
            "Verdant",
            (15, 40),
            None,
        ),
    ],
}

# Search queries for each shop
TEST_SEARCH_QUERIES = {
    "homebeer": ["Citra", "słód pilzneński", "Safale US-05", "Mosaic"],
    "homebrewing": ["Citra", "pilzneński", "US-05", "chmiel"],
    "swiatslodu": ["pilzneński", "monachijski", "karmelowy", "Weyermann"],
    "browamator": ["Citra", "słód", "drożdże", "chmiel granulat"],
    "browarbiz": ["Citra", "pilzneński", "Fermentis", "słód jasny"],
}

PARSERS = {
    "homebeer": HomebeerParser,
    "homebrewing": HomebrewingParser,
    "swiatslodu": SwiatSloduParser,
    "browamator": BrowamatorParser,
    "browarbiz": BrowarBizParser,
}


def validate_result(
    info: Optional[ItemInfo],
    expected_name: str,
    price_range: tuple,
    expected_availability: Optional[str],
) -> tuple[bool, list[str]]:
    """Validate item info against expected values. Returns (valid, warnings)."""
    warnings = []

    if info is None:
        return False, ["No data retrieved"]

    if not info.name:
        return False, ["Name is empty"]

    # Check name contains expected string
    if expected_name.lower() not in info.name.lower():
        warnings.append(f"Name doesn't contain '{expected_name}'")

    # Check price range
    if info.price is None:
        warnings.append("Price is None")
    elif not (price_range[0] <= info.price <= price_range[1]):
        warnings.append(
            f"Price {info.price} outside expected range {price_range}"
        )

    # Check availability if specified
    if expected_availability and info.availability != expected_availability:
        warnings.append(
            f"Availability '{info.availability}' != expected '{expected_availability}'"
        )

    return len(warnings) == 0, warnings


def format_item_info(info: Optional[ItemInfo]) -> str:
    """Format ItemInfo for display."""
    if info is None:
        return "  ERROR: Failed to parse item info (returned None)"

    lines = [
        f"  Name: {info.name}",
        f"  Price: {info.price} PLN" if info.price else "  Price: N/A",
        f"  Availability: {info.availability}",
        f"  Quantity: {info.quantity or 'N/A'}",
    ]

    if info.description:
        desc = info.description[:150] + "..." if len(info.description) > 150 else info.description
        lines.append(f"  Description: {desc}")
    else:
        lines.append("  Description: N/A")

    return "\n".join(lines)


def test_item_info(shop_name: str, items: list, quick: bool = False) -> tuple[int, int, int]:
    """Test get_item_info for a shop. Returns (passed, warnings, failed) count."""
    parser = PARSERS[shop_name]()
    print(f"\n{'='*60}")
    print(f"ITEM INFO TESTS: {parser.SHOP_NAME}")
    print(f"{'='*60}")

    passed = 0
    with_warnings = 0
    failed = 0

    test_items = items[:1] if quick else items

    for i, (url, expected_name, price_range, expected_avail) in enumerate(test_items, 1):
        print(f"\n[Test {i}/{len(test_items)}] URL: {url}")
        print(f"  Expected: name contains '{expected_name}', price in {price_range}")
        if expected_avail:
            print(f"  Expected availability: {expected_avail}")
        print("-" * 50)

        try:
            info = parser.get_item_info(url)
            print(format_item_info(info))

            valid, warnings = validate_result(info, expected_name, price_range, expected_avail)

            if valid:
                passed += 1
                print("  >>> STATUS: PASS")
            elif warnings and info and info.name:
                with_warnings += 1
                print(f"  >>> STATUS: PASS with warnings:")
                for w in warnings:
                    print(f"      - {w}")
            else:
                failed += 1
                print(f"  >>> STATUS: FAIL")
                for w in warnings:
                    print(f"      - {w}")
        except Exception as e:
            failed += 1
            print(f"  >>> STATUS: ERROR - {e}")

    return passed, with_warnings, failed


def test_search(shop_name: str, queries: list[str], quick: bool = False) -> tuple[int, int, int]:
    """Test search for a shop. Returns (passed, warnings, failed) count."""
    parser = PARSERS[shop_name]()
    print(f"\n{'='*60}")
    print(f"SEARCH TESTS: {parser.SHOP_NAME}")
    print(f"{'='*60}")

    passed = 0
    with_warnings = 0
    failed = 0

    test_queries = queries[:1] if quick else queries

    for i, query in enumerate(test_queries, 1):
        print(f"\n[Test {i}/{len(test_queries)}] Query: '{query}'")
        print("-" * 50)

        try:
            results = parser.search(query)

            if results and len(results) >= 1:
                passed += 1
                print(f"  Found {len(results)} results:")
                for j, url in enumerate(results[:5], 1):  # Show first 5
                    print(f"    {j}. {url}")
                if len(results) > 5:
                    print(f"    ... and {len(results) - 5} more")
                print("  >>> STATUS: PASS")
            elif results:
                with_warnings += 1
                print(f"  Found only {len(results)} result(s)")
                for url in results:
                    print(f"    - {url}")
                print("  >>> STATUS: PASS (few results)")
            else:
                failed += 1
                print("  >>> STATUS: FAIL - No results found")
        except Exception as e:
            failed += 1
            print(f"  >>> STATUS: ERROR - {e}")

    return passed, with_warnings, failed


def run_all_tests(quick: bool = False):
    """Run all semi-automated tests."""
    mode = "QUICK" if quick else "FULL"
    print("=" * 60)
    print(f"BREW SHOPS BROWSER - SEMI-AUTOMATED TESTS ({mode})")
    print("=" * 60)
    print("\nThese tests fetch real data from shops.")
    print("Review the output to verify correctness.")
    print("\nNOTE: URLs may become outdated as shop inventory changes.")
    print("If a test fails, try visiting the URL to check if it still exists.\n")

    total_passed = 0
    total_warnings = 0
    total_failed = 0

    for shop_name in PARSERS.keys():
        # Test item info
        items = TEST_ITEMS.get(shop_name, [])
        if items:
            p, w, f = test_item_info(shop_name, items, quick)
            total_passed += p
            total_warnings += w
            total_failed += f

        # Test search
        queries = TEST_SEARCH_QUERIES.get(shop_name, [])
        if queries:
            p, w, f = test_search(shop_name, queries, quick)
            total_passed += p
            total_warnings += w
            total_failed += f

    # Summary
    print(f"\n{'='*60}")
    print("TEST SUMMARY")
    print(f"{'='*60}")
    total = total_passed + total_warnings + total_failed
    print(f"Total tests: {total}")
    print(f"  PASS:     {total_passed}")
    print(f"  WARNINGS: {total_warnings}")
    print(f"  FAIL:     {total_failed}")

    if total_failed == 0:
        print("\n✓ All tests passed!")
    else:
        print(f"\n✗ {total_failed} test(s) failed - review output above")


def run_shop_test(shop_name: str, quick: bool = False):
    """Run tests for a specific shop."""
    if shop_name not in PARSERS:
        print(f"Unknown shop: {shop_name}")
        print(f"Available: {', '.join(PARSERS.keys())}")
        return

    print(f"Testing {shop_name}...")

    items = TEST_ITEMS.get(shop_name, [])
    if items:
        test_item_info(shop_name, items, quick)

    queries = TEST_SEARCH_QUERIES.get(shop_name, [])
    if queries:
        test_search(shop_name, queries, quick)


if __name__ == "__main__":
    run_all_tests()
