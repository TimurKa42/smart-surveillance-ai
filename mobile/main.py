"""
main.py (мобільна версія на Kivy)

Два екрани:
1) SetupScreen - показується, поки в застосунку ще нема збереженого
   API-ключа Gemini. Поле вводу + посилання "немає ключа?" + кнопка
   "Зберегти і продовжити".
2) MainScreen - сам застосунок: вибір відео, текстовий запит, вибір
   моделі, аналіз, звіт зі скріншотами. Логіка (нарізка відео,
   звернення до Gemini) винесена в video_tools.py і gemini_tools.py -
   так само, як і в десктопній версії.

Стиль і кольори винесені в smartsurveillance.kv (Kivy сам підвантажує
цей файл, бо він називається так само, як App-клас без суфікса "App").
"""
import os
import threading
import webbrowser

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.properties import StringProperty, BooleanProperty
from kivy.uix.screenmanager import Screen, ScreenManager, NoTransition
from kivy.uix.image import Image
from kivy.uix.button import Button
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.utils import platform

import config
from localization import Localization
from video_tools import extract_frames, grab_screenshot, format_time
import gemini_tools

MAX_WORDS_IN_PROMPT = 200
MAX_FRAMES = 150
SCREENSHOTS_SUBFOLDER = "screenshots"

API_KEY_INSTRUCTIONS_URL = "https://aistudio.google.com/apikey"

MODEL_OPTIONS = [
    ("3.1 Flash-Lite", "gemini-3.1-flash-lite"),
    ("3.5 Flash", "gemini-3.5-flash"),
]


def open_url(url):
    """
    Відкриває посилання в браузері. На звичайному комп'ютері спрацює
    звичайний webbrowser.open(). На Android немає системного виклику
    "відкрити URL" через webbrowser - там потрібно попросити саму
    систему запустити намір (Intent) на перегляд посилання.
    """
    if platform == "android":
        try:
            from jnius import autoclass, cast

            Intent = autoclass("android.content.Intent")
            Uri = autoclass("android.net.Uri")
            PythonActivity = autoclass("org.kivy.android.PythonActivity")

            intent = Intent(Intent.ACTION_VIEW, Uri.parse(url))
            current_activity = cast("android.app.Activity", PythonActivity.mActivity)
            current_activity.startActivity(intent)
        except Exception:
            pass  # якщо щось пішло не так - просто не відкриваємо, застосунок не має падати
    else:
        webbrowser.open(url)


def request_android_permissions():
    """Android 6+ вимагає запитувати дозволи на читання файлів у рантаймі."""
    if platform != "android":
        return
    try:
        from android.permissions import request_permissions, Permission
        request_permissions([
            Permission.READ_EXTERNAL_STORAGE,
            Permission.WRITE_EXTERNAL_STORAGE,
            Permission.INTERNET,
        ])
    except Exception:
        pass


class SetupScreen(Screen):
    """Перший екран - введення API-ключа Gemini."""

    error_text = StringProperty("")

    def submit_key(self):
        key = self.ids.api_key_input.text.strip()
        loc = App.get_running_app().loc

        if not key:
            self.error_text = loc.t("api_key_empty_error")
            return

        config.save_api_key(key)
        self.error_text = ""
        App.get_running_app().go_to_main_screen()

    def open_instructions(self):
        open_url(API_KEY_INSTRUCTIONS_URL)


class ModelButton(Button):
    """Кнопка вибору моделі - сама відстежує, обрана вона чи ні (для kv-стилів)."""
    is_selected = BooleanProperty(False)
    model_name = StringProperty("")


class ReportItemButton(Button):
    """Кнопка одного моменту в списку звіту."""
    is_selected = BooleanProperty(False)


