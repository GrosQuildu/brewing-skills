"""Shop parser for browar.biz (Centrum Piwowarstwa - Malt Specialist)."""

import re
from typing import Optional
from urllib.parse import quote, urljoin

import requests
from bs4 import BeautifulSoup

from ..base import ShopParser, ItemInfo


class BrowarBizParser(ShopParser):
    """Parser for browar.biz shop.

    Page structure:
    - <banner>: Top header with logo, search
    - <navigation>: Main navigation menu
    - <main>: Main content area containing:
      - Product info section (left side)
      - <complementary>: Right sidebar with account options, category menu
    - <contentinfo>: Footer with shipping info

    Main content notes:
    - The <main> tag contains both product and sidebar
    - Need to exclude <complementary> element (category sidebar)
    - Footer shows shipping costs that should not be confused with product price
    """

    SHOP_NAME = "Browar.biz (Centrum Piwowarstwa)"
    BASE_URL = "https://www.browar.biz"
    SHOP_SECTION = "/centrumpiwowarstwa/"

    # Shop-specific selectors - exclude complementary sidebar inside main
    REMOVE_SELECTORS = [
        # Structural elements
        "nav", "header", "footer", "aside",
        "[role='navigation']", "[role='banner']", "[role='contentinfo']",
        "[role='complementary']",
        # Complementary sidebar in browar.biz is inside <main>
        "complementary",
        # Common patterns
        ".nav", ".menu", ".header", ".footer", ".sidebar",
        "#nav", "#menu", "#header", "#footer", "#sidebar",
        ".navigation", ".top-bar", ".top-menu", ".bottom-bar",
        ".category-menu", ".categories", ".newsletter", ".cookie",
        ".bestsellers", ".recommended", ".recently-viewed",
        ".polecane", ".bestsellery", ".ostatnio-ogladane",
    ]

    def _is_shop_url(self, url: str) -> bool:
        """Check if URL is a shop page (not forum or other section)."""
        return self.SHOP_SECTION in url

    def _is_product_url(self, url: str) -> bool:
        """Check if URL is a product page (not category or utility page)."""
        if not self._is_shop_url(url):
            return False

        # Skip utility pages
        skip_patterns = [
            "/szukaj", "/koszyk", "/zamowienie", "/regulamin",
            "/kontakt", "/konto", "/logowanie", "/zestawy_startowe",
            "/zestawy_surowcow", "/zestawy-surowcow", "/kociolki",
            "/sprzet_zaawansowany", "/akcesoria",
        ]
        for pattern in skip_patterns:
            if pattern in url:
                return False

        # Product URLs have format: /centrumpiwowarstwa/category/subcategory/product-slug
        # At least 3 path segments after centrumpiwowarstwa
        path = url.split(self.SHOP_SECTION)[-1].rstrip("/")
        segments = [s for s in path.split("/") if s]

        # Need at least 3 segments (category/subcategory/product)
        if len(segments) < 3:
            return False

        # The last segment should look like a product slug (contains multiple hyphens or digits)
        last_segment = segments[-1]
        has_hyphens = last_segment.count("-") >= 2
        has_digits = any(c.isdigit() for c in last_segment)

        return has_hyphens or has_digits

    def get_item_info(self, url: str) -> Optional[ItemInfo]:
        """Get information about an item from its product page URL."""
        if not self._is_shop_url(url):
            print(f"URL is not a shop page: {url}")
            return None

        soup = self._fetch_page(url, reject_homepage=True)
        if not soup:
            return None

        # Extract product name from <title> tag
        # Format: "Product Name | Sklep Centrum Piwowarstwa..."
        name = None
        title_tag = soup.find("title")
        if title_tag and title_tag.string:
            title_text = title_tag.string.strip()
            if "|" in title_text:
                name = title_text.split("|")[0].strip()
            else:
                name = title_text

        # Fallback: try h1 or h2
        if not name:
            for tag in ["h1", "h2"]:
                header = soup.find(tag)
                if header:
                    name = header.get_text(strip=True)
                    break

        if not name:
            print(f"Could not extract product name from {url}")
            return None

        # Extract price - find the product price, avoiding per-kg prices and shipping costs
        prices = []

        # Patterns for prices, including those with thousand separators (space or nbsp)
        # Examples: "27,29", "2 897,99", "3 219,99 pln"
        price_patterns = [
            # Prices with thousand separators (space) and currency
            r"(\d{1,3}(?:[\s\xa0]\d{3})*)[,.](\d{2})\s*(?:zł|PLN|pln)",
            # Prices with thousand separators (space)
            r"(\d{1,3}(?:[\s\xa0]\d{3})*)[,.](\d{2})",
            # Simple prices without thousand separator
            r"(\d+)[,.](\d{2})\s*(?:zł|PLN|pln)",
            r"(\d+)[,.](\d{2})",
        ]

        # Keywords to skip (per-kg prices, shipping costs, dates, etc.)
        skip_keywords = [
            "cena za kg", "cena za l",  # per-unit prices
            "dpd", "kurier", "dostawa", "wysyłka", "pickup",  # shipping
            "koszty dostawy", "odbiory osobiste",  # shipping section
            "do 0", "do 1", "do 2", "do 3",  # date patterns like "do 08.01"
            "promocja:",  # promo dates
            "najniższa cena",  # historical lowest price (legal requirement)
            "produkty powiązane",  # related products section header
        ]

        # Skip patterns - regex patterns for prices to ignore
        skip_price_patterns = [
            r"\+\d",  # Prices starting with + (related product prices like "+69,99")
        ]

        # Look for price elements
        page_text = soup.get_text()
        in_related_section = False
        for line in page_text.split("\n"):
            line_lower = line.lower()
            # Track if we're in the related products section
            if "produkty powiązane" in line_lower:
                in_related_section = True
            # Skip lines with keywords to avoid
            if any(keyword in line_lower for keyword in skip_keywords):
                continue
            # Skip prices in related products section
            if in_related_section:
                continue
            # Skip lines with price patterns to avoid (like "+69,99")
            if any(re.search(pat, line) for pat in skip_price_patterns):
                continue
            # Try to extract price from line
            for pattern in price_patterns:
                match = re.search(pattern, line)
                if match:
                    # Remove spaces from the number part (thousand separators)
                    whole_part = match.group(1).replace(" ", "").replace("\xa0", "")
                    price_value = float(f"{whole_part}.{match.group(2)}")
                    # Filter out very low values (likely not prices)
                    if price_value > 1.0:
                        prices.append(price_value)
                    break

        # Get the first price found (main product price appears first on page)
        # Don't use min() as per-kg prices might slip through and be lower
        price = prices[0] if prices else None

        # Extract quantity from name or description
        quantity = self._parse_quantity(name)

        # Determine availability (also extracts raw text)
        availability, availability_text = self._determine_product_availability(soup)

        # Extract description as markdown
        description = None

        # browar.biz uses div.prod-holder containing p and ul elements for description
        prod_holder = soup.find("div", class_="prod-holder")
        if prod_holder:
            # Collect description from p and ul elements, excluding price info
            desc_parts = []
            for elem in prod_holder.find_all(["p", "ul"], recursive=False):
                text = elem.get_text(strip=True)
                # Skip empty elements and price-related content
                if not text or "cena za kg" in text.lower():
                    continue
                desc_parts.append(self._html_to_markdown(elem))

            if desc_parts:
                description = "\n\n".join(desc_parts)
                description = description[:5000] if len(description) > 5000 else description

        # Fallback: try generic class-based search
        if not description:
            desc_candidates = soup.find_all(["div", "p"], class_=re.compile(r"opis|desc", re.I))
            for candidate in desc_candidates:
                text = self._html_to_markdown(candidate)
                if text and len(text) > 20:
                    description = text[:5000] if len(text) > 5000 else text
                    break

        # Extract raw page data for LLM verification
        raw_data = self._extract_raw_page_data(soup)
        raw_data.availability_text = availability_text

        return ItemInfo(
            name=name,
            price=price,
            availability=availability,
            quantity=quantity,
            description=description,
            url=url,
            raw_data=raw_data,
        )

    def search(self, query: str) -> list[str]:
        """Search for products using the shop's native search.

        The shop uses a POST form that redirects to a results page.
        Form fields: query={term}, where=produkt, do=process
        """
        search_url = f"{self.BASE_URL}{self.SHOP_SECTION}wyszukiwarka"

        form_data = {
            "query": query,
            "where": "produkt",
            "do": "process",
        }

        try:
            # POST the search form - requests will follow the redirect
            response = requests.post(
                search_url,
                data=form_data,
                headers=self.HEADERS,
                timeout=15,
                allow_redirects=True,
            )
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
        except requests.RequestException as e:
            print(f"Error searching {search_url}: {e}")
            return []

        product_urls = []
        seen = set()

        # Find all links containing /centrumpiwowarstwa/
        for link in soup.find_all("a", href=True):
            href = link["href"]

            # Make absolute URL if relative
            if href.startswith("/"):
                href = urljoin(self.BASE_URL, href)
            elif not href.startswith("http"):
                continue

            # Check if it's a product URL
            if self._is_product_url(href) and href not in seen:
                seen.add(href)
                product_urls.append(href)

        return product_urls

    def _determine_product_availability(self, soup) -> tuple[str, Optional[str]]:
        """Determine product availability from specific elements.

        browar.biz structure:
        <strong>Dostępność</strong>: produkt znajduje się w magazynie
        or: <strong>Dostępność</strong>: produkt na wyczerpaniu!

        Returns:
            Tuple of (availability_status, raw_availability_text)
        """
        # Look for "Dostępność" label
        for strong in soup.find_all("strong"):
            strong_text = strong.get_text(strip=True).lower()
            if "dostępność" in strong_text:
                # Get the text that follows the strong element
                parent = strong.parent
                if parent:
                    full_text = parent.get_text(strip=True)
                    # Remove the label part to get just the status
                    raw_text = full_text.replace("Dostępność", "").replace("dostępność", "").replace(":", "").strip()
                    status = raw_text.lower()

                    if "magazynie" in status or "dostępn" in status:
                        return "in_stock", raw_text
                    elif "wyczerpaniu" in status:
                        return "low_stock", raw_text
                    elif "niedostępn" in status or "brak" in status:
                        return "out_of_stock", raw_text
                    return "unknown", raw_text

        # Fallback: check for "Dodaj do koszyka" button (indicates in stock)
        add_to_cart = soup.find(string=re.compile(r"dodaj do koszyka", re.IGNORECASE))
        if add_to_cart:
            return "in_stock", None

        # Last fallback: use base class method
        return self._determine_availability(soup), None
