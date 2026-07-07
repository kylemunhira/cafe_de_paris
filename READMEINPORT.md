python manage.py import_ingredients --replace # bakery ingredients from csvdata/BAKERY INGREDIENTS.csv (Central Stores & Bakery)
python manage.py import_menu_items --replace # for POS menu items and categories
python manage.py seed_menu_addons # for menu add-on groups linked to POS products

# Or upload CSV from the web UI:
# - List Ingredients → Upload CSV
# - List Products → Upload CSV (same as import_menu_items --replace; confirms before deactivating missing items)