class MainScreen(Screen):
    def on_pre_enter(self, *args):
        app = App.get_running_app()
        self.ids.search_label.text = app.loc.t("search_prompt_label")
        self.ids.choose_video_btn.text = app.loc.t("choose_video")
        self.ids.file_label.text = app.loc.t("no_file_selected")
        self.ids.start_btn.text = app.loc.t("start_analysis")
        self.ids.model_label.text = app.loc.t("choose_model_label")
        self.ids.word_count_label.text = app.loc.t("word_count", count=0, max=MAX_WORDS_IN_PROMPT)
        self.ids.status_label.text = ""

        self.video_path = None
        self.selected_model = None
        self.results = []
        self.current_screenshot_index = None

        self._refresh_model_buttons()

    def choose_video(self):
        """
        Відкриває нативний вибір файлу через plyer - на Android це
        системний файловий провідник, на комп'ютері - звичайне вікно
        вибору файлу.
        """
        try:
            from plyer import filechooser
        except Exception:
            self.ids.status_label.text = "plyer недоступний на цій платформі"
            return

        filechooser.open_file(
            on_selection=self._on_video_selected,
            filters=[["Video", "*.mp4", "*.avi", "*.mov", "*.mkv"]],
        )

    def _on_video_selected(self, selection):
        if not selection:
            return
        self.video_path = selection[0]
        self.ids.file_label.text = os.path.basename(self.video_path)

    def select_model(self, model_name):
        self.selected_model = model_name
        self._refresh_model_buttons()

    def _refresh_model_buttons(self):
        for child in self.ids.model_buttons.children:
            if isinstance(child, ModelButton):
                child.is_selected = (child.model_name == self.selected_model)

    def update_word_count(self, text):
        app = App.get_running_app()
        count = len(text.split()) if text.strip() else 0
        self.ids.word_count_label.text = app.loc.t("word_count", count=count, max=MAX_WORDS_IN_PROMPT)
        self.ids.word_count_label.color = (0.8, 0.2, 0.2, 1) if count > MAX_WORDS_IN_PROMPT else (0.6, 0.6, 0.6, 1)

    def start_analysis(self):
        app = App.get_running_app()
        loc = app.loc

        if not self.video_path:
            self.ids.status_label.text = loc.t("status_choose_video_first")
            return
        if not self.selected_model:
            self.ids.status_label.text = loc.t("status_choose_model")
            return

        prompt_text = self.ids.prompt_input.text.strip()
        if not prompt_text:
            self.ids.status_label.text = loc.t("status_write_query")
            return

        words = prompt_text.split()
        if len(words) > MAX_WORDS_IN_PROMPT:
            prompt_text = " ".join(words[:MAX_WORDS_IN_PROMPT])

        self.ids.start_btn.disabled = True
        self.ids.status_label.text = loc.t("status_cutting_frames")

        thread = threading.Thread(
            target=self._run_pipeline,
            args=(prompt_text, self.selected_model, loc.language),
            daemon=True,
        )
        thread.start()

    def _set_status_async(self, key, **kwargs):
        loc = App.get_running_app().loc
        Clock.schedule_once(lambda dt: setattr(self.ids.status_label, "text", loc.t(key, **kwargs)))

    def _run_pipeline(self, prompt_text, model_name, language):
        loc = App.get_running_app().loc
        try:
            frames = extract_frames(self.video_path, max_frames=MAX_FRAMES)
            self._set_status_async("status_frames_cut", count=len(frames))

            matches = gemini_tools.find_object_in_frames(
                frames, prompt_text, model_name=model_name, language=language
            )
            self._set_status_async("status_moments_found", count=len(matches))

            screenshots_dir = os.path.join(App.get_running_app().user_data_dir, SCREENSHOTS_SUBFOLDER)
            os.makedirs(screenshots_dir, exist_ok=True)

            results = []
            for match in matches:
                if not (0 <= match.frame_number < len(frames)):
                    continue
                timestamp_sec = frames[match.frame_number]["timestamp_sec"]
                screenshot_path = os.path.join(screenshots_dir, f"frame_{match.frame_number}.jpg")
                grab_screenshot(self.video_path, timestamp_sec, screenshot_path)
                results.append({
                    "time_str": format_time(timestamp_sec),
                    "timestamp_sec": timestamp_sec,
                    "description": match.description,
                    "screenshot_path": screenshot_path,
                })

            results.sort(key=lambda r: r["timestamp_sec"])
            Clock.schedule_once(lambda dt: self._show_results(results, prompt_text))

        except gemini_tools.MissingApiKeyError:
            Clock.schedule_once(lambda dt: self._on_pipeline_error(loc.t("status_error", error="no API key")))
        except Exception as error:
            Clock.schedule_once(lambda dt: self._on_pipeline_error(loc.t("status_error", error=error)))

    def _on_pipeline_error(self, text):
        self.ids.status_label.text = text
        self.ids.start_btn.disabled = False

    def _show_results(self, results, prompt_text):
        app = App.get_running_app()
        loc = app.loc

        self.ids.start_btn.disabled = False
        self.ids.status_label.text = loc.t("status_done", count=len(results))
        self.results = results

        self.ids.report_list.clear_widgets()

        if not results:
            self.ids.report_list.add_widget(Label(
                text=loc.t("nothing_found_list"), color=(0.6, 0.6, 0.6, 1), size_hint_y=None, height=40,
            ))
            self.ids.description_label.text = loc.t("nothing_found_description", query=prompt_text)
            self.ids.screenshot_image.source = ""
            return

        for index, result in enumerate(results):
            btn = ReportItemButton(
                text=f"{result['time_str']}\n{result['description'][:45]}",
                size_hint_y=None,
                height=64,
            )
            btn.bind(on_release=lambda instance, i=index: self.show_result(i))
            self.ids.report_list.add_widget(btn)

        self.show_result(0)

    def show_result(self, index):
        if not (0 <= index < len(self.results)):
            return
        self.current_screenshot_index = index
        result = self.results[index]

        # Підсвічуємо обрану кнопку (children в Kivy йдуть у зворотньому
        # порядку додавання - останній доданий віджет опиняється першим)
        children = list(reversed(self.ids.report_list.children))
        for i, child in enumerate(children):
            if isinstance(child, ReportItemButton):
                child.is_selected = (i == index)

        self.ids.description_label.text = f"{result['time_str']} — {result['description']}"
        self.ids.screenshot_image.source = result["screenshot_path"]
        self.ids.screenshot_image.reload()


class SmartSurveillanceApp(App):
    loc = None

    def build(self):
        Window.clearcolor = (0.07, 0.07, 0.09, 1)
        request_android_permissions()

        settings = {"language": "ua"}  # мобільна версія поки що без збереження мови між запусками
        self.loc = Localization(settings["language"])

        sm = ScreenManager(transition=NoTransition())
        sm.add_widget(SetupScreen(name="setup"))
        sm.add_widget(MainScreen(name="main"))

        if config.load_api_key():
            sm.current = "main"
        else:
            sm.current = "setup"

        return sm

    def go_to_main_screen(self):
        self.root.current = "main"


if __name__ == "__main__":
    SmartSurveillanceApp().run()
