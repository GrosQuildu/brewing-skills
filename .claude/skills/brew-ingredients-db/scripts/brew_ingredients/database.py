"""
SQLite database management for brewing ingredients.

Provides CRUD operations for hops, malts, and yeasts with full-text search.
"""

from __future__ import annotations
import sqlite3
from pathlib import Path
from typing import Optional, List, Type, TypeVar, Union
from datetime import datetime
from contextlib import contextmanager

from .models import (
    Hop, Malt, Yeast,
    HopPurpose, MaltCategory, Flocculation, YeastForm, YeastType, SourceType
)

T = TypeVar('T', Hop, Malt, Yeast)

# Default database path
DEFAULT_DB_PATH = Path(__file__).parent.parent / "brewing_ingredients.db"


class IngredientsDatabase:
    """
    SQLite database for brewing ingredients.

    Manages hops, malts, and yeasts with comprehensive parameters.
    """

    def __init__(self, db_path: Optional[Union[str, Path]] = None):
        """
        Initialize database connection.

        Args:
            db_path: Path to SQLite database file. Uses default if not specified.
        """
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self._connection: Optional[sqlite3.Connection] = None
        self._ensure_tables()

    @contextmanager
    def _get_connection(self):
        """Get database connection with automatic cleanup."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _ensure_tables(self):
        """Create tables if they don't exist."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Hops table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS hops (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    producer TEXT,
                    origin TEXT,
                    year_released INTEGER,

                    -- Alpha/Beta acids (%)
                    alpha_acid_min REAL,
                    alpha_acid_max REAL,
                    beta_acid_min REAL,
                    beta_acid_max REAL,
                    co_humulone_min REAL,
                    co_humulone_max REAL,

                    -- Oils (mL/100g for total, % for components)
                    total_oil_min REAL,
                    total_oil_max REAL,
                    myrcene_min REAL,
                    myrcene_max REAL,
                    humulene_min REAL,
                    humulene_max REAL,
                    caryophyllene_min REAL,
                    caryophyllene_max REAL,
                    farnesene_min REAL,
                    farnesene_max REAL,
                    linalool_min REAL,
                    linalool_max REAL,
                    geraniol_min REAL,
                    geraniol_max REAL,

                    -- Characteristics
                    purpose TEXT,
                    flavor_profile TEXT,
                    aroma_profile TEXT,
                    substitutes TEXT,

                    -- Description
                    description TEXT,
                    notes TEXT,

                    -- Metadata
                    sources TEXT,
                    source_type TEXT,  -- 'canonical' or 'composed'
                    last_updated TEXT
                )
            """)

            # Malts table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS malts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    producer TEXT,
                    origin TEXT,

                    -- Category
                    category TEXT,
                    grain_type TEXT,

                    -- Color (EBC)
                    color_ebc_min REAL,
                    color_ebc_max REAL,
                    color_unit_certain INTEGER DEFAULT 1,

                    -- Extract (% dry basis)
                    extract_min REAL,
                    extract_max REAL,
                    extract_fine_coarse_diff REAL,

                    -- Moisture (%)
                    moisture_min REAL,
                    moisture_max REAL,

                    -- Protein (%)
                    protein_min REAL,
                    protein_max REAL,

                    -- Modification
                    kolbach_index_min REAL,
                    kolbach_index_max REAL,

                    -- Enzyme activity
                    diastatic_power_min REAL,
                    diastatic_power_max REAL,
                    diastatic_power_wk_min REAL,
                    diastatic_power_wk_max REAL,
                    diastatic_power_unit_certain INTEGER DEFAULT 1,

                    -- Friability
                    friability_min REAL,
                    friability_max REAL,

                    -- Beta Glucan
                    beta_glucan_max REAL,

                    -- Usage
                    max_percentage REAL,
                    requires_mashing INTEGER DEFAULT 1,

                    -- Flavor
                    flavor_profile TEXT,

                    -- Description
                    description TEXT,
                    notes TEXT,
                    substitutes TEXT,

                    -- Metadata
                    sources TEXT,
                    source_type TEXT,  -- 'canonical' or 'composed'
                    last_updated TEXT
                )
            """)

            # Yeasts table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS yeasts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    product_code TEXT,
                    producer TEXT,

                    -- Type/Classification
                    yeast_type TEXT,
                    form TEXT,
                    species TEXT,

                    -- Fermentation characteristics
                    attenuation_min REAL,
                    attenuation_max REAL,
                    flocculation TEXT,

                    -- Temperature (Celsius)
                    temp_min REAL,
                    temp_max REAL,
                    temp_ideal_min REAL,
                    temp_ideal_max REAL,
                    temp_unit_certain INTEGER DEFAULT 1,

                    -- Alcohol tolerance (% ABV)
                    alcohol_tolerance_min REAL,
                    alcohol_tolerance_max REAL,

                    -- Cell count
                    cell_count_billion REAL,

                    -- Characteristics
                    flavor_profile TEXT,
                    produces_phenols INTEGER DEFAULT 0,
                    produces_sulfur INTEGER DEFAULT 0,
                    sta1_positive INTEGER DEFAULT 0,

                    -- Beer styles
                    beer_styles TEXT,

                    -- Description
                    description TEXT,
                    notes TEXT,
                    equivalents TEXT,

                    -- Metadata
                    sources TEXT,
                    source_type TEXT,  -- 'canonical' or 'composed'
                    last_updated TEXT,

                    UNIQUE(name, producer)
                )
            """)

            # Create indexes for common queries
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_hops_origin ON hops(origin)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_hops_purpose ON hops(purpose)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_malts_producer ON malts(producer)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_malts_category ON malts(category)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_yeasts_producer ON yeasts(producer)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_yeasts_type ON yeasts(yeast_type)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_yeasts_code ON yeasts(product_code)")

            # Run migrations for existing databases
            self._migrate_tables(cursor)

    def _migrate_tables(self, cursor):
        """Run migrations to update existing tables with new columns."""
        # Migration: Add source_type column if it doesn't exist
        for table in ['hops', 'malts', 'yeasts']:
            cursor.execute(f"PRAGMA table_info({table})")
            columns = [col[1] for col in cursor.fetchall()]
            if 'source_type' not in columns:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN source_type TEXT")

        # Migration: Add unit uncertainty columns for malts
        cursor.execute("PRAGMA table_info(malts)")
        malt_columns = [col[1] for col in cursor.fetchall()]
        if 'color_unit_certain' not in malt_columns:
            cursor.execute("ALTER TABLE malts ADD COLUMN color_unit_certain INTEGER DEFAULT 1")
        if 'diastatic_power_unit_certain' not in malt_columns:
            cursor.execute("ALTER TABLE malts ADD COLUMN diastatic_power_unit_certain INTEGER DEFAULT 1")

        # Migration: Add unit uncertainty columns for yeasts
        cursor.execute("PRAGMA table_info(yeasts)")
        yeast_columns = [col[1] for col in cursor.fetchall()]
        if 'temp_unit_certain' not in yeast_columns:
            cursor.execute("ALTER TABLE yeasts ADD COLUMN temp_unit_certain INTEGER DEFAULT 1")

    # ==================== HOP OPERATIONS ====================

    def add_hop(self, hop: Hop) -> int:
        """Add or update a hop variety."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now().isoformat()

            cursor.execute("""
                INSERT INTO hops (
                    name, producer, origin, year_released,
                    alpha_acid_min, alpha_acid_max, beta_acid_min, beta_acid_max,
                    co_humulone_min, co_humulone_max,
                    total_oil_min, total_oil_max,
                    myrcene_min, myrcene_max, humulene_min, humulene_max,
                    caryophyllene_min, caryophyllene_max, farnesene_min, farnesene_max,
                    linalool_min, linalool_max, geraniol_min, geraniol_max,
                    purpose, flavor_profile, aroma_profile, substitutes,
                    description, notes, sources, source_type, last_updated
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    producer = COALESCE(excluded.producer, producer),
                    origin = COALESCE(excluded.origin, origin),
                    year_released = COALESCE(excluded.year_released, year_released),
                    alpha_acid_min = COALESCE(excluded.alpha_acid_min, alpha_acid_min),
                    alpha_acid_max = COALESCE(excluded.alpha_acid_max, alpha_acid_max),
                    beta_acid_min = COALESCE(excluded.beta_acid_min, beta_acid_min),
                    beta_acid_max = COALESCE(excluded.beta_acid_max, beta_acid_max),
                    co_humulone_min = COALESCE(excluded.co_humulone_min, co_humulone_min),
                    co_humulone_max = COALESCE(excluded.co_humulone_max, co_humulone_max),
                    total_oil_min = COALESCE(excluded.total_oil_min, total_oil_min),
                    total_oil_max = COALESCE(excluded.total_oil_max, total_oil_max),
                    myrcene_min = COALESCE(excluded.myrcene_min, myrcene_min),
                    myrcene_max = COALESCE(excluded.myrcene_max, myrcene_max),
                    humulene_min = COALESCE(excluded.humulene_min, humulene_min),
                    humulene_max = COALESCE(excluded.humulene_max, humulene_max),
                    caryophyllene_min = COALESCE(excluded.caryophyllene_min, caryophyllene_min),
                    caryophyllene_max = COALESCE(excluded.caryophyllene_max, caryophyllene_max),
                    farnesene_min = COALESCE(excluded.farnesene_min, farnesene_min),
                    farnesene_max = COALESCE(excluded.farnesene_max, farnesene_max),
                    linalool_min = COALESCE(excluded.linalool_min, linalool_min),
                    linalool_max = COALESCE(excluded.linalool_max, linalool_max),
                    geraniol_min = COALESCE(excluded.geraniol_min, geraniol_min),
                    geraniol_max = COALESCE(excluded.geraniol_max, geraniol_max),
                    purpose = COALESCE(excluded.purpose, purpose),
                    flavor_profile = COALESCE(excluded.flavor_profile, flavor_profile),
                    aroma_profile = COALESCE(excluded.aroma_profile, aroma_profile),
                    substitutes = COALESCE(excluded.substitutes, substitutes),
                    description = COALESCE(excluded.description, description),
                    notes = COALESCE(excluded.notes, notes),
                    sources = CASE
                        WHEN sources IS NULL THEN excluded.sources
                        WHEN excluded.sources IS NULL THEN sources
                        ELSE sources || ',' || excluded.sources
                    END,
                    source_type = COALESCE(excluded.source_type, source_type),
                    last_updated = excluded.last_updated
            """, (
                hop.name, hop.producer, hop.origin, hop.year_released,
                hop.alpha_acid_min, hop.alpha_acid_max, hop.beta_acid_min, hop.beta_acid_max,
                hop.co_humulone_min, hop.co_humulone_max,
                hop.total_oil_min, hop.total_oil_max,
                hop.myrcene_min, hop.myrcene_max, hop.humulene_min, hop.humulene_max,
                hop.caryophyllene_min, hop.caryophyllene_max, hop.farnesene_min, hop.farnesene_max,
                hop.linalool_min, hop.linalool_max, hop.geraniol_min, hop.geraniol_max,
                hop.purpose.value if hop.purpose else None,
                hop.flavor_profile, hop.aroma_profile, hop.substitutes,
                hop.description, hop.notes, hop.sources,
                hop.source_type.value if hop.source_type else None,
                now
            ))

            return cursor.lastrowid

    def get_hop(self, name: str) -> Optional[Hop]:
        """Get a hop by name."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM hops WHERE name = ? COLLATE NOCASE", (name,))
            row = cursor.fetchone()
            if row:
                return self._row_to_hop(row)
            return None

    def get_hop_by_id(self, hop_id: int) -> Optional[Hop]:
        """Get a hop by ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM hops WHERE id = ?", (hop_id,))
            row = cursor.fetchone()
            if row:
                return self._row_to_hop(row)
            return None

    def search_hops(
        self,
        query: Optional[str] = None,
        origin: Optional[str] = None,
        purpose: Optional[HopPurpose] = None,
        alpha_min: Optional[float] = None,
        alpha_max: Optional[float] = None,
        limit: int = 100
    ) -> List[Hop]:
        """Search hops by various criteria."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            conditions = []
            params = []

            if query:
                conditions.append(
                    "(name LIKE ? OR flavor_profile LIKE ? OR aroma_profile LIKE ? OR description LIKE ?)"
                )
                q = f"%{query}%"
                params.extend([q, q, q, q])

            if origin:
                conditions.append("origin LIKE ?")
                params.append(f"%{origin}%")

            if purpose:
                conditions.append("purpose = ?")
                params.append(purpose.value)

            if alpha_min is not None:
                conditions.append("alpha_acid_max >= ?")
                params.append(alpha_min)

            if alpha_max is not None:
                conditions.append("alpha_acid_min <= ?")
                params.append(alpha_max)

            where_clause = " AND ".join(conditions) if conditions else "1=1"

            cursor.execute(
                f"SELECT * FROM hops WHERE {where_clause} ORDER BY name LIMIT ?",
                params + [limit]
            )

            return [self._row_to_hop(row) for row in cursor.fetchall()]

    def get_all_hops(self) -> List[Hop]:
        """Get all hops."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM hops ORDER BY name")
            return [self._row_to_hop(row) for row in cursor.fetchall()]

    def delete_hop(self, name: str) -> bool:
        """Delete a hop by name."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM hops WHERE name = ? COLLATE NOCASE", (name,))
            return cursor.rowcount > 0

    def _row_to_hop(self, row: sqlite3.Row) -> Hop:
        """Convert database row to Hop object."""
        return Hop(
            id=row["id"],
            name=row["name"],
            producer=row["producer"],
            origin=row["origin"],
            year_released=row["year_released"],
            alpha_acid_min=row["alpha_acid_min"],
            alpha_acid_max=row["alpha_acid_max"],
            beta_acid_min=row["beta_acid_min"],
            beta_acid_max=row["beta_acid_max"],
            co_humulone_min=row["co_humulone_min"],
            co_humulone_max=row["co_humulone_max"],
            total_oil_min=row["total_oil_min"],
            total_oil_max=row["total_oil_max"],
            myrcene_min=row["myrcene_min"],
            myrcene_max=row["myrcene_max"],
            humulene_min=row["humulene_min"],
            humulene_max=row["humulene_max"],
            caryophyllene_min=row["caryophyllene_min"],
            caryophyllene_max=row["caryophyllene_max"],
            farnesene_min=row["farnesene_min"],
            farnesene_max=row["farnesene_max"],
            linalool_min=row["linalool_min"],
            linalool_max=row["linalool_max"],
            geraniol_min=row["geraniol_min"],
            geraniol_max=row["geraniol_max"],
            purpose=HopPurpose(row["purpose"]) if row["purpose"] else None,
            flavor_profile=row["flavor_profile"],
            aroma_profile=row["aroma_profile"],
            substitutes=row["substitutes"],
            description=row["description"],
            notes=row["notes"],
            sources=row["sources"],
            source_type=SourceType(row["source_type"]) if row["source_type"] else None,
            last_updated=datetime.fromisoformat(row["last_updated"]) if row["last_updated"] else None
        )

    # ==================== MALT OPERATIONS ====================

    def add_malt(self, malt: Malt) -> int:
        """Add or update a malt variety."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now().isoformat()

            cursor.execute("""
                INSERT INTO malts (
                    name, producer, origin, category, grain_type,
                    color_ebc_min, color_ebc_max, color_unit_certain,
                    extract_min, extract_max, extract_fine_coarse_diff,
                    moisture_min, moisture_max,
                    protein_min, protein_max,
                    kolbach_index_min, kolbach_index_max,
                    diastatic_power_min, diastatic_power_max,
                    diastatic_power_wk_min, diastatic_power_wk_max,
                    diastatic_power_unit_certain,
                    friability_min, friability_max,
                    beta_glucan_max, max_percentage, requires_mashing,
                    flavor_profile, description, notes, substitutes,
                    sources, source_type, last_updated
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    producer = COALESCE(excluded.producer, producer),
                    origin = COALESCE(excluded.origin, origin),
                    category = COALESCE(excluded.category, category),
                    grain_type = COALESCE(excluded.grain_type, grain_type),
                    color_ebc_min = COALESCE(excluded.color_ebc_min, color_ebc_min),
                    color_ebc_max = COALESCE(excluded.color_ebc_max, color_ebc_max),
                    color_unit_certain = excluded.color_unit_certain,
                    extract_min = COALESCE(excluded.extract_min, extract_min),
                    extract_max = COALESCE(excluded.extract_max, extract_max),
                    extract_fine_coarse_diff = COALESCE(excluded.extract_fine_coarse_diff, extract_fine_coarse_diff),
                    moisture_min = COALESCE(excluded.moisture_min, moisture_min),
                    moisture_max = COALESCE(excluded.moisture_max, moisture_max),
                    protein_min = COALESCE(excluded.protein_min, protein_min),
                    protein_max = COALESCE(excluded.protein_max, protein_max),
                    kolbach_index_min = COALESCE(excluded.kolbach_index_min, kolbach_index_min),
                    kolbach_index_max = COALESCE(excluded.kolbach_index_max, kolbach_index_max),
                    diastatic_power_min = COALESCE(excluded.diastatic_power_min, diastatic_power_min),
                    diastatic_power_max = COALESCE(excluded.diastatic_power_max, diastatic_power_max),
                    diastatic_power_wk_min = COALESCE(excluded.diastatic_power_wk_min, diastatic_power_wk_min),
                    diastatic_power_wk_max = COALESCE(excluded.diastatic_power_wk_max, diastatic_power_wk_max),
                    diastatic_power_unit_certain = excluded.diastatic_power_unit_certain,
                    friability_min = COALESCE(excluded.friability_min, friability_min),
                    friability_max = COALESCE(excluded.friability_max, friability_max),
                    beta_glucan_max = COALESCE(excluded.beta_glucan_max, beta_glucan_max),
                    max_percentage = COALESCE(excluded.max_percentage, max_percentage),
                    requires_mashing = excluded.requires_mashing,
                    flavor_profile = COALESCE(excluded.flavor_profile, flavor_profile),
                    description = COALESCE(excluded.description, description),
                    notes = COALESCE(excluded.notes, notes),
                    substitutes = COALESCE(excluded.substitutes, substitutes),
                    sources = CASE
                        WHEN sources IS NULL THEN excluded.sources
                        WHEN excluded.sources IS NULL THEN sources
                        ELSE sources || ',' || excluded.sources
                    END,
                    source_type = COALESCE(excluded.source_type, source_type),
                    last_updated = excluded.last_updated
            """, (
                malt.name, malt.producer, malt.origin,
                malt.category.value if malt.category else None,
                malt.grain_type,
                malt.color_ebc_min, malt.color_ebc_max,
                1 if malt.color_unit_certain else 0,
                malt.extract_min, malt.extract_max, malt.extract_fine_coarse_diff,
                malt.moisture_min, malt.moisture_max,
                malt.protein_min, malt.protein_max,
                malt.kolbach_index_min, malt.kolbach_index_max,
                malt.diastatic_power_min, malt.diastatic_power_max,
                malt.diastatic_power_wk_min, malt.diastatic_power_wk_max,
                1 if malt.diastatic_power_unit_certain else 0,
                malt.friability_min, malt.friability_max,
                malt.beta_glucan_max, malt.max_percentage,
                1 if malt.requires_mashing else 0,
                malt.flavor_profile, malt.description, malt.notes, malt.substitutes,
                malt.sources,
                malt.source_type.value if malt.source_type else None,
                now
            ))

            return cursor.lastrowid

    def get_malt(self, name: str) -> Optional[Malt]:
        """Get a malt by name."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM malts WHERE name = ? COLLATE NOCASE", (name,))
            row = cursor.fetchone()
            if row:
                return self._row_to_malt(row)
            return None

    def search_malts(
        self,
        query: Optional[str] = None,
        producer: Optional[str] = None,
        category: Optional[MaltCategory] = None,
        color_ebc_min: Optional[float] = None,
        color_ebc_max: Optional[float] = None,
        limit: int = 100
    ) -> List[Malt]:
        """Search malts by various criteria."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            conditions = []
            params = []

            if query:
                conditions.append(
                    "(name LIKE ? OR flavor_profile LIKE ? OR description LIKE ?)"
                )
                q = f"%{query}%"
                params.extend([q, q, q])

            if producer:
                conditions.append("producer LIKE ?")
                params.append(f"%{producer}%")

            if category:
                conditions.append("category = ?")
                params.append(category.value)

            if color_ebc_min is not None:
                conditions.append("color_ebc_max >= ?")
                params.append(color_ebc_min)

            if color_ebc_max is not None:
                conditions.append("color_ebc_min <= ?")
                params.append(color_ebc_max)

            where_clause = " AND ".join(conditions) if conditions else "1=1"

            cursor.execute(
                f"SELECT * FROM malts WHERE {where_clause} ORDER BY name LIMIT ?",
                params + [limit]
            )

            return [self._row_to_malt(row) for row in cursor.fetchall()]

    def get_all_malts(self) -> List[Malt]:
        """Get all malts."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM malts ORDER BY name")
            return [self._row_to_malt(row) for row in cursor.fetchall()]

    def delete_malt(self, name: str) -> bool:
        """Delete a malt by name."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM malts WHERE name = ? COLLATE NOCASE", (name,))
            return cursor.rowcount > 0

    def _row_to_malt(self, row: sqlite3.Row) -> Malt:
        """Convert database row to Malt object."""
        return Malt(
            id=row["id"],
            name=row["name"],
            producer=row["producer"],
            origin=row["origin"],
            category=MaltCategory(row["category"]) if row["category"] else None,
            grain_type=row["grain_type"],
            color_ebc_min=row["color_ebc_min"],
            color_ebc_max=row["color_ebc_max"],
            color_unit_certain=bool(row["color_unit_certain"]) if row["color_unit_certain"] is not None else True,
            extract_min=row["extract_min"],
            extract_max=row["extract_max"],
            extract_fine_coarse_diff=row["extract_fine_coarse_diff"],
            moisture_min=row["moisture_min"],
            moisture_max=row["moisture_max"],
            protein_min=row["protein_min"],
            protein_max=row["protein_max"],
            kolbach_index_min=row["kolbach_index_min"],
            kolbach_index_max=row["kolbach_index_max"],
            diastatic_power_min=row["diastatic_power_min"],
            diastatic_power_max=row["diastatic_power_max"],
            diastatic_power_wk_min=row["diastatic_power_wk_min"],
            diastatic_power_wk_max=row["diastatic_power_wk_max"],
            diastatic_power_unit_certain=bool(row["diastatic_power_unit_certain"]) if row["diastatic_power_unit_certain"] is not None else True,
            friability_min=row["friability_min"],
            friability_max=row["friability_max"],
            beta_glucan_max=row["beta_glucan_max"],
            max_percentage=row["max_percentage"],
            requires_mashing=bool(row["requires_mashing"]),
            flavor_profile=row["flavor_profile"],
            description=row["description"],
            notes=row["notes"],
            substitutes=row["substitutes"],
            sources=row["sources"],
            source_type=SourceType(row["source_type"]) if row["source_type"] else None,
            last_updated=datetime.fromisoformat(row["last_updated"]) if row["last_updated"] else None
        )

    # ==================== YEAST OPERATIONS ====================

    def add_yeast(self, yeast: Yeast) -> int:
        """Add or update a yeast strain."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now().isoformat()

            cursor.execute("""
                INSERT INTO yeasts (
                    name, product_code, producer,
                    yeast_type, form, species,
                    attenuation_min, attenuation_max, flocculation,
                    temp_min, temp_max, temp_ideal_min, temp_ideal_max,
                    temp_unit_certain,
                    alcohol_tolerance_min, alcohol_tolerance_max,
                    cell_count_billion,
                    flavor_profile, produces_phenols, produces_sulfur, sta1_positive,
                    beer_styles, description, notes, equivalents,
                    sources, source_type, last_updated
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(name, producer) DO UPDATE SET
                    product_code = COALESCE(excluded.product_code, product_code),
                    yeast_type = COALESCE(excluded.yeast_type, yeast_type),
                    form = COALESCE(excluded.form, form),
                    species = COALESCE(excluded.species, species),
                    attenuation_min = COALESCE(excluded.attenuation_min, attenuation_min),
                    attenuation_max = COALESCE(excluded.attenuation_max, attenuation_max),
                    flocculation = COALESCE(excluded.flocculation, flocculation),
                    temp_min = COALESCE(excluded.temp_min, temp_min),
                    temp_max = COALESCE(excluded.temp_max, temp_max),
                    temp_ideal_min = COALESCE(excluded.temp_ideal_min, temp_ideal_min),
                    temp_ideal_max = COALESCE(excluded.temp_ideal_max, temp_ideal_max),
                    temp_unit_certain = excluded.temp_unit_certain,
                    alcohol_tolerance_min = COALESCE(excluded.alcohol_tolerance_min, alcohol_tolerance_min),
                    alcohol_tolerance_max = COALESCE(excluded.alcohol_tolerance_max, alcohol_tolerance_max),
                    cell_count_billion = COALESCE(excluded.cell_count_billion, cell_count_billion),
                    flavor_profile = COALESCE(excluded.flavor_profile, flavor_profile),
                    produces_phenols = excluded.produces_phenols,
                    produces_sulfur = excluded.produces_sulfur,
                    sta1_positive = excluded.sta1_positive,
                    beer_styles = COALESCE(excluded.beer_styles, beer_styles),
                    description = COALESCE(excluded.description, description),
                    notes = COALESCE(excluded.notes, notes),
                    equivalents = COALESCE(excluded.equivalents, equivalents),
                    sources = CASE
                        WHEN sources IS NULL THEN excluded.sources
                        WHEN excluded.sources IS NULL THEN sources
                        ELSE sources || ',' || excluded.sources
                    END,
                    source_type = COALESCE(excluded.source_type, source_type),
                    last_updated = excluded.last_updated
            """, (
                yeast.name, yeast.product_code, yeast.producer,
                yeast.yeast_type.value if yeast.yeast_type else None,
                yeast.form.value if yeast.form else None,
                yeast.species,
                yeast.attenuation_min, yeast.attenuation_max,
                yeast.flocculation.value if yeast.flocculation else None,
                yeast.temp_min, yeast.temp_max, yeast.temp_ideal_min, yeast.temp_ideal_max,
                1 if yeast.temp_unit_certain else 0,
                yeast.alcohol_tolerance_min, yeast.alcohol_tolerance_max,
                yeast.cell_count_billion,
                yeast.flavor_profile,
                1 if yeast.produces_phenols else 0,
                1 if yeast.produces_sulfur else 0,
                1 if yeast.sta1_positive else 0,
                yeast.beer_styles, yeast.description, yeast.notes, yeast.equivalents,
                yeast.sources,
                yeast.source_type.value if yeast.source_type else None,
                now
            ))

            return cursor.lastrowid

    def get_yeast(self, name: str, producer: Optional[str] = None) -> Optional[Yeast]:
        """Get a yeast by name and optionally producer."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if producer:
                cursor.execute(
                    "SELECT * FROM yeasts WHERE name = ? COLLATE NOCASE AND producer = ? COLLATE NOCASE",
                    (name, producer)
                )
            else:
                cursor.execute("SELECT * FROM yeasts WHERE name = ? COLLATE NOCASE", (name,))
            row = cursor.fetchone()
            if row:
                return self._row_to_yeast(row)
            return None

    def get_yeast_by_code(self, code: str) -> Optional[Yeast]:
        """Get a yeast by product code (e.g., US-05, WLP001)."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM yeasts WHERE product_code = ? COLLATE NOCASE",
                (code,)
            )
            row = cursor.fetchone()
            if row:
                return self._row_to_yeast(row)
            return None

    def search_yeasts(
        self,
        query: Optional[str] = None,
        producer: Optional[str] = None,
        yeast_type: Optional[YeastType] = None,
        form: Optional[YeastForm] = None,
        flocculation: Optional[Flocculation] = None,
        attenuation_min: Optional[float] = None,
        attenuation_max: Optional[float] = None,
        limit: int = 100
    ) -> List[Yeast]:
        """Search yeasts by various criteria."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            conditions = []
            params = []

            if query:
                conditions.append(
                    "(name LIKE ? OR product_code LIKE ? OR flavor_profile LIKE ? OR description LIKE ?)"
                )
                q = f"%{query}%"
                params.extend([q, q, q, q])

            if producer:
                conditions.append("producer LIKE ?")
                params.append(f"%{producer}%")

            if yeast_type:
                conditions.append("yeast_type = ?")
                params.append(yeast_type.value)

            if form:
                conditions.append("form = ?")
                params.append(form.value)

            if flocculation:
                conditions.append("flocculation = ?")
                params.append(flocculation.value)

            if attenuation_min is not None:
                conditions.append("attenuation_max >= ?")
                params.append(attenuation_min)

            if attenuation_max is not None:
                conditions.append("attenuation_min <= ?")
                params.append(attenuation_max)

            where_clause = " AND ".join(conditions) if conditions else "1=1"

            cursor.execute(
                f"SELECT * FROM yeasts WHERE {where_clause} ORDER BY producer, name LIMIT ?",
                params + [limit]
            )

            return [self._row_to_yeast(row) for row in cursor.fetchall()]

    def get_all_yeasts(self) -> List[Yeast]:
        """Get all yeasts."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM yeasts ORDER BY producer, name")
            return [self._row_to_yeast(row) for row in cursor.fetchall()]

    def delete_yeast(self, name: str, producer: Optional[str] = None) -> bool:
        """Delete a yeast by name and optionally producer."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if producer:
                cursor.execute(
                    "DELETE FROM yeasts WHERE name = ? COLLATE NOCASE AND producer = ? COLLATE NOCASE",
                    (name, producer)
                )
            else:
                cursor.execute("DELETE FROM yeasts WHERE name = ? COLLATE NOCASE", (name,))
            return cursor.rowcount > 0

    def _row_to_yeast(self, row: sqlite3.Row) -> Yeast:
        """Convert database row to Yeast object."""
        return Yeast(
            id=row["id"],
            name=row["name"],
            product_code=row["product_code"],
            producer=row["producer"],
            yeast_type=YeastType(row["yeast_type"]) if row["yeast_type"] else None,
            form=YeastForm(row["form"]) if row["form"] else None,
            species=row["species"],
            attenuation_min=row["attenuation_min"],
            attenuation_max=row["attenuation_max"],
            flocculation=Flocculation(row["flocculation"]) if row["flocculation"] else None,
            temp_min=row["temp_min"],
            temp_max=row["temp_max"],
            temp_ideal_min=row["temp_ideal_min"],
            temp_ideal_max=row["temp_ideal_max"],
            temp_unit_certain=bool(row["temp_unit_certain"]) if row["temp_unit_certain"] is not None else True,
            alcohol_tolerance_min=row["alcohol_tolerance_min"],
            alcohol_tolerance_max=row["alcohol_tolerance_max"],
            cell_count_billion=row["cell_count_billion"],
            flavor_profile=row["flavor_profile"],
            produces_phenols=bool(row["produces_phenols"]),
            produces_sulfur=bool(row["produces_sulfur"]),
            sta1_positive=bool(row["sta1_positive"]),
            beer_styles=row["beer_styles"],
            description=row["description"],
            notes=row["notes"],
            equivalents=row["equivalents"],
            sources=row["sources"],
            source_type=SourceType(row["source_type"]) if row["source_type"] else None,
            last_updated=datetime.fromisoformat(row["last_updated"]) if row["last_updated"] else None
        )

    # ==================== STATISTICS ====================

    def get_stats(self) -> dict:
        """Get database statistics."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            stats = {"db_path": str(self.db_path)}

            cursor.execute("SELECT COUNT(*) FROM hops")
            stats["hops_count"] = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM malts")
            stats["malts_count"] = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM yeasts")
            stats["yeasts_count"] = cursor.fetchone()[0]

            cursor.execute("SELECT DISTINCT origin FROM hops WHERE origin IS NOT NULL")
            stats["hop_origins"] = [row[0] for row in cursor.fetchall()]

            cursor.execute("SELECT DISTINCT producer FROM malts WHERE producer IS NOT NULL")
            stats["malt_producers"] = [row[0] for row in cursor.fetchall()]

            cursor.execute("SELECT DISTINCT producer FROM yeasts WHERE producer IS NOT NULL")
            stats["yeast_producers"] = [row[0] for row in cursor.fetchall()]

            return stats

    def vacuum(self):
        """Optimize database by running VACUUM."""
        with self._get_connection() as conn:
            conn.execute("VACUUM")
