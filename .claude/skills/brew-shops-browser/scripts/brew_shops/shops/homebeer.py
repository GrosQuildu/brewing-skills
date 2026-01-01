"""Parser for homebeer.pl shop."""

import re
from typing import Optional
from urllib.parse import quote

from ..base import ShopParser, ItemInfo


class HomebeerParser(ShopParser):
    """Parser for homebeer.pl - Shoper.pl based e-commerce.

    Page structure (no semantic <main> tag):
    - <banner>: Top header with logo, cart, search
    - <navigation>: Top horizontal navigation menu
    - Breadcrumb navigation
    - Content grid with:
      - Left sidebar: Categories, Login form, Contacts, Search, Product of the day,
        Recently viewed, Articles, Newsletter, Facebook widget
      - Main product area: Product name, images, availability, price, description
    - "Bestsellery" section (bestsellers to exclude)
    - <contentinfo>: Footer

    Main content notes:
    - No <main> tag - uses custom CSS grid layout
    - Product info is in a div with h1 product name
    - Sidebar contains multiple widget boxes to exclude
    - "Bestsellery" section after product should be excluded
    """

    SHOP_NAME = "homebeer.pl"
    BASE_URL = "https://homebeer.pl"
    SEARCH_URL_TEMPLATE = "https://homebeer.pl/pl_PL/searchquery/{term}/1/desc/5?url={term}"

    # Shop-specific selectors - exclude sidebar widgets and recommendation sections
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
        # Shoper platform specific boxes
        ".box-newsletter", ".box-category", ".box-producer",
        ".box-news", ".box-contact", ".box-search", ".box-login",
        # homebeer.pl specific sidebar widgets (based on content analysis)
        # These are identified by their container divs with specific titles
    ]

    # Sections inside content area to exclude
    RELATED_PRODUCTS_SELECTORS = [
        ".polecane", ".recommended", ".bestsellers",
        ".klienci-kupili", ".related-products",
        # homebeer.pl uses "Bestsellery" text heading for the bestsellers section
    ]

    # Main content selectors - homebeer.pl uses centercol class
    MAIN_CONTENT_SELECTORS = [
        ".centercol",  # homebeer.pl main content area
        # Fallbacks
        "main", "[role='main']",
        ".product-page", ".product-detail", ".product-info",
        "#product", "#product-detail",
        "#main", ".main-content", "#content", ".content",
    ]

    def get_item_info(self, url: str) -> Optional[ItemInfo]:
        """Get information about an item from its product page URL."""
        soup = self._fetch_page(url, reject_homepage=True)
        if not soup:
            return None

        # Parse product name
        name = self._parse_name(soup)
        if not name:
            return None

        # Parse price
        price = self._parse_product_price(soup)

        # Parse quantity: first from selectable options, then from name
        # Description parsing is left to the skill (requires NLP)
        quantity = self._parse_quantity_options(soup)
        if not quantity:
            quantity = self._parse_quantity(name)

        # Parse description
        description = self._parse_description(soup)

        # Determine availability (also extracts raw text)
        availability, availability_text = self._determine_product_availability(soup)

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
        """Search for products and return list of product URLs.

        Important: Only extract links from the main content area (.centercol),
        not from sidebar widgets like "Produkt dnia", "Bestsellery", or "Ostatnio oglądane".
        """
        encoded_query = quote(query)
        search_url = self.SEARCH_URL_TEMPLATE.format(term=encoded_query)

        soup = self._fetch_page(search_url)
        if not soup:
            return []

        product_urls = []

        # CRITICAL: Only search within the main content area (.centercol)
        # to avoid capturing products from sidebar widgets
        main_content = soup.find("div", class_="centercol")
        if not main_content:
            # Fallback to searching within <main> if .centercol not found
            main_content = soup.find("main")
        if not main_content:
            # Last resort: use entire page but this may include sidebar products
            main_content = soup

        # Within main content, find the search results container
        # Shoper uses .search-results or .products-list for search results
        search_container = main_content.find("div", class_="search-results")
        if not search_container:
            search_container = main_content.find("div", class_="products-list")
        if not search_container:
            search_container = main_content.find("div", class_="products")
        if not search_container:
            # If no specific container found, use main_content but exclude known sidebars
            search_container = main_content

        # Find all links that match product URL pattern (/p/ in path)
        for link in search_container.find_all("a", href=True):
            href = link["href"]
            # Product URLs contain /p/ followed by product name and ID
            if "/p/" in href or "/pl_PL/p/" in href:
                # Normalize URL
                if href.startswith("/"):
                    full_url = self.BASE_URL + href
                elif href.startswith("http"):
                    full_url = href
                else:
                    continue

                # Avoid duplicates
                if full_url not in product_urls:
                    product_urls.append(full_url)

        return product_urls

    def _parse_name(self, soup) -> Optional[str]:
        """Extract product name from page."""
        # Try h1 with product-name class first
        name_elem = soup.find("h1", class_="product-name")
        if name_elem:
            return name_elem.get_text(strip=True)

        # Fall back to any h1
        h1 = soup.find("h1")
        if h1:
            return h1.get_text(strip=True)

        # Try meta title as last resort
        title = soup.find("meta", property="og:title")
        if title and title.get("content"):
            return title["content"]

        return None

    def _parse_product_price(self, soup) -> Optional[float]:
        """Extract price from product page."""
        # Try span with itemprop="price" (schema.org)
        price_elem = soup.find("span", itemprop="price")
        if price_elem:
            # Check for content attribute first
            if price_elem.get("content"):
                try:
                    return float(price_elem["content"])
                except ValueError:
                    pass
            return self._parse_price(price_elem.get_text())

        # Try span with class "price"
        price_elem = soup.find("span", class_="price")
        if price_elem:
            return self._parse_price(price_elem.get_text())

        # Try div with class "product-price"
        price_elem = soup.find("div", class_="product-price")
        if price_elem:
            return self._parse_price(price_elem.get_text())

        # Try meta tag
        price_meta = soup.find("meta", property="product:price:amount")
        if price_meta and price_meta.get("content"):
            try:
                return float(price_meta["content"])
            except ValueError:
                pass

        return None

    def _parse_description(self, soup) -> Optional[str]:
        """Extract product description as markdown."""
        # Common description containers in Shoper
        selectors = [
            ("div", {"class": "product-description"}),
            ("div", {"class": "description"}),
            ("div", {"id": "product-description"}),
            ("div", {"itemprop": "description"}),
        ]

        for tag, attrs in selectors:
            elem = soup.find(tag, attrs)
            if elem:
                text = self._html_to_markdown(elem)
                if text:
                    return text[:5000] if len(text) > 5000 else text

        return None

    def _parse_quantity_options(self, soup) -> Optional[str]:
        """Extract quantity options from selectable product variants.

        homebeer.pl (Shoper platform) stores option data in JavaScript variables:
        - Shop.values.OptionsDefault: Base64-encoded JSON array of default option values
        - Shop.values.ProductStocksCache: Base64-encoded JSON mapping option combos to stock data

        The first quantity in the returned list corresponds to the displayed price.
        """
        import base64
        import json

        # First, try to get default and available options from Shoper JS data
        default_option_value = None
        available_option_values = set()

        # Find script content
        page_text = str(soup)

        # Extract OptionsDefault (Base64 encoded array like [55, 359])
        default_match = re.search(r'OptionsDefault\s*=\s*"([^"]+)"', page_text)
        if default_match:
            try:
                decoded = base64.b64decode(default_match.group(1)).decode('utf-8')
                default_options = json.loads(decoded)
                if default_options:
                    default_option_value = str(default_options[0])  # First value is quantity option
            except (ValueError, json.JSONDecodeError, IndexError):
                pass

        # Extract ProductStocksCache to find available combinations
        cache_match = re.search(r'ProductStocksCache\s*=\s*"([^"]+)"', page_text)
        if cache_match:
            try:
                decoded = base64.b64decode(cache_match.group(1)).decode('utf-8')
                stocks_cache = json.loads(decoded)
                # Keys are like "55,359" - extract first value (quantity option)
                # Note: stocks_cache can be a dict or list depending on product config
                if isinstance(stocks_cache, dict):
                    for key, val in stocks_cache.items():
                        if isinstance(val, dict) and val.get('can_buy', False):
                            option_vals = key.split(',')
                            if option_vals:
                                available_option_values.add(option_vals[0])
            except (ValueError, json.JSONDecodeError):
                pass

        # Now parse the HTML to get option value -> quantity label mapping
        stocks_div = soup.find("div", class_="stocks")
        if not stocks_div:
            return None

        weight_labels = ["waga", "opakowanie", "gramatura", "pojemność", "wielkość"]
        option_to_qty = {}  # Maps option value (e.g., "55") to quantity label (e.g., "100g")

        for row in stocks_div.find_all("div", class_="f-row"):
            label_div = row.find("div", class_="label")
            if not label_div:
                continue

            label_text = label_div.get_text(strip=True).lower()
            if not any(wl in label_text for wl in weight_labels):
                continue

            options_div = row.find("div", class_="stock-options")
            if not options_div:
                continue

            for wrap in options_div.find_all("span", class_="radio-wrap"):
                radio_input = wrap.find("input", type="radio")
                if not radio_input:
                    continue

                option_value = radio_input.get("value")
                if not option_value:
                    continue

                lbl = wrap.find_next_sibling("label")
                if not lbl:
                    continue

                text = lbl.get_text(strip=True)
                qty_match = re.match(r"([\d.,]+\s*(?:g|kg|ml|l))", text, re.IGNORECASE)
                if qty_match:
                    qty = qty_match.group(1).replace(" ", "")
                    option_to_qty[option_value] = qty

        if not option_to_qty:
            return None

        # Build the result: default quantity first, then available ones
        result = []

        # Add default quantity first if we know it
        if default_option_value and default_option_value in option_to_qty:
            result.append(option_to_qty[default_option_value])

        # Add other available quantities
        if available_option_values:
            for opt_val, qty in option_to_qty.items():
                if opt_val in available_option_values and qty not in result:
                    result.append(qty)
        else:
            # Fallback: if we couldn't parse availability, include all options
            for opt_val, qty in option_to_qty.items():
                if qty not in result:
                    result.append(qty)

        return ", ".join(result) if result else None

    def _determine_product_availability(self, soup) -> tuple[str, Optional[str]]:
        """Determine availability from the specific availability element.

        homebeer.pl has a specific structure:
        <div class="row availability">
            <span class="first">Dostępność:</span>
            <span class="second">dostępny</span>  <!-- or "brak towaru" -->
        </div>

        Returns:
            Tuple of (availability_status, raw_availability_text)
        """
        # Look for the availability row
        avail_row = soup.find("div", class_="row availability")
        if avail_row:
            # Get the value from the second span
            value_span = avail_row.find("span", class_="second")
            if value_span:
                raw_text = value_span.get_text(strip=True)
                value = raw_text.lower()

                if "brak" in value or "niedostępn" in value:
                    return "out_of_stock", raw_text
                elif "dostępn" in value:
                    return "in_stock", raw_text
                elif "wyczerpa" in value or "ostatni" in value:
                    return "low_stock", raw_text
                return "unknown", raw_text

        # Fallback: check for "Do koszyka" button (indicates in stock)
        add_to_cart = soup.find("button", class_=re.compile(r"add.*cart|koszyk", re.I))
        if add_to_cart:
            # Make sure it's not hidden
            parent = add_to_cart.parent
            while parent:
                classes = parent.get("class", [])
                if "none" in classes or "hidden" in classes:
                    break
                parent = parent.parent
            else:
                return "in_stock", None

        # Last fallback: use base class method
        return self._determine_availability(soup), None
