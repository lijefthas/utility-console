"""
Utility Console — Qt GUI: main window, tail window, help dialog, stylesheet, and UI helpers.
"""

import json
import os
import subprocess
from datetime import datetime

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QDialog, QFrame, QSizePolicy, QStyle,
    QLabel, QLineEdit, QPushButton, QListWidget, QListWidgetItem,
    QTableWidget, QTableWidgetItem,
    QHeaderView, QProgressBar, QTextEdit, QFileDialog, QMessageBox,
    QGroupBox, QInputDialog, QMenu,
)
from PyQt6.QtCore import Qt, QThread, QUrl, pyqtSignal
import html as _html

from PyQt6.QtGui import QDesktopServices, QFont, QColor

from utility_console.ssh.client import DEFAULT_PASS
from utility_console.os.device import (
    DIR_LIVE, DIR_ARCH, DIR_ROOT, LIVE_LOG_DIRS, ARCH_LOG_DIRS,
    CMD_ROTATE, CMD_STOPALL, CMD_STARTALL,
    KNOWN_MODULES, module_path, parse_size, parse_date_key,
)
from utility_console.workers.ssh_workers import (
    PingWorker, ListWorker, DownloadWorker, ConnectWorker,
    ScriptWorker, SystemWorker, ModuleControlWorker, SqlQueryWorker, TailWorker,
    UpdateWorker, RollbackWorker, TgzUpdateWorker, SqlFileWorker, TestModuleWorker,
    TransactionCheckWorker,
    GitLabProjectsWorker, CopyBinaryWorker,
)
from utility_console.user.developer import (
    load_dev_settings, save_dev_settings, windows_to_wsl_path,
    resolve_binaries_path, resolve_build_subpath,
    get_project_build_subpath, save_project_build_subpath,
    get_project_setting, save_project_setting, any_path_to_wsl,
    get_launch_script_path, ensure_launch_script,
)
from utility_console.db.queries import (
    SQL_SHOW_DATABASES, SQL_SHOW_TABLES, SQL_MODULE_DETAILS,
    sql_select_all, mysql_cmd,
)

_TAIL_MAX_LINES  = 5000
_LOG_COLORS = {"ERROR": "#f44747", "WARN": "#ffcc44"}
_APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_PROFILES_FILE   = os.path.join(_APP_DIR, "profiles.json")


def _load_profiles() -> list:
    try:
        with open(_PROFILES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return [p for p in data if isinstance(p, dict) and "name" in p and "ip" in p]
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []


def _save_profiles(profiles: list) -> None:
    tmp = _PROFILES_FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(profiles, f, indent=2)
        os.replace(tmp, _PROFILES_FILE)
    except OSError:
        pass

APP_NAME    = "Utility Console"
APP_VERSION = "v1.3.0"
APP_AUTHOR  = "L. I. Jefthas"
APP_EMAIL   = "louisj@nayax.com"

STYLESHEET = """
QMainWindow, QWidget {
    background-color: #2b2b2b;
    color: #d4d4d4;
    font-size: 13px;
}
QGroupBox {
    border: 1px solid #4a4a4a;
    border-radius: 4px;
    margin-top: 8px;
    padding-top: 4px;
    color: #8ab4f8;
    font-weight: bold;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 4px;
}
QLineEdit {
    background-color: #3c3c3c;
    border: 1px solid #5a5a5a;
    border-radius: 3px;
    padding: 3px 6px;
    color: #d4d4d4;
    selection-background-color: #4a9eff;
}
QLineEdit:focus { border: 1px solid #4a9eff; }
QLineEdit:disabled { background-color: #252525; color: #555555; }
QPushButton {
    background-color: #3c3c3c;
    border: 1px solid #5a5a5a;
    border-radius: 3px;
    padding: 4px 14px;
    color: #d4d4d4;
    font-weight: 600;
}
QPushButton:hover { background-color: #4a9eff; color: #ffffff; border-color: #4a9eff; }
QPushButton:pressed { background-color: #2d7dd2; }
QPushButton:disabled { background-color: #252525; color: #4a4a4a; border-color: #333333; }
QTableWidget {
    background-color: #2b2b2b;
    alternate-background-color: #313131;
    gridline-color: #3e3e3e;
    color: #d4d4d4;
    selection-background-color: #4a9eff;
    selection-color: #ffffff;
    border: 1px solid #4a4a4a;
}
QHeaderView::section {
    background-color: #3c3c3c;
    color: #8ab4f8;
    border: 1px solid #4a4a4a;
    padding: 4px 6px;
    font-weight: bold;
}
QTextEdit {
    background-color: #1e1e1e;
    color: #9cdcfe;
    border: 1px solid #4a4a4a;
    border-radius: 3px;
    font-family: 'Courier New';
    font-size: 12px;
}
QProgressBar {
    border: 1px solid #4a4a4a;
    border-radius: 3px;
    background-color: #3c3c3c;
    text-align: center;
    color: #d4d4d4;
}
QProgressBar::chunk { background-color: #4a9eff; border-radius: 2px; }
QScrollBar:vertical {
    background-color: #2b2b2b; width: 10px; border: none;
}
QScrollBar::handle:vertical {
    background-color: #5a5a5a; border-radius: 5px; min-height: 20px;
}
QScrollBar::handle:vertical:hover { background-color: #4a9eff; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QLabel { color: #d4d4d4; }
QListWidget {
    background-color: #252525;
    border: 1px solid #4a4a4a;
    border-radius: 3px;
    color: #d4d4d4;
    font-size: 11px;
    outline: none;
}
QListWidget::item { padding: 2px 6px; }
QListWidget::item:selected { background-color: #4a9eff; color: #ffffff; }
QListWidget::item:hover:!selected { background-color: #3a3a3a; }
"""


# ── UI helpers ────────────────────────────────────────────────────────────────

def _field_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet("color: #8ab4f8; font-weight: bold;")
    return lbl


_TOGGLE_BTN_STYLE = (
    "QPushButton { color: #6e6e6e; font-weight: normal; font-size: 13px;"
    " text-align: left; border: none; background: transparent; padding: 2px 0; }"
    "QPushButton:hover { color: #8ab4f8; }"
    "QPushButton:checked { color: #8ab4f8; }"
)


def _make_toggle_btn(label: str) -> QPushButton:
    btn = QPushButton(f"▶  {label}")
    btn.setFlat(True)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setCheckable(True)
    btn.setStyleSheet(_TOGGLE_BTN_STYLE)
    return btn


def _connect_toggle(btn: QPushButton, label: str, panel: QWidget) -> None:
    def _handler(checked: bool):
        btn.setText(f"{'▼' if checked else '▶'}  {label}")
        panel.setVisible(checked)
    btn.toggled.connect(_handler)


def _is_valid_ip(ip: str) -> bool:
    parts = ip.strip().split('.')
    if len(parts) != 4:
        return False
    return all(p.isdigit() and 0 <= int(p) <= 255 for p in parts)


class SortableItem(QTableWidgetItem):
    """QTableWidgetItem that sorts by a numeric key rather than display text."""
    def __init__(self, text: str, sort_key: float):
        super().__init__(text)
        self._key = sort_key

    def __lt__(self, other: QTableWidgetItem) -> bool:
        if isinstance(other, SortableItem):
            return self._key < other._key
        return super().__lt__(other)


# ── Developer dialogs ─────────────────────────────────────────────────────────

def _dev_field_row(parent_layout, label: str, value: str, password: bool = False) -> QLineEdit:
    """Add a label + QLineEdit row to parent_layout and return the QLineEdit."""
    row = QWidget()
    h = QHBoxLayout(row)
    h.setContentsMargins(0, 2, 0, 2)
    h.setSpacing(8)
    lbl = QLabel(label)
    lbl.setFixedWidth(110)
    lbl.setStyleSheet("color: #8ab4f8; font-size: 11px;")
    inp = QLineEdit(value)
    if password:
        inp.setEchoMode(QLineEdit.EchoMode.Password)
    h.addWidget(lbl)
    h.addWidget(inp, stretch=1)
    parent_layout.addWidget(row)
    return inp


class _DevSettingsDialog(QDialog):
    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Developer Settings")
        self.setMinimumWidth(520)
        self._settings = dict(settings)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # GitLab
        gitlab_box = QGroupBox("GitLab")
        gitlab_box.setStyleSheet("QGroupBox::title { color: #6e6e6e; font-weight: normal; }")
        gv = QVBoxLayout(gitlab_box)
        self._gl_url   = _dev_field_row(gv, "Instance URL", settings.get("gitlab_url", ""))
        self._gl_email = _dev_field_row(gv, "Email",        settings.get("gitlab_email", ""))
        self._gl_token = _dev_field_row(gv, "Token",        settings.get("gitlab_token", ""), password=True)

        # Local Build
        build_box = QGroupBox("Local Build")
        build_box.setStyleSheet("QGroupBox::title { color: #6e6e6e; font-weight: normal; }")
        bv = QVBoxLayout(build_box)
        git_row_w = QWidget()
        git_h = QHBoxLayout(git_row_w)
        git_h.setContentsMargins(0, 2, 0, 2)
        git_h.setSpacing(8)
        lbl_git = QLabel("Git directory")
        lbl_git.setFixedWidth(110)
        lbl_git.setStyleSheet("color: #8ab4f8; font-size: 11px;")
        self._git_dir = QLineEdit(settings.get("local_git_dir", ""))
        self._git_dir.setPlaceholderText(r"e.g. C:\_development\git")
        browse_git_btn = QPushButton("Browse…")
        browse_git_btn.setFixedWidth(77)
        browse_git_btn.clicked.connect(self._browse_git_dir)
        git_h.addWidget(lbl_git)
        git_h.addWidget(self._git_dir, stretch=1)
        git_h.addWidget(browse_git_btn)
        bv.addWidget(git_row_w)
        self._build_sub = _dev_field_row(bv, "Build subpath", settings.get("build_subpath", "{NAME}/build"))
        hint_build = QLabel("  {NAME} → uppercase project name, e.g. {NAME}/build → EPRVI/build")
        hint_build.setStyleSheet("color: #6e6e6e; font-size: 10px;")
        bv.addWidget(hint_build)

        # WSL
        wsl_box = QGroupBox("WSL")
        wsl_box.setStyleSheet("QGroupBox::title { color: #6e6e6e; font-weight: normal; }")
        wv = QVBoxLayout(wsl_box)
        self._wsl_user      = _dev_field_row(wv, "Username",     settings.get("wsl_user", ""))
        self._wsl_distro    = _dev_field_row(wv, "Distro name",  settings.get("wsl_distro", "Ubuntu"))
        self._wsl_binaries  = _dev_field_row(wv, "Binaries dir", settings.get("wsl_binaries", "/home/{USER}/binaries"))
        self._wsl_container = _dev_field_row(wv, "Container",    settings.get("wsl_container", "mam"))
        hint_wsl = QLabel("  {USER} in Binaries dir is replaced by WSL username")
        hint_wsl.setStyleSheet("color: #6e6e6e; font-size: 10px;")
        wv.addWidget(hint_wsl)

        layout.addWidget(gitlab_box)
        layout.addWidget(build_box)
        layout.addWidget(wsl_box)

        btn_row = QWidget()
        bh = QHBoxLayout(btn_row)
        bh.setContentsMargins(0, 0, 0, 0)
        cancel_btn = QPushButton("Cancel")
        save_btn   = QPushButton("Save")
        save_btn.setDefault(True)
        cancel_btn.clicked.connect(self.reject)
        save_btn.clicked.connect(self._save)
        bh.addStretch()
        bh.addWidget(cancel_btn)
        bh.addWidget(save_btn)
        layout.addWidget(btn_row)

    def _browse_git_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Select Git directory", self._git_dir.text())
        if d:
            self._git_dir.setText(d)

    def _save(self):
        d = dict(self._settings)
        d["gitlab_url"]    = self._gl_url.text().strip()
        d["gitlab_email"]  = self._gl_email.text().strip()
        d["gitlab_token"]  = self._gl_token.text().strip()
        d["local_git_dir"] = self._git_dir.text().strip()
        d["build_subpath"] = self._build_sub.text().strip()
        d["wsl_user"]      = self._wsl_user.text().strip()
        d["wsl_distro"]    = self._wsl_distro.text().strip()
        d["wsl_binaries"]  = self._wsl_binaries.text().strip()
        d["wsl_container"] = self._wsl_container.text().strip()
        save_dev_settings(d)
        self.accept()


class _GitLabBrowseDialog(QDialog):
    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Browse GitLab Repositories")
        self.setMinimumSize(580, 440)
        self._settings = settings
        self._worker   = None

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        self._status_lbl = QLabel("Loading projects…")
        self._status_lbl.setStyleSheet("color: #8ab4f8;")

        self._list = QListWidget()

        pull_btn = QPushButton("Pull")
        pull_btn.setEnabled(False)
        pull_btn.setToolTip("Pulling from GitLab is not yet implemented")

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)

        btn_row = QWidget()
        bh = QHBoxLayout(btn_row)
        bh.setContentsMargins(0, 0, 0, 0)
        bh.addWidget(pull_btn)
        bh.addStretch()
        bh.addWidget(close_btn)

        layout.addWidget(self._status_lbl)
        layout.addWidget(self._list, stretch=1)
        layout.addWidget(btn_row)

        self._fetch()

    def _fetch(self):
        self._worker = GitLabProjectsWorker(
            self._settings.get("gitlab_url", "https://gitlab.com"),
            self._settings.get("gitlab_token", ""),
        )
        self._worker.result.connect(self._on_result)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_result(self, projects: list):
        self._list.clear()
        if not projects:
            self._status_lbl.setText("No projects found.")
            return
        for p in projects:
            desc = p.get("description") or ""
            text = p["name_with_namespace"] + (f"  —  {desc}" if desc else "")
            self._list.addItem(text)
        self._status_lbl.setText(f"{len(projects)} project(s)")
        self._status_lbl.setStyleSheet("color: #4ec94e;")

    def _on_error(self, msg: str):
        self._status_lbl.setText(f"Error: {msg}")
        self._status_lbl.setStyleSheet("color: #f44747;")

    def closeEvent(self, event):
        if self._worker and self._worker.isRunning():
            self._worker.wait(2000)
        super().closeEvent(event)


