"""
main.py (мобільна версія на Kivy)
"""
import os
import threading
import webbrowser
import shutil
from kivy.uix.modalview import ModalView
from kivy.uix.scatterlayout import ScatterLayout
from kivy.uix.image import AsyncImage
from plyer import vibrator, storagepath

from kivy.animation import Animation
from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.properties import BooleanProperty, DictProperty, NumericProperty, StringProperty
from kivy.uix.screenmanager import FadeTransition, Screen, ScreenManager
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.utils import platform

import config
import settings_store
import theme
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


def animate_press(widget):
    Animation.cancel_all(widget, "scale")
    Animation(scale=0.96, duration=0.08, t="out_quad").start(widget)


def animate_release(widget):
    Animation.cancel_all(widget, "scale")
    Animation(scale=1.0, duration=0.15, t="out_back").start(widget)


def open_url(url):
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
            pass
    else:
        webbrowser.open(url)


def request_android_permissions():
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


def get_safe_insets():
    if platform != "android":
        return 0, 0, 0, 0
    try:
        from jnius import autoclass
        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        activity = PythonActivity.mActivity
        decor_view = activity.getWindow().getDecorView()
        insets = decor_view.getRootWindowInsets()
        if insets is None:
            return 0, 0, 0, 0

        Build_VERSION = autoclass("android.os.Build$VERSION")
        sdk_int = Build_VERSION.SDK_INT

        top = insets.getSystemWindowInsetTop()
        bottom = insets.getSystemWindowInsetBottom()
        left = insets.getSystemWindowInsetLeft()
        right = insets.getSystemWindowInsetRight()

        if sdk_int >= 28:
            cutout = insets.getDisplayCutout()
            if cutout is not None:
                top = max(top, cutout.getSafeInsetTop())
                bottom = max(bottom, cutout.getSafeInsetBottom())
                left = max(left, cutout.getSafeInsetLeft())
                right = max(right, cutout.getSafeInsetRight())

        density = activity.getResources().getDisplayMetrics().density
        return top / density, bottom / density, left / density, right / density
    except Exception:
        return 0, 0, 0, 0


def haptic_feedback(strength=None):
    try:
        if platform == "android":
            if strength is None:
                app = App.get_running_app()
                strength = app.vibration if app else 0.05
            if strength > 0:
                vibrator.vibrate(strength)
    except Exception:
        pass


class SettingsModal(ModalView):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.size_hint = (1, 0.45)
        self.pos_hint = {'bottom': 1}
        self.background_color = (0, 0, 0, 0)
        
    def reset_app(self):
        app = App.get_running_app()
        haptic_feedback(0.1)
        config.save_api_key("") 
        self.dismiss()
        app.root.current = "setup"

    def test_vibrate(self, instance, value):
        haptic_feedback(value)


class LightboxModal(ModalView):
    def __init__(self, image_path, **kwargs):
        super().__init__(**kwargs)
        self.image_path = image_path
        self.size_hint = (1, 1)
        self.background_color = (0, 0, 0, 0.9)
        
        scatter = ScatterLayout(do_rotation=False)
        img = AsyncImage(source=image_path, fit_mode="contain")
        scatter.add_widget(img)
        self.add_widget(scatter)
        
        close_btn = GhostButton(text="✕ Закрити", size_hint=(None, None), size=(dp(100), dp(40)), pos_hint={'top': 0.95, 'right': 0.95})
        close_btn.bind(on_release=self.dismiss)
        self.add_widget(close_btn)
        
        save_btn = AccentButton(text="📥 Зберегти", size_hint=(None, None), size=(dp(120), dp(40)), pos_hint={'bottom': 0.05, 'center_x': 0.5})
        save_btn.bind(on_release=self.save_to_gallery)
        self.add_widget(save_btn)

    def save_to_gallery(self, *args):
        try:
            haptic_feedback(0.05)
            pics_dir = storagepath.get_pictures_dir()
            filename = os.path.basename(self.image_path)
            dest = os.path.join(pics_dir, filename)
            shutil.copy(self.image_path, dest)
            self.dismiss()
        except Exception as e:
            print("Помилка збереження:", e)


