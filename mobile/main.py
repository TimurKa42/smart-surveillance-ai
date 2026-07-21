"""
main.py (мобільна версія на Kivy)
"""
import os
import threading
import time
import webbrowser
import shutil
from kivy.uix.modalview import ModalView
from kivy.uix.scatterlayout import ScatterLayout
from kivy.uix.image import AsyncImage
from plyer import storagepath

from kivy.animation import Animation
from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.properties import BooleanProperty, DictProperty, NumericProperty, StringProperty
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.screenmanager import FadeTransition, Screen, ScreenManager
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.widget import Widget
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
    # Легка мікровібрація на дотик - animate_press викликається з
    # on_press буквально КОЖНОЇ кастомної кнопки в застосунку
    # (GhostButton, AccentButton, ModelButton, ThemeChipButton,
    # ReportItemButton, CloseButton), тому це єдина точка, а не
    # окремі виклики в кожному обробнику.
    haptic_feedback()


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


# ---------------------------------------------------------------------
# Нативний вибір відео (замінює plyer.filechooser на Android).
#
# ПРИЧИНА: plyer.filechooser на Android для деяких провайдерів (напр.
# системний застосунок "Файли"/DocumentsUI, Google Drive тощо) не вміє
# перетворити повернутий content://-URI на звичайний файловий шлях і
# замість шляху мовчки повертає None у списку selection. Далі код
# викликав os.path.basename(None) -> TypeError і застосунок падав.
# Галерея зазвичай віддає шлях, який plyer розуміє, тому звідти вибір
# працював, а з "Файлів" - падав.
#
# Рішення: керуємо Android Intent'ом самі (ACTION_OPEN_DOCUMENT) і самі
# копіюємо вміст обраного URI через ContentResolver у файл усередині
# застосунку - це працює однаково надійно для БУДЬ-якого провайдера.
# ---------------------------------------------------------------------
_video_pick_callback = None
REQUEST_CODE_PICK_VIDEO = 0x4A11


def register_video_picker_listener():
    """Реєструє обробник результату Intent'а. Викликати один раз при старті застосунку."""
    if platform != "android":
        return
    try:
        from android import activity
        activity.bind(on_activity_result=_on_activity_result)
    except Exception:
        pass


def _on_activity_result(request_code, result_code, intent):
    global _video_pick_callback
    if request_code != REQUEST_CODE_PICK_VIDEO:
        return

    callback = _video_pick_callback
    _video_pick_callback = None
    if callback is None:
        return

    RESULT_OK = -1
    if result_code != RESULT_OK or intent is None:
        Clock.schedule_once(lambda dt: callback(None))
        return

    try:
        uri = intent.getData()
    except Exception:
        uri = None

    if uri is None:
        Clock.schedule_once(lambda dt: callback(None))
        return

    # Копіювання може бути повільним для великих відео - робимо у
    # фоновому потоці, щоб не заморожувати інтерфейс.
    threading.Thread(target=_copy_uri_to_local_file, args=(uri, callback), daemon=True).start()


def _query_display_name(resolver, uri):
    try:
        from jnius import autoclass
        OpenableColumns = autoclass("android.provider.OpenableColumns")
        cursor = resolver.query(uri, None, None, None, None)
        if cursor is None:
            return None
        try:
            if cursor.moveToFirst():
                index = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
                if index >= 0:
                    name = cursor.getString(index)
                    if name:
                        return name
        finally:
            cursor.close()
    except Exception:
        pass
    return None


def _copy_uri_to_local_file(uri, callback):
    try:
        from jnius import autoclass
        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        activity_obj = PythonActivity.mActivity
        resolver = activity_obj.getContentResolver()

        input_stream = resolver.openInputStream(uri)
        if input_stream is None:
            Clock.schedule_once(lambda dt: callback(None))
            return

        app = App.get_running_app()
        cache_dir = os.path.join(app.user_data_dir, "picked_videos")
        os.makedirs(cache_dir, exist_ok=True)

        display_name = _query_display_name(resolver, uri) or f"video_{int(time.time())}.mp4"
        dest_path = os.path.join(cache_dir, display_name)

        with open(dest_path, "wb") as out_file:
            java_buffer = bytearray(65536)
            while True:
                read_count = input_stream.read(java_buffer)
                if read_count == -1:
                    break
                out_file.write(bytes(java_buffer[:read_count]))
        input_stream.close()

        Clock.schedule_once(lambda dt: callback(dest_path))
    except Exception as e:
        print("Помилка копіювання обраного файлу:", e)
        Clock.schedule_once(lambda dt: callback(None))


