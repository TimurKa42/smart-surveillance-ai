import struct

import cv2

# Числові ID властивостей OpenCV, які з'явились у 4.5 (CAP_PROP_ORIENTATION_META
# і CAP_PROP_ORIENTATION_AUTO). Дістаємо через getattr із запасним значенням,
# бо в збірці для Android може стояти дещо старіша версія OpenCV, де цих
# констант ще нема серед іменованих атрибутів, хоча самі числові ID стабільні.
_CAP_PROP_ORIENTATION_META = getattr(cv2, "CAP_PROP_ORIENTATION_META", 48)


# ---------------------------------------------------------------------------
# Читання кута повороту напряму з MP4-файлу (без OpenCV)
# ---------------------------------------------------------------------------
#
# ЧОМУ ЦЕ ТУТ Є:
# OpenCV на Android (CAP_PROP_ORIENTATION_META) не вміє читати кут
# повороту з телефонних відео - завжди повертає 0, навіть якщо відео
# насправді треба повернути на 90/180/270 градусів. На Mac (desktop
# збірка OpenCV) те саме працює нормально - ось звідки різниця в
# поведінці застосунку на різних платформах.
#
# Рішення: дістаємо кут самі, читаючи "сирий" MP4-файл як послідовність
# байтів - без OpenCV і без будь-яких зовнішніх бібліотек. Це працює
# однаково на будь-якій платформі.
#
# ЩО ТАКЕ MP4-ФАЙЛ ЗСЕРЕДИНИ (коротко):
# MP4-файл складається з "боксів" (box) - шматків даних, кожен з яких
# має заголовок:
#   [4 байти: розмір цього боксу] [4 байти: назва боксу, напр. b"moov"] [дані...]
# Бокси можуть лежати один в одному, як матрьошка. Нам потрібен шлях:
#   moov -> trak -> tkhd
# "moov" - загальний контейнер з інформацією про відео.
# "trak" - один трек (доріжка). Треків може бути кілька: відео, аудіо.
# "tkhd" - заголовок треку. Саме тут лежить кут повороту та розміри
#          кадру (width/height), якщо це відео-трек.


def _read_box_header(file, offset):
    """
    Читає заголовок ОДНОГО боксу за вказаним зсувом (offset) у файлі.

    Повертає (назва_боксу, розмір_боксу, зсув_де_починаються_дані_боксу)
    або None, якщо дочитали до кінця файлу / заголовок биний.
    """
    file.seek(offset)
    header = file.read(8)
    if len(header) < 8:
        return None  # файл закінчився - боксів більше нема

    size = int.from_bytes(header[0:4], byteorder="big")
    box_type = header[4:8]
    data_start = offset + 8

    if size == 1:
        # Спеціальний випадок: розмір боксу не влазить у 4 байти,
        # тому реальний розмір (64-бітний) лежить одразу ПІСЛЯ заголовка.
        big_size_bytes = file.read(8)
        if len(big_size_bytes) < 8:
            return None
        size = int.from_bytes(big_size_bytes, byteorder="big")
        data_start = offset + 16
    elif size == 0:
        # size == 0 означає "цей бокс триває до самого кінця файлу"
        # (так буває, наприклад, з mdat, якщо файл писали "на льоту").
        file.seek(0, 2)  # перестрибуємо в кінець файлу
        size = file.tell() - offset

    return box_type, size, data_start


def _find_box(file, box_type, start, end):
    """
    Шукає бокс з назвою box_type серед "сусідів" у діапазоні [start, end)
    ОДНОГО рівня вкладеності (не заглиблюючись у самі бокси).

    Наприклад: _find_box(f, b"moov", 0, розмір_файлу) знайде "moov",
    навіть якщо перед ним стоять інші top-level бокси (ftyp, free, mdat) -
    і навіть якщо moov лежить В КІНЦІ файлу (так буває у перекодованих
    відео).

    Повертає (зсув_даних_боксу, розмір_даних_боксу) або None, якщо
    не знайшли.
    """
    offset = start
    while offset < end:
        header = _read_box_header(file, offset)
        if header is None:
            return None

        box_type_found, box_size, data_start = header
        if box_size <= 0:
            return None  # биний бокс - розмір не може бути від'ємним/нульовим

        data_size = box_size - (data_start - offset)

        if box_type_found == box_type:
            return data_start, data_size

        offset += box_size  # перестрибуємо одразу до НАСТУПНОГО боксу

    return None


