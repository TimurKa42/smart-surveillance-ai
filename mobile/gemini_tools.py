"""
gemini_tools.py (мобільна версія)

ВАЖЛИВА ЗМІНА: цей файл більше НЕ використовує офіційну бібліотеку
google-genai. Причина - вона всередині себе жорстко залежить від
pydantic, а pydantic, своєю чергою, залежить від pydantic_core -
скомпільованого Rust-модуля. python-for-android не вміє коректно
зібрати такі скомпільовані модулі під архітектуру телефону (ARM64) і
завжди підставляв версію під архітектуру сервера збірки (x86_64), через
що застосунок падав з "is for EM_X86_64 instead of EM_AARCH64" одразу
при старті.

Замість SDK тут звичайний HTTP-запит (бібліотека requests - чистий
Python, без скомпільованих залежностей) напряму до Gemini REST API.
Це трохи більше "ручної" роботи (самим формувати JSON запиту і
розбирати відповідь), зате повністю усуває проблему з архітектурою.

Головна відмінність від десктопної версії: там ключ обов'язково лежить
у .env ще ДО старту програми. Тут же користувач вводить ключ вже ПІСЛЯ
запуску застосунку, на екрані Setup - тому ключ береться "ліниво", при
кожному реальному виклику, через config.load_api_key().
"""
import base64
import json
import time
from dataclasses import dataclass
from concurrent.futures import CancelledError, ThreadPoolExecutor, as_completed

import requests

import config

BATCH_SIZE = 40

# Скільки пачок кадрів відправляємо в Gemini ОДНОЧАСНО. Раніше пачки
# йшли одна за одною в звичайному циклі - для відео, де кадрів
# набиралось на 3-4 пачки, це означало 3-4 послідовних мережевих
# очікування замість одного. Gemini REST не має проблем з паралельними
# запитами по одному ключу - це просто N незалежних HTTP-викликів.
# 4 - обережне значення з запасом під безкоштовний ліміт ключа; якщо
# у тебе платний тір - можна сміливо піднімати до 6-8.
MAX_PARALLEL_BATCHES = 4

DEFAULT_MODEL_NAME = "gemini-3.6-flash"
DEFAULT_PROMPT_LANGUAGE = "ua"

API_URL_TEMPLATE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
REQUEST_TIMEOUT_SEC = 120

# Скільки РАЗІВ ДОДАТКОВО пробуємо один і той самий батч, якщо він
# впав з ТИМЧАСОВОЮ помилкою (див. RETRYABLE_ERROR_KINDS нижче), перш
# ніж здатись і показати помилку користувачу. 3 додаткових спроби
# (тобто до 4 разів сумарно) - розумний баланс: досить, щоб пережити
# короткий "гикання" мережі чи миттєвий сплеск 429 від Gemini, і не
# настільки багато, щоб користувач сидів і чекав хвилинами на явно
# зламаний запит.
MAX_RETRIES = 3

# Базова пауза перед повтором (секунди). Кожна наступна спроба чекає
# вдвічі довше за попередню (класичний exponential backoff:
# 1.5s -> 3s -> 6s) - це дає серверу Gemini час "оговтатись" від
# перевантаження (429) чи тимчасового збою (5xx), замість того, щоб
# одразу бомбардувати його новим запитом.
RETRY_BACKOFF_BASE_SEC = 1.5

# Які "види" помилок ІМЕЄ СЕНС повторювати. "rate_limit" (429) і
# "server" (5xx) - явно тимчасові, сервер сам підказує "спробуй
# пізніше". "timeout" і "network" теж часто минущі (нестабільний
# мобільний інтернет, короткий обрив). А ось "invalid_key" (ключ
# точно поганий) чи "unknown" (щось структурно не так у відповіді)
# повторювати немає сенсу - результат буде той самий, лише даремно
# витратимо час користувача.
RETRYABLE_ERROR_KINDS = {"rate_limit", "server", "timeout", "network"}


@dataclass
class Match:
    """Один знайдений момент - номер кадру і короткий опис від Gemini."""
    frame_number: int
    description: str


