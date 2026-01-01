#!/usr/bin/env python3
"""
Command-line interface for the brewing ingredients database.

Usage:
    python -m brew_ingredients.cli [command] [options]

Commands:
    init        Initialize/create the database
    stats       Show database statistics
    schema      Show database schema
    search      Search for ingredients
    get         Get a specific ingredient by name
    export      Export database to JSON
    clear       Clear all items from database

Note: Database population is performed via LLM-driven workflow (see SKILL.md).
"""

from __future__ import annotations
import argparse
import json
import logging
import sys
from pathlib import Path

from .database import IngredientsDatabase, DEFAULT_DB_PATH
from .models import (
    Hop, Malt, Yeast,
    HopPurpose, MaltCategory, Flocculation, YeastForm, YeastType
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def cmd_init(args):
    """Initialize the database."""
    db_path = args.database or DEFAULT_DB_PATH
    logger.info(f"Initializing database at {db_path}")

    db = IngredientsDatabase(db_path)
    stats = db.get_stats()

    print(f"Database initialized at: {db_path}")
    print(f"Current contents:")
    print(f"  Hops: {stats['hops_count']}")
    print(f"  Malts: {stats['malts_count']}")
    print(f"  Yeasts: {stats['yeasts_count']}")


def cmd_clear(args):
    """Clear all items from database."""
    db_path = args.database or DEFAULT_DB_PATH

    if not Path(db_path).exists():
        print(f"Database not found at {db_path}")
        return 1

    if not args.yes:
        confirm = input(f"This will delete ALL ingredients from {db_path}. Continue? [y/N]: ")
        if confirm.lower() != 'y':
            print("Aborted.")
            return 0

    import sqlite3
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("DELETE FROM hops")
    hops_deleted = cursor.rowcount
    cursor.execute("DELETE FROM malts")
    malts_deleted = cursor.rowcount
    cursor.execute("DELETE FROM yeasts")
    yeasts_deleted = cursor.rowcount

    conn.commit()
    conn.close()

    print(f"Cleared database:")
    print(f"  Hops deleted: {hops_deleted}")
    print(f"  Malts deleted: {malts_deleted}")
    print(f"  Yeasts deleted: {yeasts_deleted}")


def cmd_stats(args):
    """Show database statistics."""
    db_path = args.database or DEFAULT_DB_PATH

    if not Path(db_path).exists():
        print(f"Database not found at {db_path}")
        print("Run 'init' or 'populate' first.")
        return 1

    db = IngredientsDatabase(db_path)
    stats = db.get_stats()

    print(f"Database: {stats['db_path']}")
    print(f"\nIngredient counts:")
    print(f"  Hops: {stats['hops_count']}")
    print(f"  Malts: {stats['malts_count']}")
    print(f"  Yeasts: {stats['yeasts_count']}")

    if stats.get('hop_origins'):
        print(f"\nHop origins: {', '.join(sorted(stats['hop_origins']))}")

    if stats.get('malt_producers'):
        print(f"\nMalt producers: {', '.join(sorted(stats['malt_producers']))}")

    if stats.get('yeast_producers'):
        print(f"\nYeast producers: {', '.join(sorted(stats['yeast_producers']))}")


def cmd_schema(args):
    """Show database schema."""
    import sqlite3

    db_path = args.database or DEFAULT_DB_PATH

    if not Path(db_path).exists():
        print(f"Database not found at {db_path}")
        print("Run 'init' or 'populate' first.")
        return 1

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get all table schemas
    cursor.execute("""
        SELECT name, sql FROM sqlite_master
        WHERE type='table' AND name NOT LIKE 'sqlite_%'
        ORDER BY name
    """)
    tables = cursor.fetchall()

    print(f"Database: {db_path}\n")
    print("=" * 60)

    for table_name, create_sql in tables:
        print(f"\n### {table_name.upper()} TABLE ###\n")
        # Pretty print the CREATE statement
        if create_sql:
            # Format nicely
            sql = create_sql.replace("CREATE TABLE", "CREATE TABLE")
            sql = sql.replace(", ", ",\n    ")
            sql = sql.replace("(", "(\n    ", 1)
            sql = sql.replace(")", "\n)", 1)
            print(sql)
        print()

    # Also show column info via PRAGMA for more detail
    if args.verbose:
        print("\n" + "=" * 60)
        print("\nDETAILED COLUMN INFO:\n")
        for table_name, _ in tables:
            print(f"\n### {table_name} ###")
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns = cursor.fetchall()
            print(f"{'Column':<30} {'Type':<15} {'Nullable':<10} {'Default':<15} {'PK'}")
            print("-" * 80)
            for col in columns:
                cid, name, dtype, notnull, default, pk = col
                nullable = "NO" if notnull else "YES"
                default_str = str(default) if default is not None else ""
                pk_str = "YES" if pk else ""
                print(f"{name:<30} {dtype:<15} {nullable:<10} {default_str:<15} {pk_str}")

    conn.close()


def cmd_search(args):
    """Search for ingredients."""
    db_path = args.database or DEFAULT_DB_PATH
    db = IngredientsDatabase(db_path)

    ingredient_type = args.type
    query = args.query
    limit = args.limit

    if ingredient_type == "hop" or ingredient_type is None:
        hops = db.search_hops(query=query, limit=limit)
        if hops:
            print(f"\n=== HOPS ({len(hops)} found) ===")
            for hop in hops:
                alpha = f"{hop.alpha_acid_min}-{hop.alpha_acid_max}%" if hop.alpha_acid_min else "N/A"
                print(f"  {hop.name} ({hop.origin or 'Unknown'}) - Alpha: {alpha}")
                if hop.flavor_profile:
                    print(f"    Flavors: {hop.flavor_profile}")

    if ingredient_type == "malt" or ingredient_type is None:
        malts = db.search_malts(query=query, limit=limit)
        if malts:
            print(f"\n=== MALTS ({len(malts)} found) ===")
            for malt in malts:
                color = f"{malt.color_ebc_min}-{malt.color_ebc_max} EBC" if malt.color_ebc_min else "N/A"
                print(f"  {malt.name} ({malt.producer or 'Unknown'}) - Color: {color}")
                if malt.flavor_profile:
                    print(f"    Flavors: {malt.flavor_profile}")

    if ingredient_type == "yeast" or ingredient_type is None:
        yeasts = db.search_yeasts(query=query, limit=limit)
        if yeasts:
            print(f"\n=== YEASTS ({len(yeasts)} found) ===")
            for yeast in yeasts:
                atten = f"{yeast.attenuation_min}-{yeast.attenuation_max}%" if yeast.attenuation_min else "N/A"
                code = f" ({yeast.product_code})" if yeast.product_code else ""
                print(f"  {yeast.name}{code} [{yeast.producer or 'Unknown'}] - Attenuation: {atten}")
                if yeast.flavor_profile:
                    print(f"    Flavors: {yeast.flavor_profile}")


def cmd_get(args):
    """Get a specific ingredient by name."""
    db_path = args.database or DEFAULT_DB_PATH
    db = IngredientsDatabase(db_path)

    name = args.name
    ingredient_type = args.type

    result = None
    if ingredient_type == "hop":
        result = db.get_hop(name)
    elif ingredient_type == "malt":
        result = db.get_malt(name)
    elif ingredient_type == "yeast":
        result = db.get_yeast(name)
    else:
        # Try all types
        result = db.get_hop(name) or db.get_malt(name) or db.get_yeast(name)

    if result:
        print(_format_ingredient(result))
    else:
        print(f"Ingredient '{name}' not found.")
        return 1


def _format_ingredient(ing) -> str:
    """Format ingredient for display."""
    lines = []

    if isinstance(ing, Hop):
        lines.append(f"=== HOP: {ing.name} ===")
        if ing.origin:
            lines.append(f"Origin: {ing.origin}")
        if ing.producer:
            lines.append(f"Producer: {ing.producer}")
        if ing.alpha_acid_min is not None:
            lines.append(f"Alpha Acid: {ing.alpha_acid_min}-{ing.alpha_acid_max}%")
        if ing.beta_acid_min is not None:
            lines.append(f"Beta Acid: {ing.beta_acid_min}-{ing.beta_acid_max}%")
        if ing.co_humulone_min is not None:
            lines.append(f"Co-humulone: {ing.co_humulone_min}-{ing.co_humulone_max}%")
        if ing.total_oil_min is not None:
            lines.append(f"Total Oil: {ing.total_oil_min}-{ing.total_oil_max} mL/100g")
        if ing.purpose:
            lines.append(f"Purpose: {ing.purpose.value}")
        if ing.flavor_profile:
            lines.append(f"Flavors: {ing.flavor_profile}")
        if ing.aroma_profile:
            lines.append(f"Aromas: {ing.aroma_profile}")
        if ing.substitutes:
            lines.append(f"Substitutes: {ing.substitutes}")
        if ing.description:
            lines.append(f"Description: {ing.description}")
        if ing.source_type:
            lines.append(f"Source Type: {ing.source_type.value}")
        if ing.sources:
            lines.append(f"Sources: {ing.sources}")

    elif isinstance(ing, Malt):
        lines.append(f"=== MALT: {ing.name} ===")
        if ing.producer:
            lines.append(f"Producer: {ing.producer}")
        if ing.origin:
            lines.append(f"Origin: {ing.origin}")
        if ing.category:
            lines.append(f"Category: {ing.category.value}")
        if ing.grain_type:
            lines.append(f"Grain: {ing.grain_type}")
        if ing.color_ebc_min is not None:
            lines.append(f"Color: {ing.color_ebc_min}-{ing.color_ebc_max} EBC")
            lov = ing.color_lovibond_typical()
            if lov:
                lines.append(f"Color: ~{lov:.1f} Lovibond")
        if ing.extract_min is not None:
            lines.append(f"Extract: {ing.extract_min}-{ing.extract_max}% (dry basis)")
        if ing.diastatic_power_min is not None:
            lines.append(f"Diastatic Power: {ing.diastatic_power_min}-{ing.diastatic_power_max} °L")
        if ing.max_percentage is not None:
            lines.append(f"Max Usage: {ing.max_percentage}%")
        if not ing.requires_mashing:
            lines.append("Requires Mashing: No (can steep)")
        if ing.flavor_profile:
            lines.append(f"Flavors: {ing.flavor_profile}")
        if ing.description:
            lines.append(f"Description: {ing.description}")
        if ing.substitutes:
            lines.append(f"Substitutes: {ing.substitutes}")
        if ing.source_type:
            lines.append(f"Source Type: {ing.source_type.value}")
        if ing.sources:
            lines.append(f"Sources: {ing.sources}")

    elif isinstance(ing, Yeast):
        lines.append(f"=== YEAST: {ing.name} ===")
        if ing.product_code:
            lines.append(f"Code: {ing.product_code}")
        if ing.producer:
            lines.append(f"Producer: {ing.producer}")
        if ing.yeast_type:
            lines.append(f"Type: {ing.yeast_type.value}")
        if ing.form:
            lines.append(f"Form: {ing.form.value}")
        if ing.species:
            lines.append(f"Species: {ing.species}")
        if ing.attenuation_min is not None:
            lines.append(f"Attenuation: {ing.attenuation_min}-{ing.attenuation_max}%")
        if ing.flocculation:
            lines.append(f"Flocculation: {ing.flocculation.value}")
        if ing.temp_min is not None:
            lines.append(f"Temperature: {ing.temp_min}-{ing.temp_max}°C")
        if ing.temp_ideal_min is not None:
            lines.append(f"Ideal Temp: {ing.temp_ideal_min}-{ing.temp_ideal_max}°C")
        if ing.alcohol_tolerance_max is not None:
            lines.append(f"Alcohol Tolerance: {ing.alcohol_tolerance_max}% ABV")
        if ing.flavor_profile:
            lines.append(f"Flavors: {ing.flavor_profile}")
        if ing.beer_styles:
            lines.append(f"Beer Styles: {ing.beer_styles}")
        if ing.equivalents:
            lines.append(f"Equivalents: {ing.equivalents}")
        if ing.produces_phenols:
            lines.append("Produces Phenols: Yes")
        if ing.sta1_positive:
            lines.append("STA1+ (Diastaticus): Yes")
        if ing.description:
            lines.append(f"Description: {ing.description}")
        if ing.source_type:
            lines.append(f"Source Type: {ing.source_type.value}")
        if ing.sources:
            lines.append(f"Sources: {ing.sources}")

    return "\n".join(lines)


def cmd_export(args):
    """Export database to JSON."""
    db_path = args.database or DEFAULT_DB_PATH
    db = IngredientsDatabase(db_path)

    output_path = args.output or "brewing_ingredients.json"

    data = {
        "hops": [],
        "malts": [],
        "yeasts": []
    }

    for hop in db.get_all_hops():
        data["hops"].append({
            "name": hop.name,
            "origin": hop.origin,
            "producer": hop.producer,
            "alpha_acid_min": hop.alpha_acid_min,
            "alpha_acid_max": hop.alpha_acid_max,
            "beta_acid_min": hop.beta_acid_min,
            "beta_acid_max": hop.beta_acid_max,
            "purpose": hop.purpose.value if hop.purpose else None,
            "flavor_profile": hop.flavor_profile,
            "substitutes": hop.substitutes,
            "source_type": hop.source_type.value if hop.source_type else None,
            "sources": hop.sources,
        })

    for malt in db.get_all_malts():
        data["malts"].append({
            "name": malt.name,
            "producer": malt.producer,
            "origin": malt.origin,
            "category": malt.category.value if malt.category else None,
            "grain_type": malt.grain_type,
            "color_ebc_min": malt.color_ebc_min,
            "color_ebc_max": malt.color_ebc_max,
            "extract_min": malt.extract_min,
            "extract_max": malt.extract_max,
            "flavor_profile": malt.flavor_profile,
            "source_type": malt.source_type.value if malt.source_type else None,
            "sources": malt.sources,
        })

    for yeast in db.get_all_yeasts():
        data["yeasts"].append({
            "name": yeast.name,
            "product_code": yeast.product_code,
            "producer": yeast.producer,
            "yeast_type": yeast.yeast_type.value if yeast.yeast_type else None,
            "form": yeast.form.value if yeast.form else None,
            "attenuation_min": yeast.attenuation_min,
            "attenuation_max": yeast.attenuation_max,
            "flocculation": yeast.flocculation.value if yeast.flocculation else None,
            "temp_min": yeast.temp_min,
            "temp_max": yeast.temp_max,
            "flavor_profile": yeast.flavor_profile,
            "equivalents": yeast.equivalents,
            "source_type": yeast.source_type.value if yeast.source_type else None,
            "sources": yeast.sources,
        })

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"Exported to {output_path}")
    print(f"  {len(data['hops'])} hops")
    print(f"  {len(data['malts'])} malts")
    print(f"  {len(data['yeasts'])} yeasts")


