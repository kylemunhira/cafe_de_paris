# Android kitchen display

Simple Android app for the kitchen: shows open POS orders, auto-prints new order tickets on a Bluetooth thermal printer, and removes orders from the screen once they are paid at the till.

## Requirements

- Android 7.0+ tablet or phone (landscape layout)
- Same Wi‑Fi network as the Café de Paris server
- Bluetooth ESC/POS thermal printer (80 mm), paired in Android settings
- Staff account with **kitchen access** (branch or HQ staff — same as the web Kitchen page)

## Setup

1. Set the server URL in `config.json` (see below).
2. Open `android-kitchen/` in **Android Studio** and run the app on the kitchen tablet.
3. Sign in with kitchen staff credentials (username + password only).
4. Open **Settings** and choose the paired Bluetooth printer address.
5. Leave the app open on the kitchen screen. It polls every 5 seconds.

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

| Event | App behaviour |
|--------|----------------|
| New open order from POS | Appears on screen and prints automatically (once per order) |
| Order paid at POS | Drops off the list on the next refresh (`status=open` filter) |
| Printer offline | Order stays visible; printing retries for unprinted orders |

API used:

- `POST /api/auth/kitchen-login/` — token login for kitchen staff
- `GET /api/orders/?status=open&branch={id}` — open orders for the signed-in branch

Printed ticket layout matches the web **order slip** (items, table, UNPAID footer).

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
