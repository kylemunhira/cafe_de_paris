# Android kitchen & POS app

Android app for branch staff:

- **Kitchen display** — shows open POS orders, auto-prints new order tickets on a Bluetooth thermal printer, and removes orders once they are paid at the till.
- **Cashier POS** — cashiers and branch managers can take orders and collect payment directly from the same app.

## Requirements

- Android 7.0+ tablet or phone (landscape layout)
- Same Wi‑Fi network as the Café de Paris server
- Bluetooth ESC/POS thermal printer (80 mm), paired in Android settings
- Staff account with **kitchen access** and/or **POS access**

| Role | App mode |
|------|----------|
| Cashier | Point of Sale (orders + payments) |
| Branch manager | Point of Sale |
| Kitchen / branch staff | Kitchen display |

## Setup

1. Set the server URL in `config.json` (see below).
2. Open `android-kitchen/` in **Android Studio** and run the app on the tablet.
3. Sign in with staff credentials (username + password only).
4. Open **Settings** and choose the paired Bluetooth printer address (kitchen display and POS).
5. **Cashiers:** use **Order** to place orders and **Receipt** to collect payment on open orders.

## Server URL (`config.json`)

Like the desktop POS, the API server address is **not** entered on the login screen. Edit `android-kitchen/config.json` before building or deploying:

```json
{
  "serverUrl": "http://192.168.1.50:8000"
}
```

Use your PC’s LAN IP (not `127.0.0.1`). Gradle copies this file into the APK on each build.

### Change URL after install (no rebuild)

On first launch the app copies `config.json` to its private storage. Edit that file on the tablet, then reopen the app:

```
Android/data/com.cafedeparis.kitchen/files/config.json
```

Or push from your PC:

```bash
adb push config.json /storage/emulated/0/Android/data/com.cafedeparis.kitchen/files/config.json
```

## How it works

### Kitchen display

| Event | App behaviour |
|--------|----------------|
| New open order from POS | Appears on screen and prints automatically (once per order) |
| Order paid at POS | Drops off the list on the next refresh (`status=open` filter) |
| Printer offline | Order stays visible; printing retries for unprinted orders |

Polls every 5 seconds.

### Cashier POS

| Tab | Purpose |
|-----|---------|
| **Order** | Browse POS catalog, build cart, place takeaway or dine-in orders (with table picker). Prints an **order ticket** (same layout as web POS) on the paired Bluetooth printer after each order. |
| **Receipt** | List open orders, select one, pay with **cash** or **customer account** |

Receipt tab refreshes every 10 seconds. After payment, a **sales receipt** is printed automatically on the paired Bluetooth printer (same as web POS).

Use **Customer payment** in the header to record account deposits. From that dialog, **Print statement** prints the customer’s full account statement (all transactions and outstanding balance) on the paired Bluetooth printer.

Use **Day end** in the header to run cash-up: enter counted till amounts per currency and print the day-end summary (requires a completed daily stock take for that date).

## API used

- `POST /api/auth/mobile-login/` — token login (kitchen and/or POS access flags)
- `GET /api/orders/?status=open&branch={id}` — open orders
- `GET /api/products/?pos_catalog=true` — POS product catalog
- `GET /api/categories/` — product categories
- `GET /api/currencies/` — payment currencies
- `GET /api/stock-takes/day-end-check/` — verify daily stock take before day end
- `GET /api/reports/day-end/` — day-end cash-up report
- `GET /api/customers/` — customers with account balances
- `GET /api/customers/{id}/statement/?all=1` — customer account statement (transactions + balances)
- `POST /api/customers/{id}/deposit/` — record customer account deposit
- `POST /api/orders/` — place order
- `PATCH /api/orders/{id}/` — link customer for account payment
- `POST /api/orders/{id}/pay/` — collect payment (cash or account)

## Server note

Run Django so the tablet can reach it, e.g.:

```bash
python manage.py runserver 0.0.0.0:8000
```

`DEBUG=True` allows HTTP from the local network. For production, use HTTPS and a proper hostname.

## Build APK from command line

```bash
cd android-kitchen
./gradlew assembleDebug
```

APK output: `app/build/outputs/apk/debug/app-debug.apk`
