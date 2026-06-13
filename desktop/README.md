# Café de Paris — Desktop POS

Standalone Electron app for **cashiers only**. Works offline with a local SQLite database and syncs orders to the central web app when online.

## Features

- Take orders and collect payments without internet
- Local product catalog and currencies (pulled from server)
- **Thermal-style printing** — auto-prints order tickets and sales receipts (printer selectable in **Settings**)
- **Automatic sync** when internet and server are available (on connect, every 30s, after orders)
- Cashier / branch manager accounts only

## Printing

| When | What prints |
|------|-------------|
| **Place order** | Order ticket (UNPAID) — items, total, table/type |
| **Collect payment** | Sales receipt (PAID) — tax breakdown, amount paid |
| **Day end** | Daily sales summary — totals, payments by currency, items sold |

Open **Settings** in the POS top bar to choose a receipt printer, or leave **System default** to use the Windows default. Use **Print test page** to verify the connection. Layout is 80mm thermal-style. Works fully offline; receipt numbers update after sync when the server assigns the official number.

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

Set the server URL in `config.json` (see below), then sign in with cashier username and password.

## Server URL (`config.json`)

The API server address is **not** shown on the login screen. Edit `desktop/config.json` before install or deployment:

```json
{
  "serverUrl": "http://127.0.0.1:8000"
}
```

After `npm run build`, the installer places `config.json` next to the `.exe` so you can change the URL without rebuilding. Restart the app after editing.

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
