"""Entry point for the Jules Pixel-Art Desktop Pet."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from jules_pet.pet_window import JulesPetWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Jules Desktop Pet")
    app.setQuitOnLastWindowClosed(False)

    pet = JulesPetWindow()
    pet.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
