[app]
title = Smart Surveillance AI
package.name = smartsurveillance
package.domain = org.manproject

source.dir = .
source.include_exts = py,kv,png,jpg,atlas

version = 1.0

# Залежності. opencv-python на Android ставиться через рецепт
# python-for-android (важкий пакет, перша збірка триватиме довго).
requirements = python3==3.11,kivy,numpy==v2.0.2,opencv,pillow,google-genai,python-dotenv,pydantic,plyer,pyjnius

orientation = portrait
fullscreen = 0

icon.filename = %(source.dir)s/icon.png

android.permissions = INTERNET,READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE

android.api = 33
android.minapi = 24
android.ndk = 25c
android.archs = arm64-v8a

[buildozer]
log_level = 2
warn_on_root = 1
