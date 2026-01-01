"""Abstract base class for shop parsers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional
import requests
from bs4 import BeautifulSoup


@dataclass
class RawPageData:
    """Raw visible data extracted from the page for LLM analysis."""
    availability_text: Optional[str] = None  # Raw text from availability element
    main_content: Optional[str] = None  # Main content area as plain text (html2text)
    meta_description: Optional[str] = None  # Meta description tag
    page_title: Optional[str] = None  # Page title


def needs_verification(info: "ItemInfo") -> tuple[bool, list[str]]:
    """Check if parsed data needs browser verification.

    Returns:
        Tuple of (needs_verification: bool, reasons: list[str])

    Verification is recommended when:
    - More than 4 quantity options (likely includes hidden/unavailable)
    - Item is out_of_stock but has quantity options
    - Price is None but item appears in stock
    - Availability is unknown
    """
    reasons = []

    if info.quantity:
        qty_count = len(info.quantity.split(","))
        if qty_count > 4:
            reasons.append(f"too_many_quantities ({qty_count} options)")

        if info.availability == "out_of_stock" and qty_count > 0:
            reasons.append("out_of_stock_with_quantities")

    if info.price is None and info.availability == "in_stock":
        reasons.append("no_price_but_in_stock")

    if info.availability == "unknown":
        reasons.append("unknown_availability")

    return len(reasons) > 0, reasons


@dataclass
class ItemInfo:
    """Information about a shop item."""
    name: str
    price: Optional[float]  # Price in PLN
    availability: str  # "in_stock", "low_stock", "out_of_stock", "unknown"
    quantity: Optional[str]  # e.g., "100g" or "100g, 1kg, 5kg" (comma-separated if multiple)
    # NOTE: When multiple quantities are available, the FIRST quantity in the list
    # corresponds to the parsed price. This is determined by the shop's default selection
    # (e.g., the checked radio button for quantity/weight options).
    description: Optional[str]
    url: str
    # Raw data for LLM verification
    raw_data: Optional[RawPageData] = None


class ShopParser(ABC):
    """Abstract base class for parsing homebrew shop websites."""

    # Override in subclasses
    SHOP_NAME: str = ""
    BASE_URL: str = ""

    # Common headers for requests
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "pl-PL,pl;q=0.9,en;q=0.8",
    }

    def _fetch_page(self, url: str, reject_homepage: bool = False) -> Optional[BeautifulSoup]:
        """Fetch a page and return BeautifulSoup object.

        Args:
            url: URL to fetch
            reject_homepage: If True, return None if final URL is the homepage

        Returns:
            BeautifulSoup object or None if fetch failed or redirected to homepage
        """
        try:
            response = requests.get(url, headers=self.HEADERS, timeout=15, allow_redirects=True)
            response.raise_for_status()

            # Check if redirected to homepage (invalid product URL)
            if reject_homepage:
                final_url = response.url.rstrip("/")
                base_url = self.BASE_URL.rstrip("/")
                if final_url == base_url:
                    print(f"Invalid URL (redirected to homepage): {url}")
                    return None

            return BeautifulSoup(response.text, "html.parser")
        except requests.RequestException as e:
            print(f"Error fetching {url}: {e}")
            return None

    @abstractmethod
    def get_item_info(self, url: str) -> Optional[ItemInfo]:
        """
        Get information about an item from its product page URL.

        Args:
            url: Full URL to the product page

        Returns:
            ItemInfo with product details, or None if parsing failed
        """
        pass

    @abstractmethod
    def search(self, query: str) -> list[str]:
        """
        Search for products using the shop's native search.

        Args:
            query: Search phrase (e.g., "Citra", "słód pilzneński")

        Returns:
            List of product page URLs
        """
        pass

    def _parse_price(self, text: str) -> Optional[float]:
        """Extract price from text like '12,99 zł' or '12.99 PLN'."""
        import re
        if not text:
            return None
        # Match patterns like "12,99", "12.99", "12,99 zł", "12.99 PLN"
        match = re.search(r"(\d+)[,.](\d{2})", text)
        if match:
            return float(f"{match.group(1)}.{match.group(2)}")
        return None

    def _parse_quantity(self, text: str) -> Optional[str]:
        """Extract quantity from text like '100g', '1 kg', '500 ml'."""
        import re
        if not text:
            return None
        # Match patterns like "100g", "1 kg", "500ml", "0.5kg"
        match = re.search(r"(\d+(?:[,\.]\d+)?)\s*(kg|g|ml|l)\b", text, re.IGNORECASE)
        if match:
            value = match.group(1).replace(",", ".")
            unit = match.group(2).lower()
            return f"{value}{unit}"
        return None

    def _html_to_markdown(self, element) -> str:
        """Convert HTML element to markdown-formatted text using markdownify library."""
        import re
        from markdownify import markdownify as md

        if element is None:
            return ""

        # Convert HTML to markdown
        html_str = str(element)
        text = md(html_str, heading_style="ATX", strip=['script', 'style'])

        # Clean up extra whitespace
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = text.strip()

        return text

    def _extract_raw_page_data(self, soup: BeautifulSoup) -> RawPageData:
        """Extract raw visible data from page for LLM verification.

        This provides the LLM with raw page information to verify
        algorithmically parsed data and make corrections if needed.
        Only extracts from main content area, excluding nav/header/footer.
        """
        import html2text

        raw = RawPageData()

        # Page title
        title_tag = soup.find("title")
        if title_tag:
            raw.page_title = title_tag.get_text(strip=True)

        # Meta description
        meta = soup.find("meta", {"name": "description"})
        if meta and meta.get("content"):
            raw.meta_description = meta["content"]

        # Find main content area (exclude nav, header, footer, menus)
        main_content = self._find_main_content(soup)

        # Convert main content to plain text using html2text
        h = html2text.HTML2Text()
        h.ignore_links = True
        h.ignore_images = True
        h.ignore_emphasis = False
        h.body_width = 0  # Don't wrap lines

        raw.main_content = h.handle(str(main_content))

        return raw

    # Selectors to remove from page when extracting main content
    # Override in subclasses for shop-specific elements
    REMOVE_SELECTORS = [
        # Structural elements
        "nav", "header", "footer", "aside",
        "[role='navigation']", "[role='banner']", "[role='contentinfo']",
        "[role='complementary']",
        # Common class/id patterns for nav/header/footer
        ".nav", ".menu", ".header", ".footer", ".sidebar",
        "#nav", "#menu", "#header", "#footer", "#sidebar",
        ".navigation", ".top-bar", ".top-menu", ".bottom-bar",
        # Common e-commerce sidebar/widget elements
        ".category-menu", ".categories", ".newsletter", ".cookie",
        ".bestsellers", ".recommended", ".recently-viewed",
        # Polish shop specific
        ".polecane", ".bestsellery", ".ostatnio-ogladane",
        # Shoper platform specific (homebeer.pl, swiatslodu.pl)
        ".box-newsletter", ".box-category", ".box-producer",
        # Hidden/unavailable elements (common CSS pattern)
        ".none", ".hidden", ".d-none", "[style*='display: none']",
        "[style*='display:none']",
    ]

    # Selectors to remove from inside main content area (related products, etc.)
    # Override in subclasses for shop-specific elements
    RELATED_PRODUCTS_SELECTORS = [
        ".polecane", ".recommended", ".bestsellers",
        ".klienci-kupili", ".related-products",
    ]

    # Polish headings/titles for sections to remove (case-insensitive matching)
    # These identify sections by their heading text when CSS selectors don't work
    EXCLUDE_SECTION_HEADINGS = [
        "bestseller", "polecane", "produkt dnia", "ostatnio oglądane",
        "klienci kupili", "pozostałe produkty", "produkty powiązane",
        "podobne produkty", "może cię zainteresować", "newsletter",
        "kategorie", "kontakt", "artykuły", "informacje",
    ]

    # Selectors to find main content container (tried in order)
    MAIN_CONTENT_SELECTORS = [
        # Semantic HTML5
        "main", "[role='main']",
        # Common product page containers
        ".product-page", ".product-detail", ".product-info",
        "#product", "#product-detail",
        # Generic content containers
        "#main", ".main-content", "#content", ".content",
    ]

    def _find_main_content(self, soup: BeautifulSoup) -> BeautifulSoup:
        """Find main content area, excluding navigation, header, footer, sidebars.

        Uses class-level REMOVE_SELECTORS, RELATED_PRODUCTS_SELECTORS,
        EXCLUDE_SECTION_HEADINGS, and MAIN_CONTENT_SELECTORS which can be
        overridden in shop-specific subclasses.

        Returns the main content element or a cleaned copy of soup.
        """
        import re

        # Remove unwanted elements from a copy
        soup_copy = BeautifulSoup(str(soup), "html.parser")

        # Remove navigation, header, footer, sidebar elements by CSS selectors
        for selector in self.REMOVE_SELECTORS:
            for elem in soup_copy.select(selector):
                elem.decompose()

        # Find main content FIRST (before removing sections by heading text)
        main_content = None
        for selector in self.MAIN_CONTENT_SELECTORS:
            main_content = soup_copy.select_one(selector)
            if main_content:
                break

        # Remove sections identified by their heading text (Polish e-commerce patterns)
        # This handles shops that don't use semantic CSS classes
        # Only process headings (h1-h6), not all divs/spans to avoid false positives
        for heading in soup_copy.find_all(["h2", "h3", "h4", "h5", "h6"]):
            heading_text = heading.get_text(strip=True).lower()
            for exclude_text in self.EXCLUDE_SECTION_HEADINGS:
                if exclude_text in heading_text:
                    # Remove the parent container of this heading (the whole section)
                    parent = heading.parent
                    # Go up a few levels to find the section container
                    for _ in range(3):
                        if parent and parent.parent:
                            # Don't remove the main content container
                            if main_content and parent == main_content:
                                break
                            # Check if parent looks like a section container
                            parent_text_len = len(parent.get_text(strip=True))
                            if parent_text_len > 100:  # Substantial section
                                parent.decompose()
                                break
                            parent = parent.parent
                    break

        # Try to find main content container (in order of specificity)
        for selector in self.MAIN_CONTENT_SELECTORS:
            main = soup_copy.select_one(selector)
            if main:
                # Further clean: remove recommendation sections inside main
                for rec_selector in self.RELATED_PRODUCTS_SELECTORS:
                    for rec in main.select(rec_selector):
                        rec.decompose()
                return main

        # Fallback: return cleaned soup
        return soup_copy

    def _determine_availability(self, soup: BeautifulSoup, text: str = "") -> str:
        """Determine availability from common Polish keywords."""
        text_lower = text.lower() if text else ""
        page_text = soup.get_text().lower() if soup else ""
        combined = text_lower + " " + page_text

        # Out of stock indicators
        out_of_stock = [
            "niedostępny", "niedostępna", "niedostępne",
            "brak w magazynie", "brak towaru",
            "powiadom o dostępności", "powiadom mnie"
        ]
        for indicator in out_of_stock:
            if indicator in combined:
                return "out_of_stock"

        # Low stock indicators
        low_stock = [
            "na wyczerpaniu", "ostatnia sztuka", "ostatnie sztuki",
            "mała ilość"
        ]
        for indicator in low_stock:
            if indicator in combined:
                return "low_stock"

        # In stock indicators
        in_stock = [
            "dostępny", "dostępna", "dostępne",
            "duża ilość", "średnia ilość", "mała ilość",
            "w magazynie", "na stanie",
            "do koszyka", "dodaj do koszyka"
        ]
        for indicator in in_stock:
            if indicator in combined:
                return "in_stock"

        return "unknown"