class SetupScreen(Screen):
    error_text = StringProperty("")

    def submit_key(self):
        key = self.ids.api_key_input.text.strip()
        app = App.get_running_app()

        # Полностью убрал строгую проверку! Оставил только проверку на пустоту.
        if not key:
            self.error_text = "Спочатку встав ключ" if app.language == 'ua' else "Please paste your key first"
            return

        config.save_api_key(key)
        self.error_text = ""
        app.go_to_main_screen()
        
    def toggle_password(self):
        inp = self.ids.api_key_input
        inp.password = not inp.password
        app = App.get_running_app()
        # Меняем текст кнопки динамически
        self.ids.eye_btn.text = ("Сховати" if app.language == "ua" else "Hide") if not inp.password else ("Показати" if app.language == "ua" else "Show")

    def open_instructions(self):
        open_url(API_KEY_INSTRUCTIONS_URL)


class ModelButton(Button):
    is_selected = BooleanProperty(False)
    model_name = StringProperty("")
    scale = NumericProperty(1.0)

class ReportItemButton(Button):
    is_selected = BooleanProperty(False)
    scale = NumericProperty(1.0)

class ThemeChipButton(Button):
    is_selected = BooleanProperty(False)
    scale = NumericProperty(1.0)

class GhostButton(Button):
    scale = NumericProperty(1.0)
    
class AccentButton(Button):
    scale = NumericProperty(1.0)


class MainScreen(Screen):
    def on_pre_enter(self, *args):
        self.video_path = None
        self.selected_model = None
        self.results = []
        self.current_screenshot_index = None

        self.refresh_dynamic_texts()
        self._refresh_model_buttons()

    def refresh_dynamic_texts(self):
        app = App.get_running_app()
        if not getattr(self, "video_path", None):
            self.ids.file_label.text = app.t("no_file_selected")

        text = self.ids.prompt_input.text
        count = len(text.split()) if text.strip() else 0
        self.ids.word_count_label.text = app.t("word_count", count=count, max=MAX_WORDS_IN_PROMPT)

    def choose_video(self):
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
        self.ids.word_count_label.text = app.t("word_count", count=count, max=MAX_WORDS_IN_PROMPT)
        over_limit = app.palette["danger"]
        muted = app.palette["text_muted"]
        self.ids.word_count_label.color = over_limit if count > MAX_WORDS_IN_PROMPT else muted

    def clear_all(self):
        app = App.get_running_app()
        self.video_path = None
        self.selected_model = None
        self.results = []
        self.current_screenshot_index = None

        self.ids.file_label.text = app.t("no_file_selected")
        self.ids.prompt_input.text = ""
        self.ids.status_label.text = ""
        self.ids.report_list.clear_widgets()
        self.ids.description_label.text = ""
        
        self.ids.screenshot_image.source = ""
        self.ids.screenshot_image.opacity = 0 
        
        self.ids.start_btn.disabled = False
        self._refresh_model_buttons()

    def start_analysis(self):
        app = App.get_running_app()

        if not self.video_path:
            self.ids.status_label.text = app.t("status_choose_video_first")
            return
        if not self.selected_model:
            self.ids.status_label.text = app.t("status_choose_model")
            return

        prompt_text = self.ids.prompt_input.text.strip()
        if not prompt_text:
            self.ids.status_label.text = app.t("status_write_query")
            return

        words = prompt_text.split()
        if len(words) > MAX_WORDS_IN_PROMPT:
            prompt_text = " ".join(words[:MAX_WORDS_IN_PROMPT])

        self.ids.start_btn.disabled = True
        self.ids.status_label.text = app.t("status_cutting_frames")

        thread = threading.Thread(
            target=self._run_pipeline,
            args=(prompt_text, self.selected_model, app.loc.language),
            daemon=True,
        )
        thread.start()

    def _set_status_async(self, key, **kwargs):
        app = App.get_running_app()
        Clock.schedule_once(lambda dt: setattr(self.ids.status_label, "text", app.t(key, **kwargs)))

    def _run_pipeline(self, prompt_text, model_name, language):
        app = App.get_running_app()
        try:
            frames = extract_frames(self.video_path, max_frames=MAX_FRAMES)
            self._set_status_async("status_frames_cut", count=len(frames))

            matches = gemini_tools.find_object_in_frames(
                frames, prompt_text, model_name=model_name, language=language
            )
            self._set_status_async("status_moments_found", count=len(matches))

            screenshots_dir = os.path.join(app.user_data_dir, SCREENSHOTS_SUBFOLDER)
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
            Clock.schedule_once(lambda dt: self._on_pipeline_error(app.t("status_error", error="no API key")))
        except Exception as error:
            Clock.schedule_once(lambda dt: self._on_pipeline_error(app.t("status_error", error=error)))

    def _on_pipeline_error(self, text):
        self.ids.status_label.text = text
        self.ids.start_btn.disabled = False

    def _show_results(self, results, prompt_text):
        app = App.get_running_app()

        self.ids.start_btn.disabled = False
        self.ids.status_label.text = app.t("status_done", count=len(results))
        self.results = results

        self.ids.report_list.clear_widgets()

        if not results:
            self.ids.report_list.add_widget(Label(
                text=app.t("nothing_found_list"), color=app.palette["text_muted"],
                size_hint_y=None, height=dp(40),
            ))
            self.ids.description_label.text = app.t("nothing_found_description", query=prompt_text)
            self.ids.screenshot_image.source = ""
            self.ids.screenshot_image.opacity = 0
            return

        for index, result in enumerate(results):
            btn = ReportItemButton(
                text=f"{result['time_str']}\n{result['description'][:45]}",
                size_hint_y=None,
                height=dp(64),
            )
            btn.bind(on_release=lambda instance, i=index: self.show_result(i))
            self.ids.report_list.add_widget(btn)

        self.show_result(0)

    def show_result(self, index):
        if not (0 <= index < len(self.results)):
            return
        self.current_screenshot_index = index
        result = self.results[index]

        children = list(reversed(self.ids.report_list.children))
        for i, child in enumerate(children):
            if isinstance(child, ReportItemButton):
                child.is_selected = (i == index)

        self.ids.description_label.text = f"{result['time_str']} — {result['description']}"

        image = self.ids.screenshot_image
        image.source = result["screenshot_path"]
        image.reload()
        image.opacity = 0
        Animation(opacity=1, duration=0.18).start(image)

    def open_lightbox(self, path):
        LightboxModal(path).open()


