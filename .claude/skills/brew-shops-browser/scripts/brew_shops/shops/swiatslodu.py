"""
Shop parser for swiatslodu.pl - Malt Specialist.

Website: https://www.swiatslodu.pl/
Specialty: Best malt selection among Polish homebrew shops.

Search URL: https://www.swiatslodu.pl/pl/searchquery/{term}
Product URL: https://www.swiatslodu.pl/[product-slug] (clean URLs)

Stock indicators:
- "duza ilosc" = in stock
- "na wyczerpaniu" = low stock
- "Powiadom o dostepnosci" = out of stock
"""

import re
from typing import Optional
from urllib.parse import quote_plus, urljoin

from bs4 import BeautifulSoup

from ..base import ShopParser, ItemInfo


class SwiatSloduParser(ShopParser):
    """Parser for swiatslodu.pl - malt specialist shop (Shoper platform).

    Page structure:
    - <banner>: Top header with logo, search, favorites, login, cart
    - <navigation>: Main horizontal menu (Promocje, Słody, Chmiele, etc.)
    - <main>: Main content area with:
      - Breadcrumb navigation
      - Product gallery
      - Product info (producer, name, rating, description, price, variants, availability)
      - Full description section (expandable)
      - Reviews section
      - "Polecane produkty" carousel (recommended products to exclude)
    - <contentinfo>: Footer with links, payment info

    Main content notes:
    - Uses semantic <main> tag
    - Price may show promotional price and "najniższa cena z 30 dni"
    - Availability shows "duża ilość", "średnia ilość", "mała ilość"
    - "Polecane produkty" carousel at bottom should be excluded
    """

    SHOP_NAME = "swiatslodu.pl"
    BASE_URL = "https://www.swiatslodu.pl"

    # Shop-specific selectors - exclude recommendation carousel
    RELATED_PRODUCTS_SELECTORS = [
        ".polecane", ".recommended", ".bestsellers",
        ".klienci-kupili", ".related-products",
        # swiatslodu.pl has "Polecane produkty" section
    ]

    # URL patterns to exclude from search results (utility/category pages)
    EXCLUDED_PATTERNS = [
        "/c/", "/searchquery", "/koszyk", "/login", "/panel",
        "/contact", "/regulamin", "/polityka", "/zwroty",
        "/jak-", "/formy_", "/czas-", "/dane-",
        "/promotions", "/favourites", "#", "/edit"
    ]

    # Category-only URLs to exclude (no product info)
    CATEGORY_ONLY = [
        "/slody-podstawowe", "/slody-specjalne", "/chmiele",
        "/drozdze-i-dodatki", "/dodatki", "/akcesoria-i-sprzet"
    ]

    def search(self, query: str, max_pages: int = 5) -> list[str]:
        """
        Search for products on swiatslodu.pl.

        Args:
            query: Search phrase (e.g., "Citra", "slod pilznenski")
            max_pages: Maximum number of result pages to fetch (default: 5)

        Returns:
            List of product page URLs
        """
        encoded_query = quote_plus(query)
        base_search_url = f"{self.BASE_URL}/pl/searchquery/{encoded_query}"

        urls = []
        seen = set()

        # Fetch multiple pages of results
        for page_num in range(1, max_pages + 1):
            # Shoper platform pagination: /pl/searchquery/{term}/{page}/phot/5
            if page_num == 1:
                search_url = base_search_url
            else:
                search_url = f"{base_search_url}/{page_num}/phot/5"

            soup = self._fetch_page(search_url)
            if not soup:
                break

            # CRITICAL: Only search within <main> to avoid sidebar/footer links
            main_content = soup.find("main")
            if not main_content:
                main_content = soup

            page_urls = []

            # swiatslodu.pl uses custom <product-link> elements for products
            # This is a Shoper platform feature - each product has 2 links (image + title)
            product_link_elements = main_content.find_all("product-link")
            if product_link_elements:
                for product_link in product_link_elements:
                    link = product_link.find("a", href=True)
                    if not link:
                        continue
                    href = link.get("href", "")

                    # Skip excluded URL patterns
                    if any(pattern in href.lower() for pattern in self.EXCLUDED_PATTERNS):
                        continue

                    # Build full URL
                    if href.startswith("/"):
                        full_url = urljoin(self.BASE_URL, href)
                    elif href.startswith(self.BASE_URL):
                        full_url = href
                    else:
                        continue

                    # Skip homepage
                    if full_url.rstrip("/") == self.BASE_URL:
                        continue

                    # Skip category-only pages
                    path = full_url.replace(self.BASE_URL, "").rstrip("/")
                    if path in self.CATEGORY_ONLY or not path:
                        continue

                    # Deduplicate
                    if full_url in seen:
                        continue
                    seen.add(full_url)

                    page_urls.append(full_url)
            else:
                # Fallback: search for links in product containers
                product_container = main_content.find("div", class_="products")
                if not product_container:
                    product_container = main_content.find("div", class_="search-results")
                if not product_container:
                    product_container = main_content

                for link in product_container.find_all("a", href=True):
                    href = link.get("href", "")

                    # Skip excluded URL patterns
                    if any(pattern in href.lower() for pattern in self.EXCLUDED_PATTERNS):
                        continue

                    # Build full URL
                    if href.startswith("/"):
                        full_url = urljoin(self.BASE_URL, href)
                    elif href.startswith(self.BASE_URL):
                        full_url = href
                    else:
                        continue

                    # Skip homepage
                    if full_url.rstrip("/") == self.BASE_URL:
                        continue

                    # Skip category-only pages
                    path = full_url.replace(self.BASE_URL, "").rstrip("/")
                    if path in self.CATEGORY_ONLY or not path:
                        continue

                    # Deduplicate
                    if full_url in seen:
                        continue
                    seen.add(full_url)

                    # Only include URLs that look like products
                    if self.BASE_URL in full_url and len(path) > 3:
                        page_urls.append(full_url)

            urls.extend(page_urls)

            # Stop if no products found on this page (end of results)
            if not page_urls:
                break

            # Check for pagination - look for page number indicator "Strona X z Y"
            pagination = soup.find("div", class_="pagination")
            if pagination:
                # Check if there's a next page by looking for page X+1 link
                next_link = pagination.find("a", href=lambda h: h and f"/{page_num + 1}/" in h if h else False)
                if not next_link:
                    # Also check pagination-page-number component
                    page_input = pagination.find("input", {"aria-label": True})
                    if page_input:
                        label = page_input.get("aria-label", "")
                        # Parse "Strona 1 z 2" format
                        import re
                        match = re.search(r"z\s*(\d+)", label)
                        if match:
                            total_pages = int(match.group(1))
                            if page_num >= total_pages:
                                break
                        else:
                            break
                    else:
                        break

        return urls

    def get_item_info(self, url: str) -> Optional[ItemInfo]:
        """
        Get information about a product from its page URL.

        Args:
            url: Full URL to the product page

        Returns:
            ItemInfo with product details, or None if parsing failed
        """
        soup = self._fetch_page(url, reject_homepage=True)
        if not soup:
            return None

        # Extract product name
        name = self._extract_name(soup)
        if not name:
            return None

        # Extract price
        price = self._extract_price(soup)

        # Determine availability (also extracts raw text)
        availability, availability_text = self._determine_product_availability(soup)

        # Extract quantity from name or page
        quantity = self._parse_quantity(name) or self._extract_quantity_from_page(soup)

        # Extract description
        description = self._extract_description(soup)

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

    def _determine_product_availability(self, soup) -> tuple[str, Optional[str]]:
        """Determine product availability from specific elements.

        swiatslodu.pl structure:
        <generic>Dostępność:</generic><strong>duża ilość</strong>

        Returns:
            Tuple of (availability_status, raw_availability_text)
        """
        # Look for "Dostępność:" followed by status text
        for text_node in soup.find_all(string=re.compile(r"Dostępność:", re.IGNORECASE)):
            parent = text_node.parent
            if parent:
                # Get next sibling or strong element
                strong = parent.find_next("strong")
                if strong:
                    raw_text = strong.get_text(strip=True)
                    status = raw_text.lower()
                    if "duża" in status or "średnia" in status:
                        return "in_stock", raw_text
                    elif "mała" in status or "wyczerp" in status or "ostatni" in status:
                        return "low_stock", raw_text
                    elif "brak" in status or "niedostępn" in status:
                        return "out_of_stock", raw_text
                    return "unknown", raw_text

        # Fallback: check for "Powiadom o dostępności" button
        notify_btn = soup.find(string=re.compile(r"powiadom o dostępności", re.IGNORECASE))
        if notify_btn:
            return "out_of_stock", "Powiadom o dostępności"

        # Fallback: check for "Dodaj do koszyka" button (indicates in stock)
        add_to_cart = soup.find(string=re.compile(r"dodaj do koszyka", re.IGNORECASE))
        if add_to_cart:
            return "in_stock", None

        return "unknown", None

    def _extract_name(self, soup) -> Optional[str]:
        """Extract product name from page."""
        # Try h1 first
        h1 = soup.find("h1")
        if h1:
            return h1.get_text(strip=True)

        # Fallback to h2 with product-name class
        h2 = soup.find("h2", class_="product-name")
        if h2:
            return h2.get_text(strip=True)

        return None

    def _extract_price(self, soup) -> Optional[float]:
        """Extract price from page.

        swiatslodu.pl (Shoper platform) has two price tab panels:
        - price-net-* (hidden) - net price without VAT
        - price-gross-* (visible) - gross price with VAT

        We need to extract the gross price (visible to customers).
        """
        # First, try to find the gross price tab panel (Shoper platform pattern)
        # Look for h-tab-panel with name containing "price-gross" (not hidden)
        gross_panel = soup.find("h-tab-panel", attrs={"name": re.compile(r"price-gross")})
        if gross_panel:
            # Find price value inside the gross panel
            price_elem = gross_panel.find(class_=re.compile(r"price__value.*bold"))
            if price_elem:
                return self._parse_price(price_elem.get_text())

        # Fallback: exclude hidden elements and find first visible price
        # Remove hidden tab panels before searching
        soup_copy = BeautifulSoup(str(soup), "html.parser")
        for hidden in soup_copy.find_all(attrs={"hidden": True}):
            hidden.decompose()
        for hidden in soup_copy.find_all("h-tab-panel", attrs={"name": re.compile(r"price-net")}):
            hidden.decompose()

        page_text = soup_copy.get_text()

        # Match price pattern like "12,99 zl" or "12.99 PLN"
        price_match = re.search(r"(\d+)[,.](\d{2})\s*(?:zł|zl|PLN)", page_text)
        if price_match:
            return float(f"{price_match.group(1)}.{price_match.group(2)}")

        # Try to find price in specific elements
        price_elem = soup_copy.find(class_=re.compile(r"price|cena", re.I))
        if price_elem:
            return self._parse_price(price_elem.get_text())

        return None

    def _extract_quantity_from_page(self, soup) -> Optional[str]:
        """Extract quantity/weight from page elements."""
        # Look for weight options (common for malt: 0.2kg, 1kg, 5kg, 25kg)
        page_text = soup.get_text()

        # Try to find weight in product details
        weight_match = re.search(
            r"(?:waga|gramatura|pojemnosc)[:\s]*(\d+(?:[,\.]\d+)?)\s*(kg|g|ml|l)\b",
            page_text,
            re.IGNORECASE
        )
        if weight_match:
            value = weight_match.group(1).replace(",", ".")
            unit = weight_match.group(2).lower()
            return f"{value}{unit}"

        return None

    def _extract_description(self, soup) -> Optional[str]:
        """Extract product description as markdown."""
        # Try common description containers
        desc_elem = soup.find(class_=re.compile(r"description|opis", re.I))
        if desc_elem:
            text = self._html_to_markdown(desc_elem)
            if text:
                return text[:5000] if len(text) > 5000 else text

        # Try meta description
        meta_desc = soup.find("meta", {"name": "description"})
        if meta_desc and meta_desc.get("content"):
            return meta_desc["content"]

        return None
