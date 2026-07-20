"""
theme.py (мобільна версія)

Менеджер теми з трьома режимами - авто / світла / темна, як і в
desktop-версії на CustomTkinter.

"Авто" на Android намагається прочитати системну нічну тему через
Configuration.uiMode (Android 10+). Якщо визначити не вдалось (старіша
Android-версія чи не-Android платформа) - чесно падаємо в темну тему,
бо саме вона тут дефолтна і найбільш перевірена.
"""
from kivy.utils import platform

THEME_AUTO = "auto"
THEME_LIGHT = "light"
THEME_DARK = "dark"

# Кольори з коментаря на початку старого .kv - лишаємо ту саму палітру
# для темної теми (щоб застосунок не змінив звичний вигляд), і додаємо
# дзеркальну світлу.
DARK = {
    "bg": (0.07, 0.07, 0.09, 1),
    "surface": (0.12, 0.12, 0.14, 1),
    "surface_alt": (0.18, 0.18, 0.21, 1),
    "card": (0.16, 0.16, 0.19, 1),
    "text": (0.95, 0.95, 0.95, 1),
    "text_muted": (0.6, 0.63, 0.65, 1),
    "accent": (0.106, 0.373, 0.655, 1),
    "accent_pressed": (0.106, 0.298, 0.525, 1),
    "danger": (0.9, 0.35, 0.35, 1),
    "status_bar_light_icons": True,
}

LIGHT = {
    "bg": (0.95, 0.95, 0.96, 1),
    "surface": (1, 1, 1, 1),
    "surface_alt": (0.89, 0.89, 0.92, 1),
    "card": (0.92, 0.92, 0.94, 1),
    "text": (0.10, 0.10, 0.12, 1),
    "text_muted": (0.42, 0.44, 0.47, 1),
    "accent": (0.145, 0.427, 0.741, 1),
    "accent_pressed": (0.09, 0.30, 0.55, 1),
    "danger": (0.80, 0.20, 0.20, 1),
    "status_bar_light_icons": False,
}


def _system_prefers_dark():
    if platform != "android":
        return True
    try:
        from jnius import autoclass

        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        activity = PythonActivity.mActivity
        config = activity.getResources().getConfiguration()

        UI_MODE_NIGHT_MASK = 0x30
        UI_MODE_NIGHT_YES = 0x20
        return (config.uiMode & UI_MODE_NIGHT_MASK) == UI_MODE_NIGHT_YES
    except Exception:
        return True


def resolve(theme_choice):
    """
    theme_choice - те, що зберігається в налаштуваннях ("auto"/"light"/"dark").
    Повертає словник кольорів, готовий до використання в .kv.
    """
    if theme_choice == THEME_LIGHT:
        return LIGHT
    if theme_choice == THEME_DARK:
        return DARK
    return DARK if _system_prefers_dark() else LIGHT