def open_native_video_picker(callback):
    """
    Викликає callback(path_or_none) з ГОЛОВНОГО потоку (через Clock)
    незалежно від платформи - MainScreen._on_video_selected() завжди
    може розраховувати на це.
    """
    global _video_pick_callback

    if platform != "android":
        # На комп'ютері (для тестування "python main.py" на Linux/macOS)
        # лишаємо plyer - там усе це не актуально.
        try:
            from plyer import filechooser
            filechooser.open_file(
                on_selection=lambda sel: callback(sel[0] if sel else None),
                filters=[["Video", "*.mp4", "*.avi", "*.mov", "*.mkv"]],
            )
        except Exception:
            callback(None)
        return

    _video_pick_callback = callback
    try:
        from jnius import autoclass, cast
        Intent = autoclass("android.content.Intent")
        PythonActivity = autoclass("org.kivy.android.PythonActivity")

        intent = Intent(Intent.ACTION_OPEN_DOCUMENT)
        intent.addCategory(Intent.CATEGORY_OPENABLE)
        intent.setType("video/*")

        current_activity = cast("android.app.Activity", PythonActivity.mActivity)
        current_activity.startActivityForResult(intent, REQUEST_CODE_PICK_VIDEO)
    except Exception as e:
        print("Не вдалось відкрити пікер файлів:", e)
        _video_pick_callback = None
        callback(None)


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


def haptic_feedback(amplitude=None, duration_ms=15):
    """
    ВАЖЛИВО: раніше "сила вібрації" керувала лише ТРИВАЛІСТЮ виклику
    plyer.vibrator.vibrate(sec) (0-0.1 сек). Різниця між, наприклад,
    0.03с і 0.08с на дотик практично непомітна - звідси і скарга, що
    "повзунок не працює". plyer взагалі не вміє керувати амплітудою.

    Тепер викликаємо android.os.Vibrator напряму через pyjnius і, якщо
    версія Android дозволяє (8.0+, API 26+), керуємо РЕАЛЬНОЮ амплітудою
    мотора через VibrationEffect.createOneShot(ms, amplitude). Це і є
    справжня "сила" вібрації, а не тривалість.

    amplitude: 0.0-1.0 (якщо None - береться app.vibration_strength)
    duration_ms: тривалість одного імпульсу в мілісекундах (за
    замовчуванням - легка мікровібрація на дотик до кнопки).
    """
    if platform != "android":
        return

    app = App.get_running_app()
    if app is not None and not app.vibration_enabled:
        return

    if amplitude is None:
        amplitude = app.vibration_strength if app is not None else 0.6
    amplitude = max(0.0, min(1.0, amplitude))
    if amplitude <= 0:
        return

    try:
        from jnius import autoclass

        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        Context = autoclass("android.content.Context")
        BuildVersion = autoclass("android.os.Build$VERSION")

        activity = PythonActivity.mActivity
        vib_service = activity.getSystemService(Context.VIBRATOR_SERVICE)
        if vib_service is None:
            return

        if BuildVersion.SDK_INT >= 26:
            VibrationEffect = autoclass("android.os.VibrationEffect")
            amplitude_int = max(1, min(255, round(amplitude * 255)))
            effect = VibrationEffect.createOneShot(duration_ms, amplitude_int)
            vib_service.vibrate(effect)
        else:
            # Старі версії Android не вміють в амплітуду - лишається
            # звичайна вібрація фіксованої "сили", керована лише часом.
            vib_service.vibrate(duration_ms)
    except Exception:
        pass


def haptic_feedback_report_ready():
    """Легка вібрація протягом ~2 секунд, коли звіт готовий."""
    haptic_feedback(duration_ms=2000)


