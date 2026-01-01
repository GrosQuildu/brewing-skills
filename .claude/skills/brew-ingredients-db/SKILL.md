# Brewing Ingredients Database

Create, populate, update, and query a local SQLite database with brewing ingredients (hops, malts, yeasts).

## Description

This skill manages a comprehensive local database of brewing ingredients with their parameters:

- **Hops**: Alpha/beta acids, oil content (myrcene, humulene, etc.), purpose, flavor profiles, substitutes
- **Malts**: Color (EBC), extract potential, diastatic power, category, flavor profiles
- **Yeasts**: Attenuation, flocculation, temperature range, flavor profiles, equivalents

All parameters use standardized units (EBC for color, Celsius for temperature, etc.).

---

## 1. Install Scripts and Initialize Empty Database

```bash
cd /Users/gros/Desktop/texts/piwo/.claude/skills/brew-ingredients-db/scripts

# Install dependencies with uv (first time)
uv sync

# Initialize empty database
uv run python -m brew_ingredients.cli init
```

---

## 2. Parallel Processing with Subagents

When populating or updating the database, use the **Task tool** to spawn subagents that process producers in parallel. This significantly speeds up workflows.

The LLM should generate prompts for subagents that include:
- The producer name and any catalog/website URLs from RESOURCES.md
- The ingredient type being processed (hops/malts/yeasts)
- Instructions to fetch product pages, parse parameters, and add to database (from this SKILL file)
- Database path and API usage examples from this skill

---

## 3. Populate Database from Empty

This is an **LLM-driven workflow**. The LLM reads resources, fetches data, parses parameters, and adds items to the database.

### Workflow Overview

For each ingredient type (hops, malts, yeasts):

1. **Read RESOURCES.md** for the ingredient type section
2. **Iterate over all producers**:
   - If **Catalog link exists**: Fetch and parse the catalog to discover all products
   - If **no Catalog link**: Use web search and Additional Resources to find producer's products
3. **For each product discovered**:
   - Find product specification page/PDF
   - Parse parameters with unit detection and conversion
   - Add to database with source links and source_type (canonical/composed)

### Detailed Steps

#### Step 3.1: Read Resources

```
Read file: scripts/RESOURCES.md
Extract producer list for the ingredient type (hops/malts/yeasts)
```

#### Step 3.2: Process Each Producer

For each producer in the list:

```
1. Check if Catalog link exists
2. If Catalog exists:
   - Fetch the catalog URL
   - Parse to extract product names and links
3. If no Catalog:
   - Use WebSearch to find "[Producer Name] [ingredient type] products"
   - Check Additional Resources databases for the producer
```

#### Step 3.3: Fetch and Parse Product Pages

For each product found:

```
1. Determine resource type (HTML page or PDF)
2. For HTML:
   - Use WebFetch to get page content
   - LLM extracts parameters from the text
3. For PDF:
   - Download PDF to temp location
   - Use pdf-to-text tool or MCP server to extract text
   - LLM extracts parameters from extracted text
4. Parse parameters with unit detection (see Unit Handling below)
5. Add to database
```

#### Step 3.4: Add Item to Database

```python
from brew_ingredients import IngredientsDatabase, Hop, Malt, Yeast, SourceType

db = IngredientsDatabase()

# Example: Adding a hop
hop = Hop(
    name="Citra",
    producer="Hop Breeding Company",
    origin="USA",
    alpha_acid_min=11.0,
    alpha_acid_max=13.0,
    beta_acid_min=3.5,
    beta_acid_max=4.5,
    purpose=HopPurpose.DUAL,
    flavor_profile="citrus,tropical,grapefruit",
    sources="https://www.hopbreeding.com/citra",
    source_type=SourceType.CANONICAL  # Official producer source
)
db.add_hop(hop)
```

### Parsing Different Resource Types

#### HTML Pages
```
1. Use WebFetch with prompt: "Extract all product parameters from this page"
2. LLM identifies parameter tables, specification lists, etc.
3. Extract name, numeric values, units
```

#### PDF Files
```
1. Download PDF to /tmp/
2. Use tool/MCP to convert PDF to text:
   - pdftotext command: pdftotext -layout file.pdf -
   - Or MCP pdf server if available
3. LLM parses the extracted text for parameters
4. Clean up temp file
```

#### Catalog Pages (Lists of Products)
```
1. Fetch catalog page
2. Extract all product links/names
3. Return list for iteration
```

---

## 4. Update the Database

This workflow ensures the database stays current with producer catalogs.

### Update Workflow

For each producer in RESOURCES.md:

