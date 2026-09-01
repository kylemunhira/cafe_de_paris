# Android kitchen APK releases

Copy the built APK here so tablets can download updates from the server.

1. Build the app in `android-kitchen/` (Android Studio or `./gradlew assembleDebug`).
2. Copy the APK to this folder as `kitchen.apk` (or the name set in `KITCHEN_APP_APK_FILENAME`).
3. In the server `.env`, set `KITCHEN_APP_VERSION_CODE` and `KITCHEN_APP_VERSION_NAME` to match `android-kitchen/app/build.gradle.kts`.
4. Restart the server (or the Windows service).

Tablets check `/api/app-version/` on startup and show an update dialog when a newer version is available.
