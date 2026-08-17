from pathlib import Path

from django.contrib.staticfiles.finders import find
from django.utils.translation import gettext as _

from ui.i18n_catalog import MSGIDS


def asset_version(_request):
    absolute = find("ui/css/app.css")
    if not absolute:
        return {"APP_CSS_VERSION": "1"}
    return {"APP_CSS_VERSION": str(int(Path(absolute).stat().st_mtime))}


def i18n_js_catalog(_request):
    """Translated strings for client-side CDP.t() lookups."""
    return {"CDP_I18N": {msgid: _(msgid) for msgid in MSGIDS}}
