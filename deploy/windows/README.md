# Windows Server deployment (Waitress + NSSM)

Run Café de Paris as a Windows service using [Waitress](https://docs.pylonsproject.org/projects/waitress/) and [NSSM](https://nssm.cc/) (Non-Sucking Service Manager).

## One-time setup

1. **Install Python 3.11+** and clone the repo to the server (e.g. `C:\Apps\cafe_de_paris`).

2. **Create the virtual environment and install dependencies:**

   ```powershell
   cd C:\Apps\cafe_de_paris
   python -m venv venv
   .\venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Configure production `.env`:**

   ```powershell
   copy .env.example .env
   notepad .env
   ```

   Set at minimum:

   - `DJANGO_DEBUG=false`
   - `DJANGO_SECRET_KEY` — a long random string
   - `DJANGO_ALLOWED_HOSTS` — server IP/hostname
   - `DJANGO_CSRF_TRUSTED_ORIGINS` — full URLs clients use
   - PostgreSQL `DB_*` settings if using Postgres

4. **Prepare the database and static files:**

   ```powershell
   .\venv\Scripts\activate
   python manage.py migrate
   python manage.py collectstatic --noinput
   python manage.py createsuperuser
   ```

5. **NSSM** should be at `C:\nssm\nssm.exe` (download from https://nssm.cc/download if needed).

6. **Test Waitress manually** before installing the service:

   ```powershell
   python run_waitress.py
   ```

   Open http://localhost:8000/ — then stop with Ctrl+C.

## Install the service

Open **PowerShell as Administrator**:

```powershell
cd C:\Apps\cafe_de_paris
.\deploy\windows\install-service.ps1
```

Default service name: `CafeDeParis`. It starts automatically on boot.

### Service management

```powershell
C:\nssm\nssm.exe status CafeDeParis
C:\nssm\nssm.exe restart CafeDeParis
C:\nssm\nssm.exe stop CafeDeParis
```

Or use `services.msc` → **Cafe de Paris**.

Logs are written to `logs\service-stdout.log` and `logs\service-stderr.log`.

## Uninstall

```powershell
.\deploy\windows\uninstall-service.ps1
```

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `WAITRESS_HOST` | `0.0.0.0` | Bind address (LAN access) |
| `WAITRESS_PORT` | `8000` | Listen port |
| `WAITRESS_THREADS` | `8` | Worker threads |

Add these to `.env`. Open port **8000** (or your chosen port) in Windows Firewall for LAN clients.

## After code updates

```powershell
cd C:\Apps\cafe_de_paris
.\venv\Scripts\activate
git pull
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
C:\nssm\nssm.exe restart CafeDeParis
```

### Android kitchen app updates

After building a new APK in `android-kitchen/`:

```powershell
copy android-kitchen\app\build\outputs\apk\debug\app-debug.apk releases\kitchen.apk
```

Update `.env` (`KITCHEN_APP_VERSION_CODE`, `KITCHEN_APP_VERSION_NAME`) to match `app/build.gradle.kts`, then restart the service. Tablets will prompt users on next launch.
