[app]
title = Smart Surveillance AI
package.name = smartsurveillance
package.domain = org.manproject

source.dir = .
source.include_exts = py,kv,png,jpg,atlas

version = 1.0

# Залежності. opencv-python на Android ставиться через рецепт
# python-for-android (важкий пакет, перша збірка триватиме довго).
requirements = python3,hostpython3,kivy,numpy==2.0.2,opencv,pillow,requests,python-dotenv,plyer,pyjnius,fpdf2

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
android.ndk = 25c
android.archs = arm64-v8a

# --- Временный пин python-for-android ---
# В master/develop p4a recipe numpy обновили до v2.3.0 (PR #3164,
# "support ndk28c"), и её C++ исходники (unique.cpp) не собираются
# компилятором из NDK 25c ("no template named 'unordered_map'").
# Пин на коммит перед этим PR: там numpy recipe = v1.26.5, собирается
# нормально под NDK 25c. Когда апстрим почистит recipe под старые NDK
# (или сам перейдёшь на NDK 28c) — этот блок можно убрать.
p4a.branch = develop
p4a.commit = a8f2ca1c5b1bb6696b47fdf2c052285e116e0ebe

[buildozer]
log_level = 2
warn_on_root = 1
