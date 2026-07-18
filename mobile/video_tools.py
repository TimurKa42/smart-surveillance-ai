import cv2


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

    Сикання (video.set) тут не проблема - викликається один раз на
    знайдений момент, а не на кожен кадр нарізки.
    """
    video = cv2.VideoCapture(video_path)
    video.set(cv2.CAP_PROP_POS_MSEC, timestamp_sec * 1000)
    success, frame = video.read()
    video.release()

    if success:
        cv2.imwrite(save_path, frame)
        return True

    return False