class SmartSurveillanceApp(App):
    theme_name = StringProperty("auto")
    language = StringProperty("ua")
    palette = DictProperty(theme.DARK)
    vibration = NumericProperty(0.05) # Добавили свойство вибрации

    is_landscape = BooleanProperty(False)
    window_width = NumericProperty(360)

    safe_top = NumericProperty(0)
    safe_bottom = NumericProperty(0)
    safe_left = NumericProperty(0)
    safe_right = NumericProperty(0)

    loc = None

    def build(self):
        request_android_permissions()

        settings = settings_store.load_settings()
        self.loc = Localization(settings["language"])
        self.language = settings["language"]
        self.theme_name = settings["theme"]
        self.vibration = settings.get("vibration", 0.05)
        self.palette = theme.resolve(self.theme_name)
        Window.clearcolor = self.palette["bg"]

        Window.bind(size=self._on_window_size)
        self._on_window_size(Window, Window.size)
        Clock.schedule_once(self._update_safe_insets, 0.3)

        sm = ScreenManager(transition=FadeTransition(duration=0.18))
        sm.add_widget(SetupScreen(name="setup"))
        sm.add_widget(MainScreen(name="main"))

        if config.load_api_key():
            sm.current = "main"
        else:
            sm.current = "setup"

        return sm

    def open_settings(self):
        haptic_feedback(0.05)
        SettingsModal().open()
        
    def safe_set_language(self, lang):
        haptic_feedback(0.05)
        self.set_language(lang)
        
    def safe_set_theme(self, theme_val):
        haptic_feedback(0.05)
        self.set_theme(theme_val)

    def save_vibration(self, value):
        self.vibration = value
        settings = settings_store.load_settings()
        settings["vibration"] = value
        settings_store.save_settings(settings)

    def t(self, key, **kwargs):
        return self.loc.t(key, **kwargs)

    def _on_window_size(self, window, size):
        width, height = size
        self.window_width = width
        self.is_landscape = width > height
        self._update_safe_insets()

    def _update_safe_insets(self, *args):
        top, bottom, left, right = get_safe_insets()
        self.safe_top = top
        self.safe_bottom = bottom
        self.safe_left = left
        self.safe_right = right

    def set_theme(self, theme_name):
        self.theme_name = theme_name
        self.palette = theme.resolve(theme_name)
        Window.clearcolor = self.palette["bg"]
        settings_store.save_settings({"theme": theme_name, "language": self.language})

    def set_language(self, language):
        self.language = language
        self.loc.set_language(language)
        settings_store.save_settings({"theme": self.theme_name, "language": language})

        if self.root:
            try:
                main_screen = self.root.get_screen("main")
                main_screen.refresh_dynamic_texts()
            except Exception:
                pass

    def go_to_main_screen(self):
        self.root.current = "main"

if __name__ == "__main__":
    SmartSurveillanceApp().run()
