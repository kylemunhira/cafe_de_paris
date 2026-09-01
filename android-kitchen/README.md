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

Use **☰ → Fiscalise** to list **today's** paid fiscal invoices. Cashiers and managers on fiscal branches can tap **Approve fiscal** to send pending proformas to ZIMRA (then a fiscal receipt with QR prints). Approved invoices can be reprinted.

## API used

- `POST /api/auth/mobile-login/` — token login (kitchen and/or POS access flags)
- `GET /api/orders/?status=open&branch={id}` — open orders
- `GET /api/products/?pos_catalog=true` — POS product catalog
- `GET /api/categories/` — product categories
- `GET /api/currencies/` — payment currencies
- `GET /api/stock-takes/day-end-check/` — verify daily stock take before day end
- `GET /api/reports/day-end/` — day-end cash-up report
- `GET /api/branches/{id}/fiscal-day/status/` — ZIMRA fiscal day status
- `POST /api/branches/{id}/fiscal-day/open/` — open fiscal day
- `POST /api/branches/{id}/fiscal-day/close/` — close fiscal day
- `GET /api/orders/?status=paid&fiscal_only=1&paid_date=YYYY-MM-DD` — today's fiscal invoices
- `POST /api/orders/{id}/approve-fiscal/` — approve proforma and submit to ZIMRA
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

## App updates (OTA)

The app checks the server on startup for a newer version. When one is available, it shows a dialog to download and install the APK from your server.

### Publish an update

1. Bump `versionCode` and `versionName` in `app/build.gradle.kts`.
2. Build the APK (Android Studio **Build → Build APK** or `./gradlew assembleDebug`).
3. On the **server**, copy the APK to the `releases/` folder as `kitchen.apk`.
4. In the server `.env`, set:
   - `KITCHEN_APP_VERSION_CODE` — must match `versionCode` in Gradle
   - `KITCHEN_APP_VERSION_NAME` — must match `versionName` in Gradle
   - Optional: `KITCHEN_APP_RELEASE_NOTES` — shown in the update dialog
5. Restart the server (or Windows service).

Tablets on the same network will be prompted on next launch. Staff can also tap **Check for updates** in Settings.

See `releases/README.md` in the project root for server-side details.

## Troubleshooting builds (Windows)

If Android Studio fails with `compileDebugKotlin` and **Access is denied** on
`lookups.tab_i.len`, OneDrive is usually locking files under `Documents\GitHub`.

**Build output is redirected** to `%LOCALAPPDATA%\cafe-de-paris\android-kitchen\`
so new builds should not hit the locked path. After pulling this change:

1. **Close Android Studio** completely.
2. Run `scripts\clean-build-cache.ps1` (or delete the folders listed below).
3. Reopen the project → **File → Sync Project with Gradle Files**.
4. **Build → Rebuild Project**.

Folders to clean:

- `android-kitchen\app\build\` (legacy; may be locked — ignore if delete fails)
- `%LOCALAPPDATA%\cafe-de-paris\android-kitchen\`
- `android-kitchen\.gradle\` (optional)

Long-term: pause OneDrive while building, or move the repo to e.g. `C:\dev\cafe_de_paris`.
