"""System tray icon. Right-click → menu (Open / Request unlock / About).
Closing the GUI window only minimizes to tray; the watchdog keeps running."""
import logging
import threading
from typing import Callable

try:
    import pystray
    from PIL import Image, ImageDraw
    HAS_TRAY = True
except ImportError:
    HAS_TRAY = False

log = logging.getLogger("novablock.tray")


def _make_icon() -> "Image.Image":
    img = Image.new("RGB", (64, 64), "#d63031")
    draw = ImageDraw.Draw(img)
    draw.ellipse((8, 8, 56, 56), outline="white", width=4)
    draw.line((20, 20, 44, 44), fill="white", width=4)
    return img


class Tray:
    def __init__(self, on_open: Callable[[], None], on_quit_attempt: Callable[[], None]):
        if not HAS_TRAY:
            self.icon = None
            return
        self.on_open = on_open
        self.on_quit_attempt = on_quit_attempt
        self.icon = pystray.Icon(
            "NovaBlock",
            _make_icon(),
            "NovaBlock — protection active",
            menu=pystray.Menu(
                pystray.MenuItem("Ouvrir NovaBlock", self._open, default=True),
                pystray.MenuItem("Quitter", self._quit_attempt),
            ),
        )

    def _open(self, *_a) -> None:
        try:
            self.on_open()
        except Exception as e:
            log.error("tray open failed: %s", e)

    def _quit_attempt(self, *_a) -> None:
        try:
            self.on_quit_attempt()
        except Exception as e:
            log.error("tray quit attempt failed: %s", e)

    def start(self) -> None:
        if not self.icon:
            return
        threading.Thread(target=self.icon.run, daemon=True, name="NovaBlockTray").start()

    def stop(self) -> None:
        if self.icon:
            try:
                self.icon.stop()
            except Exception:
                pass