SYSTEM_PROMPTS = {
    "ua": (
        "Ти - система відеоспостереження. Знайди на кадрах нижче наступний об'єкт:\n"
        "{user_prompt}\n\n"
        "Правила відповіді:\n"
        "- Якщо об'єкта на кадрі нема - просто не включай цей кадр у відповідь.\n"
        "- Опис - 3-6 слів, лише суть (що це і де), українською мовою, без вступних "
        "фраз на кшталт \"на цьому кадрі видно\" і без домислів."
    ),
    "en": (
        "You are a video surveillance system. Find the following object in the frames below:\n"
        "{user_prompt}\n\n"
        "Response rules:\n"
        "- If the object is not present in a frame, simply do not include that frame in the response.\n"
        "- Description - 3-6 words, just the essence (what it is and where), in English, without "
        "introductory phrases like \"this frame shows\" and without speculation."
    ),
}

# JSON Schema простим словником - Gemini REST API розуміє його так само,
# як і раніше через SDK, без потреби у Pydantic-класах.
RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "matches": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "frame_number": {"type": "INTEGER"},
                    "description": {"type": "STRING"},
                },
                "required": ["frame_number", "description"],
            },
        }
    },
    "required": ["matches"],
}


# Gemini 3.x (і 3.5 Flash-Lite, і 3.6 Flash) більше НЕ підтримує
# temperature/top_p/top_k у generationConfig - їх треба повністю
# прибрати з payload, інакше API повертає помилку. Замість цього
# з'явився thinkingConfig.thinkingLevel - ВАЖЛИВО: це саме ВКЛАДЕНИЙ
# об'єкт thinkingConfig з полем thinkingLevel у camelCase, а НЕ плоске
# поле "thinking_level" напряму в generationConfig (це і спричиняло
# 400 Bad Request - Gemini просто не розпізнавав такий параметр).
#
# Для нашої задачі (структурований пошук об'єкта на кадрах, відповідь
# суворо за JSON-схемою) глибокі роздуми не потрібні - тому свідомо
# беремо мінімально достатній рівень для кожної моделі:
# - Flash-Lite за замовчуванням і так найкраще працює на "minimal"
#   (це навіть офіційно рекомендований рівень Google для задач
#   класифікації/екстракції з високою пропускною здатністю).
# - 3.6 Flash за замовчуванням має "medium" - для простого пошуку
#   об'єкта в кадрі цього зайве, "low" дає ту саму точність швидше
#   й дешевше.
THINKING_LEVEL_BY_MODEL = {
    "gemini-3.5-flash-lite": "minimal",
    "gemini-3.6-flash": "low",
}
DEFAULT_THINKING_LEVEL = "low"


class MissingApiKeyError(Exception):
    """Кидається, якщо спробувати аналізувати відео без збереженого ключа."""


class GeminiApiError(Exception):
    """
    Кидається, якщо Gemini API повернув помилку (неправильний ключ, ліміти
    тощо), АБО якщо запит взагалі не дійшов до сервера (нема інтернету,
    таймаут).

    kind - короткий машинний код причини, яким UI (main.py) вибирає
    зрозумілий людині текст замість сирого технічного повідомлення:
    - "network"      - нема з'єднання з інтернетом.
    - "timeout"      - сервер не відповів вчасно.
    - "rate_limit"   - 429, перевищено ліміт запитів.
    - "invalid_key"  - 401/403, ключ не підходить.
    - "server"       - 5xx, тимчасова проблема на боці Gemini.
    - "blocked"      - Gemini відповів 200 OK, але без жодного
                       результату (найчастіше - спрацював safety-
                       фільтр і запит/кадри заблоковано).
    - "unknown"      - усе інше (напр. неочікувана структура відповіді).
    """

    def __init__(self, message, kind="unknown"):
        super().__init__(message)
        self.kind = kind


def check_api_key(api_key):
    """
    Перевіряє ключ РЕАЛЬНИМ запитом до Gemini API (список моделей -
    найлегший можливий запит, нічого не генерує і не витрачає квоту).

    Навмисно НЕ перевіряємо ключ за виглядом/префіксом рядка (напр.
    "AQ.Ab8...") - формат ключів Google може відрізнятись і змінюватись
    з часом, тому єдиний надійний спосіб дізнатись, робочий ключ чи ні -
    справді запитати ним щось у Gemini.

    Повертає один з трьох станів:
    - "valid"          - ключ підходить, 200 OK.
    - "invalid"        - Gemini явно відхилив ключ (400/401/403).
    - "network_error"  - не вдалося достукатись до сервера взагалі
                          (нема інтернету, таймаут тощо). Це НЕ означає,
                          що ключ поганий - UI повинен показати інше
                          повідомлення, а не "ключ недійсний".
    """
    try:
        response = requests.get(
            "https://generativelanguage.googleapis.com/v1beta/models",
            params={"key": api_key},
            timeout=15,
        )
    except requests.exceptions.RequestException:
        return "network_error"

    if response.status_code == 200:
        return "valid"
    if response.status_code in (400, 401, 403):
        return "invalid"
    # Інший код (5xx, тимчасові ліміти тощо) - не можемо впевнено
    # сказати, що ключ поганий, тому теж трактуємо як мережеву невдачу.
    return "network_error"


