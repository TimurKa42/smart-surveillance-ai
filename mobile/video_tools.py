import cv2

# Числові ID властивостей OpenCV, які з'явились у 4.5 (CAP_PROP_ORIENTATION_META
# і CAP_PROP_ORIENTATION_AUTO). Дістаємо через getattr із запасним значенням,
# бо в збірці для Android може стояти дещо старіша версія OpenCV, де цих
# констант ще нема серед іменованих атрибутів, хоча самі числові ID стабільні.
_CAP_PROP_ORIENTATION_META = getattr(cv2, "CAP_PROP_ORIENTATION_META", 48)


def _prepare_orientation(video):
    """
    Телефонні відео майже завжди мають метадані повороту - камеру
    тримали "на боці", а плеєр показує відео вертикально/горизонтально
    ЗАВДЯКИ цій метадані. OpenCV за замовчуванням її ІГНОРУЄ і віддає
    сирі, неповернуті кадри.

    РАНІШЕ тут спершу пробували попросити OpenCV повертати кадри
    самостійно через video.set(CAP_PROP_ORIENTATION_AUTO, 1) і, якщо
    set() повертав True, вважали поворот "вирішеним" і одразу
    поверталися з 0 (без ручного повороту).

    ПРОБЛЕМА: на багатьох Android-збірках OpenCV (зокрема тих, що
    йдуть у python-for-android/Buildozer) video.set(...) МОВЧКИ
    повертає True - властивість формально "прийнялась" - але backend
    її насправді ІГНОРУЄ, і кадри так і приходили неповернутими. Через
    це вертикальні відео в звіті лягали "на бік" (кут зчитувався
    правильно, але ніколи не застосовувався).

    Тепер ми НЕ покладаємось на цей ненадійний прапорець і ЗАВЖДИ самі
    читаємо кут із метаданих та повертаємо кадри вручну через
    _apply_manual_rotation() - це працює однаково незалежно від збірки
    OpenCV.
    """
    try:
        angle = int(video.get(_CAP_PROP_ORIENTATION_META)) % 360
    except Exception:
        angle = 0

    # ТИМЧАСОВИЙ DEBUG - видалити після діагностики повороту на Android.
    # Виводить у logcat реальні розміри кадру та кут з метаданих,
    # щоб побачити, що бачить САМЕ ця збірка OpenCV на пристрої.
    try:
        w = int(video.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(video.get(cv2.CAP_PROP_FRAME_HEIGHT))
        print(f"[ROTATION_DEBUG] frame_w={w} frame_h={h} orientation_meta={angle}")
    except Exception as debug_error:
        print(f"[ROTATION_DEBUG] failed to read debug props: {debug_error}")

    return angle


# ТИМЧАСОВИЙ DEBUG-ПЕРЕМИКАЧ - видалити після діагностики повороту.
# True = застосовувати ручний поворот (як зараз), False = вимкнути його
# повністю і подивитись, чи ця збірка OpenCV на Android повертає кадри
# сама. Дозволяє перевірити обидва варіанти без правки коду нижче.
DEBUG_APPLY_MANUAL_ROTATION = True


def _apply_manual_rotation(frame, angle):
    # ВАЖЛИВО: кут з метаданих контейнера (MP4/QuickTime rotate matrix)
    # означає "поверни кадр на цей кут ПРОТИ годинникової стрілки",
    # щоб отримати правильну орієнтацію. Раніше тут 90 і 270 були
    # переплутані місцями (застосовувався поворот У ЗВОРОТНОМУ напрямку) -
    # для кута 0/180 це непомітно (там напрямок симетричний), а от
    # вертикальні відео (90/270) через це крутило не в той бік.
    if not DEBUG_APPLY_MANUAL_ROTATION:
        return frame
    if angle == 90:
        return cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
    if angle == 180:
        return cv2.rotate(frame, cv2.ROTATE_180)
    if angle == 270:
        return cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
    return frame


def format_time(seconds):
    total_seconds = int(seconds)
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def resize_frame(frame, max_width=1024):
    height, width = frame.shape[:2]
    if width <= max_width:
        return frame
    scale = max_width / width
    new_size = (max_width, int(height * scale))
    return cv2.resize(frame, new_size)


# Роздільна здатність, у якій кадри їдуть у Gemini. Моделі не потрібно
# 4K/FullHD, щоб зрозуміти "це машина" чи "це людина" - а токенів на
# зображення у мультимодальних моделей зазвичай тим більше, чим вища
# роздільна здатність (картинка ріжеться на патчі). Роздільна здатність
# вихідного відео при цьому ніде не втрачається - grab_screenshot()
# завжди бере кадр заново з відеофайлу в оригінальній якості, для
# показу/зуму в інтерфейсі.
GEMINI_FRAME_WIDTH = 640

# На скільки відсотків пікселів має змінитись яскравість між кадрами,
# щоб вважати це "рухом", а не шумом матриці камери/вітром у листі.
MOTION_THRESHOLD_PERCENT = 2.0

# Навіть якщо руху нема - все одно беремо кадр раз на стільки "перевірок".
# Це страховка: наприклад, людина впала і лежить нерухомо - після
# падіння руху на кадрах уже нема, але кадр з нею все одно потрібен
# у звіті. Без цієї страховки чиста детекція руху таке пропустить.
FORCE_KEEP_EVERY = 12

# У скільки разів частіше, ніж підсумковий ліміт max_frames, ми
# перевіряємо кандидатів на кадр. Детектору руху потрібно з чого
# вибирати - якщо семплювати так само рідко, як раніше (без детекції),
# вибирати буде нема з чого і вся економія токенів пропаде намарно.
CANDIDATE_OVERSAMPLE = 3


def _has_motion(prev_gray, current_gray, threshold_percent=MOTION_THRESHOLD_PERCENT):
    """
    Порівнює два кадри (у відтінках сірого) і визначає, чи було між
    ними помітне переміщення.

    cv2.absdiff рахує різницю яскравості піксель до пікселя. Далі
    бінаризуємо різницю (поріг 25 - це "помітна" зміна, а не шум
    матриці) і рахуємо, який відсоток пікселів кадру реально змінився.
    """
    diff = cv2.absdiff(prev_gray, current_gray)
    _, diff_mask = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)

    changed_pixels = cv2.countNonZero(diff_mask)
    total_pixels = diff_mask.shape[0] * diff_mask.shape[1]
    percent_changed = (changed_pixels / total_pixels) * 100

    return percent_changed >= threshold_percent