class SettingsModal(ModalView):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Висота НЕ фіксована часткою екрана - вона рахується в .kv
        # (height: content.height) під реальний контент, тому зверху
        # над "Налаштування" більше нема порожнього простору.
        self.size_hint = (1, None)
        self.pos_hint = {'x': 0, 'y': 0}
        self.background_color = (0, 0, 0, 0)

    def on_open(self):
        """Плавний виїзд шторки знизу вгору замість миттєвої появи."""
        target_y = self.y
        self.y = -self.height
        Animation(y=target_y, duration=0.22, t="out_cubic").start(self)

    def reset_app(self):
        app = App.get_running_app()
        config.save_api_key("")
        self.dismiss()
        app.root.current = "setup"

    def test_vibrate(self, instance, value):
        # Довший імпульс (150мс), ніж звичайна мікровібрація на дотик
        # (15мс) - інакше різницю в амплітуді на повзунку майже не
        # відчутно, і повзунок знову здаватиметься "неробочим".
        haptic_feedback(amplitude=value, duration_ms=150)


class LightboxModal(ModalView):
    def __init__(self, image_path, **kwargs):
        super().__init__(**kwargs)
        self.image_path = image_path
        self.size_hint = (1, 1)
        self.background_color = (0, 0, 0, 0.9)

        app = App.get_running_app()

        # ВАЖЛИВО: раніше кнопки додавались напряму в ModalView з
        # pos_hint={'top': 1, ...}. Внутрішній контейнер ModalView не
        # завжди чесно підтримує pos_hint для дітей так, як звичайний
        # FloatLayout - тому кнопки "злітали" в центр екрана замість
        # правого верхнього кута. Тепер явний FloatLayout - і позиція
        # кнопок рахується вручну через self.pos (dp-точно, з
        # урахуванням вирізу камери app.safe_top/app.safe_right), а не
        # через pos_hint - це завжди працює однаково передбачувано.
        root = FloatLayout()

        scatter = ScatterLayout(do_rotation=False)
        img = AsyncImage(source=image_path, fit_mode="contain")
        scatter.add_widget(img)
        root.add_widget(scatter)

        self.top_bar = BoxLayout(
            orientation="horizontal",
            size_hint=(None, None),
            size=(dp(160), dp(44)),
            spacing=dp(8),
        )

        save_btn = GhostButton(
            text=app.t("lightbox_save") if app else "Зберегти",
            size_hint=(None, None),
            size=(dp(108), dp(44)),
        )
        save_btn.bind(on_release=self.save_to_gallery)
        self.top_bar.add_widget(save_btn)

        close_btn = CloseButton(size_hint=(None, None), size=(dp(44), dp(44)))
        close_btn.bind(on_release=self.dismiss)
        self.top_bar.add_widget(close_btn)

        root.add_widget(self.top_bar)
        self.add_widget(root)

        self._reposition_top_bar()
        Window.bind(size=self._reposition_top_bar)
        if app:
            app.bind(safe_top=self._reposition_top_bar, safe_right=self._reposition_top_bar)
        self.bind(on_dismiss=self._unbind_reposition)

    def _reposition_top_bar(self, *args):
        app = App.get_running_app()
        safe_top = app.safe_top if app else 0
        safe_right = app.safe_right if app else 0
        margin = dp(12)
        self.top_bar.pos = (
            Window.width - self.top_bar.width - margin - dp(safe_right),
            Window.height - self.top_bar.height - margin - dp(safe_top),
        )

    def _unbind_reposition(self, *args):
        Window.unbind(size=self._reposition_top_bar)
        app = App.get_running_app()
        if app:
            app.unbind(safe_top=self._reposition_top_bar, safe_right=self._reposition_top_bar)

    def save_to_gallery(self, *args):
        try:
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

class ReportItemButton(ButtonBehavior, BoxLayout):
    """
    У списку тепер тільки ЧАС - компактний чіп фіксованої висоти.
    Опис від ШІ лишається там, де й був - у панелі деталей праворуч
    (description_label), яка показує "{час} — {опис}" після вибору
    пункту. Раніше тут намагались вмістити ще й опис прямо в кожен
    пункт списку - у вузькій колонці (~40% екрана) довгий український
    текст переносився по одній літері на рядок (це і було на скріні:
    вертикальний "стовпчик" з літер).
    """
    is_selected = BooleanProperty(False)
    scale = NumericProperty(1.0)
    time_text = StringProperty("")

class ThemeChipButton(Button):
    is_selected = BooleanProperty(False)
    scale = NumericProperty(1.0)