def _get_api_key():
    api_key = config.load_api_key()
    if not api_key:
        raise MissingApiKeyError(
            "GEMINI_API_KEY не знайдено. Спочатку введи ключ на екрані налаштувань."
        )
    return api_key


def find_object_in_frames(
    frames, user_prompt, model_name=DEFAULT_MODEL_NAME, language=DEFAULT_PROMPT_LANGUAGE,
    progress_callback=None, is_cancelled=None,
):
    """
    Розбиває кадри на пачки по BATCH_SIZE і аналізує їх ПАРАЛЕЛЬНО
    (до MAX_PARALLEL_BATCHES одночасно) замість послідовного циклу.
    Порядок результатів у підсумковому списку не важливий - виклик
    show_result() у main.py все одно сортує results за timestamp_sec.

    progress_callback(done, total), якщо переданий, викликається ПІСЛЯ
    кожної завершеної пачки (done - скільки з total пачок вже готово) -
    цим main.py оновлює прогрес-бар аналізу. Викликається з фонового
    потоку, тож сам callback має бути потокобезпечним (у main.py це
    просто Clock.schedule_once).

    is_cancelled, якщо переданий, - функція БЕЗ аргументів, що повертає
    True, коли аналіз потрібно перервати (наприклад, користувач
    натиснув "Очистити все" або запустив новий аналіз, поки цей ще
    йшов). ВАЖЛИВО: реально зупинити вже запущений HTTP-запит
    неможливо (потік просто чекає відповідь сервера) - але можна
    скасувати ті батчі, які ще НЕ встигли стартувати і просто стоять у
    черзі ThreadPoolExecutor (бо одночасно виконується не більше
    MAX_PARALLEL_BATCHES). Для довгого відео з багатьма батчами це
    реально економить час, трафік і квоту API на запити, результат
    яких все одно буде проігноровано.
    """
    api_key = _get_api_key()

    batches = [
        (batch_start, frames[batch_start:batch_start + BATCH_SIZE])
        for batch_start in range(0, len(frames), BATCH_SIZE)
    ]

    if not batches:
        return []

    all_matches = []
    worker_count = min(MAX_PARALLEL_BATCHES, len(batches))
    total_batches = len(batches)
    done_batches = 0

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {
            executor.submit(_analyze_batch, api_key, batch, offset, user_prompt, model_name, language): offset
            for offset, batch in batches
        }
        for future in as_completed(futures):
            if is_cancelled is not None and is_cancelled():
                # Скасовуємо всі батчі, які ще не встигли стартувати -
                # ті, що вже виконуються (max MAX_PARALLEL_BATCHES штук),
                # усе одно доведеться дочекатись при виході з `with`
                # (ThreadPoolExecutor чекає завершення активних потоків),
                # але їхній результат нижче просто ігнорується.
                for pending_future in futures:
                    pending_future.cancel()
                break

            try:
                all_matches.extend(future.result())
            except CancelledError:
                # Сам future був скасований (не встиг стартувати) -
                # це очікувано після is_cancelled() вище, просто йдемо
                # до наступного.
                continue
            done_batches += 1
            if progress_callback is not None:
                progress_callback(done_batches, total_batches)

    return all_matches


