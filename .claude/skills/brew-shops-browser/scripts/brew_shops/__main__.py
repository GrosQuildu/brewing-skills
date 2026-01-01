"""CLI for Brew Shops Browser."""

import sys
import json
from urllib.parse import quote

from .base import needs_verification
from .shops import (
    HomebeerParser,
    HomebrewingParser,
    SwiatSloduParser,
    BrowamatorParser,
    BrowarBizParser,
)


PARSERS = {
    "homebeer": HomebeerParser,
    "homebrewing": HomebrewingParser,
    "swiatslodu": SwiatSloduParser,
    "browamator": BrowamatorParser,
    "browarbiz": BrowarBizParser,
}


def print_item_info(info):
    """Print item info as JSON."""
    if info is None:
        print("Failed to parse item info")
        return

    # Check if verification is needed
    verify_needed, verify_reasons = needs_verification(info)

    output = {
        "name": info.name,
        "price": info.price,
        "availability": info.availability,
        "quantity": info.quantity,
        "description": info.description,
        "url": info.url,
        "needs_verification": verify_needed,
        "verification_reasons": verify_reasons if verify_needed else None,
        "raw_data": None,
    }

    if info.raw_data:
        output["raw_data"] = {
            "availability_text": info.raw_data.availability_text,
            "main_content": info.raw_data.main_content,
            "meta_description": info.raw_data.meta_description,
            "page_title": info.raw_data.page_title,
        }

    print(json.dumps(output, indent=2, ensure_ascii=False))


def detect_shop(url: str) -> str:
    """Detect which shop a URL belongs to."""
    url_lower = url.lower()
    if "homebeer.pl" in url_lower:
        return "homebeer"
    elif "homebrewing.pl" in url_lower:
        return "homebrewing"
    elif "swiatslodu.pl" in url_lower:
        return "swiatslodu"
    elif "browamator.pl" in url_lower:
        return "browamator"
    elif "browar.biz" in url_lower:
        return "browarbiz"
    return ""


def cmd_info(url: str):
    """Get info about a product from its URL."""
    shop_name = detect_shop(url)
    if not shop_name:
        print(f"Unknown shop for URL: {url}")
        print(f"Supported shops: {', '.join(PARSERS.keys())}")
        sys.exit(1)

    parser = PARSERS[shop_name]()
    print(f"Using parser: {parser.SHOP_NAME}")
    print("-" * 40)
    info = parser.get_item_info(url)
    print_item_info(info)


def cmd_search(shop_name: str, query: str):
    """Search for products in a shop."""
    if shop_name not in PARSERS:
        print(f"Unknown shop: {shop_name}")
        print(f"Supported shops: {', '.join(PARSERS.keys())}")
        sys.exit(1)

    parser = PARSERS[shop_name]()
    print(f"Searching {parser.SHOP_NAME} for: {query}")
    print("-" * 40)

    results = parser.search(query)
    if not results:
        print("No results found")
        return

    print(f"Found {len(results)} results:")
    for i, url in enumerate(results, 1):
        print(f"  {i}. {url}")


def cmd_test(args: list[str]):
    """Run semi-automated tests."""
    from .tests import run_all_tests, run_shop_test, PARSERS as TEST_PARSERS

    if not args:
        # Run all tests (full mode)
        run_all_tests(quick=False)
    elif args[0] == "quick":
        # Run quick tests (1 item per shop)
        run_all_tests(quick=True)
    elif args[0] in TEST_PARSERS:
        # Run tests for specific shop
        quick = len(args) > 1 and args[1] == "quick"
        run_shop_test(args[0], quick=quick)
    else:
        print(f"Unknown test option: {args[0]}")
        print("Usage:")
        print("  python -m brew_shops test              # All tests (full)")
        print("  python -m brew_shops test quick        # All tests (quick - 1 item per shop)")
        print("  python -m brew_shops test <shop>       # Test specific shop")
        print("  python -m brew_shops test <shop> quick # Test specific shop (quick)")
        print(f"\nAvailable shops: {', '.join(TEST_PARSERS.keys())}")
        sys.exit(1)


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python -m brew_shops info <url>")
        print("  python -m brew_shops search <shop> <query>")
        print("  python -m brew_shops test [quick|<shop>]")
        print()
        print(f"Supported shops: {', '.join(PARSERS.keys())}")
        sys.exit(1)

    command = sys.argv[1]

    if command == "info":
        if len(sys.argv) < 3:
            print("Usage: python -m brew_shops info <url>")
            sys.exit(1)
        cmd_info(sys.argv[2])

    elif command == "search":
        if len(sys.argv) < 4:
            print("Usage: python -m brew_shops search <shop> <query>")
            sys.exit(1)
        cmd_search(sys.argv[2], sys.argv[3])

    elif command == "test":
        cmd_test(sys.argv[2:])

    else:
        print(f"Unknown command: {command}")
        print("Commands: info, search, test")
        sys.exit(1)


if __name__ == "__main__":
    main()
