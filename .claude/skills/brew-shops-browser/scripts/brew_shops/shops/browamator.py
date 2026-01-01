"""Shop parser for browamator.pl (Comarch eSklep platform).

NOTE: This site uses JavaScript rendering for search results.
Search functionality may return limited results.
Consider using category browsing for better results.
"""

import re
from typing import Optional
from urllib.parse import quote_plus

from ..base import ShopParser, ItemInfo


class BrowamatorParser(ShopParser):
    """Parser for browamator.pl homebrew shop (Comarch eSklep platform).

    NOTE: Site uses JavaScript rendering - search may not work well.

    Page structure:
    - <banner>: Top header with logo, search, cart
    - <banner>: Secondary header with categories, pages, contact
    - <main>: Main content area with product info
    - <contentinfo>: Footer

    Main content structure:
    - Breadcrumb list
    - Product info (image, name, price, availability, description)
    - "Produkty powiązane" section (related products to exclude)
    """

    SHOP_NAME = "Browamator"
    BASE_URL = "https://browamator.pl"

    # Shop-specific selectors - exclude "Produkty powiązane" related products section
    RELATED_PRODUCTS_SELECTORS = [
        ".polecane", ".recommended", ".bestsellers",
        ".klienci-kupili", ".related-products",
        # Browamator specific: related products section appears after main product
    ]

    # Category URLs for browsing
    CATEGORY_URLS = {
        "chmiele": "/produkty/piwo/piwo-surowce/chmiele/2-44",
        "slody": "/produkty/piwo/piwo-surowce/slody/2-35",
        "drozdze": "/produkty/piwo/piwo-surowce/drozdze/2-68",
    }

    # URL pattern: ends with /digits-digits-digits
    PRODUCT_URL_PATTERN = re.compile(r"/\d+-\d+-\d+$")

    def _is_valid_product_url(self, url: str) -> bool:
        """Check if URL matches the browamator.pl product URL pattern."""
        return bool(self.PRODUCT_URL_PATTERN.search(url))

    def get_item_info(self, url: str) -> Optional[ItemInfo]:
        """Get information about an item from its product page URL."""
        if not self._is_valid_product_url(url):
            print(f"Invalid browamator.pl product URL: {url}")
            return None

        soup = self._fetch_page(url, reject_homepage=True)
        if not soup:
            return None

        # Parse product name from <h1> tag
        h1 = soup.find("h1")
        name = h1.get_text(strip=True) if h1 else None
        if not name:
            print(f"Could not find product name on {url}")
            return None

        # Parse price - look for price patterns
        price = None
        price_text = ""

        # Try common price container classes
        price_selectors = [
            ".product-price",
            ".price",
            "[class*='price']",
            ".cena",
        ]
        for selector in price_selectors:
            price_elem = soup.select_one(selector)
            if price_elem:
                price_text = price_elem.get_text()
                price = self._parse_price(price_text)
                if price:
                    break

        # Fallback: search entire page for price pattern
        if not price:
            page_text = soup.get_text()
            price_match = re.search(r"(\d+)[,.](\d{2})\s*zł", page_text)
            if price_match:
                price = float(f"{price_match.group(1)}.{price_match.group(2)}")

        # Determine availability (also extracts raw text)
        availability, availability_text = self._parse_availability(soup)

        # Extract quantity from name
        quantity = self._parse_quantity(name)

        # Get description if available (as markdown)
        description = None
        desc_selectors = [
            ".product-description",
            ".description",
            "[class*='description']",
            ".opis",
        ]
        for selector in desc_selectors:
            desc_elem = soup.select_one(selector)
            if desc_elem:
                text = self._html_to_markdown(desc_elem)
                if text:
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

    def _parse_availability(self, soup) -> tuple[str, Optional[str]]:
        """Parse availability from browamator.pl product page.

        browamator.pl has a specific structure:
        <generic>Stany magazynowe:</generic><generic>dużo</generic>
        <generic>Dostępność:</generic><generic>Od ręki</generic>

        Returns:
            Tuple of (availability_status, raw_availability_text)
        """
        page_text = soup.get_text().lower()
        raw_text = None

        # First check for "brak towaru" which indicates out of stock
        # This takes priority over "dostępny na zamówienie"
        if "brak towaru" in page_text:
            return "out_of_stock", "brak towaru"

        # Look for "Stany magazynowe:" indicator and extract raw text
        for text_node in soup.find_all(string=re.compile(r"Stany magazynowe:", re.IGNORECASE)):
            parent = text_node.parent
            if parent:
                next_elem = parent.find_next_sibling()
                if next_elem:
                    raw_text = next_elem.get_text(strip=True)
                    status = raw_text.lower()
                    if "dużo" in status or "średnio" in status:
                        return "in_stock", raw_text
                    elif "mało" in status:
                        return "low_stock", raw_text

        # Look for "Dostępność:" indicator
        for text_node in soup.find_all(string=re.compile(r"Dostępność:", re.IGNORECASE)):
            parent = text_node.parent
            if parent:
                next_elem = parent.find_next_sibling()
                if next_elem:
                    raw_text = next_elem.get_text(strip=True)
                    status = raw_text.lower()
                    if "od ręki" in status or "towar dostępny" in status:
                        return "in_stock", raw_text
                    elif "na zamówienie" in status:
                        return "in_stock", raw_text  # Can be ordered (stock already checked above)
                    elif "niedostępny" in status or "brak" in status:
                        return "out_of_stock", raw_text
                    return "unknown", raw_text

        # Check if add-to-cart button is disabled
        cart_button = soup.select_one("button[type='submit'], .add-to-cart, .dodaj-do-koszyka")
        if cart_button:
            if cart_button.has_attr("disabled"):
                return "out_of_stock", None
            # Button exists and is not disabled - likely in stock
            return "in_stock", None

        # Fallback to base class method
        return self._determine_availability(soup), None

    def search(self, query: str) -> list[str]:
        """Search for products on browamator.pl."""
        encoded_query = quote_plus(query)
        search_url = f"{self.BASE_URL}/produkty/2?search={encoded_query}"

        soup = self._fetch_page(search_url)
        if not soup:
            return []

        # Find all product links matching the URL pattern
        product_urls = []
        seen_urls = set()

        for link in soup.find_all("a", href=True):
            href = link["href"]

            # Make absolute URL if relative
            if href.startswith("/"):
                href = f"{self.BASE_URL}{href}"
            elif not href.startswith("http"):
                # Handle relative paths without leading slash
                href = f"{self.BASE_URL}/{href}"

            # Check if it matches product URL pattern and not already seen
            if self._is_valid_product_url(href) and href not in seen_urls:
                product_urls.append(href)
                seen_urls.add(href)

        return product_urls
