"""
p4a build hook: injects android:windowSplashScreenBackground into the theme
p4a applies to PythonActivity (KivySupportCutout), so the Android 12+ SYSTEM
splash screen (shown for a split second right when you tap the icon, before
your app process even starts) draws your navy background behind the
adaptive-icon foreground instead of falling back to a dark default and
hiding it (Android only draws the adaptive icon's own background layer when
it detects "enough contrast" with the window background — our navy icon bg
is too close to the default dark window bg, so it was being skipped).

This is deliberately scoped to windowSplashScreenBackground (not the general
windowBackground) so it ONLY affects that brief system splash window and has
zero effect on your own Kivy "Loading..." screen (that one is painted by
PythonActivity.java from android.presplash_color, a separate mechanism).

Usage in buildozer.spec:
    p4a.hook = %(source.dir)s/p4a_hook.py
"""
import re
from os.path import join

# должен совпадать с icon_bg.png
SPLASH_BG_COLOR = "#061533"


def before_apk_assemble(toolchain):
    res_dir = join(toolchain._dist.dist_dir, "src", "main", "res")
    strings_xml = join(res_dir, "values", "strings.xml")

    with open(strings_xml, "r", encoding="utf-8") as f:
        content = f.read()

    if "windowSplashScreenBackground" in content:
        return  # уже пропатчено (повторный запуск/инкрементальная сборка)

    patched = re.sub(
        r'(<style name="KivySupportCutout">)',
        r'\1\n        <item name="android:windowSplashScreenBackground">%s</item>' % SPLASH_BG_COLOR,
        content,
        count=1,
    )

    if patched == content:
        print("[p4a_hook] WARNING: KivySupportCutout style not found, nothing patched")
        return

    with open(strings_xml, "w", encoding="utf-8") as f:
        f.write(patched)

    print("[p4a_hook] windowSplashScreenBackground=%s injected into KivySupportCutout" % SPLASH_BG_COLOR)