def _analyze_batch(api_key, batch, index_offset, user_prompt, model_name, language):
    """
    Аналізує одну пачку кадрів через прямий REST-виклик до Gemini.

    index_offset потрібен, щоб frame_number у відповіді вказував на
    справжній номер кадру в загальному списку (а не на позицію 0..39
    всередині конкретної пачки).

    Якщо запит впаде з ТИМЧАСОВОЮ помилкою (rate_limit/server/timeout/
    network - див. RETRYABLE_ERROR_KINDS) - повторює його ще до
    MAX_RETRIES разів із зростаючою паузою (exponential backoff),
    перш ніж остаточно здатись і перекинути помилку нагору. Помилки,
    повторення яких свідомо безглузде (поганий ключ, дивна структура
    відповіді), одразу летять нагору без жодних спроб.
    """
    system_prompt = SYSTEM_PROMPTS.get(language, SYSTEM_PROMPTS[DEFAULT_PROMPT_LANGUAGE])

    parts = [{"text": system_prompt.format(user_prompt=user_prompt)}]

    for i, frame in enumerate(batch):
        frame_number = index_offset + i
        parts.append({"text": f"Кадр номер {frame_number}:"})
        parts.append({
            "inline_data": {
                "mime_type": "image/jpeg",
                "data": base64.b64encode(frame["jpg_bytes"]).decode("ascii"),
            }
        })

    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {
            "response_mime_type": "application/json",
            "response_schema": RESPONSE_SCHEMA,
            "thinkingConfig": {
                "thinkingLevel": THINKING_LEVEL_BY_MODEL.get(model_name, DEFAULT_THINKING_LEVEL),
            },
        },
    }

    url = API_URL_TEMPLATE.format(model=model_name)

    last_error = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            return _send_batch_request(url, api_key, payload)
        except GeminiApiError as error:
            last_error = error
            is_last_attempt = attempt == MAX_RETRIES
            if error.kind not in RETRYABLE_ERROR_KINDS or is_last_attempt:
                raise
            # Пауза перед повтором росте вдвічі щоразу: 1.5s, 3s, 6s.
            # Викликається з робочого потоку ThreadPoolExecutor - тому
            # звичайний time.sleep() тут абсолютно безпечний, він не
            # блокує ні головний потік Kivy, ні інші батчі (кожен
            # виконується у своєму власному потоці).
            time.sleep(RETRY_BACKOFF_BASE_SEC * (2 ** attempt))

    # Сюди дійти неможливо (цикл або повертає результат, або кидає
    # виняток на останній спробі) - але про всяк випадок, щоб лінтер
    # і читач коду не питали "а що як last_error лишиться None".
    raise last_error


def _send_batch_request(url, api_key, payload):
    """
    Один "сирий" HTTP-виклик до Gemini + розбір відповіді. Винесено з
    _analyze_batch окремою функцією, щоб retry-цикл там міг просто
    викликати це знову при тимчасовій помилці, не дублюючи розбір
    payload щоразу.
    """
    try:
        response = requests.post(
            url,
            params={"key": api_key},
            json=payload,
            timeout=REQUEST_TIMEOUT_SEC,
        )
    except requests.exceptions.Timeout as error:
        raise GeminiApiError(f"Timeout: {error}", kind="timeout") from error
    except requests.exceptions.RequestException as error:
        # Немає з'єднання, DNS не резолвиться, обрив під час запиту
        # тощо - усе, що не дійшло до сервера взагалі.
        raise GeminiApiError(f"Network error: {error}", kind="network") from error

    if response.status_code != 200:
        detail = f"Gemini API повернув помилку {response.status_code}: {response.text[:300]}"
        if response.status_code == 429:
            kind = "rate_limit"
        elif response.status_code in (401, 403):
            kind = "invalid_key"
        elif response.status_code >= 500:
            kind = "server"
        else:
            kind = "unknown"
        raise GeminiApiError(detail, kind=kind)

    result = response.json()

    # Gemini іноді відповідає 200 OK, але БЕЗ жодного результату - типово
    # це safety-фільтр, який заблокував або сам запит (promptFeedback.
    # blockReason на верхньому рівні відповіді), або конкретну відповідь
    # (порожній список candidates). Раніше це не перевірялось окремо і
    # падало нижче в except (KeyError, IndexError) з kind="unknown" -
    # користувач бачив загальне "Щось пішло не так" замість зрозумілого
    # "Gemini відмовився аналізувати ці кадри".
    block_reason = result.get("promptFeedback", {}).get("blockReason")
    if block_reason:
        raise GeminiApiError(
            f"Gemini заблокував запит: {block_reason}", kind="blocked"
        )

    candidates = result.get("candidates") or []
    if not candidates:
        raise GeminiApiError(
            f"Gemini не повернув жодної відповіді: {json.dumps(result)[:300]}", kind="blocked"
        )

    try:
        text_answer = candidates[0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as error:
        raise GeminiApiError(
            f"Неочікувана структура відповіді Gemini: {json.dumps(result)[:300]}", kind="unknown"
        ) from error

    try:
        data = json.loads(text_answer)
    except json.JSONDecodeError as error:
        raise GeminiApiError(f"Gemini повернув невалідний JSON: {text_answer[:300]}", kind="unknown") from error

    return [
        Match(
            frame_number=int(item["frame_number"]),
            description=str(item["description"]),
        )
        for item in data.get("matches", [])
    ]