def extract_frames(video_path, max_frames=300, min_interval_sec=0.5):
    """
    Швидка й "розумна" нарізка відео на кадри для відправки в Gemini.

    Тут ДВІ сходинки економії:

    1) Швидке читання без сикання - відео читається ПОСЛІДОВНО:
       video.grab() дешево прогортає кадр без декодування,
       video.retrieve() декодує картинку лише у "кандидатів"
       (раз на interval_frames).

    2) Детекція руху (cv2.absdiff) - з кандидатів у підсумковий набір
       потрапляють лише ті, де картинка помітно змінилась порівняно
       з останнім ВЗЯТИМ кадром. Статичні шматки відео (де нічого не
       відбувається) майже не витрачають токени Gemini. Кандидатів при
       цьому перевіряємо густіше (CANDIDATE_OVERSAMPLE), щоб детектору
       було з чого обирати, а FORCE_KEEP_EVERY підстраховує від
       пропуску статичних об'єктів (див. коментар біля константи вище).

    Підсумкових кадрів завжди буде НЕ БІЛЬШЕ max_frames, але зазвичай
    помітно менше - рівно стільки, скільки реально знадобилось.
    """
    video = cv2.VideoCapture(video_path)
    if not video.isOpened():
        raise ValueError(f"Не вдалось відкрити відео: {video_path}")

    manual_rotation = _prepare_orientation(video)

    fps = video.get(cv2.CAP_PROP_FPS) or 25.0
    total_frame_count = int(video.get(cv2.CAP_PROP_FRAME_COUNT))
    duration_sec = total_frame_count / fps if fps > 0 else 0

    candidate_budget = max_frames * CANDIDATE_OVERSAMPLE
    interval_sec = max(min_interval_sec, duration_sec / candidate_budget) if duration_sec else min_interval_sec
    interval_frames = max(1, round(interval_sec * fps))

    frames = []
    frame_index = 0
    last_kept_gray = None   # кадр (у відтінках сірого), з яким порівнюємо
    skipped_in_a_row = 0    # скільки кандидатів підряд пропустили без руху

    while True:
        success = video.grab()
        if not success:
            break

        if frame_index % interval_frames == 0:
            success, frame = video.retrieve()
            if success:
                if manual_rotation:
                    frame = _apply_manual_rotation(frame, manual_rotation)
                gemini_frame = resize_frame(frame, max_width=GEMINI_FRAME_WIDTH)
                gray = cv2.cvtColor(gemini_frame, cv2.COLOR_BGR2GRAY)

                is_first_frame = last_kept_gray is None
                motion_detected = (
                    not is_first_frame and _has_motion(last_kept_gray, gray)
                )
                forced_keep = skipped_in_a_row >= FORCE_KEEP_EVERY

                if is_first_frame or motion_detected or forced_keep:
                    ok, buffer = cv2.imencode(".jpg", gemini_frame)
                    if ok:
                        frames.append({
                            "timestamp_sec": frame_index / fps,
                            "jpg_bytes": buffer.tobytes(),
                        })
                        last_kept_gray = gray
                        skipped_in_a_row = 0
                        if len(frames) >= max_frames:
                            break
                else:
                    skipped_in_a_row += 1

        frame_index += 1

    video.release()
    return frames