class GhostButton(Button):
    scale = NumericProperty(1.0)

class AccentButton(Button):
    scale = NumericProperty(1.0)

class CloseButton(Button):
    """
    Кнопка закриття лайтбоксу. Раніше хрестик малювався текстовим
    символом "✕" - на деяких системних шрифтах Android цей гліф
    відсутній і замість нього рендериться "тофу"-прямокутник (саме це
    і виглядало як "перекреслений прямокутник" на скріні). Тепер
    хрестик малюється вручну двома лініями в canvas .kv-правила -
    він не залежить від того, чи є потрібний символ у шрифті.
    """
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
        open_native_video_picker(self._on_video_selected)

    def _on_video_selected(self, path):
        """
        Викликається як з нативного пікера (Android), так і з plyer
        (десктоп-тест) - в обох випадках гарантовано з головного потоку.
        path може бути None (користувач скасував вибір, або якийсь
        провайдер файлів не віддав дані) - раніше саме на цьому падало
        з TypeError у os.path.basename(None). Тепер - просто повідомлення,
        без краху.
        """
        Clock.schedule_once(lambda dt: self._apply_video_selection(path))

    def _apply_video_selection(self, path):
        app = App.get_running_app()
        if not path or not os.path.exists(path):
            self.ids.status_label.text = app.t("status_video_open_failed")
            return
        self.video_path = path
        self.ids.file_label.text = os.path.basename(path)

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

        haptic_feedback_report_ready()

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
            # У списку - тільки час, фіксована компактна висота.
            # Повний опис від ШІ показується у панелі справа після
            # вибору (description_label), а не тут.
            btn = ReportItemButton(
                time_text=result["time_str"],
                size_hint_y=None,
                height=dp(44),
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
    # Сила вібрації (амплітуда, 0..1) - раніше називалось "vibration"
    # і було тривалістю в секундах, тепер це амплітуда мотора.
    vibration_strength = NumericProperty(0.6)
    vibration_enabled = BooleanProperty(True)

    is_landscape = BooleanProperty(False)
    window_width = NumericProperty(360)

    safe_top = NumericProperty(0)
    safe_bottom = NumericProperty(0)
    safe_left = NumericProperty(0)
    safe_right = NumericProperty(0)

    loc = None

    def build(self):
        request_android_permissions()
        register_video_picker_listener()

        settings = settings_store.load_settings()
        self.loc = Localization(settings["language"])
        self.language = settings["language"]
        self.theme_name = settings["theme"]
        self.vibration_strength = settings.get("vibration", 0.6)
        self.vibration_enabled = settings.get("vibration_enabled", True)
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
        SettingsModal().open()

    def safe_set_language(self, lang):
        self.set_language(lang)

    def safe_set_theme(self, theme_val):
        self.set_theme(theme_val)

    def toggle_vibration(self, enabled):
        self.vibration_enabled = enabled
        self._persist_settings()

    def save_vibration(self, value):
        self.vibration_strength = value
        self._persist_settings()

    def _persist_settings(self):
        """
        Зберігає ВСІ чотири налаштування одразу (тема + мова + сила
        вібрації + увімкнена/вимкнена). save_settings() перезаписує
        файл цілком - якщо зберігати лише один ключ, попередньо
        збережені значення інших губляться. Єдина точка збереження
        прибирає цей клас багів назавжди.
        """
        settings_store.save_settings({
            "theme": self.theme_name,
            "language": self.language,
            "vibration": self.vibration_strength,
            "vibration_enabled": self.vibration_enabled,
        })

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
        self._persist_settings()

    def set_language(self, language):
        # ВАЖЛИВО: спершу оновлюємо self.loc (звичайний Python-об'єкт,
        # сам по собі НЕ запускає перемальовування .kv), і лише ПОТІМ
        # self.language (це Kivy Property - саме її зміна змушує .kv
        # перечитати app.t(...) по всьому екрану). Якщо зробити навпаки
        # (як було) - .kv встигає перечитати тексти ДО того, як self.loc
        # дізнався про нову мову, тому підсвітка кнопки "стрибає" на
        # нову мову, а самі тексти лишаються зі старої - це і був баг
        # "інверсії" UA/EN.
        self.loc.set_language(language)
        self.language = language
        self._persist_settings()

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