#### Step 4.1: Discover Current Products
```
1. Fetch producer's catalog (or search if no catalog)
2. Get list of all current products
3. Compare with items in database for this producer
4. Identify:
   - Missing items (in catalog but not in DB)
   - Existing items (in both)
   - Potentially removed items (in DB but not in catalog)
```

#### Step 4.2: Handle Missing Items
```
For each missing item:
1. Fetch product specification page
2. Parse parameters (as in populate workflow)
3. Add to database with source links
```

#### Step 4.3: Verify Existing Items
```
For each existing item:
1. Get stored source links from DB
2. Check if links are still valid (not 404/broken)
3. If broken:
   - Search for new canonical source
   - Update parameters and source links
   - Update RESOURCES.md if catalog link changed
4. If valid:
   - Fetch current parameters from source
   - Compare with stored parameters
   - Update if significantly different (not just noise)
```

#### Step 4.4: Update RESOURCES.md
```
If producer website or catalog link is broken/changed:
1. Search for new official website
2. Update Website column in RESOURCES.md
3. Search for new catalog page
4. Update Catalog column in RESOURCES.md
```

### Idempotency

The update workflow should be **idempotent**:
- Running update multiple times without catalog changes should produce no database changes
- If every update makes many changes, investigate:
  - Inconsistent parsing
  - Unit conversion issues
  - Catalog structure changes

---

## 5. Query the Database

### CLI Commands

```bash
cd /Users/gros/Desktop/texts/piwo/.claude/skills/brew-ingredients-db/scripts

# Show statistics
uv run python -m brew_ingredients.cli stats

# Show database schema
uv run python -m brew_ingredients.cli schema
uv run python -m brew_ingredients.cli schema -v  # verbose with column details

# Search for ingredients
uv run python -m brew_ingredients.cli search "citra"
uv run python -m brew_ingredients.cli search "caramel" -t malt
uv run python -m brew_ingredients.cli search "saison" -t yeast

# Get specific ingredient details
uv run python -m brew_ingredients.cli get "Citra"
uv run python -m brew_ingredients.cli get "Pilsner Malt" -t malt
uv run python -m brew_ingredients.cli get "US-05" -t yeast

# Export to JSON
uv run python -m brew_ingredients.cli export -o ingredients.json

# Clear all items (for repopulation)
uv run python -m brew_ingredients.cli clear -y
```

### Direct SQLite Queries

```bash
sqlite3 scripts/brewing_ingredients.db

# Count items
SELECT COUNT(*) FROM hops;
SELECT COUNT(*) FROM malts;
SELECT COUNT(*) FROM yeasts;

# Search hops by alpha acid
SELECT name, alpha_acid_min, alpha_acid_max FROM hops
WHERE alpha_acid_max >= 10 ORDER BY alpha_acid_max DESC;

# Find yeasts by producer
SELECT name, product_code, attenuation_min, attenuation_max
FROM yeasts WHERE producer = 'Fermentis';
```

---

## 6. Use in Python

```python
from brew_ingredients import IngredientsDatabase, Hop, Malt, Yeast
from brew_ingredients import HopPurpose, MaltCategory, Flocculation, SourceType

# Open database
db = IngredientsDatabase()

# Search hops by alpha acid range
hops = db.search_hops(alpha_min=10, alpha_max=15)
for hop in hops:
    print(f"{hop.name}: {hop.alpha_acid_min}-{hop.alpha_acid_max}%")

# Get specific malt
malt = db.get_malt("Maris Otter Pale Ale Malt")
if malt:
    print(f"Color: {malt.color_ebc_min}-{malt.color_ebc_max} EBC")

# Search yeasts by producer
fermentis = db.search_yeasts(producer="Fermentis")
for yeast in fermentis:
    print(f"{yeast.product_code}: {yeast.name}")

# Add custom ingredient
custom_hop = Hop(
    name="My Custom Hop",
    origin="USA",
    alpha_acid_min=12.0,
    alpha_acid_max=14.0,
    purpose=HopPurpose.DUAL,
    flavor_profile="citrus,tropical",
    sources="custom entry",
    source_type=SourceType.COMPOSED
)
db.add_hop(custom_hop)

# Get all items
all_hops = db.get_all_hops()
all_malts = db.get_all_malts()
all_yeasts = db.get_all_yeasts()
```

---

## Unit Handling

### Standardized Units

All parameters in the database use these standardized units:

| Parameter | Unit | Notes |
|-----------|------|-------|
| Alpha/Beta Acid | % | Percentage by weight |
| Co-humulone | % of alpha acids | |
| Total Oil | mL/100g | |
| Oil Components | % of total oil | Myrcene, humulene, etc. |
| Color | EBC | European Brewery Convention |
| Extract | % dry basis | |
| Moisture/Protein | % | |
| Kolbach Index | % | SNR |
| Diastatic Power | °Lintner or °WK | Store both if available |
| Attenuation | % | Apparent attenuation |
| Temperature | °C | Celsius |
| Alcohol Tolerance | % ABV | |