# Кут повороту "закодований" у матриці tkhd чотирма числами (a, b, c, d).
# Це стандартні значення, які реально пишуть телефони/редактори відео.
# Формат чисел - fixed-point 16.16 (число ціле, помножене на 65536).
_ONE = 0x10000  # 1.0 у форматі fixed-point 16.16

_ROTATION_MATRIX_TO_ANGLE = {
    (_ONE, 0, 0, _ONE): 0,
    (0, _ONE, -_ONE, 0): 90,
    (-_ONE, 0, 0, -_ONE): 180,
    (0, -_ONE, _ONE, 0): 270,
}


def _matrix_to_angle(a, b, c, d):
    """
    Перетворює 4 числа матриці на кут повороту (0/90/180/270).

    Якщо матриця не збігається ЖОДНИМ з очікуваних 4 варіантів (це
    може бути дзеркальне відображення або щось екзотичне) - чесно
    повертаємо 0 замість того, щоб намагатись вгадати.
    """
    return _ROTATION_MATRIX_TO_ANGLE.get((a, b, c, d), 0)


def _read_tkhd_fields(file, data_start, data_size):
    """
    Читає з одного tkhd-боксу дві речі:
      1) width, height - потрібні лише щоб зрозуміти, чи це відео-трек
         (у аудіо-треку тут завжди 0x0)
      2) матрицю (a, b, c, d) - з неї рахуємо кут повороту

    Повертає (width, height, a, b, c, d) або None, якщо бокс закороткий/биний.
    """
    file.seek(data_start)
    payload = file.read(data_size)
    if len(payload) < 1:
        return None

    version = payload[0]

    # Розмір "часових" полів (creation/modification/duration) залежить
    # від версії боксу: version=0 -> 4-байтні поля, version=1 -> 8-байтні.
    # Якщо це не врахувати, всі наступні зсуви (в т.ч. матриця і
    # width/height) "поплетуть" і ми прочитаємо сміття замість чисел.
    if version == 1:
        time_fields_size = 8 + 8 + 4 + 4 + 8  # creation+modification+track_id+reserved+duration
    else:
        time_fields_size = 4 + 4 + 4 + 4 + 4

    # Після часових полів завжди йде однаковий для обох версій блок:
    # reserved(8) + layer(2) + alternate_group(2) + volume(2) + reserved(2) = 16 байт
    fixed_block_size = 8 + 2 + 2 + 2 + 2

    matrix_offset = 4 + time_fields_size + fixed_block_size  # 4 = version+flags
    matrix_size = 36  # 9 чисел по 4 байти

    matrix_end = matrix_offset + matrix_size
    width_height_end = matrix_end + 8  # width(4) + height(4)

    if len(payload) < width_height_end:
        return None  # бокс коротший, ніж очікувалось - щось не так, здаємось

    def read_fixed_point(raw_bytes):
        # Fixed-point 16.16 і ЗІ ЗНАКОМ (потрібно для -1.0 у матриці
        # при поворотах на 180). "big" - порядок байтів, як завжди в MP4.
        return int.from_bytes(raw_bytes, byteorder="big", signed=True)

    # З 9 чисел матриці нам потрібні лише перші 4 (a, b, c, d) -
    # решта 5 для звичайного повороту телефонної камери завжди стандартні
    # і на кут не впливають.
    a = read_fixed_point(payload[matrix_offset : matrix_offset + 4])
    b = read_fixed_point(payload[matrix_offset + 4 : matrix_offset + 8])
    c = read_fixed_point(payload[matrix_offset + 12 : matrix_offset + 16])
    d = read_fixed_point(payload[matrix_offset + 16 : matrix_offset + 20])

    width = int.from_bytes(payload[matrix_end : matrix_end + 4], byteorder="big")
    height = int.from_bytes(payload[matrix_end + 4 : matrix_end + 8], byteorder="big")

    return width, height, a, b, c, d


