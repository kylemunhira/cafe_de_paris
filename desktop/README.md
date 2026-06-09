# Café de Paris — Desktop POS

Standalone Electron app for **cashiers only**. Works offline with a local SQLite database and syncs orders to the central web app when online.

## Features

- Take orders and collect payments without internet
- Local product catalog and currencies (pulled from server)
- **Thermal-style printing** — auto-prints to the **default printer** (order ticket + sales receipt)
- **Automatic sync** when internet and server are available (on connect, every 30s, after orders)
- Cashier / branch manager accounts only

## Printing

| When | What prints |
|------|-------------|
| **Place order** | Order ticket (UNPAID) — items, total, table/type |
| **Collect payment** | Sales receipt (PAID) — tax breakdown, amount paid |

Printing goes straight to the **Windows default printer** (80mm receipt layout). Set your receipt printer as the system default in Windows Settings → Printers. Works fully offline; receipt numbers update after sync when the server assigns the official number.

Sync runs automatically when the network is up and the server responds (`GET /api/sync/ping/`). Pending orders upload as soon as connectivity returns.

## Setup

1. Start the Django web app (`python manage.py runserver`).
2. Create a cashier user with a staff profile assigned to a branch.
3. Install desktop dependencies:

```bash
cd desktop
npm install
npm run rebuild
```

## Run (development)

```bash
npm start
```

Sign in with the server URL (e.g. `http://127.0.0.1:8000`), cashier username, and password.

## Build Windows installer

```bash
npm run build
```

Output is in `desktop/dist/`.

## Sync API

| Endpoint | Description |
|----------|-------------|
| `POST /api/auth/desktop-login/` | Get auth token (cashiers only) |
| `GET /api/sync/pull/` | Download catalog + currencies |
| `POST /api/sync/push/` | Upload pending offline orders |

Orders use a client UUID for idempotent sync — uploading the same order twice will not create duplicates on the server.
