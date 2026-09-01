from django.conf import settings
from django.http import FileResponse, Http404
from rest_framework.response import Response
from rest_framework.views import APIView


class AppVersionView(APIView):
    """Return latest kitchen app version info for OTA updates."""

    authentication_classes = []
    permission_classes = []

    def get(self, request):
        current_code = request.query_params.get("version_code")
        try:
            current = int(current_code) if current_code else None
        except ValueError:
            current = None

        latest_code = settings.KITCHEN_APP_VERSION_CODE
        latest_name = settings.KITCHEN_APP_VERSION_NAME
        min_code = settings.KITCHEN_APP_MIN_VERSION_CODE
        force = settings.KITCHEN_APP_FORCE_UPDATE
        if current is not None and current < min_code:
            force = True

        update_available = current is None or current < latest_code
        apk_path = settings.RELEASES_DIR / settings.KITCHEN_APP_APK_FILENAME
        apk_available = apk_path.is_file()

        apk_url = None
        if apk_available and update_available:
            apk_url = request.build_absolute_uri("/api/app-version/download/")

        return Response(
            {
                "latest_version_code": latest_code,
                "latest_version_name": latest_name,
                "min_version_code": min_code,
                "update_available": update_available and apk_available,
                "apk_url": apk_url,
                "release_notes": settings.KITCHEN_APP_RELEASE_NOTES,
                "force_update": force and update_available and apk_available,
            }
        )


class AppVersionDownloadView(APIView):
    """Serve the latest kitchen APK from the server releases folder."""

    authentication_classes = []
    permission_classes = []

    def get(self, request):
        apk_path = settings.RELEASES_DIR / settings.KITCHEN_APP_APK_FILENAME
        if not apk_path.is_file():
            raise Http404("APK not found on server.")
        return FileResponse(
            open(apk_path, "rb"),
            as_attachment=True,
            filename=settings.KITCHEN_APP_APK_FILENAME,
            content_type="application/vnd.android.package-archive",
        )
