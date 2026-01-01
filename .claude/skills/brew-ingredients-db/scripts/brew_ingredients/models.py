"""
Data models for brewing ingredients.

All units are standardized:
- Color: EBC (European Brewery Convention)
- Alpha/Beta Acid: % by weight
- Oils: % of total oil content
- Total Oil: mL/100g
- Extract: % dry basis
- Moisture: %
- Attenuation: % apparent
- Temperature: Celsius
- Alcohol Tolerance: % ABV
- Diastatic Power: Lintner (°L) or Windisch-Kolbach (°WK)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, List
from enum import Enum
from datetime import datetime


class HopPurpose(str, Enum):
    """Hop usage purpose."""
    AROMA = "aroma"
    BITTERING = "bittering"
    DUAL = "dual"


class MaltCategory(str, Enum):
    """Malt category/type."""
    BASE = "base"
    CARAMEL = "caramel"
    CRYSTAL = "crystal"
    ROASTED = "roasted"
    SPECIALTY = "specialty"
    SMOKED = "smoked"
    ACIDULATED = "acidulated"
    WHEAT = "wheat"
    RYE = "rye"
    OATS = "oats"
    OTHER = "other"


class Flocculation(str, Enum):
    """Yeast flocculation level."""
    VERY_LOW = "very_low"
    LOW = "low"
    MEDIUM_LOW = "medium_low"
    MEDIUM = "medium"
    MEDIUM_HIGH = "medium_high"
    HIGH = "high"
    VERY_HIGH = "very_high"


class YeastForm(str, Enum):
    """Yeast product form."""
    DRY = "dry"
    LIQUID = "liquid"


class YeastType(str, Enum):
    """Yeast fermentation type."""
    ALE = "ale"
    LAGER = "lager"
    WHEAT = "wheat"
    BELGIAN = "belgian"
    KVEIK = "kveik"
    WILD = "wild"
    BRETT = "brettanomyces"
    HYBRID = "hybrid"
    WINE = "wine"
    OTHER = "other"


class SourceType(str, Enum):
    """
    Indicates the authority level of data sources for ingredient parameters.

    CANONICAL: Parameters fetched from official producer website/documentation.
               When a canonical source exists, ONLY that source should be used.
               Examples: fermentis.com for Fermentis yeasts, yakimachief.com for YCH hops

    COMPOSED: Parameters composed/aggregated from non-canonical sources.
              Used when no official producer documentation is available.
              May combine data from multiple third-party databases, shops, or references.
              Examples: Beer Maverick, homebrew shop listings, community databases
    """
    CANONICAL = "canonical"
    COMPOSED = "composed"


@dataclass
class Hop:
    """
    Hop variety with comprehensive parameters.

    All numeric ranges stored as min/max pairs.
    """
    # Identity
    name: str
    id: Optional[int] = None

    # Producer/Origin
    producer: Optional[str] = None  # Hop Breeding Company, Yakima Chief, etc.
    origin: Optional[str] = None    # Country/region: USA, Germany, New Zealand, etc.
    year_released: Optional[int] = None

    # Acid Content (%)
    alpha_acid_min: Optional[float] = None
    alpha_acid_max: Optional[float] = None
    beta_acid_min: Optional[float] = None
    beta_acid_max: Optional[float] = None
    co_humulone_min: Optional[float] = None  # % of alpha acids
    co_humulone_max: Optional[float] = None

    # Oil Content
    total_oil_min: Optional[float] = None  # mL/100g
    total_oil_max: Optional[float] = None
    myrcene_min: Optional[float] = None    # % of total oil
    myrcene_max: Optional[float] = None
    humulene_min: Optional[float] = None
    humulene_max: Optional[float] = None
    caryophyllene_min: Optional[float] = None
    caryophyllene_max: Optional[float] = None
    farnesene_min: Optional[float] = None
    farnesene_max: Optional[float] = None
    linalool_min: Optional[float] = None
    linalool_max: Optional[float] = None
    geraniol_min: Optional[float] = None
    geraniol_max: Optional[float] = None

    # Characteristics
    purpose: Optional[HopPurpose] = None
    flavor_profile: Optional[str] = None  # Comma-separated: "citrus,tropical,pine"
    aroma_profile: Optional[str] = None   # Comma-separated descriptors

    # Substitutes
    substitutes: Optional[str] = None  # Comma-separated hop names

    # Description
    description: Optional[str] = None
    notes: Optional[str] = None

    # Metadata
    sources: Optional[str] = None  # Comma-separated source names
    source_type: Optional['SourceType'] = None  # canonical or composed
    last_updated: Optional[datetime] = None

    def alpha_acid_typical(self) -> Optional[float]:
        """Get typical (midpoint) alpha acid value."""
        if self.alpha_acid_min is not None and self.alpha_acid_max is not None:
            return (self.alpha_acid_min + self.alpha_acid_max) / 2
        return self.alpha_acid_min or self.alpha_acid_max

    def beta_acid_typical(self) -> Optional[float]:
        """Get typical (midpoint) beta acid value."""
        if self.beta_acid_min is not None and self.beta_acid_max is not None:
            return (self.beta_acid_min + self.beta_acid_max) / 2
        return self.beta_acid_min or self.beta_acid_max

    def get_flavors(self) -> List[str]:
        """Get flavor profile as list."""
        if self.flavor_profile:
            return [f.strip() for f in self.flavor_profile.split(",")]
        return []

    def get_substitutes(self) -> List[str]:
        """Get substitutes as list."""
        if self.substitutes:
            return [s.strip() for s in self.substitutes.split(",")]
        return []


@dataclass
class Malt:
    """
    Malt variety with comprehensive parameters.

    Color in EBC, extract as % dry basis.
    """
    # Identity
    name: str
    id: Optional[int] = None

    # Producer/Origin
    producer: Optional[str] = None  # Weyermann, Castle, Crisp, etc.
    origin: Optional[str] = None    # Country: Germany, Belgium, UK, etc.

    # Category
    category: Optional[MaltCategory] = None
    grain_type: Optional[str] = None  # barley, wheat, rye, oats, etc.

    # Color (EBC)
    color_ebc_min: Optional[float] = None
    color_ebc_max: Optional[float] = None
    color_unit_certain: bool = True  # False if source unit (EBC/Lovibond/SRM) was ambiguous

    # Extract (% dry basis)
    extract_min: Optional[float] = None
    extract_max: Optional[float] = None
    extract_fine_coarse_diff: Optional[float] = None

    # Moisture (%)
    moisture_min: Optional[float] = None
    moisture_max: Optional[float] = None

    # Protein (%)
    protein_min: Optional[float] = None
    protein_max: Optional[float] = None

    # Modification
    kolbach_index_min: Optional[float] = None  # SNR/Soluble Nitrogen Ratio
    kolbach_index_max: Optional[float] = None

    # Enzyme Activity
    diastatic_power_min: Optional[float] = None  # Lintner
    diastatic_power_max: Optional[float] = None
    diastatic_power_wk_min: Optional[float] = None  # Windisch-Kolbach
    diastatic_power_wk_max: Optional[float] = None
    diastatic_power_unit_certain: bool = True  # False if source unit (Lintner/WK) was ambiguous

    # Friability
    friability_min: Optional[float] = None
    friability_max: Optional[float] = None

    # Beta Glucan (for wheat/oats)
    beta_glucan_max: Optional[float] = None  # mg/L

    # Usage
    max_percentage: Optional[float] = None  # Maximum recommended % of grist
    requires_mashing: bool = True

    # Flavor
    flavor_profile: Optional[str] = None  # Comma-separated descriptors

    # Description
    description: Optional[str] = None
    notes: Optional[str] = None

    # Substitutes
    substitutes: Optional[str] = None

    # Metadata
    sources: Optional[str] = None
    source_type: Optional['SourceType'] = None  # canonical or composed
    last_updated: Optional[datetime] = None

    def color_ebc_typical(self) -> Optional[float]:
        """Get typical (midpoint) color value."""
        if self.color_ebc_min is not None and self.color_ebc_max is not None:
            return (self.color_ebc_min + self.color_ebc_max) / 2
        return self.color_ebc_min or self.color_ebc_max

    def color_lovibond_typical(self) -> Optional[float]:
        """Get typical color in Lovibond."""
        ebc = self.color_ebc_typical()
        if ebc is not None:
            return (ebc - 1.2) / 2.65
        return None

    def extract_typical(self) -> Optional[float]:
        """Get typical extract value."""
        if self.extract_min is not None and self.extract_max is not None:
            return (self.extract_min + self.extract_max) / 2
        return self.extract_min or self.extract_max

    def get_flavors(self) -> List[str]:
        """Get flavor profile as list."""
        if self.flavor_profile:
            return [f.strip() for f in self.flavor_profile.split(",")]
        return []

    def get_substitutes(self) -> List[str]:
        """Get substitutes as list."""
        if self.substitutes:
            return [s.strip() for s in self.substitutes.split(",")]
        return []


@dataclass
class Yeast:
    """
    Yeast strain with comprehensive parameters.

    Temperature in Celsius, attenuation as %.
    """
    # Identity
    name: str
    id: Optional[int] = None
    product_code: Optional[str] = None  # US-05, WLP001, 1056, OYL-004, etc.

    # Producer
    producer: Optional[str] = None  # Fermentis, Lallemand, White Labs, Wyeast, Omega

    # Type/Classification
    yeast_type: Optional[YeastType] = None
    form: Optional[YeastForm] = None
    species: Optional[str] = None  # S. cerevisiae, S. pastorianus, Brettanomyces, etc.

    # Fermentation characteristics
    attenuation_min: Optional[float] = None  # %
    attenuation_max: Optional[float] = None
    flocculation: Optional[Flocculation] = None

    # Temperature range (Celsius)
    temp_min: Optional[float] = None
    temp_max: Optional[float] = None
    temp_ideal_min: Optional[float] = None
    temp_ideal_max: Optional[float] = None
    temp_unit_certain: bool = True  # False if source unit (°C/°F) was ambiguous

    # Alcohol tolerance (% ABV)
    alcohol_tolerance_min: Optional[float] = None
    alcohol_tolerance_max: Optional[float] = None

    # Cell count (for liquid yeasts)
    cell_count_billion: Optional[float] = None  # Billion cells per package

    # Characteristics
    flavor_profile: Optional[str] = None  # Comma-separated: "clean,fruity,estery"
    produces_phenols: bool = False
    produces_sulfur: bool = False
    sta1_positive: bool = False  # Diastaticus - can ferment dextrins

    # Recommended styles
    beer_styles: Optional[str] = None  # Comma-separated style names

    # Description
    description: Optional[str] = None
    notes: Optional[str] = None

    # Equivalents
    equivalents: Optional[str] = None  # Comma-separated equivalent product codes

    # Metadata
    sources: Optional[str] = None
    source_type: Optional['SourceType'] = None  # canonical or composed
    last_updated: Optional[datetime] = None

    def attenuation_typical(self) -> Optional[float]:
        """Get typical (midpoint) attenuation value."""
        if self.attenuation_min is not None and self.attenuation_max is not None:
            return (self.attenuation_min + self.attenuation_max) / 2
        return self.attenuation_min or self.attenuation_max

    def temp_range_str(self) -> str:
        """Get temperature range as string."""
        if self.temp_min is not None and self.temp_max is not None:
            return f"{self.temp_min}-{self.temp_max}°C"
        return "N/A"

    def get_flavors(self) -> List[str]:
        """Get flavor profile as list."""
        if self.flavor_profile:
            return [f.strip() for f in self.flavor_profile.split(",")]
        return []

    def get_equivalents(self) -> List[str]:
        """Get equivalent products as list."""
        if self.equivalents:
            return [e.strip() for e in self.equivalents.split(",")]
        return []

    def get_beer_styles(self) -> List[str]:
        """Get recommended beer styles as list."""
        if self.beer_styles:
            return [s.strip() for s in self.beer_styles.split(",")]
        return []