def grab_screenshot(video_path, timestamp_sec, save_path):
    """
    Дістає один кадр за часовою міткою і зберігає як є, без рамок,
    в ОРИГІНАЛЬНІЙ якості (тут роздільну здатність НЕ стискаємо, на
    відміну від кадрів, які їдуть у Gemini) - щоб в інтерфейсі можна
    було дивитись і зумити чітку картинку.

    ВАЖЛИВО: раніше тут використовувався video.set(CAP_PROP_POS_MSEC).
    На багатьох Android-збірках OpenCV цей seek або "прилипає" до
    найближчого опорного кадру (keyframe) - вони в телефонних
    H.264-роликах стоять рідко, - або взагалі мовчки НЕ спрацьовує,
    і читання просто продовжується з поточної позиції (для щойно
    відкритого VideoCapture це позиція 0) - тому в звіті всім
    моментам підставлявся один і той самий, перший кадр відео.

    Натомість гортаємо кадри послідовно через grab() (дешева операція
    без декодування) до потрібного індексу і декодуємо лише останній -
    так само, як робить extract_frames(). Повільніше за прямий seek,
    зате завжди повертає справді той кадр, що треба.

    ПРИМІТКА: якщо потрібно дістати ДЕКІЛЬКА кадрів з одного відео
    (як у звіті аналізу) - використовуй grab_screenshots_batch()
    нижче, вона відкриває файл лише ОДИН раз замість N.
    """
    video = cv2.VideoCapture(video_path)
    manual_rotation = _prepare_orientation(video)

    fps = video.get(cv2.CAP_PROP_FPS) or 25.0
    target_frame_index = max(0, int(round(timestamp_sec * fps)))

    frame_index = 0
    ok = True
    while frame_index < target_frame_index and ok:
        ok = video.grab()
        frame_index += 1

    success, frame = video.read()
    video.release()

    if success:
        if manual_rotation:
            frame = _apply_manual_rotation(frame, manual_rotation)
        cv2.imwrite(save_path, frame)
        return True

    return False


def grab_screenshots_batch(video_path, timestamp_and_path_list):
    """
    Дістає ОДРАЗУ кілька кадрів за ОДНЕ відкриття відеофайлу.

    ПРОБЛЕМА, яку це вирішує: раніше для звіту з N знайдених моментів
    grab_screenshot() викликався в циклі N разів - кожен виклик заново
    відкривав VideoCapture і гортав файл від нульового кадру. Для
    відео з великою кількістю знайдених моментів це N повних проходів
    замість одного.

    ТУТ: сортуємо цілі за часовою міткою і йдемо по відео СТРОГО
    вперед одним проходом, вихоплюючи потрібні кадри по дорозі -
    так само дешево (через grab(), без декодування "зайвих" кадрів),
    як це вже робить extract_frames().

    timestamp_and_path_list: список кортежів (timestamp_sec, save_path).
    Повертає set успішно збережених save_path.
    """
    video = cv2.VideoCapture(video_path)
    manual_rotation = _prepare_orientation(video)
    fps = video.get(cv2.CAP_PROP_FPS) or 25.0

    targets = sorted(
        ((max(0, int(round(ts * fps))), path) for ts, path in timestamp_and_path_list),
        key=lambda item: item[0],
    )

    saved = set()
    frame_index = 0
    target_pos = 0

    while target_pos < len(targets):
        target_frame_index, save_path = targets[target_pos]

        while frame_index < target_frame_index:
            if not video.grab():
                video.release()
                return saved
            frame_index += 1

        success, frame = video.read()
        frame_index += 1
        if success:
            if manual_rotation:
                frame = _apply_manual_rotation(frame, manual_rotation)
            cv2.imwrite(save_path, frame)
            saved.add(save_path)

        target_pos += 1

    video.release()
    return saved