### Unit Detection and Conversion

When parsing parameters, the LLM must:

1. **Detect the unit** from context (explicit label, typical ranges, regional conventions)
2. **Convert to standard unit** using formulas below
3. **Mark uncertainty** if unit cannot be determined

#### Color Conversion
```
EBC = (Lovibond × 2.65) + 1.2
Lovibond = (EBC - 1.2) / 2.65
SRM ≈ EBC / 1.97

Detection hints:
- EBC: European sources, values typically 2-1500
- Lovibond/SRM: US sources, values typically 1-600
- If ambiguous, check if value is in expected range for the malt type
```

#### Temperature Conversion
```
°C = (°F - 32) × 5/9
°F = (°C × 9/5) + 32

Detection hints:
- European producers typically use °C
- US producers may use °F
- Fermentation temps: 15-25°C (59-77°F) for ales, 8-14°C (46-57°F) for lagers
```

#### Diastatic Power Conversion
```
Lintner ≈ (WK + 16) / 3.5
WK ≈ (Lintner × 3.5) - 16

Detection hints:
- WK (Windisch-Kolbach): European, values 0-400
- Lintner: US/UK, values 0-200
- Store in both fields if possible
```

#### Volume Conversion
```
1 US gallon = 3.78541 liters
1 US quart = 0.946353 liters
1 Imperial gallon = 4.54609 liters
```

#### Weight Conversion
```
1 oz = 28.3495 g
1 lb = 453.592 g
```

#### Extract Potential (PPG ↔ PKL)
```
PKL = PPG × 8.3454
PPG = PKL / 8.3454
```

### Uncertainty Tracking

When parsing cannot determine the unit with confidence:

```python
# For malt color where unit is ambiguous
malt = Malt(
    name="Some Malt",
    color_ebc_min=25.0,  # Converted assuming Lovibond
    color_ebc_max=30.0,
    color_unit_certain=False,  # Mark as uncertain
    ...
)

# For yeast temperature where unit is ambiguous
yeast = Yeast(
    name="Some Yeast",
    temp_min=18.0,  # Converted assuming °F
    temp_max=22.0,
    temp_unit_certain=False,  # Mark as uncertain
    ...
)

# For malt diastatic power where unit is ambiguous
malt = Malt(
    name="Some Malt",
    diastatic_power_min=100.0,  # Unknown if Lintner or WK
    diastatic_power_max=120.0,
    diastatic_power_unit_certain=False,
    ...
)
```

---

## Source Type Classification

Each ingredient has a `source_type` field:

- **CANONICAL**: Data from official producer website/documentation
  - When canonical source exists, prefer it over other sources
  - Examples: fermentis.com, yakimachief.com, weyermann.de

- **COMPOSED**: Data aggregated from non-canonical sources
  - Used when no official producer documentation available
  - May combine multiple sources: Beer Maverick, homebrew shops, community databases

```python
from brew_ingredients import SourceType

# Official producer data
hop.source_type = SourceType.CANONICAL
hop.sources = "https://www.yakimachief.com/citra"

# Aggregated from databases
hop.source_type = SourceType.COMPOSED
hop.sources = "beermaverick.com,brewersfriend.com"
```

---

## Data Resources

See `scripts/RESOURCES.md` for the full list of:
- Producer websites and catalog links
- Additional resource databases

---

## Key Parameters Reference

### Hops
- **Alpha Acid (AA%)**: 1-20%, primary bittering compound
- **Beta Acid**: Contributes to aroma stability
- **Co-humulone**: % of alpha acids (lower = smoother bitterness)
- **Total Oil**: mL/100g, aromatic potential
- **Myrcene**: Resinous/herbal character
- **Humulene**: Spicy/noble character
- **Purpose**: Aroma, Bittering, or Dual

### Malts
- **Color (EBC)**: 2-1500+ depending on type
- **Extract (% dry)**: 75-82% for base malts
- **Diastatic Power**: Enzyme activity for conversion
- **Protein**: 9-12%, affects head retention

### Yeasts
- **Attenuation**: 65-95% (higher = drier beer)
- **Flocculation**: Very Low to Very High
- **Temperature**: Optimal fermentation range (°C)
- **Alcohol Tolerance**: Maximum ABV

---

## Notes

- Database uses UPSERT logic - existing ingredients are updated, not duplicated
- Sources are tracked for each ingredient for reference and updates
- Population and updates are LLM-driven, not automated scripts
- Prefer canonical sources when available
