# Data Directory

This directory stores your personal Swiggy order data in SQLite database format.

## Files
- `swiggy.db` - SQLite database with normalized order data (created automatically)
- `*.backup` - Backup files (created automatically)

## Security Note
**⚠️ IMPORTANT**: This directory contains personal data and is excluded from version control.
Never commit personal order data to public repositories.

## Database Schema
The SQLite database uses a normalized relational schema:
- `orders` table - Core order records with restaurant and timing information
- `order_cuisines` table - Cuisine tags associated with each order

## Setup
The database will be automatically created and populated when you:
1. Provide your session cookies as function arguments (never stored in config)
2. Run the sync_orders tool via MCP server or REST API endpoint

The database file is automatically ignored by git for your privacy.
