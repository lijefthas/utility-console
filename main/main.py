"""
Author: L. I. Jefthas
Program: Utility Console
Date: May 2026
Version: 1.0.0
"""

import sys
from PyQt6.QtWidgets import QApplication
from utility_console.ui.window import MainWindow, STYLESHEET


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLESHEET)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
