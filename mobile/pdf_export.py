"""
pdf_export.py

Генерація PDF-звіту по ОДНОМУ знайденому кадру: скріншот, час у
відео (ЧЧ:ММ:СС), опис від Gemini і, якщо відомий, номер кадру.

Навмисно окремий модуль (а не метод усередині main.py) - як і
video_tools.py/gemini_tools.py, це чиста логіка без Kivy-залежностей,
її легко тестувати і використати повторно (наприклад, пізніше -
"експортувати всю історію одним PDF").
"""
import os
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# ---------------------------------------------------------------------
# Кирилиця: вбудовані шрифти reportlab (Helvetica і т.д.) не мають
# кириличних гліфів - український/російський текст просто не
# з'явиться в PDF. Тому шукаємо системний TTF-шрифт з підтримкою
# кирилиці і реєструємо його. На Android такий шрифт завжди є
# (Roboto), на десктопі - DejaVuSans майже завжди присутній.
# Якщо жодного не знайшлось - тихо лишаємось на Helvetica (латиниця
# і цифри й так відобразяться коректно, кирилиця - ні, але застосунок
# не впаде).
# ---------------------------------------------------------------------
_FONT_NAME = "Helvetica"
_FONT_BOLD = "Helvetica-Bold"
_FONT_CANDIDATES = [
    ("/system/fonts/Roboto-Regular.ttf", "/system/fonts/Roboto-Bold.ttf"),
    ("/system/fonts/DroidSans.ttf", "/system/fonts/DroidSans-Bold.ttf"),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
]


def _register_cyrillic_font():
    global _FONT_NAME, _FONT_BOLD
    for regular_path, bold_path in _FONT_CANDIDATES:
        if os.path.exists(regular_path):
            try:
                pdfmetrics.registerFont(TTFont("ReportRegular", regular_path))
                _FONT_NAME = "ReportRegular"
                if os.path.exists(bold_path):
                    pdfmetrics.registerFont(TTFont("ReportBold", bold_path))
                    _FONT_BOLD = "ReportBold"
                else:
                    _FONT_BOLD = "ReportRegular"
                return
            except Exception:
                continue


_register_cyrillic_font()

PAGE_W, PAGE_H = A4
MARGIN = 18 * mm


def _wrap_text(text, font_name, font_size, max_width, c):
    """Розбиває текст на рядки так, щоб кожен влазив у max_width
    (reportlab сам цього не робить - drawString не переносить рядки)."""
    words = text.split()
    lines = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if c.stringWidth(candidate, font_name, font_size) <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def export_frame_to_pdf(
    output_path,
    image_path,
    time_str,
    description,
    video_name="",
    frame_index=None,
):
    """
    Створює один PDF-файл зі скріном кадру + метаданими.

    output_path   - куди зберегти PDF (повний шлях, з .pdf)
    image_path    - шлях до JPG/PNG скріншота кадру
    time_str      - таймкод у відео, формат "ЧЧ:ММ:СС" (див. video_tools.format_time)
    description   - опис від Gemini
    video_name    - назва вихідного відеофайлу (опційно)
    frame_index   - порядковий номер кадру в списку знахідок (опційно, 1-based)
    """
    c = canvas.Canvas(output_path, pagesize=A4)
    content_width = PAGE_W - 2 * MARGIN
    y = PAGE_H - MARGIN

    # --- Заголовок ---
    c.setFont(_FONT_BOLD, 16)
    title = "Smart Surveillance - звіт по кадру"
    c.drawString(MARGIN, y, title)
    y -= 9 * mm

    c.setStrokeColorRGB(0.75, 0.75, 0.75)
    c.line(MARGIN, y, PAGE_W - MARGIN, y)
    y -= 8 * mm

    # --- Метадані (час, кадр, відео, дата створення звіту) ---
    c.setFont(_FONT_NAME, 11)
    meta_lines = [f"Час у відео: {time_str}"]
    if frame_index is not None:
        meta_lines.append(f"Кадр №: {frame_index}")
    if video_name:
        meta_lines.append(f"Відео: {video_name}")
    meta_lines.append(f"Звіт створено: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    for line in meta_lines:
        c.drawString(MARGIN, y, line)
        y -= 6 * mm
    y -= 4 * mm

    # --- Зображення ---
    if image_path and os.path.exists(image_path):
        try:
            img = ImageReader(image_path)
            img_w, img_h = img.getSize()
            aspect = img_h / float(img_w)

            max_img_w = content_width
            max_img_h = PAGE_H * 0.55  # не даємо картинці "з'їсти" місце під опис
            draw_w = max_img_w
            draw_h = draw_w * aspect
            if draw_h > max_img_h:
                draw_h = max_img_h
                draw_w = draw_h / aspect

            x = MARGIN + (content_width - draw_w) / 2
            y -= draw_h
            c.drawImage(img, x, y, width=draw_w, height=draw_h, preserveAspectRatio=True)
            y -= 8 * mm
        except Exception:
            c.setFont(_FONT_NAME, 10)
            c.drawString(MARGIN, y, "[не вдалось завантажити зображення]")
            y -= 10 * mm
    else:
        c.setFont(_FONT_NAME, 10)
        c.drawString(MARGIN, y, "[зображення відсутнє]")
        y -= 10 * mm

    # --- Опис від ШІ ---
    c.setFont(_FONT_BOLD, 12)
    c.drawString(MARGIN, y, "Опис (Gemini):")
    y -= 7 * mm

    c.setFont(_FONT_NAME, 11)
    description = description or "-"
    for paragraph in description.splitlines() or [description]:
        for line in _wrap_text(paragraph, _FONT_NAME, 11, content_width, c):
            if y < MARGIN + 10 * mm:
                c.showPage()
                y = PAGE_H - MARGIN
                c.setFont(_FONT_NAME, 11)
            c.drawString(MARGIN, y, line)
            y -= 6 * mm

    c.save()
    return output_path


def build_pdf_filename(time_str, frame_index=None):
    """Ім'я файлу без конфліктів: час + (за наявності) номер кадру +
    мітка створення, щоб повторний експорт того ж кадру не
    перезаписував попередній файл мовчки."""
    safe_time = time_str.replace(":", "-")
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if frame_index is not None:
        return f"report_{safe_time}_frame{frame_index}_{stamp}.pdf"
    return f"report_{safe_time}_{stamp}.pdf"
