"""
Brewing Ingredients Database

A SQLite database for storing and managing brewing ingredients (hops, malts, yeasts)
with comprehensive parameters. Data population is performed by LLM-driven workflows.
"""

from .database import IngredientsDatabase
from .models import (
    Hop, Malt, Yeast,
    HopPurpose, MaltCategory, Flocculation, YeastForm, YeastType, SourceType
)

__version__ = "1.0.0"
__all__ = [
    "IngredientsDatabase",
    "Hop", "Malt", "Yeast",
    "HopPurpose", "MaltCategory", "Flocculation", "YeastForm", "YeastType", "SourceType",
]