def main():
    parser = argparse.ArgumentParser(
        description="Brewing Ingredients Database CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        "-d", "--database",
        help=f"Path to database file (default: {DEFAULT_DB_PATH})"
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # init command
    init_parser = subparsers.add_parser("init", help="Initialize database")

    # clear command
    clear_parser = subparsers.add_parser("clear", help="Clear all items from database")
    clear_parser.add_argument(
        "-y", "--yes", action="store_true",
        help="Skip confirmation prompt"
    )

    # stats command
    stats_parser = subparsers.add_parser("stats", help="Show database statistics")

    # schema command
    schema_parser = subparsers.add_parser("schema", help="Show database schema")
    schema_parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Show detailed column info"
    )

    # search command
    search_parser = subparsers.add_parser("search", help="Search for ingredients")
    search_parser.add_argument("query", help="Search query")
    search_parser.add_argument(
        "-t", "--type",
        choices=["hop", "malt", "yeast"],
        help="Ingredient type to search"
    )
    search_parser.add_argument(
        "-l", "--limit", type=int, default=20,
        help="Maximum results (default: 20)"
    )

    # get command
    get_parser = subparsers.add_parser("get", help="Get a specific ingredient")
    get_parser.add_argument("name", help="Ingredient name")
    get_parser.add_argument(
        "-t", "--type",
        choices=["hop", "malt", "yeast"],
        help="Ingredient type"
    )

    # export command
    export_parser = subparsers.add_parser("export", help="Export to JSON")
    export_parser.add_argument(
        "-o", "--output",
        help="Output file path (default: brewing_ingredients.json)"
    )

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 0

    commands = {
        "init": cmd_init,
        "clear": cmd_clear,
        "stats": cmd_stats,
        "schema": cmd_schema,
        "search": cmd_search,
        "get": cmd_get,
        "export": cmd_export,
    }

    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main() or 0)
