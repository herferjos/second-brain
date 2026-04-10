from __future__ import annotations

import Foundation
import Speech

from ..config import load_settings


def _supported_locale_ids() -> list[str]:
    locales = Speech.SFSpeechRecognizer.supportedLocales()
    if locales is None:
        return []
    try:
        locale_ids = {str(locale.localeIdentifier()) for locale in locales if locale is not None}
    except Exception:
        locale_ids = set()
        for locale in list(locales):
            try:
                locale_ids.add(str(locale.localeIdentifier()))
            except Exception:
                continue
    return sorted(locale_ids)


def _language_code_for_locale(locale_id: str) -> str | None:
    try:
        ns_locale = Foundation.NSLocale.alloc().initWithLocaleIdentifier_(locale_id)
    except Exception:
        return None
    code = None
    try:
        if hasattr(ns_locale, "languageCode"):
            code = ns_locale.languageCode()
        if not code:
            code = ns_locale.objectForKey_(Foundation.NSLocaleLanguageCode)
    except Exception:
        code = None
    return str(code).lower() if code else None


def resolve_locale(detected_code: str | None, explicit: str | None) -> str:
    explicit_locale = (explicit or "").strip()
    if explicit_locale and explicit_locale.lower() == "auto":
        explicit_locale = ""

    configured = load_settings().locale.strip()
    if configured.lower() == "auto":
        configured = ""

    selected = explicit_locale or configured
    supported = _supported_locale_ids()
    if selected and selected in supported:
        resolved_selected = selected
    else:
        resolved_selected = selected
        selected_code = _language_code_for_locale(selected) if selected else None
        if selected_code:
            for locale_id in supported:
                if _language_code_for_locale(locale_id) == selected_code:
                    resolved_selected = locale_id
                    break

    detected = (detected_code or "").strip().lower()
    if not detected:
        return resolved_selected
    if selected:
        selected_code = _language_code_for_locale(selected)
        if selected_code and selected_code == detected:
            return resolved_selected

    for locale_id in supported:
        if _language_code_for_locale(locale_id) == detected:
            return locale_id

    return resolved_selected
