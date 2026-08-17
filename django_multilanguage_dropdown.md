# Django Multi-Language Dropdown Implementation

## User Request

The user showed a website screenshot with a language dropdown containing:

- English
- Français
- Español
- العربية
- 中文

They asked how to implement a similar language dropdown in a Python project.

## Recommended Approach

For a Django project, use Django's built-in internationalization (`i18n`) system.

There are two main parts:

1. The language selector/dropdown UI.
2. Django's translation system that changes the website text.

---

## 1. Configure Django

In `settings.py`:

```python
LANGUAGE_CODE = "en"

LANGUAGES = [
    ("en", "English"),
    ("fr", "Français"),
    ("es", "Español"),
    ("ar", "العربية"),
    ("zh-hans", "中文"),
]

USE_I18N = True

MIDDLEWARE = [
    # ...
    "django.middleware.locale.LocaleMiddleware",
    # ...
]
```

`LocaleMiddleware` should be placed after `SessionMiddleware` and before `CommonMiddleware`.

---

## 2. Add Django's Language URL

In the main `urls.py`:

```python
from django.urls import path, include

urlpatterns = [
    # your other URLs

    path("i18n/", include("django.conf.urls.i18n")),
]
```

Django provides the `/i18n/setlang/` endpoint for changing the selected language.

---

## 3. Create the Language Dropdown

In a base template such as `templates/base.html`:

```html
{% load i18n %}

<div class="language-selector">
    <button class="language-button" onclick="toggleLanguages()">
        🌐 {{ LANGUAGE_CODE|default:"en"|upper }}
        <span>⌃</span>
    </button>

    <div id="language-menu" class="language-menu">
        <form action="{% url 'set_language' %}" method="post">
            {% csrf_token %}

            <input type="hidden" name="next" value="{{ request.path }}">

            {% get_current_language as CURRENT_LANGUAGE %}

            <button type="submit" name="language" value="en">
                English
            </button>

            <button type="submit" name="language" value="fr">
                Français
            </button>

            <button type="submit" name="language" value="es">
                Español
            </button>

            <button type="submit" name="language" value="ar">
                العربية
            </button>

            <button type="submit" name="language" value="zh-hans">
                中文
            </button>
        </form>
    </div>
</div>
```

---

## 4. Style the Dropdown

Example CSS:

```css
.language-selector {
    position: relative;
    display: inline-block;
}

.language-button {
    background: transparent;
    border: none;
    font-size: 18px;
    cursor: pointer;
    padding: 10px 15px;
}

.language-menu {
    display: none;
    position: absolute;
    right: 0;
    top: 100%;
    width: 220px;
    background: white;
    box-shadow: 0 5px 20px rgba(0, 0, 0, 0.15);
    z-index: 1000;
}

.language-menu form {
    display: flex;
    flex-direction: column;
}

.language-menu button {
    background: white;
    border: none;
    text-align: left;
    padding: 20px 30px;
    font-size: 18px;
    cursor: pointer;
}

.language-menu button:hover {
    background: #f2f2f2;
}
```

---

## 5. Add JavaScript

```javascript
function toggleLanguages() {
    const menu = document.getElementById("language-menu");

    if (menu.style.display === "block") {
        menu.style.display = "none";
    } else {
        menu.style.display = "block";
    }
}
```

---

## 6. Mark Website Text for Translation

Instead of:

```html
<h1>Who we are</h1>
<p>Welcome to our website</p>
```

use:

```html
{% load i18n %}

<h1>{% trans "Who we are" %}</h1>

<p>{% trans "Welcome to our website" %}</p>
```

For longer text, use:

```html
{% blocktrans %}
    Welcome to our website
{% endblocktrans %}
```

Django can then identify these strings as translatable.

---

## 7. Generate Translation Files

Run:

```bash
django-admin makemessages -l fr
django-admin makemessages -l es
django-admin makemessages -l ar
django-admin makemessages -l zh_Hans
```

This creates translation files such as:

```text
locale/
├── fr/
│   └── LC_MESSAGES/
│       └── django.po
├── es/
│   └── LC_MESSAGES/
│       └── django.po
├── ar/
│   └── LC_MESSAGES/
│       └── django.po
└── zh_Hans/
    └── LC_MESSAGES/
        └── django.po
```

Example French translation:

```po
msgid "Who we are"
msgstr "Qui sommes-nous"
```

Another example:

```po
msgid "Welcome to our website"
msgstr "Bienvenue sur notre site"
```

After editing the translation files, compile them:

```bash
django-admin compilemessages
```

---

## 8. Optional: Language-Specific URLs

For a professional public website, it can be useful to have language-specific URLs:

```text
/en/
```

```text
/fr/
```

```text
/es/
```

```text
/ar/
```

```text
/zh-hans/
```

This can be useful for SEO because search engines can index each language separately.

---

## Recommended Architecture

For a Django website, a clean structure could be:

```text
project/
├── manage.py
├── project/
│   ├── settings.py
│   ├── urls.py
│   └── ...
├── templates/
│   └── base.html
├── static/
│   ├── css/
│   │   └── language.css
│   └── js/
│       └── language.js
├── locale/
│   ├── fr/
│   ├── es/
│   ├── ar/
│   └── zh_Hans/
└── apps/
    └── ...
```

## Summary

Django already provides the backend functionality required for multilingual websites. The recommended solution is:

- Use Django `LocaleMiddleware`.
- Define supported languages in `LANGUAGES`.
- Add Django's `set_language` URL.
- Create a custom dropdown matching the site's design.
- Mark template text using `{% trans %}` or `{% blocktrans %}`.
- Generate `.po` translation files with `makemessages`.
- Translate the strings.
- Run `compilemessages`.
- Optionally use language-specific URLs such as `/en/`, `/fr/`, and `/es/`.

This approach avoids building a custom language-management system from scratch and integrates directly with Django templates.
