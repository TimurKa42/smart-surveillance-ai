[app]
title = Smart Surveillance AI
package.name = smartsurveillance
package.domain = org.manproject
source.dir = .
source.include_exts = py,kv,png,jpg,atlas
version = 1.0
# Залежності. opencv-python на Android ставиться через рецепт
# python-for-android (важкий пакет, перша збірка триватиме довго).
requirements = python3,kivy,numpy,opencv,pillow,requests,python-dotenv,plyer,pyjnius,fpdf2,fonttools
orientation = portrait
fullscreen = 0
icon.filename = %(source.dir)s/icon.png
icon.adaptive_foreground.filename = %(source.dir)s/icon_fg.png
icon.adaptive_background.filename = %(source.dir)s/icon_bg.png
# Цвет фона заставки при запуске (совпадает с фоном иконки),
# чтобы не было белой рамки/вспышки на старте
android.presplash_color = #061533
android.permissions = INTERNET,READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE,VIBRATE
android.api = 35
android.minapi = 24
android.ndk = 27b
android.archs = arm64-v8a
# --- p4a: используем актуальный develop, ЗАКРЕПЛЁННЫЙ на конкретный коммит ---
# Раньше был запинен старый коммит p4a (a8f2ca1c...), т.к. recipe
# numpy v2.3.0 (PR #3164, "support ndk28c") не собирался под NDK 25c
# ("no template named 'unordered_map'"). Вместо отката p4a назад
# (что вскрыло другой баг: старый recipe numpy 1.26.5 падал с
# "Cannot import 'mesonpy'" — isolated build не мог поставить
# meson-python) — подняли NDK до 27b, под которым актуальный
# recipe numpy из develop собирается нормально.
#
# 21.08.2026: без пина коммита апстримный develop сам собой поднял
# версию рецепта freetype с 2.10.1 до 2.14.1, из-за чего сломался
# наш pre-download воркэраунд в build-apk.yml (качал не тот файл,
# а прямая загрузка с download.savannah.gnu.org падала 502).
# Чтобы рецепты (freetype/numpy/opencv/...) больше не менялись
# у нас под ногами без предупреждения — фиксируем конкретный коммит.
# Обновлять сознательно: смотреть `git ls-remote <repo> develop`.
p4a.hook = %(source.dir)s/p4a_hook.py
p4a.branch = develop
p4a.commit = 7af1d1325ef460def993cc7871c43d04bc877a94
[buildozer]
log_level = 2
warn_on_root = 1
