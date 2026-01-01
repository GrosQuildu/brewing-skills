# Brew Shops Browser

Browse Polish homebrew shop websites to find brewing ingredients (malts, hops, yeasts).

## Installation

```bash
cd .claude/skills/brew-shops-browser/scripts
uv venv
uv pip install -e .
```

## Usage

This skill provides two main functionalities:

1. **Get item info** - Given a product URL, returns structured info:
   - Name
   - Price (in PLN)
   - Availability (in stock / out of stock)
   - Quantity (weight/volume)
   - Description
   - Raw page data (for LLM verification)

2. **Search products** - Given a search phrase, returns list of product URLs

## Supported Shops

- homebeer.pl (Shoper platform)
- homebrewing.pl
- swiatslodu.pl (Shoper platform)
- browamator.pl (Comarch eSklep platform)
- browar.biz

## Page Layout Structure

Each shop has a specific page layout. The parsers extract data from the main content area,
excluding headers, footers, navigation menus, sidebars, and related product sections.

### Common Page Elements (excluded from data extraction):

- **Headers/Banners**: Logo, search, cart, account icons
- **Navigation**: Menu bars, category menus
- **Footers**: Company info, links, payment methods
- **Sidebars**: Category lists, login forms, newsletter signup, contact info
- **Related products**: "Polecane produkty", "Bestsellery", "Klienci kupili także"

### Shop-specific layouts:

| Shop | Platform | Main content | Key exclusions |
|------|----------|--------------|----------------|
| browamator.pl | Comarch eSklep | `<main>` tag | "Produkty powiązane" |
| browar.biz | Custom | `<main>` tag | `<complementary>` sidebar, shipping costs |
| homebeer.pl | Shoper | CSS grid (no `<main>`) | Sidebar widgets, "Bestsellery" |
| homebrewing.pl | Custom | Table layout (no `<main>`) | Left sidebar, "Klienci zakupili także" |
| swiatslodu.pl | Shoper | `<main>` tag | "Polecane produkty" carousel |

## Running the script

```bash
cd .claude/skills/brew-shops-browser/scripts
uv run python -m brew_shops <command> <args>
```

### Get item info:
```bash
uv run python -m brew_shops info "https://homebeer.pl/pl/p/Chmiel-Citra-USA-granulat/288"
```

### Search products:
```bash
uv run python -m brew_shops search homebeer "Citra"
uv run python -m brew_shops search swiatslodu "słód pilzneński"
```

## Running tests

Semi-automated tests that display parsed data for review:

```bash
uv run python -m brew_shops test
```
