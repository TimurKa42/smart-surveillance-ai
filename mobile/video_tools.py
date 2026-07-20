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

GEMINI_FRAME_WIDTH = 640
MOTION_THRESHOLD_PERCENT = 2.0
FORCE_KEEP_EVERY = 12
CANDIDATE_OVERSAMPLE = 3

def _has_motion(prev_gray, current_gray, threshold_percent=MOTION_THRESHOLD_PERCENT):
    diff = cv2.absdiff(prev_gray, current_gray)
    _, diff_mask = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)
    changed_pixels = cv2.countNonZero(diff_mask)
    total_pixels = diff_mask.shape[0] * diff_mask.shape[1]
    percent_changed = (changed_pixels / total_pixels) * 100
    return percent_changed >= threshold_percent

def extract_frames(video_path, max_frames=300, min_interval_sec=0.5):
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
    last_kept_gray = None
    skipped_in_a_row = 0

    while True:
        success = video.grab()
        if not success:
            break

        if frame_index % interval_frames == 0:
            success, frame = video.retrieve()
            if success:
                # Обов'язковий поворот, якщо відео вертикальне
                if frame.shape[0] > frame.shape[1]:
                    frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)

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
    video = cv2.VideoCapture(video_path)
    video.set(cv2.CAP_PROP_POS_MSEC, timestamp_sec * 1000)
    success, frame = video.read()
    video.release()

    if success:
        # Обов'язковий поворот для скріншотів, якщо відео вертикальне
        if frame.shape[0] > frame.shape[1]:
            frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
            
        cv2.imwrite(save_path, frame)
        return True

    return False
