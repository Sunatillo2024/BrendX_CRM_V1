"""Server-side UZ/RU translations.

The dictionary lives in one place: ``static/js/translations.js`` (used by the
browser). This module loads it once and exposes a ``translator(lang)`` callable,
so the server and the client can never drift apart. English is not supported.
"""
import json
from functools import lru_cache
from pathlib import Path

from django.conf import settings

LANGUAGES = [
    {'code': 'uz', 'label': "O'zbekcha"},
    {'code': 'ru', 'label': 'Русский'},
]
DEFAULT_LANG = 'uz'


@lru_cache(maxsize=1)
def _dictionaries():
    path = Path(settings.BASE_DIR) / 'static' / 'js' / 'translations.js'
    try:
        text = path.read_text(encoding='utf-8')
        # The file is ``window.BRANDX_TRANSLATIONS = { ... };`` where the object
        # body is strict JSON (also valid JS for the browser). Extract the
        # object between the outermost braces and parse it.
        start, end = text.index('{'), text.rindex('}')
        data = json.loads(text[start:end + 1])
        return {
            'uz': data.get('uz', {}),
            'ru': data.get('ru', {}),
        }
    except Exception:  # pragma: no cover - never break rendering on i18n parse
        return {'uz': {}, 'ru': {}}


def translator(lang):
    """Return a callable ``t(key) -> str`` for the given language."""
    lang = lang if lang in ('uz', 'ru') else DEFAULT_LANG
    table = _dictionaries().get(lang, {})
    fallback = _dictionaries().get(DEFAULT_LANG, {})

    def t(key, default=None):
        if key in table:
            return table[key]
        if key in fallback:
            return fallback[key]
        return default if default is not None else key

    return t
