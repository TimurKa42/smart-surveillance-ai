"""
config.py (мобільна версія)

На Android застосунок НЕ може писати файли поруч зі своїм кодом
(APK - це фактично архів лише для читання). Тому .env зберігаємо в
окремій теці, яку Android виділяє саме цьому застосунку для його даних
- App.user_data_dir. На комп'ютері (коли тестуєш через `buildozer
android debug deploy run` чи просто `python main.py` на Linux/macOS/
Windows) user_data_dir теж працює - там це буде звичайна тека в
домашній директорії користувача.
"""
import os
from kivy.app import App

ENV_FILENAME = ".env"


def get_env_path():
    """Шлях до .env у теці даних застосунку (створює теку, якщо нема)."""
    app = App.get_running_app()
    base_dir = app.user_data_dir if app else os.getcwd()
    os.makedirs(base_dir, exist_ok=True)
    return os.path.join(base_dir, ENV_FILENAME)


def load_api_key():
    """Повертає збережений ключ або None, якщо його ще нема."""
    path = get_env_path()
    if not os.path.exists(path):
        return None

    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("GEMINI_API_KEY="):
                    key = line.split("=", 1)[1].strip()
                    return key or None
    except OSError:
        return None

    return None


def save_api_key(key):
    """Зберігає ключ у .env - файл рівно з одним рядком, як і в desktop-версії."""
    path = get_env_path()
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"GEMINI_API_KEY={key.strip()}\n")
