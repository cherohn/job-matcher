"""Record a real fullscreen demo GIF of the Job Matcher desktop app."""

import sys
import time
import ctypes
from pathlib import Path

from PIL import Image, ImageGrab


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_desktop import JobMatcherApp  # noqa: E402


OUTPUT = ROOT / "assets" / "jobmatcher-demo.gif"
SIZE = (1920, 1080)
FPS = 8
SECONDS_PER_SCREEN = 1.4
SCREENS = [
    "Menu",
    "Busca",
    "Analisar vaga",
    "Otimizar curriculo",
    "Candidaturas",
    "Mercado",
    "Relatorios",
]


def settle(app, seconds=0.25):
    deadline = time.time() + seconds
    while time.time() < deadline:
        app.update()
        time.sleep(0.02)


def capture_app(app):
    app.update_idletasks()
    hwnd = app.winfo_id()
    if sys.platform == "win32":
        hwnd = ctypes.windll.user32.GetParent(hwnd) or hwnd
    image = ImageGrab.grab(window=hwnd).convert("RGB")
    if image.size != SIZE:
        image = image.resize(SIZE, Image.Resampling.LANCZOS)
    return image.convert("P", palette=Image.Palette.ADAPTIVE, colors=256)


def main():
    app = JobMatcherApp()
    app.withdraw()
    app.geometry(f"{SIZE[0]}x{SIZE[1]}+0+0")
    app.attributes("-fullscreen", True)
    app.attributes("-topmost", True)
    app.deiconify()
    app.focus_force()
    settle(app, 0.8)

    frames = []
    try:
        for screen in SCREENS:
            app._show_tab(screen)
            settle(app, 0.35)
            for _ in range(round(FPS * SECONDS_PER_SCREEN)):
                frames.append(capture_app(app))
                settle(app, 1 / FPS)
    finally:
        app.attributes("-topmost", False)
        app.attributes("-fullscreen", False)
        app.destroy()

    frames[0].save(
        OUTPUT,
        save_all=True,
        append_images=frames[1:],
        duration=round(1000 / FPS),
        loop=0,
        optimize=True,
        disposal=2,
    )
    print(f"Recorded {OUTPUT.relative_to(ROOT)} with {len(frames)} real app frames at {SIZE[0]}x{SIZE[1]}.")


if __name__ == "__main__":
    main()
