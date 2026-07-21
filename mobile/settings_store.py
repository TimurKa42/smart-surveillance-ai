"""
settings_store.py (мобільна версія)

Зберігає тему, мову і силу вібрації в JSON-файлі в теці даних
застосунку - за тим самим принципом, що й config.py зберігає API-ключ.
"""
import json
import os

from kivy.app import App

SETTINGS_FILENAME = "settings.json"

DEFAULTS = {
    "theme": "auto",
    "language": "ua",
    # У секундах - саме такий формат очікує plyer.vibrator.vibrate(sec).
    "vibration": 0.05,
}


def _get_settings_path():
    app = App.get_running_app()
    base_dir = app.user_data_dir if app else os.getcwd()
    os.makedirs(base_dir, exist_ok=True)
    return os.path.join(base_dir, SETTINGS_FILENAME)


def load_settings():
    path = _get_settings_path()
    if not os.path.exists(path):
        return dict(DEFAULTS)

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        merged = dict(DEFAULTS)
        merged.update(data)
        return merged
    except (OSError, json.JSONDecodeError):
        return dict(DEFAULTS)


def save_settings(settings):
    path = _get_settings_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)
