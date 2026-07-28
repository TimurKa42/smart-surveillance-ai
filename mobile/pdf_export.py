"""
pdf_export.py

Генерація PDF-звіту по ОДНОМУ знайденому кадру: скріншот, час у
відео (ГГ:ХХ:СС), опис від Gemini і, якщо відомий, номер кадру.

Навмисно окремий модуль (а не метод усередині main.py) - як і
video_tools.py/gemini_tools.py, це чиста логіка без Kivy-залежностей,
її легко тестувати і використати повторно (наприклад, пізніше -
"експортувати всю історію одним PDF").

Примітка: раніше тут використовувався reportlab, але його C-розширення
(_rl_accel) не компілюється під Android-збіркою на сучасному Python
(python-for-android тягне Python 3.14, а reportlab.rl_accel лізе у
внутрішню структуру CPython-кадру, яку прибрали ще в 3.11+). fpdf2 -
чиста Python-бібліотека без C-коду, тому збирається на Android без
проблем і дає той самий результат.
"""
import os
from datetime import datetime

from fpdf import FPDF
from PIL import Image

# ---------------------------------------------------------------------
# Кирилиця: вбудовані шрифти fpdf (Helvetica і т.д.) не мають
# кириличних гліфів - український/російський текст просто не
# з'явиться в PDF. Тому шукаємо системний TTF-шрифт з підтримкою
# кирилиці і реєструємо його. На Android такий шрифт завжди є
# (Roboto), на десктопі - DejaVuSans майже завжди присутній.
# Якщо жодного не знайшлось - тихо лишаємось на Helvetica (латиниця
# і цифри й так відобразяться коректно, кирилиця - ні, але застосунок
# не впаде).
# ---------------------------------------------------------------------
_FONT_CANDIDATES = [
    ("/system/fonts/Roboto-Regular.ttf", "/system/fonts/Roboto-Bold.ttf"),
    ("/system/fonts/DroidSans.ttf", "/system/fonts/DroidSans-Bold.ttf"),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
]


def _find_cyrillic_font():
    """Повертає (шлях_regular, шлях_bold) першого знайденого шрифту,
    або (None, None), якщо нічого не знайшлося."""
    for regular_path, bold_path in _FONT_CANDIDATES:
        if os.path.exists(regular_path):
            if os.path.exists(bold_path):
                return regular_path, bold_path
            return regular_path, regular_path
    return None, None


PAGE_W = 210.0  # A4, мм
PAGE_H = 297.0
MARGIN = 18.0


def _wrap_text(text, pdf, max_width):
    """Розбиває текст на рядки так, щоб кожен влазив у max_width
    (аналог reportlab-обгортки; fpdf multi_cell вміє це сам, але тут
    лишаємо ручний варіант для однакового контролю за висотою рядка)."""
    words = text.split()
    lines = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if pdf.get_string_width(candidate) <= max_width:
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
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=MARGIN)
    pdf.set_margins(MARGIN, MARGIN, MARGIN)
    pdf.add_page()

    regular_path, bold_path = _find_cyrillic_font()
    if regular_path:
        pdf.add_font("Report", "", regular_path)
        pdf.add_font("Report", "B", bold_path)
        font_name = "Report"
    else:
        font_name = "Helvetica"

    content_width = PAGE_W - 2 * MARGIN

    # --- Заголовок ---
    pdf.set_font(font_name, "B", 16)
    pdf.cell(content_width, 9, "Smart Surveillance - звіт по кадру", new_x="LMARGIN", new_y="NEXT")

    pdf.set_draw_color(190, 190, 190)
    y = pdf.get_y() + 2
    pdf.line(MARGIN, y, PAGE_W - MARGIN, y)
    pdf.set_y(y + 6)

    # --- Метадані (час, кадр, відео, дата створення звіту) ---
    pdf.set_font(font_name, "", 11)
    meta_lines = [f"Час у відео: {time_str}"]
    if frame_index is not None:
        meta_lines.append(f"Кадр №: {frame_index}")
    if video_name:
        meta_lines.append(f"Відео: {video_name}")
    meta_lines.append(f"Звіт створено: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    for line in meta_lines:
        pdf.cell(content_width, 6, line, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    # --- Зображення ---
    if image_path and os.path.exists(image_path):
        try:
            with Image.open(image_path) as img:
                img_w, img_h = img.size
            aspect = img_h / float(img_w)

            max_img_w = content_width
            max_img_h = PAGE_H * 0.55  # не даємо картинці "з'їсти" місце під опис
            draw_w = max_img_w
            draw_h = draw_w * aspect
            if draw_h > max_img_h:
                draw_h = max_img_h
                draw_w = draw_h / aspect

            x = MARGIN + (content_width - draw_w) / 2
            pdf.image(image_path, x=x, y=pdf.get_y(), w=draw_w, h=draw_h)
            pdf.set_y(pdf.get_y() + draw_h + 8)
        except Exception:
            pdf.set_font(font_name, "", 10)
            pdf.cell(content_width, 10, "[не вдалось завантажити зображення]", new_x="LMARGIN", new_y="NEXT")
    else:
        pdf.set_font(font_name, "", 10)
        pdf.cell(content_width, 10, "[зображення відсутнє]", new_x="LMARGIN", new_y="NEXT")

    # --- Опис від ШІ ---
    pdf.set_font(font_name, "B", 12)
    pdf.cell(content_width, 7, "Опис (Gemini):", new_x="LMARGIN", new_y="NEXT")

    pdf.set_font(font_name, "", 11)
    description = description or "-"
    for paragraph in description.splitlines() or [description]:
        for line in _wrap_text(paragraph, pdf, content_width):
            pdf.cell(content_width, 6, line, new_x="LMARGIN", new_y="NEXT")

    pdf.output(output_path)
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
