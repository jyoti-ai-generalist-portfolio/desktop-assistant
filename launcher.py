"""
Desktop launcher for the AI Assistant.

Adds, on top of the plain Flask app:
  - A system tray icon (Open Assistant / Quit)
  - A global hotkey (Ctrl+Shift+Space) to summon the assistant from
    anywhere, even when it's not focused
  - Launches the UI as an "app window" (no address bar/tabs) instead
    of a regular browser tab, using Chrome/Edge's --app mode — this
    looks like a native app and costs far less RAM than Electron

Run this INSTEAD of app.py directly:
    pip install pystray pillow pynput
    python launcher.py

Platform notes:
  - Windows / Linux (X11): tray icon and hotkey both work out of the box.
  - Linux (Wayland): global hotkey capture is unreliable by design
    (Wayland restricts apps from listening to input outside their own
    window) — the tray icon still works fine, use its "Open Assistant"
    menu item instead.
  - macOS: you'll be prompted to grant "Accessibility" permission the
    first time the hotkey listener starts (System Settings > Privacy
    & Security > Accessibility) — without it the hotkey silently does
    nothing, but the tray icon still works.
"""

import threading
import time
import subprocess
import shutil
import sys
import os
import webbrowser

import requests
from PIL import Image, ImageDraw
import pystray

from app import app  # your existing Flask app object — unchanged

HOST = "127.0.0.1"
PORT = 5000
URL = f"http://{HOST}:{PORT}"

_window_process = None


# ---------------------------------------------------------------------
# 1. Run Flask in a background thread
# ---------------------------------------------------------------------
def run_flask():
    app.run(host=HOST, port=PORT, debug=False, use_reloader=False)


def wait_for_server(timeout=15):
    start = time.time()
    while time.time() - start < timeout:
        try:
            requests.get(URL, timeout=1)
            return True
        except requests.exceptions.ConnectionError:
            time.sleep(0.3)
    return False


# ---------------------------------------------------------------------
# 2. Open the assistant as an "app window" (no tabs/address bar)
# ---------------------------------------------------------------------
def find_chromium_browser():
    """Return a path to Chrome/Chromium/Edge if installed, else None."""
    for name in (
        "google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
        "microsoft-edge", "microsoft-edge-stable",
    ):
        path = shutil.which(name)
        if path:
            return path
    for path in (
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ):
        if os.path.exists(path):
            return path
    return None


def open_assistant_window():
    """Open (or re-open) the assistant window. Prefers a Chrome/Edge
    '--app' window (no chrome/tabs, looks native, low overhead);
    falls back to the default browser if neither is installed."""
    global _window_process
    browser_path = find_chromium_browser()
    if browser_path:
        _window_process = subprocess.Popen([
            browser_path,
            f"--app={URL}",
            "--window-size=420,640",
        ])
    else:
        webbrowser.open(URL)


# ---------------------------------------------------------------------
# 3. System tray icon
# ---------------------------------------------------------------------
def make_icon_image():
    """Draw a simple tray icon in memory — no external asset file needed."""
    img = Image.new("RGB", (64, 64), "#1e1f22")
    d = ImageDraw.Draw(img)
    d.ellipse((8, 8, 56, 56), fill="#3a6df0")
    d.text((26, 20), "A", fill="white")
    return img


def on_open(icon, item):
    open_assistant_window()


def on_quit(icon, item):
    icon.stop()
    # The Flask dev server has no clean programmatic shutdown hook from
    # here, so just end the whole process — fine for a personal local tool.
    os._exit(0)


def run_tray():
    icon = pystray.Icon(
        "desktop_assistant",
        make_icon_image(),
        "Desktop Assistant",
        menu=pystray.Menu(
            pystray.MenuItem("Open Assistant", on_open, default=True),
            pystray.MenuItem("Quit", on_quit),
        ),
    )
    icon.run()  # blocks — must run on the main thread on macOS


# ---------------------------------------------------------------------
# 4. Global hotkey (Ctrl+Shift+Space)
# ---------------------------------------------------------------------
def run_hotkey_listener():
    try:
        from pynput import keyboard
    except ImportError:
        print("pynput not installed — skipping global hotkey. "
              "Install with: pip install pynput")
        return

    try:
        hotkey = keyboard.HotKey(
            keyboard.HotKey.parse("<ctrl>+<shift>+space"),
            open_assistant_window,
        )

        def on_press(key):
            hotkey.press(listener.canonical(key))

        def on_release(key):
            hotkey.release(listener.canonical(key))

        with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
            listener.join()
    except Exception as e:
        print(f"Global hotkey unavailable ({e}). "
              "On Linux/Wayland or macOS this may need extra permissions "
              "(see the notes at the top of this file) — the tray icon "
              "still works as a fallback.")


# ---------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------
if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()

    print("Starting local server…")
    if not wait_for_server():
        print("Server didn't start in time — check the errors above.")
        sys.exit(1)

    threading.Thread(target=run_hotkey_listener, daemon=True).start()

    open_assistant_window()

    # Tray icon runs on the main thread (required on macOS)
    run_tray()