def read_rotation_from_mp4(video_path):
    """
    Головна функція: відкриває MP4-файл і повертає кут повороту
    ВІДЕО-треку (0, 90, 180 або 270).

    Якщо щось пішло не так (файл биний, не MP4, нестандартна структура) -
    ТИХО повертає 0, так само як поводиться застосунок зараз, коли
    OpenCV не може прочитати метадані. Жодних винятків назовні -
    аналіз відео не повинен падати через це.
    """
    try:
        with open(video_path, "rb") as file:
            file.seek(0, 2)  # у кінець файлу, щоб дізнатись його розмір
            file_size = file.tell()

            moov_location = _find_box(file, b"moov", 0, file_size)
            if moov_location is None:
                return 0  # немає moov - не схоже на нормальний MP4

            moov_start, moov_size = moov_location
            moov_end = moov_start + moov_size

            # У файлі може бути кілька "trak" (наприклад відео + аудіо).
            # Йдемо по них по черзі і беремо ПЕРШИЙ, у якого в tkhd
            # стоять ненульові width/height - це і є відео-трек
            # (в аудіо-треку ці поля завжди 0x0).
            offset = moov_start
            while offset < moov_end:
                trak_location = _find_box(file, b"trak", offset, moov_end)
                if trak_location is None:
                    break  # більше треків нема

                trak_start, trak_size = trak_location
                trak_end = trak_start + trak_size

                tkhd_location = _find_box(file, b"tkhd", trak_start, trak_end)
                if tkhd_location is not None:
                    tkhd_start, tkhd_size = tkhd_location
                    fields = _read_tkhd_fields(file, tkhd_start, tkhd_size)
                    if fields is not None:
                        width, height, a, b, c, d = fields
                        if width != 0 and height != 0:
                            # Знайшли відео-трек - рахуємо кут і виходимо.
                            return _matrix_to_angle(a, b, c, d)

                # Це був не той trak (аудіо чи щось інше) - йдемо до наступного.
                offset = trak_start + trak_size

            return 0  # жодного відео-треку з нормальним tkhd не знайшли
    except (OSError, struct.error, ValueError):
        # Битий файл, обірваний запис, дивний контейнер - що завгодно.
        # Не валимо аналіз відео через це, просто кажемо "без повороту".
        return 0


def _prepare_orientation(video, video_path):
    """
    Телефонні відео майже завжди мають метадані повороту - камеру
    тримали "на боці", а плеєр показує відео вертикально/горизонтально
    ЗАВДЯКИ цій метадані. OpenCV за замовчуванням її ІГНОРУЄ і віддає
    сирі, неповернуті кадри.

    РАНІШЕ тут кут читався через video.get(CAP_PROP_ORIENTATION_META).
    На Android ця властивість НІКОЛИ не працює правильно - завжди
    повертає 0, навіть коли відео насправді треба повернути. Через
    це на телефоні всі вертикальні відео лягали "на бік" у звіті,
    хоча той самий код на Mac (desktop-збірка OpenCV) працював
    нормально.

    ТЕПЕР кут читається напряму з файлу через read_rotation_from_mp4()
    (дивись коментар над цією функцією вище) - без участі OpenCV,
    тому працює однаково на будь-якій платформі.
    """
    angle = read_rotation_from_mp4(video_path)

    # ТИМЧАСОВИЙ DEBUG - видалити після діагностики повороту на Android.
    # Виводить у logcat кут зі старого (ненадійного) способу поруч з
    # новим, щоб наочно порівняти їх на реальному пристрої.
    try:
        old_meta_angle = int(video.get(_CAP_PROP_ORIENTATION_META)) % 360
        w = int(video.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(video.get(cv2.CAP_PROP_FRAME_HEIGHT))
        print(
            f"[ROTATION_DEBUG] frame_w={w} frame_h={h} "
            f"old_orientation_meta={old_meta_angle} tkhd_angle={angle}"
        )
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
    # означає "поверни кадр на цей кут ЗА годинниковою стрілкою", щоб
    # отримати правильну орієнтацію (це стандартна конвенція matrix-полів
    # tkhd, якою користуються камери на кшталт Samsung S24). Напрямки
    # для 90/270 були переплутані місцями - через це відео з камери
    # (де кут реально 90 або 270, а не 0, як у перекодованих Telegram-
    # відео) вертілось у зворотний бік, що на виході давало помітну
    # різницю в 180° від правильної орієнтації.
    if not DEBUG_APPLY_MANUAL_ROTATION:
        return frame
    if angle == 90:
        return cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
    if angle == 180:
        return cv2.rotate(frame, cv2.ROTATE_180)
    if angle == 270:
        return cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
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

    manual_rotation = _prepare_orientation(video, video_path)

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
    manual_rotation = _prepare_orientation(video, video_path)

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
    manual_rotation = _prepare_orientation(video, video_path)
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
