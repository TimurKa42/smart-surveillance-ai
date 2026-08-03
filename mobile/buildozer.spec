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

[buildozer]
log_level = 2
warn_on_root = 1
