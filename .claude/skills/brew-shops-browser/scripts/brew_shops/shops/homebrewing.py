"""Parser for homebrewing.pl shop."""

import re
from typing import Optional

from ..base import ShopParser, ItemInfo


class HomebrewingParser(ShopParser):
    """Parser for homebrewing.pl homebrew shop.

    Page structure (no semantic <main> tag):
    - Header area with logo, search, top navigation
    - Breadcrumb navigation
    - Content grid with:
      - Left sidebar: Information, Categories (expandable), Newsletter, Cennik, Contact
      - Main product area: Images, product info, description, tabs
    - "Klienci zakupili także" section (related products to exclude)
    - "Pozostałe produkty z kategorii" section (category products to exclude)
    - <contentinfo>: Footer

    Main content notes:
    - No <main> tag - uses table-based layout with CSS
    - Product info includes shipping cost "od 15,95 zł" which should not be confused with price
    - Price follows "Cena:" label
    - Availability follows "Dostępność:" label
    """

    SHOP_NAME = "Homebrewing.pl"
    BASE_URL = "https://homebrewing.pl/"
    SEARCH_URL = "https://homebrewing.pl/szukaj.html/szukaj={term}"

    # Pattern for product URLs: -p-[PRODUCT_ID].html
    PRODUCT_URL_PATTERN = re.compile(r"-p-\d+\.html")

    # Shop-specific selectors - exclude sidebar and recommendation sections
    REMOVE_SELECTORS = [
        # Structural elements
        "nav", "header", "footer", "aside",
        "[role='navigation']", "[role='banner']", "[role='contentinfo']",
        "[role='complementary']",
        # Common patterns
        ".nav", ".menu", ".header", ".footer", ".sidebar",
        "#nav", "#menu", "#header", "#footer", "#sidebar",
        ".navigation", ".top-bar", ".top-menu", ".bottom-bar",
        # E-commerce sidebar elements
        ".category-menu", ".categories", ".newsletter", ".cookie",
        ".bestsellers", ".recommended", ".recently-viewed",
        # Polish shop specific
        ".polecane", ".bestsellery", ".ostatnio-ogladane",
    ]

    # Sections inside content area to exclude
    RELATED_PRODUCTS_SELECTORS = [
        ".polecane", ".recommended", ".bestsellers",
        ".klienci-kupili", ".related-products",
        # homebrewing.pl has "Klienci zakupili także" and "Pozostałe produkty z kategorii"
    ]

    def get_item_info(self, url: str) -> Optional[ItemInfo]:
        """Get information about an item from its product page URL."""
        soup = self._fetch_page(url, reject_homepage=True)
        if not soup:
            return None

        # Parse product name from <h1> tag
        name = self._parse_name(soup)
        if not name:
            return None

        # Parse price
        price = self._parse_product_price(soup)

        # Determine availability (also extracts raw text)
        availability, availability_text = self._determine_product_availability(soup)

        # Parse quantity from name or description
        quantity = self._parse_quantity(name)

        # Get description
        description = self._parse_description(soup)

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
        """Search for products using the shop's native search."""
        search_url = self.SEARCH_URL.format(term=query)
        soup = self._fetch_page(search_url)
        if not soup:
            return []

        product_urls = []

        # Find all links that match the product URL pattern
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if self.PRODUCT_URL_PATTERN.search(href):
                # Ensure we have a full URL
                if href.startswith("http"):
                    full_url = href
                elif href.startswith("/"):
                    full_url = self.BASE_URL.rstrip("/") + href
                else:
                    full_url = self.BASE_URL + href

                # Avoid duplicates
                if full_url not in product_urls:
                    product_urls.append(full_url)

        return product_urls

    def _parse_name(self, soup) -> Optional[str]:
        """Extract product name from the page."""
        h1 = soup.find("h1")
        if h1:
            return h1.get_text(strip=True)
        return None

    def _parse_product_price(self, soup) -> Optional[float]:
        """Extract price from the product page.

        The page has multiple price elements including shipping costs and
        related product prices. We specifically look for the main product
        price which appears after "Cena:" label.
        """
        page_text = soup.get_text()

        # Primary method: Look for "Cena:" followed by price
        # This is the most reliable way to find the main product price
        # Pattern: "Cena: 30,30 zł" or "Cena:30,30 zł"
        cena_match = re.search(
            r"Cena:\s*(\d+)[,.](\d{2})\s*zł",
            page_text,
            re.IGNORECASE
        )
        if cena_match:
            return float(f"{cena_match.group(1)}.{cena_match.group(2)}")

        # Fallback: Try to find price containers with specific structure
        # Look for text that contains "Cena" near a price
        for text_node in soup.find_all(string=re.compile(r"Cena", re.IGNORECASE)):
            parent = text_node.parent
            if parent:
                # Get the next sibling or parent's text
                next_text = parent.get_text()
                price = self._parse_price(next_text)
                if price:
                    return price

        return None

    def _determine_product_availability(self, soup) -> tuple[str, Optional[str]]:
        """Determine product availability from the specific availability element.

        homebrewing.pl structure:
        <p><span>Dostępność:</span><strong>Dostępny</strong></p>
        Note: The strong element is a sibling, not inside the span.

        Returns:
            Tuple of (availability_status, raw_availability_text)
        """
        # Look for "Dostępność:" label and get the next strong element (sibling)
        for text_node in soup.find_all(string=re.compile(r"Dostępność:", re.IGNORECASE)):
            parent = text_node.parent
            if parent:
                # Get the next strong element (it's a sibling, not inside parent)
                strong = parent.find_next("strong")
                if strong:
                    raw_text = strong.get_text(strip=True)
                    status = raw_text.lower()
                    # Check out_of_stock indicators first (order matters!)
                    if "niedostępn" in status or "brak" in status:
                        return "out_of_stock", raw_text
                    elif "zapytaj" in status:  # "Zapytaj o dostępność"
                        return "out_of_stock", raw_text
                    elif "wyczerp" in status or "ostatni" in status:
                        return "low_stock", raw_text
                    elif "dostępn" in status:  # "Dostępny" - check after "zapytaj"
                        return "in_stock", raw_text
                    # Unknown status - return raw text for LLM to analyze
                    return "unknown", raw_text

        # Note: "Powiadom mnie o dostępności" button exists on ALL product pages
        # (hidden when in stock, shown when out of stock), so we can't use it as fallback

        # Use the base class method for other cases
        return self._determine_availability(soup), None

    def _parse_description(self, soup) -> Optional[str]:
        """Extract product description from the page.

        homebrewing.pl structure:
        <div class="widoczna tz_opis GlownyOpisProduktu">description text</div>
        """
        # Try specific class first (most reliable)
        desc_elem = soup.find("div", class_="GlownyOpisProduktu")
        if desc_elem:
            text = self._html_to_markdown(desc_elem)
            if text:
                return text[:5000] if len(text) > 5000 else text

        # Fallback: look for any div with opis/description in class (find_all to skip empty ones)
        for desc_elem in soup.find_all("div", class_=re.compile(r"description|opis", re.IGNORECASE)):
            text = self._html_to_markdown(desc_elem)
            if text and len(text) > 20:  # Skip very short/empty divs
                return text[:5000] if len(text) > 5000 else text

        return None
