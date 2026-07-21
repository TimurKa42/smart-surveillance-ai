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
        "window_title": "Smart Surveillance AI",

        "choose_video": "Обрати відео",
        "no_file_selected": "Файл не обрано",
        "clear_all": "Очистити все",

        "search_prompt_label": "Кого/що шукати на відео:",
        "word_count": "{count}/{max}",

        "start_analysis": "Почати аналіз",

        "choose_model_label": "Оберіть модель:",

        "report_label": "Звіт",
        "photo_placeholder": "Тут з'явиться скріншот",
        "nothing_found_photo": "Нічого не знайдено 🙁",

        "status_choose_video_first": "Спочатку обери відео",
        "status_choose_model": "Обери модель (3.1 Flash-Lite або 3.5 Flash)",
        "status_write_query": "Напиши, кого або що шукати",
        "status_cutting_frames": "Нарізаю відео на кадри...",
        "status_frames_cut": "Кадрів нарізано: {count}. Питаю Gemini...",
        "status_moments_found": "Моментів знайдено: {count}. Зберігаю кадри...",
        "status_done": "Готово! Знайдено моментів: {count}",
        "status_error": "Помилка: {error}",

        "nothing_found_list": "Нічого не знайдено",
        "nothing_found_description": "За запитом «{query}» на відео нічого не знайдено.",

        "lightbox_close": "✕ Закрити",

        "file_dialog_title": "Обери відео",
        "file_dialog_video_files": "Відеофайли",
        "file_dialog_all_files": "Усі файли",

        "theme_label": "Тема:",
        "theme_auto": "Авто",
        "theme_light": "Світла",
        "theme_dark": "Темна",

        "language_label": "Мова:",

        # ---- екран вводу API-ключа ----
        "api_key_screen_title": "Вітаємо у Smart Surveillance AI",
        "api_key_screen_subtitle": "Щоб почати, встав свій API-ключ Gemini",
        "api_key_placeholder": "Встав свій ключ сюди...",
        "api_key_no_key_hint": "Немає ключа? Дізнатись, як отримати",
        "api_key_submit": "Зберегти і продовжити",
        "api_key_empty_error": "Спочатку встав ключ",
        "api_key_invalid": "Ключ недійсний або немає доступу до Gemini API",

        # ---- шторка налаштувань ----
        "settings_title": "Налаштування",
        "reset_button": "Скинути API Ключ",

        # ---- перегляд фото (lightbox) ----
        "lightbox_save": "Зберегти",
        "image_saved": "Збережено в галерею",
        "image_save_failed": "Не вдалось зберегти",

        # ---- вибір відео ----
        "status_video_open_failed": "Не вдалося відкрити обраний файл. Спробуй ще раз",
    },
    LANG_EN: {
        "window_title": "Smart Surveillance AI",

        "choose_video": "Choose video",
        "no_file_selected": "No file selected",
        "clear_all": "Clear all",

        "search_prompt_label": "Who/what to look for in the video:",
        "word_count": "{count}/{max}",

        "start_analysis": "Start analysis",

        "choose_model_label": "Choose a model:",

        "report_label": "Report",
        "photo_placeholder": "The screenshot will appear here",
        "nothing_found_photo": "Nothing found 🙁",

        "status_choose_video_first": "Please choose a video first",
        "status_choose_model": "Choose a model (3.1 Flash-Lite or 3.5 Flash)",
        "status_write_query": "Write who or what to look for",
        "status_cutting_frames": "Cutting the video into frames...",
        "status_frames_cut": "Frames cut: {count}. Asking Gemini...",
        "status_moments_found": "Moments found: {count}. Saving frames...",
        "status_done": "Done! Moments found: {count}",
        "status_error": "Error: {error}",

        "nothing_found_list": "Nothing found",
        "nothing_found_description": "Nothing was found in the video for the query \u201c{query}\u201d.",

        "lightbox_close": "✕ Close",

        "file_dialog_title": "Choose a video",
        "file_dialog_video_files": "Video files",
        "file_dialog_all_files": "All files",

        "theme_label": "Theme:",
        "theme_auto": "Auto",
        "theme_light": "Light",
        "theme_dark": "Dark",

        "language_label": "Language:",

        # ---- API key setup screen ----
        "api_key_screen_title": "Welcome to Smart Surveillance AI",
        "api_key_screen_subtitle": "To get started, paste your Gemini API key",
        "api_key_placeholder": "Paste your key here...",
        "api_key_no_key_hint": "No key? Learn how to get one",
        "api_key_submit": "Save and continue",
        "api_key_empty_error": "Please paste your key first",
        "api_key_invalid": "Invalid key or no access to Gemini API",

        # ---- settings sheet ----
        "settings_title": "Settings",
        "reset_button": "Reset API Key",

        # ---- photo viewer (lightbox) ----
        "lightbox_save": "Save",
        "image_saved": "Saved to gallery",
        "image_save_failed": "Failed to save",

        # ---- video picking ----
        "status_video_open_failed": "Couldn't open the selected file. Please try again",
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