class _BuildModuleDialog(QDialog):
    binary_ready = pyqtSignal(str)

    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Build Module")
        self.setMinimumSize(580, 500)
        self._settings    = dict(settings)
        self._project     = None
        self._copy_worker = None

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # Git dir row
        dir_row = QWidget()
        dr = QHBoxLayout(dir_row)
        dr.setContentsMargins(0, 0, 0, 0)
        dr.setSpacing(6)
        self._dir_lbl = QLabel(settings.get("local_git_dir") or "(not configured — use Change…)")
        self._dir_lbl.setStyleSheet("color: #d4d4d4; font-size: 11px;")
        change_btn = QPushButton("Change…")
        change_btn.setFixedWidth(72)
        change_btn.clicked.connect(self._change_dir)
        dr.addWidget(_field_label("Git Dir"))
        dr.addWidget(self._dir_lbl, stretch=1)
        dr.addWidget(change_btn)

        layout.addWidget(dir_row)
        layout.addWidget(_field_label("Projects"))

        self._proj_list = QListWidget()
        self._proj_list.currentItemChanged.connect(self._on_project_selected)
        layout.addWidget(self._proj_list, stretch=1)

        # Per-project build subpath
        bp_row = QWidget()
        bp_h = QHBoxLayout(bp_row)
        bp_h.setContentsMargins(0, 2, 0, 2)
        bp_h.setSpacing(6)
        self._build_path_in = QLineEdit()
        self._build_path_in.setPlaceholderText("e.g. EPRVI/build")
        self._build_path_in.setEnabled(False)
        self._build_path_in.textChanged.connect(self._update_path_labels)
        self._browse_subpath_btn = QPushButton("Browse…")
        self._browse_subpath_btn.setFixedWidth(70)
        self._browse_subpath_btn.setEnabled(False)
        self._browse_subpath_btn.clicked.connect(self._browse_build_subpath)
        self._save_path_btn = QPushButton("Save")
        self._save_path_btn.setFixedWidth(50)
        self._save_path_btn.setEnabled(False)
        self._save_path_btn.clicked.connect(self._save_build_path)
        bp_h.addWidget(_field_label("Build subpath"))
        bp_h.addWidget(self._build_path_in, stretch=1)
        bp_h.addWidget(self._browse_subpath_btn)
        bp_h.addWidget(self._save_path_btn)
        layout.addWidget(bp_row)

        # Per-project binary
        bin_row = QWidget()
        bin_h = QHBoxLayout(bin_row)
        bin_h.setContentsMargins(0, 2, 0, 2)
        bin_h.setSpacing(6)
        self._binary_in = QLineEdit()
        self._binary_in.setPlaceholderText("binary filename (default: project name)")
        self._binary_in.setEnabled(False)
        self._browse_binary_btn = QPushButton("Browse…")
        self._browse_binary_btn.setFixedWidth(70)
        self._browse_binary_btn.setEnabled(False)
        self._browse_binary_btn.clicked.connect(self._browse_binary)
        self._save_binary_btn = QPushButton("Save")
        self._save_binary_btn.setFixedWidth(50)
        self._save_binary_btn.setEnabled(False)
        self._save_binary_btn.clicked.connect(
            lambda: self._save_project_field("binary", self._binary_in)
        )
        bin_h.addWidget(_field_label("Binary"))
        bin_h.addWidget(self._binary_in, stretch=1)
        bin_h.addWidget(self._browse_binary_btn)
        bin_h.addWidget(self._save_binary_btn)
        layout.addWidget(bin_row)

        # Per-project WSL source path
        src_row = QWidget()
        src_h = QHBoxLayout(src_row)
        src_h.setContentsMargins(0, 2, 0, 2)
        src_h.setSpacing(6)
        self._wsl_src_in = QLineEdit()
        self._wsl_src_in.setPlaceholderText("WSL path to binary (auto-computed if empty)")
        self._wsl_src_in.setEnabled(False)
        self._browse_wsl_src_btn = QPushButton("Browse…")
        self._browse_wsl_src_btn.setFixedWidth(70)
        self._browse_wsl_src_btn.setEnabled(False)
        self._browse_wsl_src_btn.clicked.connect(self._browse_wsl_src)
        self._save_wsl_src_btn = QPushButton("Save")
        self._save_wsl_src_btn.setFixedWidth(50)
        self._save_wsl_src_btn.setEnabled(False)
        self._save_wsl_src_btn.clicked.connect(
            lambda: self._save_project_field("wsl_src", self._wsl_src_in)
        )
        src_h.addWidget(_field_label("WSL src"))
        src_h.addWidget(self._wsl_src_in, stretch=1)
        src_h.addWidget(self._browse_wsl_src_btn)
        src_h.addWidget(self._save_wsl_src_btn)
        layout.addWidget(src_row)

        # Per-project WSL destination directory
        dst_row = QWidget()
        dst_h = QHBoxLayout(dst_row)
        dst_h.setContentsMargins(0, 2, 0, 2)
        dst_h.setSpacing(6)
        self._wsl_dst_in = QLineEdit()
        self._wsl_dst_in.setPlaceholderText("WSL destination dir (default: global wsl_binaries)")
        self._wsl_dst_in.setEnabled(False)
        self._browse_wsl_dst_btn = QPushButton("Browse…")
        self._browse_wsl_dst_btn.setFixedWidth(70)
        self._browse_wsl_dst_btn.setEnabled(False)
        self._browse_wsl_dst_btn.clicked.connect(self._browse_wsl_dest)
        self._save_wsl_dst_btn = QPushButton("Save")
        self._save_wsl_dst_btn.setFixedWidth(50)
        self._save_wsl_dst_btn.setEnabled(False)
        self._save_wsl_dst_btn.clicked.connect(
            lambda: self._save_project_field("wsl_dest", self._wsl_dst_in)
        )
        dst_h.addWidget(_field_label("WSL dest"))
        dst_h.addWidget(self._wsl_dst_in, stretch=1)
        dst_h.addWidget(self._browse_wsl_dst_btn)
        dst_h.addWidget(self._save_wsl_dst_btn)
        layout.addWidget(dst_row)

        self._sel_lbl = QLabel("Selected:   —")
        self._sh_lbl  = QLabel("Launch sh:  —")
        for lbl in (self._sel_lbl, self._sh_lbl):
            lbl.setStyleSheet("color: #6e6e6e; font-size: 11px;")
            layout.addWidget(lbl)

        self._launch_btn = QPushButton("Launch Build Console")
        self._launch_btn.setEnabled(False)
        self._launch_btn.clicked.connect(self._launch_console)

        self._copy_btn = QPushButton("Copy Binary to WSL")
        self._copy_btn.setEnabled(False)
        self._copy_btn.clicked.connect(self._copy_binary)

        act_row = QWidget()
        ah = QHBoxLayout(act_row)
        ah.setContentsMargins(0, 0, 0, 0)
        ah.setSpacing(8)
        ah.addWidget(self._launch_btn)
        ah.addWidget(self._copy_btn)
        ah.addStretch()
        layout.addWidget(act_row)

        self._log_area = QTextEdit()
        self._log_area.setReadOnly(True)
        self._log_area.setFixedHeight(100)
        self._log_area.setFont(QFont("Courier New", 9))
        self._log_area.setStyleSheet(
            "background-color: #1e1e1e; color: #d4d4d4; border: none;"
        )
        layout.addWidget(self._log_area)

        self._refresh_projects()

    def _refresh_projects(self):
        self._proj_list.clear()
        git_dir = self._settings.get("local_git_dir", "")
        if not git_dir or not os.path.isdir(git_dir):
            self._proj_list.addItem("(git directory not configured or not found)")
            return
        try:
            entries = sorted(
                e for e in os.listdir(git_dir)
                if os.path.isdir(os.path.join(git_dir, e)) and not e.startswith(".")
            )
        except OSError as exc:
            self._proj_list.addItem(f"Error reading directory: {exc}")
            return
        for entry in entries:
            self._proj_list.addItem(entry)

    def _change_dir(self):
        d = QFileDialog.getExistingDirectory(
            self, "Select Git directory", self._settings.get("local_git_dir", "")
        )
        if d:
            self._settings["local_git_dir"] = d
            self._dir_lbl.setText(d)
            save_dev_settings(self._settings)
            self._refresh_projects()

    def _on_project_selected(self, current, _previous):
        all_widgets = (
            self._build_path_in, self._browse_subpath_btn, self._save_path_btn,
            self._binary_in, self._browse_binary_btn, self._save_binary_btn,
            self._wsl_src_in, self._browse_wsl_src_btn, self._save_wsl_src_btn,
            self._wsl_dst_in, self._browse_wsl_dst_btn, self._save_wsl_dst_btn,
            self._launch_btn, self._copy_btn,
        )
        if current is None or current.text().startswith("("):
            self._project = None
            for w in all_widgets:
                w.setEnabled(False)
            return
        project = current.text()
        self._project = project

        self._build_path_in.blockSignals(True)
        self._build_path_in.setText(get_project_build_subpath(self._settings, project))
        self._build_path_in.blockSignals(False)
        self._binary_in.setText(get_project_setting(self._settings, project, "binary") or "")
        self._wsl_src_in.setText(get_project_setting(self._settings, project, "wsl_src") or "")
        self._wsl_dst_in.setText(get_project_setting(self._settings, project, "wsl_dest") or "")

        for w in all_widgets:
            w.setEnabled(True)

        self._update_path_labels()

    def _update_path_labels(self):
        if not self._project:
            return
        launch_script = get_launch_script_path(self._project)
        launch_note   = "" if os.path.exists(launch_script) else "  (will be created on first launch)"
        self._sel_lbl.setText(f"Selected:   {self._project}")
        self._sel_lbl.setStyleSheet("color: #d4d4d4; font-size: 11px;")
        self._sh_lbl.setText(f"Launch sh:  {launch_script}{launch_note}")
        self._sh_lbl.setStyleSheet("color: #d4d4d4; font-size: 11px;")

    def _save_build_path(self):
        if not self._project:
            return
        subpath = self._build_path_in.text().strip()
        save_project_build_subpath(self._project, subpath)
        self._settings = load_dev_settings()
        self._log_area.append(f"Saved build subpath for {self._project}: {subpath}")

    def _save_project_field(self, key: str, line_edit) -> None:
        if not self._project:
            return
        value = line_edit.text().strip()
        save_project_setting(self._project, key, value)
        self._settings = load_dev_settings()
        self._log_area.append(f"Saved {key} for {self._project}: {value or '(cleared)'}")

    def _browse_build_subpath(self):
        if not self._project:
            return
        git_dir = self._settings.get("local_git_dir", "")
        start = os.path.join(git_dir, self._project) if git_dir else ""
        d = QFileDialog.getExistingDirectory(self, "Select build output directory", start)
        if not d:
            return
        project_dir = os.path.join(git_dir, self._project)
        try:
            rel = os.path.relpath(d, project_dir).replace("\\", "/")
            if not rel.startswith(".."):
                self._build_path_in.setText(rel)
                return
        except ValueError:
            pass
        self._build_path_in.setText(d.replace("\\", "/"))

    def _browse_binary(self):
        if not self._project:
            return
        git_dir = self._settings.get("local_git_dir", "")
        sub = self._build_path_in.text().strip() or get_project_build_subpath(self._settings, self._project)
        start = os.path.join(git_dir, self._project, sub) if git_dir else ""
        path, _ = QFileDialog.getOpenFileName(self, "Select binary file", start)
        if path:
            self._binary_in.setText(os.path.basename(path))

    def _browse_wsl_src(self):
        if not self._project:
            return
        git_dir = self._settings.get("local_git_dir", "")
        sub = self._build_path_in.text().strip() or get_project_build_subpath(self._settings, self._project)
        start = os.path.join(git_dir, self._project, sub) if git_dir else ""
        path, _ = QFileDialog.getOpenFileName(self, "Select binary source file", start)
        if path:
            self._wsl_src_in.setText(any_path_to_wsl(path))

    def _browse_wsl_dest(self):
        distro = self._settings.get("wsl_distro", "Ubuntu")
        start = f"\\\\wsl$\\{distro}"
        d = QFileDialog.getExistingDirectory(self, "Select WSL destination directory", start)
        if d:
            self._wsl_dst_in.setText(any_path_to_wsl(d))

    def _launch_console(self):
        if not self._project:
            return
        import ctypes, shutil, tempfile
        s         = self._settings
        wsl_user  = s.get("wsl_user", "")
        container = s.get("wsl_container", "mam")
        wsl_path  = windows_to_wsl_path(os.path.join(s.get("local_git_dir", ""), self._project))

        # Ensure the per-project docker launch script exists in build_scripts/.
        # Docker logic lives there — edit that file to change container entry.
        launch_win, created = ensure_launch_script(self._project, container)
        wsl_launch = windows_to_wsl_path(launch_win)
        if created:
            self._log_area.append(f"Created launch script: {launch_win}")
        else:
            self._log_area.append(f"Using launch script:   {launch_win}")

        # Temp entry script: cd to project dir, then delegate to the launch script.
        # Kept separate so wt.exe never sees a ";" in its command-line argv tokens
        # (wt.exe splits on ";" for multi-tab syntax, breaking bash -c invocations).
        tmp_path = os.path.join(tempfile.gettempdir(), f"vis_entry_{self._project}.sh")
        with open(tmp_path, "w", encoding="utf-8", newline="\n") as f:
            f.write("#!/bin/bash\n")
            f.write(f'cd "{wsl_path}"\n')
            f.write(f'bash "{wsl_launch}" "{container}"\n')
        wsl_entry = windows_to_wsl_path(tmp_path)

        # -e execs bash directly (no default-shell wrapper), avoiding bash -c "..." quoting issues.
        # Omit -u entirely when wsl_user is empty so WSL uses its default user.
        user_flag = f" -u {wsl_user}" if wsl_user else ""
        wsl_args  = f"wsl.exe{user_flag} -e bash {wsl_entry}"

        # Windows Terminal via ShellExecuteW — correct API for UWP/App Execution
        # Aliases (CreateProcess fails from a GUI process without an attached console)
        if shutil.which("wt.exe"):
            try:
                ret = int(ctypes.windll.shell32.ShellExecuteW(
                    None, "open", "wt.exe", wsl_args, None, 1
                ))
                if ret > 32:
                    self._log_area.append(
                        f"Launched: Windows Terminal → wsl -u {wsl_user} → {container}"
                    )
                    return
                self._log_area.append(f"Windows Terminal error (code {ret}), falling back to cmd…")
            except Exception as exc:
                self._log_area.append(f"Windows Terminal error: {exc}, falling back to cmd…")

        # Fallback: new console window via cmd start (shell=True → cmd handles quoting)
        try:
            subprocess.Popen(f'start "Build: {self._project}" {wsl_args}', shell=True)
            self._log_area.append(f"Launched: cmd → wsl -u {wsl_user} → {container}")
        except Exception as exc:
            self._log_area.append(f"[error] {exc}")

    def _copy_binary(self):
        if not self._project:
            return
        s        = self._settings
        wsl_user = s.get("wsl_user", "")
        distro   = s.get("wsl_distro", "Ubuntu")
        sub      = self._build_path_in.text().strip() or get_project_build_subpath(s, self._project)
        binary   = self._binary_in.text().strip() or self._project
        wsl_git  = windows_to_wsl_path(s.get("local_git_dir", ""))
        src_path = self._wsl_src_in.text().strip() or f"{wsl_git}/{self._project}/{sub}/{binary}"
        dst_dir  = self._wsl_dst_in.text().strip() or resolve_binaries_path(s)

        self._copy_btn.setEnabled(False)
        self._log_area.append(f"Copying {binary} to WSL {dst_dir}/ …")

        self._copy_worker = CopyBinaryWorker(wsl_user, src_path, dst_dir, distro)
        self._copy_worker.log.connect(self._log_area.append)
        self._copy_worker.success.connect(self._on_copy_success)
        self._copy_worker.error.connect(self._on_copy_error)
        self._copy_worker.finished.connect(lambda: self._copy_btn.setEnabled(True))
        self._copy_worker.start()

    def _on_copy_success(self, unc_path: str):
        self._log_area.append(f"Done: {unc_path}")
        self.binary_ready.emit(unc_path)

    def _on_copy_error(self, msg: str):
        self._log_area.append(f"[error] {msg}")


