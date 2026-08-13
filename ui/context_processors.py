from pathlib import Path

from django.contrib.staticfiles.finders import find


def asset_version(_request):
    absolute = find("ui/css/app.css")
    if not absolute:
        return {"APP_CSS_VERSION": "1"}
    return {"APP_CSS_VERSION": str(int(Path(absolute).stat().st_mtime))}
