"""
gemini_tools.py (мобільна версія)

Головна відмінність від десктопної версії: там ключ обов'язково лежить
у .env ще ДО старту програми (інакше вона одразу падає з ValueError).
Тут же користувач вводить ключ вже ПІСЛЯ запуску застосунку, на екрані
Setup - тому клієнта Gemini не можна створювати один раз при імпорті
модуля. Замість цього client створюється "ліниво", при першому
реальному виклику, і бере ключ через config.load_api_key().
"""
from google import genai
from google.genai import types

import json
from dataclasses import dataclass

import config

BATCH_SIZE = 40

DEFAULT_MODEL_NAME = "gemini-3.5-flash"
DEFAULT_PROMPT_LANGUAGE = "ua"


@dataclass
class Match:
    """
    Один знайдений момент. Раніше це був клас на Pydantic (BaseModel),
    але pydantic_core - це скомпільований Rust-модуль, а
    python-for-android не вміє зібрати його під архітектуру телефону
    (ARM64) - тому на Android застосунок падав з помилкою "is for
    EM_X86_64 instead of EM_AARCH64". dataclass - частина стандартної
    бібліотеки Python, чистий Python-код без компільованих залежностей,
    тому працює однаково і на десктопі, і на Android.
    """
    frame_number: int
    description: str


SYSTEM_PROMPTS = {
    "ua": (
        "Ти - система відеоспостереження. Знайди на кадрах нижче наступний об'єкт:\n"
        "{user_prompt}\n\n"
        "Правила відповіді:\n"
        "- Якщо об'єкта на кадрі нема - просто не включай цей кадр у відповідь.\n"
        "- Опис - 3-6 слів, лише суть (що це і де), українською мовою, без вступних "
        "фраз на кшталт \"на цьому кадрі видно\" і без домислів.\n\n"
        "Відповідай СУВОРО у форматі JSON без жодного додаткового тексту:\n"
        '{{"matches": [{{"frame_number": 0, "description": "..."}}]}}'
    ),
    "en": (
        "You are a video surveillance system. Find the following object in the frames below:\n"
        "{user_prompt}\n\n"
        "Response rules:\n"
        "- If the object is not present in a frame, simply do not include that frame in the response.\n"
        "- Description - 3-6 words, just the essence (what it is and where), in English, without "
        "introductory phrases like \"this frame shows\" and without speculation.\n\n"
        "Respond STRICTLY in this JSON format with no extra text:\n"
        '{{"matches": [{{"frame_number": 0, "description": "..."}}]}}'
    ),
}

# JSON Schema (звичайний словник, не Pydantic-клас) - так само надійно
# примушує Gemini повертати структуровану відповідь, але без жодних
# зовнішніх бібліотек чи скомпільованого коду.
RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "matches": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "frame_number": {"type": "integer"},
                    "description": {"type": "string"},
                },
                "required": ["frame_number", "description"],
            },
        }
    },
    "required": ["matches"],
}


class MissingApiKeyError(Exception):
    """Кидається, якщо спробувати аналізувати відео без збереженого ключа."""


def _get_client():
    api_key = config.load_api_key()
    if not api_key:
        raise MissingApiKeyError(
            "GEMINI_API_KEY не знайдено. Спочатку введи ключ на екрані налаштувань."
        )
    return genai.Client(api_key=api_key)


def find_object_in_frames(frames, user_prompt, model_name=DEFAULT_MODEL_NAME, language=DEFAULT_PROMPT_LANGUAGE):
    """Розбиває кадри на пачки по BATCH_SIZE і аналізує кожну окремим запитом."""
    client = _get_client()
    all_matches = []

    for batch_start in range(0, len(frames), BATCH_SIZE):
        batch = frames[batch_start:batch_start + BATCH_SIZE]
        batch_matches = _analyze_batch(client, batch, batch_start, user_prompt, model_name, language)
        all_matches.extend(batch_matches)

    return all_matches


def _analyze_batch(client, batch, index_offset, user_prompt, model_name, language):
    system_prompt = SYSTEM_PROMPTS.get(language, SYSTEM_PROMPTS[DEFAULT_PROMPT_LANGUAGE])
    contents = [system_prompt.format(user_prompt=user_prompt)]

    for i, frame in enumerate(batch):
        frame_number = index_offset + i
        contents.append(f"Кадр номер {frame_number}:")
        contents.append(
            types.Part.from_bytes(data=frame["jpg_bytes"], mime_type="image/jpeg")
        )

    response = client.models.generate_content(
        model=model_name,
        contents=contents,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=RESPONSE_SCHEMA,
            temperature=0.0,
        ),
    )

    data = json.loads(response.text)
    return [
        Match(
            frame_number=int(item["frame_number"]),
            description=str(item["description"]),
        )
        for item in data.get("matches", [])
    ]