class _DevMenuDialog(QDialog):
    binary_ready = pyqtSignal(str)

    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Developer")
        self.setWindowFlags(Qt.WindowType.Window)
        self.setMinimumWidth(300)
        self._settings   = settings
        self._build_dlg  = None
        self._browse_dlg = None

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        settings_btn = QPushButton("⚙ Settings")
        settings_btn.setStyleSheet(
            "QPushButton { color: #6e6e6e; border: none; background: transparent;"
            " font-size: 11px; padding: 2px 6px; }"
            "QPushButton:hover { color: #d4d4d4; }"
        )
        settings_btn.clicked.connect(self._on_settings)
        top_row = QWidget()
        th = QHBoxLayout(top_row)
        th.setContentsMargins(0, 0, 0, 0)
        th.addStretch()
        th.addWidget(settings_btn)
        layout.addWidget(top_row)

        browse_btn = QPushButton("Browse Repo")
        browse_btn.setMinimumHeight(42)
        browse_btn.clicked.connect(self._on_browse_repo)

        build_btn = QPushButton("Build Module")
        build_btn.setMinimumHeight(42)
        build_btn.clicked.connect(self._on_build_module)

        layout.addWidget(browse_btn)
        layout.addWidget(build_btn)
        layout.addStretch()

    def _on_settings(self):
        dlg = _DevSettingsDialog(self._settings, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._settings = load_dev_settings()

    def _on_browse_repo(self):
        if self._browse_dlg and self._browse_dlg.isVisible():
            self._browse_dlg.raise_()
            return
        self._browse_dlg = _GitLabBrowseDialog(self._settings, self)
        self._browse_dlg.show()

    def _on_build_module(self):
        if self._build_dlg and self._build_dlg.isVisible():
            self._build_dlg.raise_()
            return
        self._build_dlg = _BuildModuleDialog(self._settings, self)
        self._build_dlg.binary_ready.connect(self.binary_ready)
        self._build_dlg.show()


# ── Tail window ───────────────────────────────────────────────────────────────

class TailWindow(QWidget):
    closed = pyqtSignal()

    def __init__(self, ip, port, username, password, remote_path):
        super().__init__()
        self.setWindowTitle(f"tail -f  {remote_path}")
        self.setWindowFlags(Qt.WindowType.Window)
        self.resize(860, 460)
        self._all_lines = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        filter_row = QWidget()
        fh = QHBoxLayout(filter_row)
        fh.setContentsMargins(0, 0, 0, 0)
        fh.setSpacing(6)
        self._filter_in = QLineEdit()
        self._filter_in.setPlaceholderText("Filter ...")
        self._filter_in.textChanged.connect(self._apply_filter)
        fh.addWidget(_field_label("Filter"))
        fh.addWidget(self._filter_in, stretch=1)
        layout.addWidget(filter_row)

        self._text = QTextEdit()
        self._text.setReadOnly(True)
        self._text.setFont(QFont("Courier New", 9))
        self._text.setStyleSheet(
            "background-color: #1e1e1e; color: #d4d4d4; border: none;"
        )
        layout.addWidget(self._text)

        self._worker = TailWorker(ip, port, username, password, remote_path)
        self._worker.line.connect(self._append)
        self._worker.start()

    def _append(self, line: str):
        self._all_lines.append(line)
        if len(self._all_lines) > _TAIL_MAX_LINES:
            del self._all_lines[:_TAIL_MAX_LINES // 5]
            self._apply_filter(self._filter_in.text())
            return
        ftext = self._filter_in.text().lower()
        if not ftext or ftext in line.lower():
            self._text.append(line)
        sb = self._text.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _apply_filter(self, text: str):
        lower = text.lower()
        visible = [l for l in self._all_lines if not lower or lower in l.lower()]
        self._text.setPlainText("\n".join(visible))
        sb = self._text.verticalScrollBar()
        sb.setValue(sb.maximum())

    def closeEvent(self, event):
        self._worker.stop()
        if not self._worker.wait(3000):
            self._worker.terminate()
        event.accept()
        self.closed.emit()


# ── Help / about dialog ───────────────────────────────────────────────────────

class _HelpDialog(QDialog):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"About — {APP_NAME}")
        self.setFixedWidth(360)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 20, 28, 20)
        layout.setSpacing(4)
        self._add_icon(layout)
        self._add_title(layout)
        self._add_separator(layout)
        self._add_info(layout)
        self._add_separator(layout)
        self._add_build_date(layout)
        self._add_ok_button(layout)
        self.adjustSize()

    def _add_icon(self, layout: QVBoxLayout) -> None:
        icon = QApplication.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxQuestion)
        pixmap = icon.pixmap(64, 64)
        lbl = QLabel()
        lbl.setPixmap(pixmap)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl)
        layout.addSpacing(8)

    def _section(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("font-size: 8pt; font-weight: bold; background: transparent; color: #8ab4f8;")
        return lbl

    def _body(self, text: str, wrap: bool = False) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("font-size: 9pt; background: transparent;")
        if wrap:
            lbl.setWordWrap(True)
        return lbl

    def _add_title(self, layout: QVBoxLayout) -> None:
        name = QLabel(APP_NAME)
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name.setStyleSheet("font-size: 13pt; font-weight: bold; background: transparent;")
        layout.addWidget(name)
        ver = QLabel(APP_VERSION)
        ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ver.setStyleSheet("font-size: 10pt; background: transparent;")
        layout.addWidget(ver)

    def _add_separator(self, layout: QVBoxLayout) -> None:
        layout.addSpacing(6)
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(sep)
        layout.addSpacing(6)

    def _add_info(self, layout: QVBoxLayout) -> None:
        layout.addWidget(self._section("Author"))
        layout.addWidget(self._body(APP_AUTHOR))
        layout.addSpacing(4)
        layout.addWidget(self._section("Email issues / suggestions"))
        btn = QPushButton(APP_EMAIL)
        btn.setFlat(True)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(
            "color: #4a9eff; text-decoration: underline; border: none;"
            "background: transparent; text-align: left; padding: 0; margin: 0;"
        )
        subject = "Utility Console"
        btn.clicked.connect(lambda: QDesktopServices.openUrl(
            QUrl(f"mailto:{APP_EMAIL}?subject={subject.replace(' ', '%20')}")
        ))
        layout.addWidget(btn)

    def _add_build_date(self, layout: QVBoxLayout) -> None:
        layout.addWidget(self._section("Build date"))
        ts = os.path.getmtime(os.path.abspath(__file__))
        date_str = datetime.fromtimestamp(ts).strftime("%d %B %Y  %H:%M")
        layout.addWidget(self._body(date_str))

    def _add_ok_button(self, layout: QVBoxLayout) -> None:
        layout.addSpacing(16)
        ok = QPushButton("OK")
        ok.setFixedWidth(80)
        ok.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(ok)
        row.addStretch()
        layout.addLayout(row)


# ── Module details dialog ─────────────────────────────────────────────────────

class _ModuleDetailsDialog(QDialog):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setWindowTitle("Module Details")
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        self.resize(400, 300)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self._status_lbl = QLabel("Loading ...")
        self._status_lbl.setStyleSheet("color: #8ab4f8; font-weight: bold;")
        layout.addWidget(self._status_lbl)

        self._table = QTableWidget(0, 2)
        self._table.setHorizontalHeaderLabels(["Module", "Version"])
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSortIndicatorShown(True)
        hdr.setSortIndicator(0, Qt.SortOrder.AscendingOrder)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.setSortingEnabled(True)
        layout.addWidget(self._table)

        ok_btn = QPushButton("OK")
        ok_btn.setFixedWidth(80)
        ok_btn.clicked.connect(self.accept)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(ok_btn)
        layout.addLayout(btn_row)

    def set_data(self, rows: list) -> None:
        self._status_lbl.setText(f"{len(rows)} module(s)")
        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)
        for name, version in rows:
            r = self._table.rowCount()
            self._table.insertRow(r)
            self._table.setItem(r, 0, QTableWidgetItem(name))
            self._table.setItem(r, 1, QTableWidgetItem(version))
        self._table.setSortingEnabled(True)
        self._table.sortItems(0, Qt.SortOrder.AscendingOrder)

    def set_error(self, msg: str) -> None:
        self._status_lbl.setText(f"Error: {msg}")
        self._status_lbl.setStyleSheet("color: #f44747; font-weight: bold;")


# ── Generic SQL result dialog ─────────────────────────────────────────────────

class _SqlListDialog(QDialog):
    def __init__(self, parent: QWidget, title: str, column: str, rows: list,
                 row_action=None, row_action_label: str = "Select") -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        self.resize(320, 440)
        self._all_rows = rows
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self._count_lbl = QLabel(f"{len(rows)} result(s)")
        self._count_lbl.setStyleSheet("color: #8ab4f8; font-weight: bold;")
        layout.addWidget(self._count_lbl)

        self._filter_in = QLineEdit()
        self._filter_in.setPlaceholderText("Filter ...")
        self._filter_in.textChanged.connect(self._apply_filter)
        layout.addWidget(self._filter_in)

        self._table = QTableWidget(0, 1)
        self._table.setHorizontalHeaderLabels([column])
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        if row_action:
            self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            self._table.customContextMenuRequested.connect(
                lambda pos, a=row_action, l=row_action_label: self._on_row_context(pos, l, a))
        self._populate(rows)
        layout.addWidget(self._table)

        ok_btn = QPushButton("OK")
        ok_btn.setFixedWidth(80)
        ok_btn.clicked.connect(self.accept)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(ok_btn)
        layout.addLayout(btn_row)

    def _populate(self, rows: list) -> None:
        self._table.setRowCount(0)
        for row in rows:
            r = self._table.rowCount()
            self._table.insertRow(r)
            self._table.setItem(r, 0, QTableWidgetItem(row))

    def _apply_filter(self, text: str) -> None:
        filtered = [r for r in self._all_rows if text.lower() in r.lower()] if text else self._all_rows
        self._count_lbl.setText(f"{len(filtered)} result(s)")
        self._populate(filtered)

    def _on_row_context(self, pos, label: str, action) -> None:
        item = self._table.itemAt(pos)
        if not item:
            return
        menu = QMenu(self)
        act  = menu.addAction(label)
        if menu.exec(self._table.mapToGlobal(pos)) == act:
            action(self._table.item(item.row(), 0).text())


# ── SQL table (multi-column) result dialog ────────────────────────────────────

class _SqlTableDialog(QDialog):
    def __init__(self, parent: QWidget, title: str,
                 headers: list, rows: list) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setWindowFlags(
            self.windowFlags()
            & ~Qt.WindowType.WindowContextHelpButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
        )
        self.resize(720, 450)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        lbl = QLabel(f"{len(rows)} row(s)")
        lbl.setStyleSheet("color: #8ab4f8; font-weight: bold;")
        layout.addWidget(lbl)

        ncols = len(headers)
        table = QTableWidget(0, ncols)
        table.setHorizontalHeaderLabels(headers)
        hdr = table.horizontalHeader()
        for i in range(ncols):
            hdr.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
        if ncols:
            hdr.setSectionResizeMode(ncols - 1, QHeaderView.ResizeMode.Stretch)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        for row in rows:
            r = table.rowCount()
            table.insertRow(r)
            for c, val in enumerate(row):
                table.setItem(r, c, QTableWidgetItem(val))
        layout.addWidget(table)

        ok_btn = QPushButton("OK")
        ok_btn.setFixedWidth(80)
        ok_btn.clicked.connect(self.accept)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(ok_btn)
        layout.addLayout(btn_row)


