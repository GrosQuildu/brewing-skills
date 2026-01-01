#!/usr/bin/env python3
"""
Brewing Ingredients Database Web Viewer

A beautiful single-page web application to browse the brewing ingredients database.
Supports viewing malts, hops, and yeasts with their parameters, sources, and metadata.

Usage:
    python web_viewer.py [--port PORT] [--host HOST]

Features:
    - Main view with statistics for each ingredient type
    - Drill-down by producer with item counts
    - Expandable items showing all parameters
    - Visual indicators for non-canonical sources and uncertain units
    - Global search across all ingredients
    - Producer and item filtering
    - Expand all / collapse all functionality
"""

import argparse
import json
import sqlite3
import webbrowser
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import threading
import time

# Database path
DB_PATH = Path(__file__).parent / "brewing_ingredients.db"


def get_db_connection():
    """Get a database connection with row factory."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_stats():
    """Get overall database statistics."""
    conn = get_db_connection()
    cursor = conn.cursor()

    stats = {}

    # Malts stats
    cursor.execute("SELECT COUNT(*) as count, COUNT(DISTINCT producer) as producers FROM malts")
    row = cursor.fetchone()
    stats['malts'] = {'count': row['count'], 'producers': row['producers']}

    # Hops stats
    cursor.execute("SELECT COUNT(*) as count, COUNT(DISTINCT producer) as producers FROM hops")
    row = cursor.fetchone()
    stats['hops'] = {'count': row['count'], 'producers': row['producers']}

    # Yeasts stats
    cursor.execute("SELECT COUNT(*) as count, COUNT(DISTINCT producer) as producers FROM yeasts")
    row = cursor.fetchone()
    stats['yeasts'] = {'count': row['count'], 'producers': row['producers']}

    conn.close()
    return stats


def get_producers(ingredient_type):
    """Get all producers for an ingredient type with item counts."""
    conn = get_db_connection()
    cursor = conn.cursor()

    table = ingredient_type
    cursor.execute(f"""
        SELECT
            COALESCE(producer, 'Unknown') as producer,
            COUNT(*) as count
        FROM {table}
        GROUP BY producer
        ORDER BY producer
    """)

    producers = [{'name': row['producer'], 'count': row['count']} for row in cursor.fetchall()]
    conn.close()
    return producers


def get_items_by_producer(ingredient_type, producer):
    """Get all items for a specific producer."""
    conn = get_db_connection()
    cursor = conn.cursor()

    table = ingredient_type
    if producer == 'Unknown':
        cursor.execute(f"SELECT * FROM {table} WHERE producer IS NULL ORDER BY name")
    else:
        cursor.execute(f"SELECT * FROM {table} WHERE producer = ? ORDER BY name", (producer,))

    items = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return items


def search_all(query):
    """Search across all ingredient types."""
    conn = get_db_connection()
    cursor = conn.cursor()
    results = {'malts': [], 'hops': [], 'yeasts': []}

    q = f"%{query}%"

    # Search malts
    cursor.execute("""
        SELECT *, 'malt' as type FROM malts
        WHERE name LIKE ? OR producer LIKE ? OR flavor_profile LIKE ? OR description LIKE ?
        ORDER BY name LIMIT 50
    """, (q, q, q, q))
    results['malts'] = [dict(row) for row in cursor.fetchall()]

    # Search hops
    cursor.execute("""
        SELECT *, 'hop' as type FROM hops
        WHERE name LIKE ? OR producer LIKE ? OR flavor_profile LIKE ? OR aroma_profile LIKE ? OR description LIKE ?
        ORDER BY name LIMIT 50
    """, (q, q, q, q, q))
    results['hops'] = [dict(row) for row in cursor.fetchall()]

    # Search yeasts
    cursor.execute("""
        SELECT *, 'yeast' as type FROM yeasts
        WHERE name LIKE ? OR producer LIKE ? OR product_code LIKE ? OR flavor_profile LIKE ? OR description LIKE ?
        ORDER BY name LIMIT 50
    """, (q, q, q, q, q))
    results['yeasts'] = [dict(row) for row in cursor.fetchall()]

    conn.close()
    return results


# HTML template with embedded CSS and JavaScript
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Brewing Ingredients Database</title>
    <style>
        :root {
            --bg-primary: #1a1a2e;
            --bg-secondary: #16213e;
            --bg-tertiary: #0f3460;
            --bg-card: #1f2940;
            --accent-primary: #e94560;
            --accent-secondary: #f39c12;
            --accent-tertiary: #3498db;
            --text-primary: #ecf0f1;
            --text-secondary: #bdc3c7;
            --text-muted: #7f8c8d;
            --border-color: #34495e;
            --canonical-bg: transparent;
            --composed-bg: rgba(243, 156, 18, 0.15);
            --uncertain-bg: rgba(233, 69, 96, 0.2);
            --uncertain-border: #e94560;
            --shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
            --radius: 8px;
        }

        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            min-height: 100vh;
            line-height: 1.6;
        }

        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
        }

        header {
            background: var(--bg-secondary);
            padding: 15px 0;
            margin-bottom: 0;
            border-bottom: 2px solid var(--accent-primary);
            position: sticky;
            top: 0;
            z-index: 100;
        }

        header .container {
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 15px;
        }

        h1 {
            font-size: 1.8rem;
            color: var(--text-primary);
            display: flex;
            align-items: center;
            gap: 10px;
        }

        h1 .logo {
            font-size: 2rem;
        }

        .search-container {
            display: flex;
            gap: 10px;
            align-items: center;
        }

        .search-input {
            padding: 10px 15px;
            border: 2px solid var(--border-color);
            border-radius: var(--radius);
            background: var(--bg-tertiary);
            color: var(--text-primary);
            font-size: 1rem;
            width: 300px;
            transition: border-color 0.3s;
        }

        .search-input:focus {
            outline: none;
            border-color: var(--accent-primary);
        }

        .search-input::placeholder {
            color: var(--text-muted);
        }

        .btn {
            padding: 10px 20px;
            border: none;
            border-radius: var(--radius);
            cursor: pointer;
            font-size: 0.95rem;
            font-weight: 500;
            transition: all 0.3s;
        }

        .btn-primary {
            background: var(--accent-primary);
            color: white;
        }

        .btn-primary:hover {
            background: #c13a52;
        }

        .btn-secondary {
            background: var(--bg-tertiary);
            color: var(--text-primary);
            border: 1px solid var(--border-color);
        }

        .btn-secondary:hover {
            background: var(--border-color);
        }

        /* Navigation breadcrumb */
        .breadcrumb {
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 0;
            padding: 10px 20px;
            background: #1a2744;
            border-radius: 0;
            position: sticky;
            top: 123px;
            z-index: 99;
        }

        .breadcrumb-item {
            color: var(--accent-tertiary);
            cursor: pointer;
            transition: color 0.3s;
        }

        .breadcrumb-item:hover {
            color: var(--accent-primary);
        }

        .breadcrumb-separator {
            color: var(--text-muted);
        }

        .breadcrumb-current {
            color: var(--text-primary);
            font-weight: 500;
        }

        /* Main view - Stats cards */
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }

        .stat-card {
            background: var(--bg-card);
            border-radius: var(--radius);
            padding: 30px;
            text-align: center;
            cursor: pointer;
            transition: all 0.3s;
            border: 2px solid transparent;
            box-shadow: var(--shadow);
        }

        .stat-card:hover {
            transform: translateY(-5px);
            border-color: var(--accent-primary);
        }

        .stat-card.malts { border-left: 4px solid #f39c12; }
        .stat-card.hops { border-left: 4px solid #27ae60; }
        .stat-card.yeasts { border-left: 4px solid #9b59b6; }

        .stat-card h2 {
            font-size: 1.5rem;
            margin-bottom: 15px;
            color: var(--text-primary);
        }

        .stat-number {
            font-size: 3rem;
            font-weight: 700;
            color: var(--accent-primary);
        }

        .stat-label {
            color: var(--text-secondary);
            font-size: 1rem;
            margin-top: 5px;
        }

        .stat-producers {
            margin-top: 15px;
            padding-top: 15px;
            border-top: 1px solid var(--border-color);
            color: var(--text-muted);
        }

        /* Controls bar */
        .controls-bar {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            padding: 10px 20px;
            background: #1a2744;
            border-radius: 0;
            flex-wrap: wrap;
            gap: 15px;
            position: sticky;
            top: 213px;
            z-index: 97;
            border-bottom: 2px solid var(--accent-primary);
        }

        .filter-input {
            padding: 8px 12px;
            border: 1px solid var(--border-color);
            border-radius: var(--radius);
            background: var(--bg-tertiary);
            color: var(--text-primary);
            font-size: 0.9rem;
            width: 200px;
        }

        .filter-input:focus {
            outline: none;
            border-color: var(--accent-tertiary);
        }

        .toggle-container {
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .toggle-switch {
            position: relative;
            width: 50px;
            height: 26px;
        }

        .toggle-switch input {
            opacity: 0;
            width: 0;
            height: 0;
        }

        .toggle-slider {
            position: absolute;
            cursor: pointer;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background-color: var(--border-color);
            transition: 0.4s;
            border-radius: 26px;
        }

        .toggle-slider:before {
            position: absolute;
            content: "";
            height: 20px;
            width: 20px;
            left: 3px;
            bottom: 3px;
            background-color: white;
            transition: 0.4s;
            border-radius: 50%;
        }

        input:checked + .toggle-slider {
            background-color: var(--accent-primary);
        }

        input:checked + .toggle-slider:before {
            transform: translateX(24px);
        }

        /* Producer list */
        .producer-list {
            display: flex;
            flex-direction: column;
            gap: 10px;
        }

        .producer-card {
            background: var(--bg-card);
            border-radius: var(--radius);
            overflow: hidden;
            box-shadow: var(--shadow);
            transition: all 0.3s;
        }

        .producer-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 15px 20px;
            cursor: pointer;
            transition: background 0.3s;
        }

        .producer-header:hover {
            background: var(--bg-tertiary);
        }

        .producer-name {
            font-size: 1.1rem;
            font-weight: 500;
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .producer-count {
            background: var(--accent-tertiary);
            color: white;
            padding: 3px 10px;
            border-radius: 15px;
            font-size: 0.85rem;
        }

        .expand-icon {
            transition: transform 0.3s;
            color: var(--text-muted);
        }

        .producer-card.expanded .expand-icon {
            transform: rotate(180deg);
        }

        .producer-items {
            display: none;
            padding: 0 20px 20px;
            border-top: 1px solid var(--border-color);
        }

        .producer-card.expanded .producer-items {
            display: block;
        }

        /* Item cards */
        .item-card {
            background: var(--bg-secondary);
            border-radius: var(--radius);
            margin-top: 15px;
            padding: 15px;
            border-left: 3px solid var(--accent-tertiary);
        }

        .item-card.composed {
            background: var(--composed-bg);
            border-left-color: var(--accent-secondary);
        }

        .item-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            margin-bottom: 10px;
            flex-wrap: wrap;
            gap: 10px;
        }

        .item-name {
            font-size: 1.1rem;
            font-weight: 600;
            color: var(--text-primary);
        }

        .item-badges {
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
        }

        .badge {
            padding: 3px 8px;
            border-radius: 4px;
            font-size: 0.75rem;
            font-weight: 500;
            text-transform: uppercase;
        }

        .badge-canonical {
            background: var(--accent-tertiary);
            color: white;
        }

        .badge-composed {
            background: var(--accent-secondary);
            color: #1a1a2e;
        }

        .badge-category {
            background: var(--bg-tertiary);
            color: var(--text-secondary);
        }

        /* Parameters grid */
        .params-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
            gap: 10px;
            margin-top: 15px;
        }

        .param {
            padding: 8px 12px;
            background: var(--bg-primary);
            border-radius: 4px;
            font-size: 0.9rem;
        }

        .param.uncertain {
            background: var(--uncertain-bg);
            border: 1px dashed var(--uncertain-border);
        }

        .param-label {
            color: var(--text-muted);
            font-size: 0.8rem;
            display: block;
            margin-bottom: 2px;
        }

        .param-value {
            color: var(--text-primary);
            font-weight: 500;
        }

        .uncertain-icon {
            color: var(--uncertain-border);
            margin-left: 5px;
            cursor: help;
        }

        /* Description and notes */
        .item-description {
            margin-top: 15px;
            padding: 10px;
            background: var(--bg-primary);
            border-radius: 4px;
            color: var(--text-secondary);
            font-size: 0.9rem;
        }

        /* Sources */
        .sources-section {
            margin-top: 15px;
            padding-top: 15px;
            border-top: 1px solid var(--border-color);
        }

        .sources-title {
            color: var(--text-muted);
            font-size: 0.85rem;
            margin-bottom: 8px;
        }

        .source-link {
            display: inline-block;
            color: var(--accent-tertiary);
            text-decoration: none;
            font-size: 0.85rem;
            margin-right: 15px;
            margin-bottom: 5px;
            transition: color 0.3s;
        }

        .source-link:hover {
            color: var(--accent-primary);
        }

        /* Search results */
        .search-results {
            margin-top: 20px;
        }

        .search-section {
            margin-bottom: 30px;
        }

        .search-section h3 {
            color: var(--text-primary);
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 2px solid var(--border-color);
        }

        .search-section h3.malts { border-color: #f39c12; }
        .search-section h3.hops { border-color: #27ae60; }
        .search-section h3.yeasts { border-color: #9b59b6; }

        /* Legend */
        .legend {
            display: flex;
            gap: 20px;
            padding: 10px 20px;
            background: #121f38;
            border-radius: 0;
            margin-bottom: 0;
            flex-wrap: wrap;
            position: sticky;
            top: 169px;
            z-index: 98;
            border-bottom: 1px solid var(--border-color);
        }

        .legend-item {
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 0.9rem;
            color: var(--text-secondary);
        }

        .legend-color {
            width: 20px;
            height: 20px;
            border-radius: 4px;
        }

        .legend-color.canonical {
            background: var(--accent-tertiary);
        }

        .legend-color.composed {
            background: var(--accent-secondary);
        }

        .legend-color.uncertain {
            background: var(--uncertain-bg);
            border: 1px dashed var(--uncertain-border);
        }

        /* Loading state */
        .loading {
            text-align: center;
            padding: 40px;
            color: var(--text-muted);
        }

        .spinner {
            width: 40px;
            height: 40px;
            border: 4px solid var(--border-color);
            border-top-color: var(--accent-primary);
            border-radius: 50%;
            animation: spin 1s linear infinite;
            margin: 0 auto 15px;
        }

        @keyframes spin {
            to { transform: rotate(360deg); }
        }

        /* Empty state */
        .empty-state {
            text-align: center;
            padding: 60px 20px;
            color: var(--text-muted);
        }

        .empty-state-icon {
            font-size: 4rem;
            margin-bottom: 20px;
        }

        /* Responsive */
        @media (max-width: 768px) {
            h1 { font-size: 1.4rem; }
            .search-input { width: 100%; }
            .stat-number { font-size: 2.5rem; }
            .params-grid { grid-template-columns: 1fr; }
        }
    </style>
</head>
<body>
    <header>
        <div class="container">
            <h1><span class="logo">🍺</span> Brewing Ingredients Database</h1>
            <div class="search-container">
                <input type="text" class="search-input" id="globalSearch" placeholder="Search all ingredients...">
                <button class="btn btn-primary" onclick="performGlobalSearch()">Search</button>
            </div>
        </div>
    </header>

    <main class="container">
        <div id="breadcrumb" class="breadcrumb" style="display: none;">
            <span class="breadcrumb-item" onclick="showMainView()">Home</span>
        </div>

        <div id="legend" class="legend" style="display: none;">
            <div class="legend-item">
                <div class="legend-color canonical"></div>
                <span>Canonical source (official producer data)</span>
            </div>
            <div class="legend-item">
                <div class="legend-color composed"></div>
                <span>Composed source (aggregated data)</span>
            </div>
            <div class="legend-item">
                <div class="legend-color uncertain"></div>
                <span>Uncertain unit conversion</span>
            </div>
        </div>

        <div id="content">
            <div class="loading">
                <div class="spinner"></div>
                Loading...
            </div>
        </div>
    </main>

    <script>
        // State management
        let currentView = 'main';
        let currentType = null;
        let expandedProducers = new Set();
        let producersData = [];
        let expandAll = false;

        // API calls
        async function fetchStats() {
            const response = await fetch('/api/stats');
            return response.json();
        }

        async function fetchProducers(type) {
            const response = await fetch(`/api/producers/${type}`);
            return response.json();
        }

        async function fetchItems(type, producer) {
            const response = await fetch(`/api/items/${type}/${encodeURIComponent(producer)}`);
            return response.json();
        }

        async function searchAll(query) {
            const response = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
            return response.json();
        }

        // View rendering
        function showMainView() {
            currentView = 'main';
            currentType = null;
            expandedProducers.clear();
            document.getElementById('breadcrumb').style.display = 'none';
            document.getElementById('legend').style.display = 'none';
            loadMainView();
        }

        async function loadMainView() {
            const content = document.getElementById('content');
            content.innerHTML = '<div class="loading"><div class="spinner"></div>Loading...</div>';

            try {
                const stats = await fetchStats();
                content.innerHTML = `
                    <div class="stats-grid">
                        <div class="stat-card malts" onclick="showTypeView('malts')">
                            <h2>Malts</h2>
                            <div class="stat-number">${stats.malts.count}</div>
                            <div class="stat-label">varieties</div>
                            <div class="stat-producers">${stats.malts.producers} producers</div>
                        </div>
                        <div class="stat-card hops" onclick="showTypeView('hops')">
                            <h2>Hops</h2>
                            <div class="stat-number">${stats.hops.count}</div>
                            <div class="stat-label">varieties</div>
                            <div class="stat-producers">${stats.hops.producers} producers</div>
                        </div>
                        <div class="stat-card yeasts" onclick="showTypeView('yeasts')">
                            <h2>Yeasts</h2>
                            <div class="stat-number">${stats.yeasts.count}</div>
                            <div class="stat-label">strains</div>
                            <div class="stat-producers">${stats.yeasts.producers} producers</div>
                        </div>
                    </div>
                `;
            } catch (error) {
                content.innerHTML = `<div class="empty-state"><div class="empty-state-icon">❌</div>Error loading data: ${error.message}</div>`;
            }
        }

        async function showTypeView(type) {
            currentView = 'type';
            currentType = type;
            expandedProducers.clear();
            expandAll = false;

            const typeName = type.charAt(0).toUpperCase() + type.slice(1);
            document.getElementById('breadcrumb').style.display = 'flex';
            document.getElementById('breadcrumb').innerHTML = `
                <span class="breadcrumb-item" onclick="showMainView()">Home</span>
                <span class="breadcrumb-separator">›</span>
                <span class="breadcrumb-current">${typeName}</span>
            `;
            document.getElementById('legend').style.display = 'flex';

            const content = document.getElementById('content');
            content.innerHTML = '<div class="loading"><div class="spinner"></div>Loading...</div>';

            try {
                producersData = await fetchProducers(type);
                renderProducerList(true);
            } catch (error) {
                content.innerHTML = `<div class="empty-state"><div class="empty-state-icon">❌</div>Error loading data: ${error.message}</div>`;
            }
        }

        function renderProducerList(initialRender = false) {
            const content = document.getElementById('content');
            const filteredProducers = filterProducers(producersData);

            // Only render controls bar on initial render
            if (initialRender) {
                let html = `
                    <div class="controls-bar">
                        <div style="display: flex; gap: 10px; align-items: center;">
                            <input type="text" class="filter-input" id="producerFilter" placeholder="Filter producers..." oninput="filterList()">
                            <input type="text" class="filter-input" id="itemFilter" placeholder="Filter items..." oninput="filterList()">
                        </div>
                        <div class="toggle-container">
                            <span>Expand All</span>
                            <label class="toggle-switch">
                                <input type="checkbox" id="expandAllToggle" ${expandAll ? 'checked' : ''} onchange="toggleExpandAll()">
                                <span class="toggle-slider"></span>
                            </label>
                        </div>
                    </div>
                    <div id="producer-list-container" class="producer-list"></div>
                `;
                content.innerHTML = html;
            }

            // Update only the producer list
            const listContainer = document.getElementById('producer-list-container');
            let listHtml = '';

            if (filteredProducers.length === 0) {
                listHtml = '<div class="empty-state"><div class="empty-state-icon">🔍</div>No producers found matching your filter</div>';
            } else {
                for (const producer of filteredProducers) {
                    const isExpanded = expandAll || expandedProducers.has(producer.name);
                    listHtml += `
                        <div class="producer-card ${isExpanded ? 'expanded' : ''}" id="producer-${encodeId(producer.name)}">
                            <div class="producer-header" onclick="toggleProducer('${escapeJs(producer.name)}')">
                                <div class="producer-name">
                                    ${escapeHtml(producer.name)}
                                    <span class="producer-count">${producer.count} items</span>
                                </div>
                                <span class="expand-icon">▼</span>
                            </div>
                            <div class="producer-items" id="items-${encodeId(producer.name)}">
                                ${isExpanded ? '<div class="loading"><div class="spinner"></div>Loading items...</div>' : ''}
                            </div>
                        </div>
                    `;
                }
            }

            listContainer.innerHTML = listHtml;

            // Load expanded items
            if (expandAll) {
                filteredProducers.forEach(p => loadProducerItems(p.name));
            } else {
                expandedProducers.forEach(name => {
                    if (filteredProducers.some(p => p.name === name)) {
                        loadProducerItems(name);
                    }
                });
            }
        }

        function filterList() {
            window.producerFilterValue = document.getElementById('producerFilter')?.value || '';
            window.itemFilterValue = document.getElementById('itemFilter')?.value || '';
            renderProducerList(false);
        }

        function filterProducers(producers) {
            const producerFilter = (document.getElementById('producerFilter')?.value || '').toLowerCase();
            window.producerFilterValue = producerFilter;
            return producers.filter(p => p.name.toLowerCase().includes(producerFilter));
        }

        async function toggleProducer(name) {
            const card = document.getElementById(`producer-${encodeId(name)}`);
            const itemsContainer = document.getElementById(`items-${encodeId(name)}`);

            if (expandedProducers.has(name)) {
                expandedProducers.delete(name);
                card.classList.remove('expanded');
            } else {
                expandedProducers.add(name);
                card.classList.add('expanded');
                itemsContainer.innerHTML = '<div class="loading"><div class="spinner"></div>Loading items...</div>';
                await loadProducerItems(name);
            }
        }

        async function loadProducerItems(producer) {
            const itemsContainer = document.getElementById(`items-${encodeId(producer)}`);
            if (!itemsContainer) return;

            try {
                const items = await fetchItems(currentType, producer);
                const itemFilter = (document.getElementById('itemFilter')?.value || '').toLowerCase();
                window.itemFilterValue = itemFilter;

                const filteredItems = items.filter(item =>
                    item.name.toLowerCase().includes(itemFilter) ||
                    (item.flavor_profile && item.flavor_profile.toLowerCase().includes(itemFilter)) ||
                    (item.description && item.description.toLowerCase().includes(itemFilter))
                );

                if (filteredItems.length === 0) {
                    itemsContainer.innerHTML = '<div class="empty-state">No items match your filter</div>';
                } else {
                    itemsContainer.innerHTML = filteredItems.map(item => renderItem(item, currentType)).join('');
                }
            } catch (error) {
                itemsContainer.innerHTML = `<div class="empty-state">Error loading items: ${error.message}</div>`;
            }
        }

        function toggleExpandAll() {
            expandAll = document.getElementById('expandAllToggle').checked;
            if (expandAll) {
                producersData.forEach(p => expandedProducers.add(p.name));
            } else {
                expandedProducers.clear();
            }
            renderProducerList(false);
        }

        function renderItem(item, type, showProducer = false) {
            const isComposed = item.source_type === 'composed';
            let html = `<div class="item-card ${isComposed ? 'composed' : ''}">`;

            // Header
            html += `<div class="item-header">`;
            html += `<div class="item-name">${escapeHtml(item.name)}`;
            if (type === 'yeasts' && item.product_code) {
                html += ` <span style="color: var(--text-muted); font-weight: normal;">(${escapeHtml(item.product_code)})</span>`;
            }
            if (showProducer && item.producer) {
                html += ` <span style="color: var(--text-secondary); font-weight: normal;">— ${escapeHtml(item.producer)}</span>`;
            }
            html += `</div>`;

            html += `<div class="item-badges">`;
            if (item.source_type === 'canonical') {
                html += `<span class="badge badge-canonical">Canonical</span>`;
            } else if (item.source_type === 'composed') {
                html += `<span class="badge badge-composed">Composed</span>`;
            }
            if (type === 'malts' && item.category) {
                html += `<span class="badge badge-category">${escapeHtml(item.category)}</span>`;
            }
            if (type === 'hops' && item.purpose) {
                html += `<span class="badge badge-category">${escapeHtml(item.purpose)}</span>`;
            }
            if (type === 'yeasts' && item.yeast_type) {
                html += `<span class="badge badge-category">${escapeHtml(item.yeast_type)}</span>`;
            }
            if (type === 'yeasts' && item.form) {
                html += `<span class="badge badge-category">${escapeHtml(item.form)}</span>`;
            }
            html += `</div></div>`;

            // Parameters
            html += `<div class="params-grid">`;
            html += renderParams(item, type);
            html += `</div>`;

            // Description
            if (item.description) {
                html += `<div class="item-description">${escapeHtml(item.description)}</div>`;
            }

            // Flavor profile
            if (item.flavor_profile) {
                html += `<div class="item-description"><strong>Flavor:</strong> ${escapeHtml(item.flavor_profile)}</div>`;
            }
            if (type === 'hops' && item.aroma_profile) {
                html += `<div class="item-description"><strong>Aroma:</strong> ${escapeHtml(item.aroma_profile)}</div>`;
            }

            // Sources
            if (item.sources) {
                html += `<div class="sources-section">`;
                html += `<div class="sources-title">Sources:</div>`;
                const sources = item.sources.split(',').map(s => s.trim()).filter(s => s);
                sources.forEach(source => {
                    const displayUrl = source.length > 50 ? source.substring(0, 50) + '...' : source;
                    html += `<a href="${escapeHtml(source)}" class="source-link" target="_blank" rel="noopener">${escapeHtml(displayUrl)}</a>`;
                });
                html += `</div>`;
            }

            html += `</div>`;
            return html;
        }

        function renderParams(item, type) {
            let html = '';

            if (type === 'malts') {
                if (item.color_ebc_min != null || item.color_ebc_max != null) {
                    const uncertain = !item.color_unit_certain;
                    html += renderParam('Color (EBC)', formatRange(item.color_ebc_min, item.color_ebc_max), uncertain);
                }
                if (item.extract_min != null || item.extract_max != null) {
                    html += renderParam('Extract (%)', formatRange(item.extract_min, item.extract_max, 1));
                }
                if (item.moisture_min != null || item.moisture_max != null) {
                    html += renderParam('Moisture (%)', formatRange(item.moisture_min, item.moisture_max, 1));
                }
                if (item.protein_min != null || item.protein_max != null) {
                    html += renderParam('Protein (%)', formatRange(item.protein_min, item.protein_max, 1));
                }
                if (item.kolbach_index_min != null || item.kolbach_index_max != null) {
                    html += renderParam('Kolbach Index', formatRange(item.kolbach_index_min, item.kolbach_index_max, 1));
                }
                if (item.diastatic_power_min != null || item.diastatic_power_max != null) {
                    const uncertain = !item.diastatic_power_unit_certain;
                    html += renderParam('Diastatic Power (°L)', formatRange(item.diastatic_power_min, item.diastatic_power_max), uncertain);
                }
                if (item.diastatic_power_wk_min != null || item.diastatic_power_wk_max != null) {
                    html += renderParam('Diastatic Power (°WK)', formatRange(item.diastatic_power_wk_min, item.diastatic_power_wk_max));
                }
                if (item.friability_min != null || item.friability_max != null) {
                    html += renderParam('Friability (%)', formatRange(item.friability_min, item.friability_max, 1));
                }
                if (item.max_percentage != null) {
                    html += renderParam('Max in Grist', item.max_percentage + '%');
                }
                if (item.grain_type) {
                    html += renderParam('Grain', item.grain_type);
                }
                if (item.origin) {
                    html += renderParam('Origin', item.origin);
                }
            }

            if (type === 'hops') {
                if (item.alpha_acid_min != null || item.alpha_acid_max != null) {
                    html += renderParam('Alpha Acid (%)', formatRange(item.alpha_acid_min, item.alpha_acid_max, 1));
                }
                if (item.beta_acid_min != null || item.beta_acid_max != null) {
                    html += renderParam('Beta Acid (%)', formatRange(item.beta_acid_min, item.beta_acid_max, 1));
                }
                if (item.co_humulone_min != null || item.co_humulone_max != null) {
                    html += renderParam('Co-Humulone (%)', formatRange(item.co_humulone_min, item.co_humulone_max));
                }
                if (item.total_oil_min != null || item.total_oil_max != null) {
                    html += renderParam('Total Oil (mL/100g)', formatRange(item.total_oil_min, item.total_oil_max, 1));
                }
                if (item.myrcene_min != null || item.myrcene_max != null) {
                    html += renderParam('Myrcene (%)', formatRange(item.myrcene_min, item.myrcene_max));
                }
                if (item.humulene_min != null || item.humulene_max != null) {
                    html += renderParam('Humulene (%)', formatRange(item.humulene_min, item.humulene_max));
                }
                if (item.caryophyllene_min != null || item.caryophyllene_max != null) {
                    html += renderParam('Caryophyllene (%)', formatRange(item.caryophyllene_min, item.caryophyllene_max));
                }
                if (item.farnesene_min != null || item.farnesene_max != null) {
                    html += renderParam('Farnesene (%)', formatRange(item.farnesene_min, item.farnesene_max));
                }
                if (item.origin) {
                    html += renderParam('Origin', item.origin);
                }
                if (item.year_released) {
                    html += renderParam('Released', item.year_released);
                }
                if (item.substitutes) {
                    html += renderParam('Substitutes', item.substitutes);
                }
            }

            if (type === 'yeasts') {
                if (item.attenuation_min != null || item.attenuation_max != null) {
                    html += renderParam('Attenuation (%)', formatRange(item.attenuation_min, item.attenuation_max));
                }
                if (item.temp_min != null || item.temp_max != null) {
                    const uncertain = !item.temp_unit_certain;
                    html += renderParam('Temp Range (°C)', formatRange(item.temp_min, item.temp_max), uncertain);
                }
                if (item.temp_ideal_min != null || item.temp_ideal_max != null) {
                    html += renderParam('Ideal Temp (°C)', formatRange(item.temp_ideal_min, item.temp_ideal_max));
                }
                if (item.flocculation) {
                    html += renderParam('Flocculation', item.flocculation.replace(/_/g, ' '));
                }
                if (item.alcohol_tolerance_min != null || item.alcohol_tolerance_max != null) {
                    html += renderParam('Alcohol Tolerance (%)', formatRange(item.alcohol_tolerance_min, item.alcohol_tolerance_max));
                }
                if (item.species) {
                    html += renderParam('Species', item.species);
                }
                if (item.cell_count_billion) {
                    html += renderParam('Cell Count', item.cell_count_billion + 'B');
                }
                if (item.produces_phenols) {
                    html += renderParam('Produces Phenols', 'Yes');
                }
                if (item.produces_sulfur) {
                    html += renderParam('Produces Sulfur', 'Yes');
                }
                if (item.sta1_positive) {
                    html += renderParam('STA1+ (Diastaticus)', 'Yes');
                }
                if (item.beer_styles) {
                    html += renderParam('Beer Styles', item.beer_styles);
                }
                if (item.equivalents) {
                    html += renderParam('Equivalents', item.equivalents);
                }
            }

            return html;
        }

        function renderParam(label, value, uncertain = false) {
            const uncertainClass = uncertain ? 'uncertain' : '';
            const uncertainIcon = uncertain ? '<span class="uncertain-icon" title="Unit conversion may be uncertain">⚠</span>' : '';
            return `
                <div class="param ${uncertainClass}">
                    <span class="param-label">${escapeHtml(label)}${uncertainIcon}</span>
                    <span class="param-value">${escapeHtml(String(value))}</span>
                </div>
            `;
        }

        function formatRange(min, max, decimals = 0) {
            if (min == null && max == null) return '-';
            if (min == null) return '≤' + max.toFixed(decimals);
            if (max == null) return '≥' + min.toFixed(decimals);
            if (min === max) return min.toFixed(decimals);
            return min.toFixed(decimals) + ' - ' + max.toFixed(decimals);
        }

        // Global search
        async function performGlobalSearch() {
            const query = document.getElementById('globalSearch').value.trim();
            if (!query) {
                showMainView();
                return;
            }

            currentView = 'search';
            currentType = null;
            document.getElementById('breadcrumb').style.display = 'flex';
            document.getElementById('breadcrumb').innerHTML = `
                <span class="breadcrumb-item" onclick="showMainView()">Home</span>
                <span class="breadcrumb-separator">›</span>
                <span class="breadcrumb-current">Search: "${escapeHtml(query)}"</span>
            `;
            document.getElementById('legend').style.display = 'flex';

            const content = document.getElementById('content');
            content.innerHTML = '<div class="loading"><div class="spinner"></div>Searching...</div>';

            try {
                const results = await searchAll(query);
                let html = '<div class="search-results">';

                // Malts
                html += `<div class="search-section">`;
                html += `<h3 class="malts">Malts (${results.malts.length} results)</h3>`;
                if (results.malts.length === 0) {
                    html += `<div class="empty-state">No malts found</div>`;
                } else {
                    html += results.malts.map(item => renderItem(item, 'malts', true)).join('');
                }
                html += `</div>`;

                // Hops
                html += `<div class="search-section">`;
                html += `<h3 class="hops">Hops (${results.hops.length} results)</h3>`;
                if (results.hops.length === 0) {
                    html += `<div class="empty-state">No hops found</div>`;
                } else {
                    html += results.hops.map(item => renderItem(item, 'hops', true)).join('');
                }
                html += `</div>`;

                // Yeasts
                html += `<div class="search-section">`;
                html += `<h3 class="yeasts">Yeasts (${results.yeasts.length} results)</h3>`;
                if (results.yeasts.length === 0) {
                    html += `<div class="empty-state">No yeasts found</div>`;
                } else {
                    html += results.yeasts.map(item => renderItem(item, 'yeasts', true)).join('');
                }
                html += `</div>`;

                html += '</div>';
                content.innerHTML = html;
            } catch (error) {
                content.innerHTML = `<div class="empty-state"><div class="empty-state-icon">❌</div>Error searching: ${error.message}</div>`;
            }
        }

        // Utility functions
        function escapeHtml(text) {
            if (text == null) return '';
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        function escapeJs(text) {
            return text.replace(/\\\\/g, '\\\\\\\\').replace(/'/g, "\\\\'").replace(/"/g, '\\\\"');
        }

        function encodeId(text) {
            return btoa(encodeURIComponent(text)).replace(/[+/=]/g, '_');
        }

        // Initialize
        document.getElementById('globalSearch').addEventListener('keypress', function(e) {
            if (e.key === 'Enter') performGlobalSearch();
        });

        loadMainView();
    </script>
</body>
</html>
"""


class RequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the web viewer."""

    def log_message(self, format, *args):
        """Suppress default logging."""
        pass

    def send_json(self, data, status=200):
        """Send JSON response."""
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def send_html(self, html, status=200):
        """Send HTML response."""
        self.send_response(status)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(html.encode())

    def do_GET(self):
        """Handle GET requests."""
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        try:
            if path == '/' or path == '/index.html':
                self.send_html(HTML_TEMPLATE)

            elif path == '/api/stats':
                self.send_json(get_stats())

            elif path.startswith('/api/producers/'):
                ingredient_type = path.split('/')[-1]
                if ingredient_type in ('malts', 'hops', 'yeasts'):
                    self.send_json(get_producers(ingredient_type))
                else:
                    self.send_json({'error': 'Invalid ingredient type'}, 400)

            elif path.startswith('/api/items/'):
                parts = path.split('/')
                if len(parts) >= 4:
                    ingredient_type = parts[3]
                    producer = '/'.join(parts[4:])  # Handle producer names with slashes
                    from urllib.parse import unquote
                    producer = unquote(producer)
                    if ingredient_type in ('malts', 'hops', 'yeasts'):
                        self.send_json(get_items_by_producer(ingredient_type, producer))
                    else:
                        self.send_json({'error': 'Invalid ingredient type'}, 400)
                else:
                    self.send_json({'error': 'Invalid path'}, 400)

            elif path == '/api/search':
                q = query.get('q', [''])[0]
                if q:
                    self.send_json(search_all(q))
                else:
                    self.send_json({'malts': [], 'hops': [], 'yeasts': []})

            else:
                self.send_json({'error': 'Not found'}, 404)

        except Exception as e:
            self.send_json({'error': str(e)}, 500)


def open_browser(port):
    """Open browser after a short delay."""
    time.sleep(1)
    webbrowser.open(f'http://localhost:{port}')


def main():
    parser = argparse.ArgumentParser(description='Brewing Ingredients Database Web Viewer')
    parser.add_argument('--port', '-p', type=int, default=8080, help='Port to run the server on (default: 8080)')
    parser.add_argument('--host', '-H', type=str, default='localhost', help='Host to bind to (default: localhost)')
    parser.add_argument('--no-browser', '-n', action='store_true', help='Do not open browser automatically')
    args = parser.parse_args()

    # Check database exists
    if not DB_PATH.exists():
        print(f"Error: Database not found at {DB_PATH}")
        print("Please ensure the database exists before running the web viewer.")
        return 1

    server = HTTPServer((args.host, args.port), RequestHandler)
    url = f'http://{args.host}:{args.port}'

    print(f"🍺 Brewing Ingredients Database Web Viewer")
    print(f"   Server running at: {url}")
    print(f"   Database: {DB_PATH}")
    print(f"   Press Ctrl+C to stop")
    print()

    if not args.no_browser:
        threading.Thread(target=open_browser, args=(args.port,), daemon=True).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n\nShutting down server...")
        server.shutdown()

    return 0


if __name__ == '__main__':
    exit(main())
