"""
localization.py

Проста локалізація інтерфейсу без сторонніх бібліотек - звичайний
словник рядків на дві мови: українську (за замовчуванням) та англійську.
Російська мова прибрана повністю.

Як користуватись:
    loc = Localization("ua")
    label.configure(text=loc.t("start_analysis"))

Для рядків з підстановкою значень (наприклад "Знайдено: {count}")
достатньо передати іменований аргумент:
    loc.t("status_done", count=5)
"""

LANG_UA = "ua"
LANG_EN = "en"

DEFAULT_LANGUAGE = LANG_UA

TEXTS = {
    LANG_UA: {
        "choose_video": "Обрати\nвідео",
        "loading_video": "Завантаження відео...",
        "no_file_selected": "Файл не обрано",
        "clear_all": "Очистити все",

        "search_prompt_label": "Кого/що шукати на відео:",
        "word_count": "{count}/{max}",

        "start_analysis": "Почати аналіз",

        "choose_model_label": "Оберіть модель:",

        "status_choose_video_first": "Спочатку обери відео",
        "status_choose_model": "Обери модель (3.5 Flash-Lite або 3.6 Flash)",
        "status_write_query": "Напиши, кого або що шукати",
        "status_cutting_frames": "Нарізаю відео на кадри...",
        "status_frames_cut": "Кадрів нарізано: {count}. Питаю Gemini...",
        "status_moments_found": "Моментів знайдено: {count}. Зберігаю кадри...",
        "status_done": "Готово! Знайдено моментів: {count}",
        "status_error": "Помилка: {error}",
        "status_cancelled": "Скасовано",

        "nothing_found_list": "Нічого не знайдено",
        "nothing_found_description": "За запитом «{query}» на відео нічого не знайдено.",

        # ---- екран вводу API-ключа ----
        "api_key_screen_title": "Вітаємо у Smart Surveillance AI",
        "api_key_screen_subtitle": "Щоб почати, встав свій API-ключ Gemini",
        "api_key_placeholder": "Встав свій ключ сюди...",
        "api_key_no_key_hint": "Немає ключа? Дізнатись, як отримати",
        "api_key_submit": "Зберегти і продовжити",

        # ---- перегляд фото (lightbox) ----
        "lightbox_save": "Зберегти",
        "image_saved": "Збережено в галерею",
        "image_save_failed": "Не вдалось зберегти",

        # ---- вибір відео ----
        "status_video_open_failed": "Не вдалося відкрити обраний файл. Спробуй ще раз",

        # ---- помилки Gemini API (gemini_tools.GeminiApiError.kind) ----
        "error_network": "Немає з'єднання з інтернетом. Перевір підключення, будь ласка",
        "error_timeout": "Сервер не відповів вчасно. Спробуй ще раз",
        "error_rate_limit": "Забагато запитів. Зачекай трохи і спробуй ще раз",
        "error_invalid_key": "Проблема з API-ключем. Перевір його в налаштуваннях",
        "error_server": "Сервіс Gemini тимчасово недоступний. Спробуй пізніше",
        "error_unknown": "Щось пішло не так. Спробуй ще раз",

        # ---- історія кадрів (HistoryModal) ----
        "history_view_frames": "Переглянути кадри",
        "history_delete_all": "Видалити все",
        "history_delete_confirm": "Видалити {count} кадрів?",
        "history_empty": "Кадрів не знайдено",
        "history_deleted": "Кадри видалено",
        "history_delete_failed": "Не вдалось видалити",

        # ---- про застосунок (AboutModal) ----
        "about_title": "Про застосунок",
        "about_body": (
            "Smart Surveillance AI допомагає швидко знайти потрібні "
            "моменти на відео з камер спостереження за допомогою "
            "штучного інтелекту.\n\n"
            "Як користуватись:\n\n"
            "1. Натисни «Обрати відео» і вибери запис з пристрою.\n\n"
            "2. У полі нижче напиши, кого або що потрібно знайти - "
            "наприклад, «людина в червоній куртці» або «собака».\n\n"
            "3. Обери модель аналізу: 3.5 Flash-Lite працює швидше, "
            "3.6 Flash - точніше розпізнає складні випадки.\n\n"
            "4. Натисни «Почати аналіз» і зачекай - відео нарізається "
            "на кадри, а нейромережа переглядає їх і шукає збіги.\n\n"
            "5. Коли аналіз завершиться, знайдені моменти можна "
            "переглянути в «Меню» -> «Переглянути кадри». Звідти ж "
            "кадри можна зберегти в галерею або видалити.\n\n"
            "Ключ Gemini API зберігається лише на пристрої і ніколи "
            "нікуди не передається окрім прямих запитів до Google Gemini."
        ),
        "about_copyright": "Корпорація Тимур Каленик, 2026",
    },
    LANG_EN: {
        "choose_video": "Choose\nvideo",
        "loading_video": "Loading video...",
        "no_file_selected": "No file selected",
        "clear_all": "Clear all",

        "search_prompt_label": "Who/what to look for in the video:",
        "word_count": "{count}/{max}",

        "start_analysis": "Start analysis",

        "choose_model_label": "Choose a model:",

        "status_choose_video_first": "Please choose a video first",
        "status_choose_model": "Choose a model (3.5 Flash-Lite or 3.6 Flash)",
        "status_write_query": "Write who or what to look for",
        "status_cutting_frames": "Cutting the video into frames...",
        "status_frames_cut": "Frames cut: {count}. Asking Gemini...",
        "status_moments_found": "Moments found: {count}. Saving frames...",
        "status_done": "Done! Moments found: {count}",
        "status_error": "Error: {error}",
        "status_cancelled": "Cancelled",

        "nothing_found_list": "Nothing found",
        "nothing_found_description": "Nothing was found in the video for the query \u201c{query}\u201d.",

        # ---- API key setup screen ----
        "api_key_screen_title": "Welcome to Smart Surveillance AI",
        "api_key_screen_subtitle": "To get started, paste your Gemini API key",
        "api_key_placeholder": "Paste your key here...",
        "api_key_no_key_hint": "No key? Learn how to get one",
        "api_key_submit": "Save and continue",

        # ---- photo viewer (lightbox) ----
        "lightbox_save": "Save",
        "image_saved": "Saved to gallery",
        "image_save_failed": "Failed to save",

        # ---- video picking ----
        "status_video_open_failed": "Couldn't open the selected file. Please try again",

        # ---- Gemini API errors (gemini_tools.GeminiApiError.kind) ----
        "error_network": "No internet connection. Please check your network",
        "error_timeout": "The server didn't respond in time. Please try again",
        "error_rate_limit": "Too many requests. Wait a bit and try again",
        "error_invalid_key": "There's a problem with your API key. Check it in settings",
        "error_server": "Gemini is temporarily unavailable. Please try again later",
        "error_unknown": "Something went wrong. Please try again",

        # ---- frame history (HistoryModal) ----
        "history_view_frames": "View frames",
        "history_delete_all": "Delete all",
        "history_delete_confirm": "Delete {count} frames?",
        "history_empty": "No frames found",
        "history_deleted": "Frames deleted",
        "history_delete_failed": "Failed to delete",

        # ---- about the app (AboutModal) ----
        "about_title": "About the app",
        "about_body": (
            "Smart Surveillance AI helps you quickly find the moments "
            "you need in security camera footage using artificial "
            "intelligence.\n\n"
            "How to use it:\n\n"
            "1. Tap \u201cChoose video\u201d and pick a recording from your "
            "device.\n\n"
            "2. In the field below, write who or what you want to find - "
            "for example, \u201cperson in a red jacket\u201d or \u201cdog\u201d.\n\n"
            "3. Pick an analysis model: 3.5 Flash-Lite works faster, "
            "3.6 Flash recognizes tricky cases more accurately.\n\n"
            "4. Tap \u201cStart analysis\u201d and wait - the video gets cut "
            "into frames, and the neural network scans them for "
            "matches.\n\n"
            "5. Once the analysis is done, you can view the found "
            "moments from \u201cMenu\u201d -> \u201cView screenshots\u201d. From there "
            "you can also save frames to the gallery or delete them.\n\n"
            "Your Gemini API key is stored only on your device and is "
            "never sent anywhere except in direct requests to Google "
            "Gemini."
        ),
        "about_copyright": "Timur Kalenyk Corporation, 2026",
    },
}


class Localization:
    """Зберігає поточну мову інтерфейсу і повертає переклади за ключем."""

    def __init__(self, language=DEFAULT_LANGUAGE):
        self.language = language if language in TEXTS else DEFAULT_LANGUAGE

    def set_language(self, language):
        if language in TEXTS:
            self.language = language

    def t(self, key, **kwargs):
        """
        Повертає переклад за ключем поточної мови.

        Якщо в тексті є місця під підстановку (наприклад "{count}"),
        передай їх іменованими аргументами - вони підставляться через
        str.format(). Якщо ключа раптом нема в словнику - повертаємо
        сам ключ, щоб інтерфейс не падав, а показував хоч щось.
        """
        text = TEXTS[self.language].get(key, key)
        if kwargs:
            return text.format(**kwargs)
        return text