# ── Log panel resize handle ───────────────────────────────────────────────────

class _ResizeHandle(QFrame):
    """Draggable strip at the top of the log panel; adjusts log_area height."""
    def __init__(self, target: QWidget):
        super().__init__()
        self._target  = target
        self._drag_y  = None
        self._start_h = None
        self.setFixedHeight(4)
        self.setCursor(Qt.CursorShape.SizeVerCursor)
        self.setStyleSheet(
            "QFrame { background-color: #3a3a3a; }"
            "QFrame:hover { background-color: #4a9eff; }"
        )

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_y  = event.globalPosition().y()
            self._start_h = self._target.height()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_y is not None:
            delta = int(self._drag_y - event.globalPosition().y())
            self._target.setFixedHeight(max(30, self._start_h + delta))
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_y  = None
        self._start_h = None
        event.accept()


# ── Main window ───────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1200, 750)
        self._profiles            = _load_profiles()
        self._filtered_profiles   = []
        self._current_dir         = None
        self._current_dirs        = []
        self._primary_dir         = None
        self._all_rows            = []
        self._worker              = None
        self._system_worker       = None
        self._script_worker       = None
        self._tail_windows        = []
        self._download_had_error  = False
        self._update_local_file   = None
        self._update_module_name  = None
        self._update_is_tgz       = False
        self._update_is_sql       = False
        self._sql_files           = []
        self._update_worker       = None
        self._tgz_worker           = None
        self._sql_worker           = None
        self._rollback_worker      = None
        self._test_worker          = None
        self._test_stop_requested  = False
        self._txn_check_worker     = None
        self._details_worker       = None
        self._module_ctrl_worker  = None
        self._sql_query_worker    = None
        self._dev_mode            = False
        self._dev_settings        = load_dev_settings()
        self._build_ui()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setSpacing(13)
        layout.addWidget(self._build_top_bar())
        self._view_logs_toggle = _make_toggle_btn("View logs")
        self._view_logs_panel = QWidget()
        pv = QVBoxLayout(self._view_logs_panel)
        pv.setContentsMargins(0, 4, 0, 0)
        pv.setSpacing(6)
        pv.addWidget(self._build_filter_bar())
        pv.addWidget(self._build_table(), stretch=3)
        pv.addWidget(self._build_bottom())
        self._view_logs_panel.setVisible(False)
        _connect_toggle(self._view_logs_toggle, "View logs", self._view_logs_panel)
        layout.addWidget(self._view_logs_toggle)
        layout.addWidget(self._view_logs_panel, stretch=100)
        layout.addStretch(1)
        layout.addWidget(self._build_log_panel())
        self.statusBar().setStyleSheet(
            "QStatusBar { background-color: #1e1e1e; color: #ffcc44;"
            " font-size: 12px; padding: 2px 8px; border-top: 1px solid #4a4a4a; }"
        )

    def _build_top_bar(self) -> QWidget:
        bar = QWidget()
        v = QVBoxLayout(bar)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(13)
        v.addWidget(self._build_row1())

        login_row = QWidget()
        lh = QHBoxLayout(login_row)
        lh.setContentsMargins(0, 0, 0, 0)
        lh.setSpacing(6)
        lh.addWidget(self._build_login_info_btn(), alignment=Qt.AlignmentFlag.AlignTop)
        lh.addWidget(self._build_login_box(), stretch=1)
        v.addWidget(login_row)

        v.addWidget(self._build_update_box())

        actions_row = QWidget()
        ah = QHBoxLayout(actions_row)
        ah.setContentsMargins(0, 0, 0, 0)
        ah.setSpacing(8)
        ah.addWidget(self._build_buttons())
        ah.addWidget(self._build_system_box())
        ah.addStretch(1)
        ah.addWidget(self._build_database_box())
        v.addWidget(actions_row)

        return bar

    def _build_login_info_btn(self) -> QPushButton:
        btn = QPushButton("?")
        btn.setFixedSize(20, 20)
        btn.setFlat(True)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(
            "color: #8ab4f8; font-size: 13px; font-weight: bold;"
            "border: none; padding: 0; background: transparent;"
        )
        btn.clicked.connect(lambda: QMessageBox.information(
            self,
            "Default VIS Login",
            "Edit these fields if you want to use a different username or password to login.",
        ))
        return btn

    def _build_row1(self) -> QWidget:
        container = QWidget()
        v = QVBoxLayout(container)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)

        self.ip_in = QLineEdit()
        self.ip_in.setPlaceholderText("IP Address")
        self.ip_in.setFixedWidth(220)
        self.ip_in.textChanged.connect(self._on_ip_changed)

        self.port_in = QLineEdit("22")
        self.port_in.setFixedWidth(48)

        self.save_profile_btn = QPushButton("💾")
        self.save_profile_btn.setFixedSize(22, 22)
        self.save_profile_btn.setEnabled(False)
        self.save_profile_btn.setToolTip("Save connection profile")
        self.save_profile_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_profile_btn.setStyleSheet(
            "QPushButton { font-size: 13px; border: none; background: transparent;"
            " color: #8ab4f8; padding: 0; }"
            "QPushButton:hover { color: #ffffff; }"
            "QPushButton:disabled { color: #3a3a3a; }"
        )
        self.save_profile_btn.clicked.connect(self._on_save_profile)

        self.profile_list = QListWidget()
        self.profile_list.setMaximumHeight(80)
        self.profile_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._populate_profile_list()
        self.profile_list.itemClicked.connect(self._on_profile_selected)

        ip_row = QWidget()
        ir = QHBoxLayout(ip_row)
        ir.setContentsMargins(0, 0, 0, 0)
        ir.setSpacing(6)
        ir.addWidget(_field_label("IP"))
        ir.addWidget(self.ip_in)
        ir.addWidget(_field_label("Port"))
        ir.addWidget(self.port_in)
        ir.addWidget(self.save_profile_btn)

        self._profiles_toggle = _make_toggle_btn("Saved profiles")

        self._profile_filter_in = QLineEdit()
        self._profile_filter_in.setPlaceholderText("Filter profiles ...")
        self._profile_filter_in.textChanged.connect(self._populate_profile_list)

        self._profile_row = QWidget()
        pr = QVBoxLayout(self._profile_row)
        pr.setContentsMargins(0, 2, 0, 0)
        pr.setSpacing(4)
        pr.addWidget(self._profile_filter_in)
        pr.addWidget(self.profile_list)
        self._profile_row.setVisible(False)
        _connect_toggle(self._profiles_toggle, "Saved profiles", self._profile_row)

        self._vis_toggle = _make_toggle_btn("VIS")
        self._vis_toggle.setChecked(True)
        self._vis_panel = QWidget()
        bv = QVBoxLayout(self._vis_panel)
        bv.setContentsMargins(6, 0, 0, 0)
        bv.setSpacing(4)
        bv.addWidget(ip_row)
        bv.addWidget(self._profiles_toggle)
        bv.addWidget(self._profile_row)
        _connect_toggle(self._vis_toggle, "VIS", self._vis_panel)

        self.connect_btn = QPushButton("Connect")
        self.connect_btn.setEnabled(False)
        self.connect_btn.clicked.connect(self._on_connect)

        self.logout_btn = QPushButton("Disconnect")
        self.logout_btn.setEnabled(False)
        self.logout_btn.setStyleSheet("""
            QPushButton { color: #f44747; border-color: #f44747; }
            QPushButton:hover { background-color: #f44747; color: #ffffff; border-color: #f44747; }
            QPushButton:disabled { color: #4a4a4a; border-color: #333333; background-color: #252525; }
        """)
        self.logout_btn.clicked.connect(self._on_logout)

        help_btn = QPushButton("?")
        help_btn.setFixedSize(20, 20)
        help_btn.setFlat(True)
        help_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        help_btn.setToolTip("Help")
        help_btn.setStyleSheet(
            "color: #8ab4f8; font-size: 13px; font-weight: bold;"
            "border: none; padding: 0; background: transparent;"
        )
        help_btn.clicked.connect(self._show_help)

        self.ping_btn = QPushButton("Ping test")
        self.ping_btn.setEnabled(False)
        self.ping_btn.clicked.connect(self._on_ping)
        self.ping_status_lbl = QLabel()
        self.ping_status_lbl.setVisible(False)
        self.connect_status_lbl = QLabel()

        self.dev_mode_btn = QPushButton("Dev Mode")
        self.dev_mode_btn.setCheckable(True)
        self.dev_mode_btn.setToolTip("Simulate connection — buttons log only, no SSH")
        self.dev_mode_btn.setStyleSheet(
            "QPushButton { color: #6e6e6e; border: 1px dashed #4a4a4a; border-radius: 3px;"
            " padding: 4px 10px; background: transparent; }"
            "QPushButton:hover:!checked { color: #d4d4d4; border-color: #6e6e6e; }"
            "QPushButton:checked { background-color: #2a1a00; color: #ffaa00;"
            " border: 1px solid #ffaa00; font-weight: bold; }"
            "QPushButton:disabled { color: #3a3a3a; border-color: #333333; }"
        )
        self.dev_mode_btn.toggled.connect(self._on_dev_mode_toggled)

        conn_box = QGroupBox("Connection")
        conn_box.setStyleSheet("QGroupBox::title { color: #6e6e6e; font-weight: normal; }")
        conn_box.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        ch = QHBoxLayout(conn_box)
        ch.setContentsMargins(6, 4, 6, 4)
        ch.setSpacing(6)
        ch.addWidget(self.connect_btn)
        ch.addWidget(self.connect_status_lbl)
        ch.addWidget(self.ping_btn)
        ch.addWidget(self.ping_status_lbl)
        ch.addWidget(self.logout_btn)
        ch.addSpacing(8)
        ch.addWidget(self.dev_mode_btn)

        vis_container = QWidget()
        vc = QVBoxLayout(vis_container)
        vc.setContentsMargins(0, 0, 0, 0)
        vc.setSpacing(2)
        vc.addWidget(self._vis_toggle)
        vc.addWidget(self._vis_panel)

        row1 = QWidget()
        h1 = QHBoxLayout(row1)
        h1.setContentsMargins(0, 0, 0, 0)
        h1.setSpacing(6)
        h1.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        h1.addWidget(vis_container, alignment=Qt.AlignmentFlag.AlignTop)
        h1.addWidget(conn_box, alignment=Qt.AlignmentFlag.AlignVCenter)
        h1.addStretch()
        self._menu_btn = QPushButton("☰")
        self._menu_btn.setFixedWidth(28)
        self._menu_btn.setToolTip("App menu")
        self._menu_btn.setStyleSheet(
            "QPushButton { color: #8ab4f8; border: none; background: transparent;"
            " font-size: 15px; padding: 0; }"
            "QPushButton:hover { color: #ffffff; }"
        )
        self._menu_btn.clicked.connect(self._on_menu_btn)
        h1.addWidget(self._menu_btn, alignment=Qt.AlignmentFlag.AlignVCenter)
        h1.addSpacing(4)
        h1.addWidget(help_btn, alignment=Qt.AlignmentFlag.AlignVCenter)

        v.addWidget(row1)
        return container

    def _build_login_box(self) -> QWidget:
        container = QWidget()
        v = QVBoxLayout(container)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(2)

        self._login_toggle = _make_toggle_btn("Default VIS login")

        self._login_fields = QWidget()
        h = QHBoxLayout(self._login_fields)
        h.setContentsMargins(0, 2, 0, 2)
        h.setSpacing(8)
        self.user_in = QLineEdit(); self.user_in.setPlaceholderText("root")
        self.pass_in = QLineEdit(); self.pass_in.setPlaceholderText("default root password")
        self.pass_in.setEchoMode(QLineEdit.EchoMode.Password)
        for lbl, field in [("User", self.user_in), ("Password", self.pass_in)]:
            h.addWidget(_field_label(lbl))
            h.addWidget(field, stretch=1)
        self._login_fields.setVisible(False)
        _connect_toggle(self._login_toggle, "Default VIS login", self._login_fields)

        v.addWidget(self._login_toggle)
        v.addWidget(self._login_fields)
        return container

    # ── Connection profiles ───────────────────────────────────────────────────

    def _populate_profile_list(self, filter_text: str = "") -> None:
        self.profile_list.blockSignals(True)
        self.profile_list.clear()
        lower = filter_text.lower().strip()
        self._filtered_profiles = [
            p for p in self._profiles
            if not lower
            or lower in p["name"].lower()
            or lower in p["ip"].lower()
            or lower in str(p.get("port", "")).lower()
        ]
        if not self._filtered_profiles:
            placeholder = "— Saved profiles —" if not self._profiles else "No matches"
            item = QListWidgetItem(placeholder)
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.profile_list.addItem(item)
        else:
            for p in self._filtered_profiles:
                item = QListWidgetItem(f"{p['name']}  |  {p['ip']} : {p['port']}")
                item.setData(Qt.ItemDataRole.UserRole, p)
                self.profile_list.addItem(item)
        self.profile_list.blockSignals(False)

    def _on_profile_selected(self, item: QListWidgetItem) -> None:
        p = item.data(Qt.ItemDataRole.UserRole)
        if p is None:
            return
        self.ip_in.setText(p["ip"])
        self.port_in.setText(str(p.get("port", "22")))
        self.user_in.setText(p.get("username", ""))
        self.pass_in.setText(p.get("password", ""))
        if p.get("username", "root") != "root" or p.get("password"):
            if not self._login_toggle.isChecked():
                self._login_toggle.setChecked(True)
        self._profiles_toggle.setChecked(False)

    def _on_save_profile(self) -> None:
        ip   = self.ip_in.text().strip()
        port = self.port_in.text().strip() or "22"
        name, ok = QInputDialog.getText(self, "Save Profile", "Profile name:", text=ip)
        if not ok or not name.strip():
            return
        name     = name.strip()
        username = self.user_in.text().strip() or "root"
        password = self.pass_in.text()
        stored_pw = "" if (not password or password == DEFAULT_PASS) else password
        for p in self._profiles:
            if p["name"] == name:
                p.update(ip=ip, port=port, username=username, password=stored_pw)
                break
        else:
            self._profiles.append(dict(name=name, ip=ip, port=port, username=username, password=stored_pw))
            if not self._profiles_toggle.isChecked():
                self._profiles_toggle.setChecked(True)
        _save_profiles(self._profiles)
        self._populate_profile_list(self._profile_filter_in.text())
        self._select_profile_by_name(name)

    def _select_profile_by_name(self, name: str) -> None:
        for i, p in enumerate(self._filtered_profiles):
            if p["name"] == name:
                self.profile_list.setCurrentRow(i)
                return

    def _build_update_box(self) -> QWidget:
        container = QWidget()
        v = QVBoxLayout(container)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(2)

        self._update_toggle = _make_toggle_btn("Update Module")

        self._update_panel = QWidget()
        ph = QHBoxLayout(self._update_panel)
        ph.setContentsMargins(0, 4, 0, 4)
        ph.setSpacing(10)

        self.browse_btn = QPushButton("Browse file ...")
        self.browse_btn.setEnabled(False)
        self.browse_btn.clicked.connect(self._on_browse_binary)
        self.file_lbl = QLabel("No file selected")
        self.file_lbl.setStyleSheet("color: #6e6e6e; font-style: italic;")
        file_area = QWidget()
        fa = QVBoxLayout(file_area)
        fa.setContentsMargins(0, 0, 0, 0)
        fa.setSpacing(4)
        fa.addWidget(self.browse_btn)
        fa.addWidget(self.file_lbl)
        fa.addStretch()

        ctrl_box = QGroupBox("Update controls")
        ctrl_box.setStyleSheet("QGroupBox::title { color: #6e6e6e; font-weight: normal; }")
        ctrl_box.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        cv = QVBoxLayout(ctrl_box)
        cv.setContentsMargins(6, 4, 6, 6)
        cv.setSpacing(5)

        self.upd_start_btn    = QPushButton("Start")
        self.upd_rollback_btn = QPushButton("Rollback")
        self.upd_test_btn     = QPushButton("Test Module")
        self.upd_details_btn  = QPushButton("Module Details")
        self.upd_details_btn.setStyleSheet("font-weight: bold;")

        for btn in (self.upd_start_btn, self.upd_rollback_btn, self.upd_test_btn):
            btn.setEnabled(False)
            cv.addWidget(btn)
        self.upd_details_btn.setEnabled(False)

        self.upd_start_btn.clicked.connect(self._on_update_start)
        self.upd_rollback_btn.clicked.connect(self._on_update_rollback)
        self.upd_test_btn.clicked.connect(self._on_update_test)
        self.upd_details_btn.clicked.connect(self._on_module_details)

        ph.addWidget(file_area, stretch=1)
        ph.addWidget(ctrl_box)

        self._update_panel.setVisible(False)
        _connect_toggle(self._update_toggle, "Update Module", self._update_panel)
        v.addWidget(self._update_toggle)
        v.addWidget(self._update_panel)
        return container

    def _build_buttons(self) -> QGroupBox:
        box = QGroupBox("Actions")
        box.setStyleSheet("QGroupBox::title { color: #6e6e6e; font-weight: normal; }")
        outer = QHBoxLayout(box)
        outer.setContentsMargins(4, 2, 4, 2)
        outer.setSpacing(7)

        _bold = "font-weight: bold;"
        self.live_btn    = QPushButton("Live Logs");          self.live_btn.setEnabled(False);    self.live_btn.setStyleSheet(_bold)
        self.arch_btn    = QPushButton("Archived Logs");      self.arch_btn.setEnabled(False);    self.arch_btn.setStyleSheet(_bold)
        self.rotate_btn  = QPushButton("Rotate Logs");        self.rotate_btn.setEnabled(False);  self.rotate_btn.setStyleSheet(_bold)
        self.refresh_btn = QPushButton("⟳ Refresh");         self.refresh_btn.setEnabled(False); self.refresh_btn.setStyleSheet(_bold)
        self.stop_btn    = QPushButton("Stop All Modules");   self.stop_btn.setEnabled(False);    self.stop_btn.setStyleSheet(_bold)
        self.start_btn   = QPushButton("Start All Modules");  self.start_btn.setEnabled(False);   self.start_btn.setStyleSheet(_bold)
        self.truncate_btn = QPushButton("Truncate");          self.truncate_btn.setEnabled(False)
        self.live_btn.clicked.connect(lambda: self._list_files(LIVE_LOG_DIRS, label="Live Logs", primary_dir=DIR_LIVE))
        self.arch_btn.clicked.connect(lambda: self._list_files(ARCH_LOG_DIRS, label="Archived Logs", primary_dir=DIR_ARCH))
        self.truncate_btn.clicked.connect(self._on_truncate)
        self.rotate_btn.clicked.connect(self._on_rotate)
        self.refresh_btn.clicked.connect(self._on_refresh)
        self.stop_btn.clicked.connect(self._on_stop_all)
        self.start_btn.clicked.connect(self._on_start_all)

        view_box = QGroupBox("Logs")
        view_box.setStyleSheet("QGroupBox::title { color: #6e6e6e; font-weight: normal; }")
        vl = QVBoxLayout(view_box)
        vl.setContentsMargins(4, 2, 4, 2)
        vl.setSpacing(5)
        vl.addWidget(self.live_btn)
        vl.addWidget(self.arch_btn)
        vl.addWidget(self.truncate_btn)
        vl.addStretch()

        ctrl_box = QGroupBox("Controls")
        ctrl_box.setStyleSheet("QGroupBox::title { color: #6e6e6e; font-weight: normal; }")
        ctl = QVBoxLayout(ctrl_box)
        ctl.setContentsMargins(4, 2, 4, 2)
        ctl.setSpacing(5)
        ctl.addWidget(self.rotate_btn)
        ctl.addWidget(self.stop_btn)
        ctl.addWidget(self.start_btn)
        ctl.addWidget(self.upd_details_btn)

        act_box = QGroupBox("Status")
        act_box.setStyleSheet("QGroupBox::title { color: #6e6e6e; font-weight: normal; }")
        al = QVBoxLayout(act_box)
        al.setContentsMargins(4, 2, 4, 2)
        al.setSpacing(5)
        al.addWidget(self.refresh_btn)
        al.addStretch()

        outer.addWidget(view_box)
        outer.addWidget(ctrl_box, stretch=1)
        outer.addWidget(act_box)
        return box

    def _build_system_box(self) -> QGroupBox:
        box = QGroupBox("System")
        box.setStyleSheet("QGroupBox::title { color: #6e6e6e; font-weight: normal; }")
        box.setFixedWidth(280)
        box.setMaximumHeight(220)
        v = QVBoxLayout(box)
        v.setContentsMargins(4, 2, 4, 2)
        v.setSpacing(2)
        self.sys_count_lbl = QLabel("Programs running (—)")
        self.sys_count_lbl.setStyleSheet("color: #8ab4f8; font-weight: bold; font-size: 11px;")
        self.sys_refresh_lbl = QLabel("")
        self.sys_refresh_lbl.setStyleSheet("color: #6e6e6e; font-size: 10px;")
        self.sys_table = QTableWidget(0, 2)
        self.sys_table.setHorizontalHeaderLabels(["Module", "PID"])
        hdr = self.sys_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.sys_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.sys_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.sys_table.setAlternatingRowColors(True)
        self.sys_table.verticalHeader().setVisible(False)
        self.sys_table.setMinimumWidth(260)
        self.sys_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.sys_table.customContextMenuRequested.connect(self._on_sys_context_menu)
        v.addWidget(self.sys_count_lbl)
        v.addWidget(self.sys_refresh_lbl)
        v.addWidget(self.sys_table)
        return box

    def _build_database_box(self) -> QGroupBox:
        box = QGroupBox("Database")
        box.setStyleSheet("QGroupBox::title { color: #6e6e6e; font-weight: normal; }")
        box.setFixedWidth(280)
        vl = QVBoxLayout(box)
        vl.setContentsMargins(4, 2, 4, 2)
        vl.setSpacing(5)

        self.db_show_all_btn = QPushButton("Show All"); self.db_show_all_btn.setEnabled(False)
        self.db_show_all_btn.clicked.connect(self._on_db_eprvi_show_more)
        vl.addWidget(self.db_show_all_btn)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        sep.setStyleSheet("color: #4a4a4a;")
        vl.addWidget(sep)

        self.db_eprvi_btn    = QPushButton("eprvi");    self.db_eprvi_btn.setEnabled(False)
        self.db_eprstate_btn = QPushButton("eprstate"); self.db_eprstate_btn.setEnabled(False)
        self.db_eprtip_btn   = QPushButton("eprtip");   self.db_eprtip_btn.setEnabled(False)
        self.db_insite_btn   = QPushButton("insite");   self.db_insite_btn.setEnabled(False)
        self.db_mysql_btn    = QPushButton("mysql");    self.db_mysql_btn.setEnabled(False)
        for btn, db in [(self.db_eprvi_btn, "eprvi"), (self.db_eprstate_btn, "eprstate"),
                        (self.db_eprtip_btn, "eprtip"), (self.db_insite_btn, "insite"),
                        (self.db_mysql_btn, "mysql")]:
            btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            btn.customContextMenuRequested.connect(
                lambda pos, b=btn, d=db: self._on_db_context_menu(b, d, pos)
            )
            vl.addWidget(btn)
        vl.addStretch()
        return box

    def _build_filter_bar(self) -> QWidget:
        bar = QWidget()
        h   = QHBoxLayout(bar)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)

        self.filter_in = QLineEdit()
        self.filter_in.setPlaceholderText("Filter logs ...")
        self.filter_in.setFixedWidth(200)
        self.filter_in.textChanged.connect(self._apply_filter)

        self.dl_btn = QPushButton("Download")
        self.dl_btn.setEnabled(False)
        self.dl_btn.setStyleSheet("""
            QPushButton {
                background-color: #4a9eff;
                color: #ffffff;
                font-size: 13px;
                font-weight: bold;
                border: none;
                border-radius: 4px;
                padding: 4px 18px;
            }
            QPushButton:hover    { background-color: #6ab8ff; }
            QPushButton:pressed  { background-color: #2d7dd2; }
            QPushButton:disabled { background-color: #1e3048; color: #3a5a78; border: none; }
        """)
        self.dl_btn.clicked.connect(self._on_download)

        h.addWidget(_field_label("Filter"))
        h.addWidget(self.filter_in)
        h.addStretch()
        h.addWidget(self.dl_btn)
        return bar

    def _build_table(self) -> QTableWidget:
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Date", "Filename", "Size", "Watch"])
        self.table.setColumnWidth(0, 130)
        self.table.setColumnWidth(2, 70)
        self.table.setColumnWidth(3, 60)
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnHidden(3, True)
        hdr.setSortIndicatorShown(True)
        hdr.setSortIndicator(0, Qt.SortOrder.DescendingOrder)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        return self.table

    def _build_bottom(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(2)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        status_row = QWidget()
        sh = QHBoxLayout(status_row)
        sh.setContentsMargins(0, 0, 0, 0)
        sh.addStretch()
        self.status_lbl = QLabel()
        self.status_lbl.setVisible(False)
        sh.addWidget(self.status_lbl)
        v.addWidget(self.progress_bar)
        v.addWidget(status_row)
        return w

    def _build_log_panel(self) -> QWidget:
        outer = QWidget()
        ov = QVBoxLayout(outer)
        ov.setContentsMargins(0, 0, 0, 0)
        ov.setSpacing(0)

        # ── Main panel: title bar + log area ──────────────────────────────────
        self._log_panel_widget = QWidget()
        pv = QVBoxLayout(self._log_panel_widget)
        pv.setContentsMargins(0, 0, 0, 0)
        pv.setSpacing(0)

        title_bar = QWidget()
        title_bar.setFixedHeight(22)
        title_bar.setStyleSheet("background-color: #1e1e1e;")
        th = QHBoxLayout(title_bar)
        th.setContentsMargins(8, 0, 4, 0)
        th.setSpacing(2)

        title_lbl = QLabel("Events")
        title_lbl.setStyleSheet(
            "color: #8ab4f8; font-size: 11px; font-weight: bold; background: transparent;"
        )

        _ctrl = (
            "QPushButton { color: #888888; font-size: 13px; border: none;"
            " background: transparent; padding: 0 3px; min-width: 20px; }"
            "QPushButton:hover { color: #ffffff; }"
        )

        self._log_min_btn = QPushButton("—")
        self._log_min_btn.setFixedSize(20, 20)
        self._log_min_btn.setStyleSheet(_ctrl)
        self._log_min_btn.setToolTip("Minimize")
        self._log_min_btn.setCheckable(True)

        log_clear_btn = QPushButton("⊘")
        log_clear_btn.setFixedSize(20, 20)
        log_clear_btn.setStyleSheet(_ctrl)
        log_clear_btn.setToolTip("Clear")
        log_clear_btn.clicked.connect(lambda: self.log_area.clear())

        log_close_btn = QPushButton("×")
        log_close_btn.setFixedSize(20, 20)
        log_close_btn.setStyleSheet(
            _ctrl + "QPushButton:hover { color: #f44747; }"
        )
        log_close_btn.setToolTip("Close")

        th.addWidget(title_lbl)
        th.addStretch()
        th.addWidget(log_clear_btn)
        th.addWidget(self._log_min_btn)
        th.addWidget(log_close_btn)
        pv.addWidget(title_bar)

        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setFixedHeight(150)
        self.log_area.setFont(QFont("Courier New", 9))
        self.log_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.log_area.setStyleSheet(
            "QTextEdit { border: none; border-radius: 0px; }"
        )
        self.log_area.document().setDefaultStyleSheet("p { margin: 0; padding: 0; }")
        pv.addWidget(self.log_area)

        ov.addWidget(_ResizeHandle(self.log_area))
        ov.addWidget(self._log_panel_widget)

        # ── Restore strip (visible only when panel is closed via ×) ──────────
        self._log_restore_strip = QWidget()
        self._log_restore_strip.setFixedHeight(20)
        self._log_restore_strip.setStyleSheet("background-color: #1e1e1e;")
        self._log_restore_strip.setVisible(False)
        rs = QHBoxLayout(self._log_restore_strip)
        rs.setContentsMargins(8, 0, 4, 0)
        rs.setSpacing(0)
        restore_btn = QPushButton("[]  Events")
        restore_btn.setFlat(True)
        restore_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        restore_btn.setStyleSheet(
            "QPushButton { color: #8ab4f8; font-size: 11px; border: none;"
            " background: transparent; padding: 0; text-align: left; }"
            "QPushButton:hover { color: #ffffff; }"
        )
        rs.addWidget(restore_btn)
        rs.addStretch()
        ov.addWidget(self._log_restore_strip)

        # ── Behaviour ─────────────────────────────────────────────────────────
        def _toggle_min(checked: bool):
            self.log_area.setVisible(not checked)
            self._log_min_btn.setText("[]" if checked else "—")
            self._log_min_btn.setToolTip("Restore" if checked else "Minimize")

        def _close():
            self._log_panel_widget.setVisible(False)
            self._log_restore_strip.setVisible(True)

        def _restore():
            self._log_restore_strip.setVisible(False)
            self._log_panel_widget.setVisible(True)
            if self._log_min_btn.isChecked():
                self._log_min_btn.setChecked(False)

        self._log_min_btn.toggled.connect(_toggle_min)
        log_close_btn.clicked.connect(_close)
        restore_btn.clicked.connect(_restore)

        return outer

    # ── Status helpers ────────────────────────────────────────────────────────

    def _set_status(self, text: str, color: str):
        self.status_lbl.setText(text)
        self.status_lbl.setStyleSheet(
            f"color: {color}; font-size: 14px; font-weight: bold; padding-right: 4px;"
        )
        self.status_lbl.setVisible(True)

    def _set_status_ok(self, msg: str = "Download complete"):
        self._set_status(f"✔  {msg}", "#4ec94e")

    def _set_status_error(self, msg: str = "Error — check log"):
        self._set_status(f"✘  {msg}", "#f44747")

    def _clear_status(self):
        self.status_lbl.setVisible(False)

    def _log(self, msg: str, level: str = "INFO"):
        ts   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        text = _html.escape(f"{ts} [{level}] {msg}")
        color = _LOG_COLORS.get(level, "#9cdcfe")
        self.log_area.append(f'<span style="color:{color};">{text}</span>')
        self.log_area.verticalScrollBar().setValue(
            self.log_area.verticalScrollBar().maximum())

    # ── Connection helpers ────────────────────────────────────────────────────

    def _get_conn(self):
        ip = self.ip_in.text().strip()
        if not ip:
            QMessageBox.warning(self, "Missing IP", "Please enter an IP address.")
            return None
        username = self.user_in.text().strip() or "root"
        password = self.pass_in.text() or DEFAULT_PASS
        try:
            port = int(self.port_in.text().strip())
        except ValueError:
            port = 22
        return ip, port, username, password

    def _set_fields_locked(self, locked: bool):
        style = "QLineEdit { background-color: #1e2a3a; color: #6a9eff; border-color: #2a4a6a; }" if locked else ""
        for field in (self.ip_in, self.port_in, self.user_in, self.pass_in):
            field.setReadOnly(locked)
            field.setStyleSheet(style)
        self.profile_list.setEnabled(not locked)
        self._profile_filter_in.setEnabled(not locked)
        self.save_profile_btn.setEnabled(not locked and _is_valid_ip(self.ip_in.text()))

    # ── Event handlers ────────────────────────────────────────────────────────

    def _on_ip_changed(self, text: str):
        valid = _is_valid_ip(text)
        self.connect_btn.setEnabled(valid or self._dev_mode)
        self.ping_btn.setEnabled(valid)
        self.save_profile_btn.setEnabled(valid)

    def _on_dev_mode_toggled(self, checked: bool):
        self._dev_mode = checked
        self.connect_btn.setEnabled(checked or _is_valid_ip(self.ip_in.text()))
        if checked:
            self._log("[Dev Mode] Enabled — SSH bypassed; action buttons will log only.", "INFO")
        else:
            self._log("[Dev Mode] Disabled.", "INFO")

    def _dev_log(self, btn_name: str):
        msg = f"[Dev Mode] '{btn_name}' button pressed"
        self._log(msg, "INFO")
        self.statusBar().showMessage(msg)

    def _on_ping(self):
        if self._dev_mode:
            self._dev_log("Ping test")
            return
        ip = self.ip_in.text().strip()
        self._log(f"Pinging {ip} (4 packets) ...", "INFO")
        self.ping_btn.setEnabled(False)
        self.ping_status_lbl.setVisible(False)
        self._ping_worker = PingWorker(ip)
        self._ping_worker.output.connect(lambda line: self._log(line, "INFO"))
        self._ping_worker.result.connect(self._on_ping_result)
        self._ping_worker.finished.connect(lambda: self._log("Ping complete.", "INFO"))
        self._ping_worker.finished.connect(lambda: self.ping_btn.setEnabled(True))
        self._ping_worker.start()

    def _on_ping_result(self, success: bool):
        if success:
            self.ping_status_lbl.setText("✔  Reachable")
            self.ping_status_lbl.setStyleSheet("color: #4ec94e; font-weight: bold;")
        else:
            self.ping_status_lbl.setText("✘  Connection failed")
            self.ping_status_lbl.setStyleSheet("color: #f44747; font-weight: bold;")
        self.ping_status_lbl.setVisible(True)

    def _on_connect(self):
        if self._dev_mode:
            self._log("[Dev Mode] Simulating connection ...", "INFO")
            self.connect_btn.setEnabled(False)
            self.connect_status_lbl.setText("Connecting…")
            self.connect_status_lbl.setStyleSheet("color: #d4d4d4;")
            self._on_connect_success()
            return
        conn = self._get_conn()
        if not conn:
            return
        ip, port, username, password = conn
        self.connect_btn.setEnabled(False)
        self.connect_status_lbl.setText("Connecting…")
        self.connect_status_lbl.setStyleSheet("color: #d4d4d4;")
        self._connect_worker = ConnectWorker(ip, port, username, password)
        self._connect_worker.success.connect(self._on_connect_success)
        self._connect_worker.error.connect(self._on_connect_error)
        self._connect_worker.start()

    def _on_connect_success(self):
        self._vis_toggle.setChecked(False)
        self.dev_mode_btn.setEnabled(False)
        self.connect_status_lbl.setText("✔  Connected" + ("  [Dev Mode]" if self._dev_mode else ""))
        self.connect_status_lbl.setStyleSheet("color: #4ec94e; font-weight: bold;")
        self._set_fields_locked(True)
        self.live_btn.setEnabled(True)
        self.arch_btn.setEnabled(True)
        self.rotate_btn.setEnabled(True)
        self.stop_btn.setEnabled(True)
        self.start_btn.setEnabled(True)
        self.logout_btn.setEnabled(True)
        self.ping_btn.setEnabled(False)
        self.upd_details_btn.setEnabled(True)
        self.browse_btn.setEnabled(True)
        for btn in (self.db_show_all_btn, self.db_eprvi_btn, self.db_eprstate_btn,
                    self.db_eprtip_btn, self.db_insite_btn, self.db_mysql_btn):
            btn.setEnabled(True)
        if self._update_module_name:
            self.upd_start_btn.setEnabled(True)
        self._refresh_system()

    def _on_connect_error(self, msg: str):
        self.connect_status_lbl.setText(f"✘  {msg}")
        self.connect_status_lbl.setStyleSheet("color: #f44747; font-weight: bold;")
        self.connect_btn.setEnabled(_is_valid_ip(self.ip_in.text()))

    def _on_logout(self):
        if self._worker and self._worker.isRunning():
            self._worker.quit()
            self._worker.wait()
        for win in self._tail_windows:
            win.close()
        self._tail_windows.clear()
        self._current_dir     = None
        self._current_dirs    = []
        self._primary_dir     = None
        self._all_rows        = []
        self.table.setRowCount(0)
        self.table.setColumnHidden(3, True)
        self.progress_bar.setVisible(False)
        self._clear_status()
        self.dl_btn.setEnabled(False)
        self.truncate_btn.setEnabled(False)
        self.logout_btn.setEnabled(False)
        self._set_fields_locked(False)
        self.connect_status_lbl.setText("")
        self.statusBar().clearMessage()
        self.sys_count_lbl.setText("Programs running (—)")
        self.sys_table.setRowCount(0)
        self.live_btn.setText("Live Logs")
        self.arch_btn.setText("Archived Logs")
        self.live_btn.setEnabled(False)
        self.arch_btn.setEnabled(False)
        self.rotate_btn.setEnabled(False)
        self.refresh_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)
        self.start_btn.setEnabled(False)
        if self._test_worker and self._test_worker.isRunning():
            self._test_worker.stop()
        self.browse_btn.setEnabled(False)
        for btn in (self.db_show_all_btn, self.db_eprvi_btn, self.db_eprstate_btn,
                    self.db_eprtip_btn, self.db_insite_btn, self.db_mysql_btn):
            btn.setEnabled(False)
        self._set_module_btns(False)
        self.upd_test_btn.setText("Test Module")
        self._reset_file_selection()
        self._profile_filter_in.clear()
        self.profile_list.clearSelection()
        self.dev_mode_btn.setEnabled(True)
        self._vis_toggle.setChecked(True)
        self._on_ip_changed(self.ip_in.text())

    def _on_selection_changed(self):
        has_sel = bool(self.table.selectedItems())
        self.dl_btn.setEnabled(has_sel)
        self.truncate_btn.setEnabled(has_sel)

    # ── File listing & table ──────────────────────────────────────────────────

    def _list_files(self, remote_dirs: list, label: str = "", primary_dir: str = ""):
        if self._dev_mode:
            self._dev_log(label or "View Logs")
            return
        conn = self._get_conn()
        if not conn:
            return
        ip, port, username, password = conn
        self._view_logs_toggle.setChecked(True)
        self._current_dirs = remote_dirs
        self._current_dir  = primary_dir or (remote_dirs[0][0] if remote_dirs else "")
        self._primary_dir  = self._current_dir
        self._all_rows     = []
        self.table.setRowCount(0)
        self.table.setColumnHidden(3, remote_dirs != LIVE_LOG_DIRS)
        self.dl_btn.setEnabled(False)
        if self._worker and self._worker.isRunning():
            self._worker.blockSignals(True)
        prefix = f"[{label}] " if label else ""
        self._log(f"{prefix}Connecting to {ip}:{port} as {username} ...")
        self._worker = ListWorker(ip, port, username, password, remote_dirs)
        self._worker.files_ready.connect(self._on_files_listed)
        self._worker.log.connect(lambda m: self._log(m, "INFO"))
        self._worker.error.connect(lambda e: (self._log(e, "ERROR"), self._set_status_error("Connection failed")))
        self._worker.start()

    def _on_files_listed(self, files: list):
        self._all_rows = files
        self._populate_table(files)
        self.refresh_btn.setEnabled(True)
        count = len(files)
        if self._current_dir == DIR_LIVE:
            self.live_btn.setText(f"Live Logs ({count})")
        elif self._current_dir == DIR_ARCH:
            self.arch_btn.setText(f"Archived Logs ({count})")

    def _populate_table(self, files: list):
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        for date, filename, size, full_path in files:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, SortableItem(date, parse_date_key(date)))
            name_item = QTableWidgetItem(filename)
            name_item.setData(Qt.ItemDataRole.UserRole, full_path)
            self.table.setItem(row, 1, name_item)
            self.table.setItem(row, 2, SortableItem(size, parse_size(size)))
            self.table.item(row, 2).setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            eye_btn = QPushButton("👁")
            eye_btn.setToolTip(f"Watch live: {filename}")
            eye_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            eye_btn.setStyleSheet(
                "QPushButton { font-size: 16px; border: none; background: transparent; color: #4a9eff; }"
                "QPushButton:hover { color: #ffffff; }"
            )
            eye_btn.clicked.connect(lambda _checked, fp=full_path: self._open_tail(fp))
            self.table.setCellWidget(row, 3, eye_btn)
        self.table.setSortingEnabled(True)

    def _apply_filter(self, text: str):
        lower = text.lower()
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 1)
            self.table.setRowHidden(row, bool(lower and item and lower not in item.text().lower()))

    # ── Download ──────────────────────────────────────────────────────────────

    def _on_download(self):
        if self._dev_mode:
            self._dev_log("Download")
            return
        conn = self._get_conn()
        if not conn:
            return
        ip, port, username, password = conn
        rows         = sorted({i.row() for i in self.table.selectedItems()})
        remote_paths = [self.table.item(r, 1).data(Qt.ItemDataRole.UserRole) for r in rows]
        local_dir = QFileDialog.getExistingDirectory(self, "Select Download Folder")
        if not local_dir:
            return
        self._log(f"Starting download of {len(remote_paths)} file(s) to {local_dir} ...")
        self._clear_status()
        self._download_had_error = False
        self.dl_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(len(remote_paths))
        self.progress_bar.setValue(0)
        self._worker = DownloadWorker(ip, port, username, password, remote_paths, local_dir)
        self._worker.progress.connect(lambda cur, _: self.progress_bar.setValue(cur))
        self._worker.log.connect(lambda m: self._log(m, "INFO"))
        self._worker.warn.connect(lambda m: self._log(m, "WARN"))
        self._worker.error.connect(self._on_download_error)
        self._worker.finished.connect(self._on_download_done)
        self._worker.start()

    def _on_download_error(self, msg: str):
        self._log(msg, "ERROR")
        self._download_had_error = True
        self._set_status_error()

    def _on_download_done(self):
        self.progress_bar.setValue(self.progress_bar.maximum())
        if self._download_had_error:
            self._log("Finished with errors.", "WARN")
        else:
            self._log("All downloads complete.", "INFO")
            self._set_status_ok()
        self.dl_btn.setEnabled(True)

    # ── Truncate ──────────────────────────────────────────────────────────────

    def _on_truncate(self):
        if self._dev_mode:
            self._dev_log("Truncate")
            return
        rows = sorted({i.row() for i in self.table.selectedItems()})
        remote_paths = [self.table.item(r, 1).data(Qt.ItemDataRole.UserRole) for r in rows]
        if not remote_paths:
            return
        command = "truncate -s 0 " + " ".join(remote_paths)
        self.truncate_btn.setEnabled(False)
        self._run_script(
            command=command,
            label="Truncate",
            busy_msg="⟳  Truncating log(s) — please wait ...",
            done_msg="Truncate complete",
            fail_prefix="Truncate failed",
            refresh_files=True,
        )

    # ── VIS controls (rotate / stop all / start all) ──────────────────────────

    def _action_buttons(self):
        return (self.live_btn, self.arch_btn, self.rotate_btn,
                self.refresh_btn, self.stop_btn, self.start_btn)

    def _run_script(self, command: str, label: str, busy_msg: str,
                    done_msg: str, fail_prefix: str, refresh_files: bool = False,
                    disabled_after: tuple = (), timeout: int = None):
        conn = self._get_conn()
        if not conn:
            return
        ip, port, username, password = conn
        for btn in self._action_buttons():
            btn.setEnabled(False)
        self.statusBar().showMessage(busy_msg)
        self._log(f"[{label}] {command}", "INFO")
        self._script_worker = ScriptWorker(ip, port, username, password, command, timeout=timeout)
        self._script_worker.log.connect(lambda m: self._log(m, "INFO"))
        self._script_worker.success.connect(
            lambda: self._on_script_done(done_msg, refresh_files, disabled_after))
        self._script_worker.error.connect(
            lambda msg: self._on_script_error(f"{fail_prefix}: {msg}"))
        self._script_worker.start()

    def _on_script_done(self, msg: str, refresh_files: bool, disabled_after: tuple = ()):
        self._log(f"{msg}.", "INFO")
        self.statusBar().clearMessage()
        self._set_status_ok(msg)
        for btn in self._action_buttons():
            btn.setEnabled(btn not in disabled_after)
        if refresh_files:
            self.refresh_btn.setEnabled(False)
            self._on_refresh()
        else:
            self._refresh_system()

    def _on_script_error(self, msg: str):
        self._log(msg, "ERROR")
        self.statusBar().clearMessage()
        self._set_status_error(msg)
        for btn in self._action_buttons():
            btn.setEnabled(True)

    # ── Transaction guard ─────────────────────────────────────────────────────

    def _guard_transaction(self, callback):
        """Run the unfinalized-transaction check; call callback() only if clear."""
        if self._txn_check_worker and self._txn_check_worker.isRunning():
            return
        if self._txn_check_worker:
            self._txn_check_worker.clear.disconnect()
            self._txn_check_worker.blocked.disconnect()
            self._txn_check_worker.error.disconnect()
            self._txn_check_worker.wait()  # let Qt finish internal thread cleanup before GC
        conn = self._get_conn()
        if not conn:
            return
        ip, port, username, password = conn
        self.statusBar().showMessage("⟳  Checking for ongoing transactions ...")
        self._txn_check_worker = TransactionCheckWorker(ip, port, username, password)
        self._txn_check_worker.clear.connect(lambda: self._on_guard_clear(callback))
        self._txn_check_worker.blocked.connect(self._on_guard_blocked)
        self._txn_check_worker.error.connect(self._on_guard_error)
        self._txn_check_worker.start()

    def _on_guard_clear(self, callback):
        self.statusBar().clearMessage()
        callback()

    def _on_guard_error(self, err: str):
        self.statusBar().clearMessage()
        self._log(f"[Transaction check] {err} — operation blocked", "WARN")
        msg = QMessageBox(self)
        msg.setWindowTitle("Transaction Check Failed")
        msg.setIcon(QMessageBox.Icon.Critical)
        msg.setTextFormat(Qt.TextFormat.RichText)
        msg.setText(
            "<b>Operation blocked.</b><br>"
            "The transaction check failed — cannot confirm the system is idle.<br><br>"
            f"<i>{_html.escape(err)}</i>"
        )
        msg.exec()

    def _on_guard_blocked(self, row: dict):
        self.statusBar().clearMessage()
        self._show_transaction_blocked_popup(row)

    def _show_transaction_blocked_popup(self, row: dict):
        fields = ("token", "date_time", "controller_reference",
                  "pump", "nozzle", "sale_volume", "sale_value")
        rows_html = "".join(
            f"<tr><td align='left'><b>{f}</b></td>"
            f"<td align='right'>&nbsp;&nbsp;{row.get(f, '—')}</td></tr>"
            for f in fields
        )
        msg = QMessageBox(self)
        msg.setWindowTitle("Ongoing Transaction")
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setTextFormat(Qt.TextFormat.RichText)
        msg.setText(
            "<b>Operation not permitted!</b><br>"
            "There is an ongoing transaction.<br><br>"
            f"<table>{rows_html}</table>"
        )
        msg.exec()

    # ── Script actions ────────────────────────────────────────────────────────

    def _on_rotate(self):
        if self._dev_mode:
            self._dev_log("Rotate Logs")
            return
        self._guard_transaction(self._do_rotate)

    def _do_rotate(self):
        self._run_script(
            command=CMD_ROTATE,
            label="Rotate Logs",
            busy_msg="⟳  Rotating logs — please wait ...",
            done_msg="Rotate complete",
            fail_prefix="Rotate failed",
            refresh_files=True,
        )

    def _on_stop_all(self):
        if self._dev_mode:
            self._dev_log("Stop All Modules")
            return
        self._guard_transaction(self._do_stop_all)

    def _do_stop_all(self):
        self._run_script(
            command=CMD_STOPALL,
            label="Stop All Modules",
            busy_msg="⟳  Stopping all modules — please wait ...",
            done_msg="Stop All complete",
            fail_prefix="Stop All failed",
            disabled_after=(self.stop_btn,),
            timeout=30,
        )

    def _on_start_all(self):
        if self._dev_mode:
            self._dev_log("Start All Modules")
            return
        self._guard_transaction(self._do_start_all)

    def _do_start_all(self):
        self._run_script(
            command=CMD_STARTALL,
            label="Start All Modules",
            busy_msg="⟳  Starting all modules — please wait ...",
            done_msg="Start All complete",
            fail_prefix="Start All failed",
            timeout=30,
        )

    # ── System monitoring ─────────────────────────────────────────────────────

    def _refresh_system(self):
        if self._dev_mode:
            return
        if self._system_worker and self._system_worker.isRunning():
            return
        conn = self._get_conn()
        if not conn:
            return
        ip, port, username, password = conn
        self._system_worker = SystemWorker(ip, port, username, password)
        self._system_worker.result.connect(self._on_system_result)
        self._system_worker.error.connect(lambda e: self._log(f"System check: {e}", "ERROR"))
        self._system_worker.start()

    def _on_system_result(self, items: list):
        running_count = sum(1 for i in items if i["running"])
        self.sys_count_lbl.setText(f"Programs running ({running_count})")
        self.sys_refresh_lbl.setText("Last refresh  " + datetime.now().strftime("%H:%M:%S"))
        self.sys_table.setSortingEnabled(False)
        self.sys_table.setRowCount(0)
        grey = QColor("#6e6e6e")
        for data in items:
            r = self.sys_table.rowCount()
            self.sys_table.insertRow(r)
            name_item = QTableWidgetItem(data["name"])
            pid_item  = QTableWidgetItem(data["pid"] if data["pid"] else "")
            name_item.setData(Qt.ItemDataRole.UserRole, data)
            if not data["running"]:
                name_item.setForeground(grey)
                pid_item.setForeground(grey)
            self.sys_table.setItem(r, 0, name_item)
            self.sys_table.setItem(r, 1, pid_item)
        self.sys_table.setSortingEnabled(True)

    def _on_sys_context_menu(self, pos):
        item = self.sys_table.itemAt(pos)
        if not item:
            return
        data = self.sys_table.item(item.row(), 0).data(Qt.ItemDataRole.UserRole)
        if not data:
            return
        menu   = QMenu(self)
        action = menu.addAction("Kill module" if data["running"] else "Start module")
        if menu.exec(self.sys_table.mapToGlobal(pos)) == action:
            self._on_module_control(data["name"], pid=data["pid"] if data["running"] else None)

    def _on_module_control(self, name: str, pid=None):
        if self._dev_mode:
            self._dev_log(f"{'Kill' if pid else 'Start'} {name}")
            return
        conn = self._get_conn()
        if not conn:
            return
        ip, port, username, password = conn
        self._log(f"[{'kill' if pid else 'start'}] {name} ...", "INFO")
        self._module_ctrl_worker = ModuleControlWorker(ip, port, username, password, name, pid)
        self._module_ctrl_worker.log.connect(lambda m: self._log(m, "INFO"))
        self._module_ctrl_worker.success.connect(self._on_module_ctrl_done)
        self._module_ctrl_worker.error.connect(lambda e: self._log(e, "ERROR"))
        self._module_ctrl_worker.start()

    def _on_module_ctrl_done(self):
        self._log("Done.", "INFO")
        self._refresh_system()

    # ── Database box ──────────────────────────────────────────────────────────

    def _on_db_context_menu(self, btn: QPushButton, db_name: str, pos):
        menu             = QMenu(self)
        show_tables_act  = menu.addAction("Show tables")
        if menu.exec(btn.mapToGlobal(pos)) == show_tables_act:
            self._on_db_show_tables(db_name)

    def _on_db_show_tables(self, db_name: str):
        if self._dev_mode:
            self._dev_log(f"{db_name} – Show tables")
            return
        conn = self._get_conn()
        if not conn:
            return
        ip, port, username, password = conn
        self._log(f"[{db_name}] Running SHOW TABLES ...", "INFO")
        self._sql_query_worker = SqlQueryWorker(
            ip, port, username, password, SQL_SHOW_TABLES, database=db_name)
        self._sql_query_worker.result.connect(
            lambda rows, d=db_name: self._on_db_show_tables_result(d, rows))
        self._sql_query_worker.error.connect(lambda e: self._log(f"[{db_name}] {e}", "ERROR"))
        self._sql_query_worker.start()

    def _on_db_show_tables_result(self, db_name: str, rows: list):
        self._log(f"[{db_name}] {len(rows)} table(s).", "INFO")
        _SqlListDialog(
            self, f"{db_name} – Tables", "Table", rows,
            row_action=lambda t, d=db_name: self._on_db_select_table(d, t),
            row_action_label="Select all rows",
        ).exec()

    def _on_db_select_table(self, db_name: str, table_name: str):
        conn = self._get_conn()
        if not conn:
            return
        ip, port, username, password = conn
        self._log(f"[{db_name}] SELECT * FROM {table_name} ...", "INFO")
        self._sql_query_worker = SqlQueryWorker(
            ip, port, username, password,
            sql_select_all(table_name), database=db_name, with_headers=True)
        self._sql_query_worker.result.connect(
            lambda lines, d=db_name, t=table_name: self._on_db_select_result(d, t, lines))
        self._sql_query_worker.error.connect(
            lambda e, d=db_name: self._log(f"[{d}] {e}", "ERROR"))
        self._sql_query_worker.start()

    def _on_db_select_result(self, db_name: str, table_name: str, lines: list):
        if lines:
            headers = lines[0].split('\t')
            data    = [l.split('\t') for l in lines[1:]]
        else:
            headers, data = [], []
        self._log(f"[{db_name}] {table_name}: {len(data)} row(s).", "INFO")
        _SqlTableDialog(self, f"{db_name}.{table_name}", headers, data).exec()

    def _on_db_eprvi_show_more(self):
        if self._dev_mode:
            self._dev_log("eprvi – Show more")
            return
        conn = self._get_conn()
        if not conn:
            return
        ip, port, username, password = conn
        self._log("[eprvi] Running SHOW DATABASES ...", "INFO")
        self._sql_query_worker = SqlQueryWorker(ip, port, username, password, SQL_SHOW_DATABASES)
        self._sql_query_worker.result.connect(self._on_db_eprvi_show_more_result)
        self._sql_query_worker.error.connect(lambda e: self._log(f"[eprvi] {e}", "ERROR"))
        self._sql_query_worker.start()

    def _on_db_eprvi_show_more_result(self, rows: list):
        self._log(f"[eprvi] {len(rows)} database(s) found.", "INFO")
        dlg = _SqlListDialog(self, "eprvi – Databases", "Database", rows)
        dlg.exec()

    def _on_refresh(self):
        if self._dev_mode:
            self._dev_log("Refresh")
            return
        self.ping_status_lbl.setVisible(False)
        self._reset_file_selection()
        self.upd_start_btn.setEnabled(False)
        if self._current_dirs:
            self.refresh_btn.setEnabled(False)
            self._clear_status()
            self._log("Refreshing file list ...", "INFO")
            self._list_files(self._current_dirs, label="Refresh", primary_dir=self._primary_dir)
        self._refresh_system()

    # ── Tail (live view) ──────────────────────────────────────────────────────

    def _prune_tail_windows(self):
        self._tail_windows = [w for w in self._tail_windows if w.isVisible()]

    def _open_tail(self, remote_path: str):
        conn = self._get_conn()
        if not conn:
            return
        ip, port, username, password = conn
        self._prune_tail_windows()
        win = TailWindow(ip, port, username, password, remote_path)
        win.closed.connect(self._prune_tail_windows)
        self._tail_windows.append(win)
        win.show()

    # ── Module update ─────────────────────────────────────────────────────────

    def _on_browse_binary(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Select Module, Package, or SQL Script",
            filter="All Supported (*.tgz *.sql);;SQL Scripts (*.sql);;Binary or Package (*.tgz);;All Files (*)",
        )
        if not files:
            return
        connected = self.logout_btn.isEnabled()
        all_sql = all(f.endswith(".sql") for f in files)
        if all_sql:
            self._update_is_tgz      = False
            self._update_is_sql      = True
            self._update_module_name = None
            self._update_local_file  = files[0]
            self._sql_files          = files
            n = len(files)
            label = os.path.basename(files[0]) if n == 1 else f"{n} SQL files"
            self.file_lbl.setText(f"{label}  ✔ SQL script(s)")
            self.file_lbl.setStyleSheet("color: #4ec94e;")
            self.upd_start_btn.setEnabled(connected)
        elif len(files) == 1:
            path     = files[0]
            filename = os.path.basename(path)
            self._update_local_file = path
            self._update_is_sql     = False
            self._sql_files         = []
            if filename.endswith(".tgz"):
                self._update_is_tgz      = True
                self._update_module_name = None
                self.file_lbl.setText(f"{filename}  ✔ package (modules auto-detected)")
                self.file_lbl.setStyleSheet("color: #4ec94e;")
                self.upd_start_btn.setEnabled(connected)
            elif filename in KNOWN_MODULES:
                self._update_is_tgz      = False
                self._update_module_name = filename
                self.file_lbl.setText(f"{filename}  ✔ recognized module")
                self.file_lbl.setStyleSheet("color: #4ec94e;")
                self.upd_start_btn.setEnabled(connected)
            else:
                self._update_is_tgz      = False
                self._update_module_name = None
                known = ", ".join(sorted(KNOWN_MODULES))
                self.file_lbl.setText(f"{filename}  ✘ unrecognized  (expected: {known})")
                self.file_lbl.setStyleSheet("color: #f44747;")
                self.upd_start_btn.setEnabled(False)
        else:
            self._update_is_tgz      = False
            self._update_is_sql      = False
            self._update_module_name = None
            self._sql_files          = []
            self.file_lbl.setText("Mixed selection — select only .sql files or a single binary/package")
            self.file_lbl.setStyleSheet("color: #f44747;")
            self.upd_start_btn.setEnabled(False)

    def _set_module_btns(self, enabled: bool):
        for btn in (self.upd_start_btn, self.upd_rollback_btn,
                    self.upd_test_btn, self.upd_details_btn):
            btn.setEnabled(enabled)
        if enabled:
            self._sync_start_btn()

    def _sync_start_btn(self):
        """Re-evaluate Start eligibility against the current file selection."""
        connected = self.logout_btn.isEnabled()
        valid     = bool(self._update_is_tgz or self._update_module_name or self._update_is_sql)
        self.upd_start_btn.setEnabled(connected and valid)

    def _reset_file_selection(self):
        self._update_local_file  = None
        self._update_module_name = None
        self._update_is_tgz      = False
        self._update_is_sql      = False
        self._sql_files          = []
        self.file_lbl.setText("No file selected")
        self.file_lbl.setStyleSheet("color: #6e6e6e; font-style: italic;")

    def _on_update_start(self):
        if self._dev_mode:
            self._dev_log("Update Start")
            return
        if not self._update_local_file:
            return
        if self._update_is_tgz:
            self._guard_transaction(self._start_tgz_update)
        elif self._update_is_sql:
            self._guard_transaction(self._start_sql_run)
        elif self._update_module_name:
            self._guard_transaction(self._start_binary_update)

    def _start_binary_update(self):
        if self._update_worker and self._update_worker.isRunning():
            return
        conn = self._get_conn()
        if not conn:
            return
        ip, port, username, password = conn
        self._set_module_btns(False)
        self.file_lbl.setText(os.path.basename(self._update_local_file))
        self.file_lbl.setStyleSheet("color: #d4d4d4; font-style: normal;")
        self.statusBar().showMessage(f"⟳  Preparing update for {self._update_module_name} ...")
        self._log(f"[Update] Starting update for {self._update_module_name} ...", "INFO")
        self._update_worker = UpdateWorker(
            ip, port, username, password, self._update_local_file, self._update_module_name)
        self._update_worker.log.connect(lambda m: self._log(m, "INFO"))
        self._update_worker.step.connect(lambda s: self.statusBar().showMessage(f"⟳  {s}"))
        self._update_worker.success.connect(self._on_update_success)
        self._update_worker.error.connect(self._on_update_error)
        self._update_worker.start()

    def _start_tgz_update(self):
        if self._tgz_worker and self._tgz_worker.isRunning():
            return
        conn = self._get_conn()
        if not conn:
            return
        ip, port, username, password = conn
        self._set_module_btns(False)
        self.file_lbl.setText(os.path.basename(self._update_local_file))
        self.file_lbl.setStyleSheet("color: #d4d4d4; font-style: normal;")
        self.statusBar().showMessage("⟳  Preparing package upload ...")
        self._log(f"[TGZ] Deploying: {os.path.basename(self._update_local_file)} ...", "INFO")
        self._tgz_worker = TgzUpdateWorker(
            ip, port, username, password, self._update_local_file)
        self._tgz_worker.log.connect(lambda m: self._log(m, "INFO"))
        self._tgz_worker.step.connect(lambda s: self.statusBar().showMessage(f"⟳  {s}"))
        self._tgz_worker.success.connect(self._on_tgz_success)
        self._tgz_worker.error.connect(self._on_update_error)
        self._tgz_worker.start()

    def _on_update_success(self, module_name: str):
        self.statusBar().clearMessage()
        self._log(f"✔ Update complete — {module_name} deployed successfully.", "INFO")
        self._set_status_ok(f"{module_name} updated successfully")
        self._set_module_btns(True)
        self._refresh_system()

    def _on_tgz_success(self):
        self.statusBar().clearMessage()
        self._log("✔ Package deployed successfully.", "INFO")
        self._set_status_ok("Package deployed successfully")
        self._set_module_btns(True)
        self._refresh_system()

    def _start_sql_run(self):
        if self._sql_worker and self._sql_worker.isRunning():
            return
        conn = self._get_conn()
        if not conn:
            return
        ip, port, username, password = conn
        self._set_module_btns(False)
        n = len(self._sql_files)
        self.statusBar().showMessage("⟳  Preparing SQL upload ...")
        self._log(f"[SQL] Running {n} file(s): {', '.join(os.path.basename(f) for f in self._sql_files)} ...", "INFO")
        self._sql_worker = SqlFileWorker(ip, port, username, password, self._sql_files)
        self._sql_worker.log.connect(lambda m: self._log(m, "INFO"))
        self._sql_worker.step.connect(lambda s: self.statusBar().showMessage(f"⟳  {s}"))
        self._sql_worker.success.connect(self._on_sql_success)
        self._sql_worker.error.connect(self._on_update_error)
        self._sql_worker.start()

    def _on_sql_success(self):
        self.statusBar().clearMessage()
        self._log("✔ SQL file(s) executed successfully.", "INFO")
        self._set_status_ok("SQL executed successfully")
        self._set_module_btns(True)
        self._refresh_system()

    def _on_update_error(self, msg: str):
        self.statusBar().clearMessage()
        self._log(f"Update failed: {msg}", "ERROR")
        self._set_status_error("Update failed")
        self.upd_start_btn.setEnabled(
            bool(self._update_is_tgz or self._update_module_name or self._update_is_sql)
        )
        self.upd_rollback_btn.setEnabled(False)
        self.upd_test_btn.setEnabled(False)
        self.upd_details_btn.setEnabled(True)
        self._refresh_system()

    def _on_update_rollback(self):
        if self._dev_mode:
            self._dev_log("Rollback")
            return
        if not self._update_module_name:
            return
        self._guard_transaction(self._do_rollback)

    def _do_rollback(self):
        conn = self._get_conn()
        if not conn:
            return
        ip, port, username, password = conn
        self._set_module_btns(False)
        self.statusBar().showMessage(f"⟳  Rolling back {self._update_module_name} ...")
        self._log(f"[Rollback] Rolling back {self._update_module_name} ...", "INFO")
        self._rollback_worker = RollbackWorker(
            ip, port, username, password, self._update_module_name)
        self._rollback_worker.log.connect(lambda m: self._log(m, "INFO"))
        self._rollback_worker.step.connect(lambda s: self.statusBar().showMessage(f"⟳  {s}"))
        self._rollback_worker.success.connect(self._on_rollback_success)
        self._rollback_worker.error.connect(self._on_rollback_error)
        self._rollback_worker.start()

    def _on_rollback_success(self):
        self.statusBar().clearMessage()
        self._log("✔ Rollback complete.", "INFO")
        self._set_status_ok("Rollback complete")
        self._set_module_btns(True)
        self._refresh_system()

    def _on_rollback_error(self, msg: str):
        self.statusBar().clearMessage()
        self._log(f"Rollback failed: {msg}", "ERROR")
        self._set_status_error("Rollback failed")
        self._set_module_btns(True)
        self.upd_start_btn.setEnabled(bool(self._update_module_name))
        self._refresh_system()

    def _on_update_test(self):
        if self._dev_mode:
            self._dev_log("Test Module")
            return
        if self._test_worker and self._test_worker.isRunning():
            self._test_stop_requested = True
            self._test_worker.stop()
            return
        if not self._update_module_name:
            return
        conn = self._get_conn()
        if not conn:
            return
        ip, port, username, password = conn
        self.upd_test_btn.setText("■ Stop Test")
        self._set_module_btns(False)
        self.upd_test_btn.setEnabled(True)
        self._log(f"[Test] Running {module_path(self._update_module_name)}/{self._update_module_name} ...", "INFO")
        self._test_worker = TestModuleWorker(
            ip, port, username, password, self._update_module_name)
        self._test_worker.line.connect(lambda m: self._log(m, "INFO"))
        self._test_worker.running.connect(self._on_test_running)
        self._test_worker.stopped.connect(self._on_test_stopped)
        self._test_worker.start()

    def _on_test_running(self):
        self._set_status_ok(f"{self._update_module_name} is running — test successful")
        self._log(f"[Test] {self._update_module_name} still running after 3 s — test successful.", "INFO")

    def _on_test_stopped(self, returncode: int):
        self.upd_test_btn.setText("Test Module")
        self._set_module_btns(True)
        user_stopped = self._test_stop_requested
        self._test_stop_requested = False
        if user_stopped or returncode in (0, -9, -1):
            self._log(f"[Test] {self._update_module_name} stopped (rc={returncode}).", "INFO")
        else:
            self._log(f"[Test] {self._update_module_name} exited with rc={returncode}.", "WARN")
            self._set_status_error(f"Test: module exited unexpectedly (rc={returncode})")

    def _on_module_details(self):
        if self._dev_mode:
            self._dev_log("Module Details")
            return
        conn = self._get_conn()
        if not conn:
            return
        ip, port, username, password = conn
        self.upd_details_btn.setEnabled(False)
        dlg = _ModuleDetailsDialog(self)
        dlg.show()
        def _on_result(lines):
            rows = []
            for line in lines:
                if '|' in line:
                    name, ver = line.split('|', 1)
                    rows.append((name.strip(), ver.strip()))
            dlg.set_data(rows)
            self.upd_details_btn.setEnabled(True)

        def _on_error(e):
            dlg.set_error(e)
            self.upd_details_btn.setEnabled(True)

        self._details_worker = SqlQueryWorker(ip, port, username, password, SQL_MODULE_DETAILS)
        self._details_worker.result.connect(_on_result)
        self._details_worker.error.connect(_on_error)
        self._details_worker.start()

    # ── Developer menu ───────────────────────────────────────────────────────

    def _on_menu_btn(self):
        menu = QMenu(self)
        menu.addAction("Developer…").triggered.connect(self._on_developer)
        menu.exec(self._menu_btn.mapToGlobal(self._menu_btn.rect().bottomLeft()))

    def _on_developer(self):
        s = self._dev_settings
        required = ("gitlab_token", "wsl_user", "local_git_dir")
        if any(not s.get(k) for k in required):
            dlg = _DevSettingsDialog(s, self)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return
            self._dev_settings = load_dev_settings()
        dlg = _DevMenuDialog(self._dev_settings, self)
        dlg.binary_ready.connect(self._on_binary_ready_from_build)
        dlg.show()

    def _on_binary_ready_from_build(self, win_path: str):
        self._update_local_file = win_path
        filename = os.path.basename(win_path)
        if filename in KNOWN_MODULES:
            self._update_module_name = filename
            self.file_lbl.setText(f"{filename}  ✔ recognized module")
            self.file_lbl.setStyleSheet("color: #4ec94e;")
            self.upd_start_btn.setEnabled(self.logout_btn.isEnabled())
        else:
            self._update_module_name = None
            known = ", ".join(sorted(KNOWN_MODULES))
            self.file_lbl.setText(f"{filename}  ✘ unrecognized  (expected: {known})")
            self.file_lbl.setStyleSheet("color: #f44747;")
            self.upd_start_btn.setEnabled(False)
        self._log(f"[Build] Binary ready: {win_path}")

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def closeEvent(self, event):
        for win in self._tail_windows:
            win.close()
        if self._script_worker and self._script_worker.isRunning():
            self._script_worker.stop()
        if self._test_worker and self._test_worker.isRunning():
            self._test_worker.stop()
        for attr in ("_worker", "_ping_worker", "_system_worker", "_script_worker",
                     "_update_worker", "_rollback_worker", "_test_worker", "_details_worker"):
            w = getattr(self, attr, None)
            if w and w.isRunning():
                w.quit()
                w.wait(5000)
        event.accept()

    def _show_help(self):
        _HelpDialog(self).exec()
