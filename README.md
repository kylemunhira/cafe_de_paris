# Café de Paris

Multi-branch coffee shop and bakery management system. Central HQ coordinates branches, inventory, POS sales, and bakery production.

See [coffee_shop_system_design.md](coffee_shop_system_design.md) for the full architecture.

## Phase 1

- Django backend with REST API
- Modern web dashboard (POS, orders, products, branches)
- Branch and product management
- Basic POS order creation and payment
- Django Admin dashboard

## Phase 2 (current)

- Branch inventory listing and manual adjustments
- Stock transfer workflow: request → approve → dispatch → deliver
- Low-stock inventory alerts via API filter
- **Desktop POS** — offline cashier app with sync (see [desktop/README.md](desktop/README.md))

## Quick start

```bash
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS/Linux

pip install -r requirements.txt
copy .env.example .env         # Windows
# cp .env.example .env         # macOS/Linux

python manage.py migrate
python manage.py seed_demo
python manage.py createsuperuser
python manage.py runserver
```

- **Dashboard:** http://127.0.0.1:8000/
- **POS:** http://127.0.0.1:8000/pos/
- **Admin:** http://127.0.0.1:8000/admin/
- **API:** http://127.0.0.1:8000/api/

## API endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET/POST | `/api/branches/` | List or create branches |
| GET/POST | `/api/categories/` | Product categories |
| GET/POST | `/api/products/` | Products |
| GET/POST | `/api/orders/` | Create POS orders |
| POST | `/api/orders/{id}/pay/` | Mark order as paid |
| GET | `/api/inventory/` | List branch stock (filter: `branch`, `product`, `low_stock`, `threshold`) |
| POST | `/api/inventory/adjust/` | Adjust stock at a branch |
| GET/POST | `/api/transfers/` | List or request stock transfers |
| POST | `/api/transfers/{id}/approve/` | HQ approves a transfer request |
| POST | `/api/transfers/{id}/dispatch/` | Deduct stock from source branch |
| POST | `/api/transfers/{id}/deliver/` | Add stock to destination branch |
| POST | `/api/transfers/{id}/cancel/` | Cancel a pending transfer |

### Example: create an order

```json
POST /api/orders/
{
  "branch": 2,
  "order_type": "takeaway",
  "items": [
    {"product_id": 1, "quantity": 2},
    {"product_id": 3, "quantity": 1}
  ]
}
```

### Example: stock transfer workflow

```json
POST /api/transfers/
{
  "from_branch": 1,
  "to_branch": 3,
  "product": 1,
  "quantity": "20"
}

POST /api/transfers/1/approve/
POST /api/transfers/1/dispatch/
POST /api/transfers/1/deliver/
```

### Example: adjust inventory

```json
POST /api/inventory/adjust/
{
  "branch": 3,
  "product": 1,
  "delta": "-2"
}
```

## Tech stack

- Python / Django / Django REST Framework
- SQLite (dev) or PostgreSQL (production)
- Django Admin for HQ dashboard
