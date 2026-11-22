"""GitHub Release Tracker (PyQt6 edition).

A small, portable desktop application that tracks the latest release of GitHub
projects with configurable Source and Target platform columns
(PC, Android, Switch, Switch 2, PS5, PS4, PS3) via drop-down box.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PyQt6.QtCore import Qt, QThread, QUrl, pyqtSignal
from PyQt6.QtGui import QAction, QColor, QDesktopServices, QFont, QIcon, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from tracker_core import (
    APP_NAME,
    APP_VERSION,
    COL_BASE,
    COL_MIN,
    COLS,
    MAX_CUSTOM_NAME,
    MAX_IMPORT_BYTES,
    NO_DESCRIPTION,
    PLATFORMS,
    REPO_URL,
    SORTABLE,
    GitHubError,
    HttpNet,
    apply_rename,
    apply_result,
    build_export,
    checked_label,
    data_to_json,
    default_data,
    default_platform,
    display_name,
    fetch_repo_info,
    get_latest,
    has_update,
    layout_columns,
    merge_projects,
    normalize_platform,
    normalize_project,
    now_iso,
    parse_data,
    parse_import,
    parse_repo,
    project_key,
    published_label,
    release_label,
    safe_github_url,
    sort_order,
    status_text,
    today_ymd,
)


def get_palette(dark: bool) -> Dict[str, str]:
    if dark:
        return {
            "bg": "#202124",
            "fg": "#e8eaed",
            "field": "#2b2d31",
            "sel_bg": "#2f6fbf",
            "sel_fg": "#ffffff",
            "btn_bg": "#3a3d42",
            "btn_active": "#4a4d52",
            "border": "#4a4d52",
            "update_bg": "#4d4210",
            "update_fg": "#ffe9a6",
            "error_fg": "#ff8a80",
            "none_fg": "#9aa0a6",
            "sub_fg": "#9aa0a6",
            "line": "#3d4046",
            "link": "#4da3ff",
            "head_bg": "#33363b",
        }
    return {
        "bg": "#f3f3f3",
        "fg": "#1b1b1b",
        "field": "#ffffff",
        "sel_bg": "#0078d4",
        "sel_fg": "#ffffff",
        "btn_bg": "#e1e1e1",
        "btn_active": "#d0d0d0",
        "border": "#bdbdbd",
        "update_bg": "#fff3cd",
        "update_fg": "#1b1b1b",
        "error_fg": "#b00020",
        "none_fg": "#777777",
        "sub_fg": "#666666",
        "line": "#d4d4d4",
        "link": "#0b57d0",
        "head_bg": "#e5e5e5",
    }


def data_file_path() -> Path:
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
    else:
        exe_dir = Path(__file__).resolve().parent

    probe = exe_dir / f".write_test_{os.getpid()}"
    try:
        probe.write_bytes(b"x")
        probe.unlink(missing_ok=True)
        return exe_dir / "projects.json"
    except Exception:
        pass

    appdata = os.environ.get("APPDATA")
    if appdata:
        d = Path(appdata) / "GitHubReleaseTracker"
        try:
            d.mkdir(parents=True, exist_ok=True)
            return d / "projects.json"
        except Exception:
            pass
    return exe_dir / "projects.json"


def load_data(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return default_data()
    try:
        text = path.read_text(encoding="utf-8")
        parsed = parse_data(text)
        if parsed is not None:
            return parsed
    except Exception:
        pass
    try:
        bak = path.with_suffix(path.suffix + ".bak")
        path.replace(bak)
    except Exception:
        pass
    return default_data()


def write_atomic(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def detect_system_dark() -> bool:
    if sys.platform == "win32":
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
            ) as key:
                val, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
                return int(val) == 0
        except Exception:
            return True
    return True


class AddProjectWorker(QThread):
    finished_add = pyqtSignal(object, object)  # (result_tuple_or_None, error_str_or_None)

    def __init__(self, net: HttpNet, owner: str, repo: str, token: str) -> None:
        super().__init__()
        self.net = net
        self.owner = owner
        self.repo = repo
        self.token = token

    def run(self) -> None:
        try:
            latest = get_latest(self.net, self.owner, self.repo, self.token, True)
            try:
                info = fetch_repo_info(self.net, self.owner, self.repo, self.token)
            except GitHubError as e:
                if e.kind == "not_found":
                    raise
                info = {
                    "owner": self.owner,
                    "repo": self.repo,
                    "title": self.repo,
                    "description": "",
                    "html_url": f"https://github.com/{self.owner}/{self.repo}",
                }
            self.finished_add.emit((info, latest), None)
        except Exception as e:
            self.finished_add.emit(None, str(e))


class CheckUpdatesWorker(QThread):
    finished_check = pyqtSignal(list, object)  # (results, rate_remaining)

    def __init__(
        self, net: HttpNet, snapshot: List[Tuple[str, str, bool]], token: str
    ) -> None:
        super().__init__()
        self.net = net
        self.snapshot = snapshot
        self.token = token

    def run(self) -> None:
        results: List[Tuple[str, Optional[Dict[str, Any]], Optional[str]]] = []
        for owner, repo, inc in self.snapshot:
            key = f"{owner}/{repo}".lower()
            try:
                rel = get_latest(self.net, owner, repo, self.token, inc)
                results.append((key, rel, None))
            except GitHubError as e:
                results.append((key, None, str(e)))
                if e.kind == "rate_limit":
                    break
            except Exception as e:
                results.append((key, None, str(e)))
        self.finished_check.emit(results, self.net.rate_remaining)


class AboutDialog(QDialog):
    def __init__(self, parent: QWidget, pal: Dict[str, str]) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"About {APP_NAME}")
        self.setFixedSize(430, 196)
        self.pal = pal

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        top = QHBoxLayout()
        icon_lbl = QLabel("GRT")
        icon_lbl.setFixedSize(48, 48)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setStyleSheet(
            f"background-color: {pal['sel_bg']}; color: {pal['sel_fg']}; "
            "font-weight: bold; font-size: 15px; border-radius: 8px;"
        )
        top.addWidget(icon_lbl, 0, Qt.AlignmentFlag.AlignTop)

        info_col = QVBoxLayout()
        info_col.setSpacing(4)
        head = QLabel(APP_NAME)
        head_font = QFont("Segoe UI", 13)
        head_font.setBold(True)
        head.setFont(head_font)
        info_col.addWidget(head)

        ver = QLabel(f"Version {APP_VERSION} (PyQt6)")
        info_col.addWidget(ver)

        desc = QLabel(
            "Tracks the latest release of the GitHub projects you follow. "
            "No account, login or token needed. MIT License."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {pal['sub_fg']};")
        info_col.addWidget(desc)

        link = QLabel(f'<a href="{REPO_URL}" style="color: {pal["link"]};">{REPO_URL}</a>')
        link.setOpenExternalLinks(True)
        info_col.addWidget(link)

        top.addLayout(info_col, 1)
        layout.addLayout(top)
        layout.addStretch(1)

        btns = QHBoxLayout()
        btns.addStretch(1)
        copy_btn = QPushButton("Copy version")
        copy_btn.setFixedSize(96, 28)
        copy_btn.clicked.connect(self._copy_version)
        btns.addWidget(copy_btn)

        close_btn = QPushButton("Close")
        close_btn.setFixedSize(84, 28)
        close_btn.setDefault(True)
        close_btn.clicked.connect(self.accept)
        btns.addWidget(close_btn)
        layout.addLayout(btns)

    def _copy_version(self) -> None:
        text = f"{APP_NAME} v{APP_VERSION}"
        cb = QApplication.clipboard()
        if cb:
            cb.setText(text)


class SettingsDialog(QDialog):
    def __init__(
        self,
        parent: QWidget,
        pal: Dict[str, str],
        token: str,
        check_on_launch: bool,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setFixedSize(440, 236)
        self.pal = pal
        self.saved_token = token
        self.saved_launch = check_on_launch

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        lbl = QLabel("GitHub personal access token (optional)")
        layout.addWidget(lbl)

        self.token_edit = QLineEdit(token)
        self.token_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.token_edit.setMaxLength(200)
        self.token_edit.setFixedHeight(28)
        layout.addWidget(self.token_edit)

        note = QLabel(
            "Not needed for normal use: releases are read from GitHub's public feed. "
            "A token only helps if the feed is blocked or for stable-only mode. "
            "It is stored in plain text in projects.json and is never written to exported files."
        )
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {pal['sub_fg']}; font-size: 12px;")
        layout.addWidget(note)

        self.launch_cb = QCheckBox("Check for updates when the app starts")
        self.launch_cb.setChecked(check_on_launch)
        layout.addWidget(self.launch_cb)

        layout.addStretch(1)

        btns = QHBoxLayout()
        about_btn = QPushButton("About")
        about_btn.setFixedSize(84, 28)
        about_btn.clicked.connect(self._show_about)
        btns.addWidget(about_btn)

        btns.addStretch(1)

        save_btn = QPushButton("Save")
        save_btn.setFixedSize(84, 28)
        save_btn.setDefault(True)
        save_btn.clicked.connect(self._on_save)
        btns.addWidget(save_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedSize(84, 28)
        cancel_btn.clicked.connect(self.reject)
        btns.addWidget(cancel_btn)
        layout.addLayout(btns)

    def _show_about(self) -> None:
        dlg = AboutDialog(self, self.pal)
        dlg.exec()

    def _on_save(self) -> None:
        self.saved_token = self.token_edit.text().strip()[:200]
        self.saved_launch = self.launch_cb.isChecked()
        self.accept()


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.data_path = data_file_path()
        self.data = load_data(self.data_path)
        theme_pref = self.data["settings"].get("theme", "")
        if theme_pref == "dark":
            self.dark = True
        elif theme_pref == "light":
            self.dark = False
        else:
            self.dark = detect_system_dark()

        self.net = HttpNet()
        self.busy = False
        self.suppress_events = False
        self.col_base = list(COL_BASE)
        self.view_indices: List[int] = []
        self.worker: Optional[QThread] = None

        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.resize(1260, 560)
        self.setMinimumSize(840, 340)

        icon_path = Path(__file__).resolve().parent / "icon.ico"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        central = QWidget(self)
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 8)
        root.setSpacing(6)

        # Row 1: GitHub project entry + Add project
        row1 = QHBoxLayout()
        row1.setSpacing(8)
        self.entry_label = QLabel("GitHub project (URL or owner/repo):")
        row1.addWidget(self.entry_label)

        self.entry_edit = QLineEdit()
        self.entry_edit.setMaxLength(300)
        self.entry_edit.setFixedHeight(28)
        self.entry_edit.setPlaceholderText("owner/repo or https://github.com/owner/repo")
        self.entry_edit.returnPressed.connect(self.add_project)
        row1.addWidget(self.entry_edit, 1)

        self.add_btn = QPushButton("+  Add project")
        self.add_btn.setFixedHeight(28)
        self.add_btn.clicked.connect(self.add_project)
        row1.addWidget(self.add_btn)
        root.addLayout(row1)

        # Row 2: Toolbar buttons
        row2 = QHBoxLayout()
        row2.setSpacing(8)

        self.check_btn = QPushButton("↻  Check for updates")
        self.check_btn.setFixedHeight(30)
        self.check_btn.clicked.connect(self.check_updates)
        row2.addWidget(self.check_btn)

        self.seen_btn = QPushButton("☑  Mark as seen")
        self.seen_btn.setFixedHeight(30)
        self.seen_btn.clicked.connect(self.mark_seen)
        row2.addWidget(self.seen_btn)

        self.open_btn = QPushButton("↗  Open release page")
        self.open_btn.setFixedHeight(30)
        self.open_btn.clicked.connect(self.open_release)
        row2.addWidget(self.open_btn)

        self.remove_btn = QPushButton("🗑  Remove")
        self.remove_btn.setFixedHeight(30)
        self.remove_btn.clicked.connect(self.remove_selected)
        row2.addWidget(self.remove_btn)

        row2.addStretch(1)

        self.import_btn = QPushButton("📥  Import")
        self.import_btn.setFixedHeight(30)
        self.import_btn.clicked.connect(self.import_json)
        row2.addWidget(self.import_btn)

        self.export_btn = QPushButton("📤  Export")
        self.export_btn.setFixedHeight(30)
        self.export_btn.clicked.connect(self.export_json)
        row2.addWidget(self.export_btn)

        self.settings_btn = QPushButton("⚙  Settings")
        self.settings_btn.setFixedHeight(30)
        self.settings_btn.clicked.connect(self.show_settings)
        row2.addWidget(self.settings_btn)
        root.addLayout(row2)

        # Row 3: 8-Column Table (Project, Repository, Source, Target, Current release, Published, Status, Last checked)
        self.table = QTableWidget(0, len(COLS), self)
        self.table.setHorizontalHeaderLabels([title for _, title in COLS])
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(28)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.on_table_context_menu)
        self.table.itemSelectionChanged.connect(self.on_selection_changed)
        self.table.cellDoubleClicked.connect(self.on_cell_double_clicked)
        self.table.itemChanged.connect(self.on_item_changed)

        header = self.table.horizontalHeader()
        header.setSectionsClickable(True)
        header.setHighlightSections(False)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.sectionClicked.connect(self.on_header_clicked)
        header.sectionResized.connect(self.on_section_resized)

        root.addWidget(self.table, 1)

        # Row 4: Status bar + Moon/Sun theme toggle button
        row4 = QHBoxLayout()
        row4.setSpacing(8)
        self.status_lbl = QLabel("Add a project to get started.")
        self.status_lbl.setFixedHeight(26)
        self.status_lbl.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.status_lbl.customContextMenuRequested.connect(self.on_status_context_menu)
        row4.addWidget(self.status_lbl, 1)

        self.theme_btn = QPushButton("☀" if self.dark else "☾")
        self.theme_btn.setFixedSize(28, 28)
        self.theme_btn.setToolTip(
            "Switch to light mode" if self.dark else "Switch to dark mode"
        )
        self.theme_btn.clicked.connect(self.toggle_theme)
        row4.addWidget(self.theme_btn)
        root.addLayout(row4)

        # Keyboard shortcuts (Delete, F2)
        del_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Delete), self.table)
        del_shortcut.activated.connect(self.remove_selected)
        f2_shortcut = QShortcut(QKeySequence(Qt.Key.Key_F2), self.table)
        f2_shortcut.activated.connect(self.rename_selected)

        self.apply_theme()
        self.update_headings()
        self.render_table()
        self.apply_columns()

        if self.data["settings"].get("check_on_launch") and self.data["projects"]:
            self.check_updates()

    # ------------------------------------------------------------------ Theme & Layout
    def pal(self) -> Dict[str, str]:
        return get_palette(self.dark)

    def apply_theme(self) -> None:
        p = self.pal()
        self.theme_btn.setText("☀" if self.dark else "☾")
        self.theme_btn.setToolTip(
            "Switch to light mode" if self.dark else "Switch to dark mode"
        )
        self.setStyleSheet(
            f"""
            QMainWindow, QDialog, QWidget {{
                background-color: {p['bg']};
                color: {p['fg']};
                font-family: "Segoe UI", sans-serif;
                font-size: 13px;
            }}
            QLineEdit {{
                background-color: {p['field']};
                color: {p['fg']};
                border: 1px solid {p['border']};
                border-radius: 4px;
                padding: 2px 8px;
            }}
            QLineEdit:focus {{
                border: 1px solid {p['sel_bg']};
            }}
            QPushButton {{
                background-color: {p['btn_bg']};
                color: {p['fg']};
                border: 1px solid {p['border']};
                border-radius: 4px;
                padding: 2px 12px;
            }}
            QPushButton:pressed {{
                background-color: {p['btn_active']};
            }}
            QPushButton:disabled {{
                color: {p['none_fg']};
            }}
            QTableWidget {{
                background-color: {p['field']};
                color: {p['fg']};
                gridline-color: {p['line']};
                border: 1px solid {p['border']};
                selection-background-color: {p['sel_bg']};
                selection-color: {p['sel_fg']};
            }}
            QHeaderView::section {{
                background-color: {p['head_bg']};
                color: {p['fg']};
                font-weight: bold;
                border: none;
                border-right: 1px solid {p['line']};
                border-bottom: 1px solid {p['line']};
                padding: 4px 6px;
            }}
            QComboBox {{
                background-color: {p['field']};
                color: {p['fg']};
                border: 1px solid {p['border']};
                border-radius: 3px;
                padding: 1px 6px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {p['field']};
                color: {p['fg']};
                selection-background-color: {p['sel_bg']};
                selection-color: {p['sel_fg']};
            }}
            QMenu {{
                background-color: {p['field']};
                color: {p['fg']};
                border: 1px solid {p['border']};
            }}
            QMenu::item:selected {{
                background-color: {p['sel_bg']};
                color: {p['sel_fg']};
            }}
            """
        )
        self.render_table()

    def toggle_theme(self) -> None:
        self.dark = not self.dark
        self.data["settings"]["theme"] = "dark" if self.dark else "light"
        self.persist()
        self.apply_theme()
        self.set_status("Dark mode" if self.dark else "Light mode")

    def resizeEvent(self, event: Any) -> None:
        super().resizeEvent(event)
        self.apply_columns()

    def apply_columns(self) -> None:
        avail = max(700, self.table.viewport().width())
        widths = layout_columns(tuple(self.col_base), COL_MIN, avail)
        self.suppress_events = True
        for i, w in enumerate(widths):
            self.table.setColumnWidth(i, w)
        self.suppress_events = False

    def on_section_resized(self, logical_index: int, _old: int, new_size: int) -> None:
        if self.suppress_events:
            return
        if 0 <= logical_index < len(self.col_base):
            self.col_base[logical_index] = max(COL_MIN[logical_index], new_size)

    # ------------------------------------------------------------------ Table Rendering
    def selected_keys(self) -> List[str]:
        rows = sorted({idx.row() for idx in self.table.selectedIndexes()})
        keys: List[str] = []
        for r in rows:
            if 0 <= r < len(self.view_indices):
                p = self.data["projects"][self.view_indices[r]]
                keys.append(project_key(p))
        return keys

    def update_headings(self) -> None:
        sort_col = self.data["settings"].get("sort_col", "")
        sort_asc = self.data["settings"].get("sort_asc", True)
        labels: List[str] = []
        for cid, title in COLS:
            if cid == sort_col:
                arrow = " ▲" if sort_asc else " ▼"
                labels.append(f"{title}{arrow}")
            else:
                labels.append(title)
        self.table.setHorizontalHeaderLabels(labels)

    def on_header_clicked(self, col_idx: int) -> None:
        cid = COLS[col_idx][0]
        if cid not in SORTABLE:
            return
        if self.data["settings"].get("sort_col") == cid:
            self.data["settings"]["sort_asc"] = not self.data["settings"].get(
                "sort_asc", True
            )
        else:
            self.data["settings"]["sort_col"] = cid
            self.data["settings"]["sort_asc"] = cid != "published"
        self.persist()
        self.update_headings()
        self.render_table()

    def render_table(self) -> None:
        keep = set(self.selected_keys())
        self.suppress_events = True
        self.view_indices = sort_order(
            self.data["projects"],
            self.data["settings"].get("sort_col", ""),
            self.data["settings"].get("sort_asc", True),
        )
        p = self.pal()
        self.table.setRowCount(len(self.view_indices))

        for row, ix in enumerate(self.view_indices):
            proj = self.data["projects"][ix]
            pkey = project_key(proj)

            bg_color = QColor(p["field"])
            fg_color = QColor(p["fg"])
            if proj.get("error"):
                fg_color = QColor(p["error_fg"])
            elif has_update(proj):
                bg_color = QColor(p["update_bg"])
                fg_color = QColor(p["update_fg"])
            elif not proj.get("latest"):
                fg_color = QColor(p["none_fg"])

            texts = [
                display_name(proj),
                f"{proj['owner']}/{proj['repo']}",
                proj.get("source", "PC"),
                proj.get("target", "PC"),
                release_label(proj),
                published_label(proj),
                status_text(proj),
                checked_label(proj),
            ]

            for col, text in enumerate(texts):
                if col in (2, 3):
                    field_name = "source" if col == 2 else "target"
                    combo = QComboBox(self.table)
                    combo.addItems(list(PLATFORMS))
                    curr_val = normalize_platform(proj.get(field_name))
                    combo.setCurrentText(curr_val)
                    combo.currentTextChanged.connect(
                        lambda val, k=pkey, f=field_name: self.on_platform_changed(
                            k, f, val
                        )
                    )
                    self.table.setCellWidget(row, col, combo)
                else:
                    item = QTableWidgetItem(text)
                    item.setBackground(bg_color)
                    item.setForeground(fg_color)
                    if col == 0:
                        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
                    else:
                        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    self.table.setItem(row, col, item)

            if pkey in keep:
                self.table.selectRow(row)

        self.suppress_events = False

    def on_platform_changed(self, pkey: str, field: str, value: str) -> None:
        if self.suppress_events:
            return
        norm = normalize_platform(value)
        for proj in self.data["projects"]:
            if project_key(proj) == pkey:
                if proj.get(field) != norm:
                    proj[field] = norm
                    self.persist()
                    label = "Source" if field == "source" else "Target"
                    self.set_status(f"{label} set to {norm}.")
                break

    # ------------------------------------------------------------------ Actions
    def set_status(self, text: str) -> None:
        self.status_lbl.setText(text)

    def persist(self) -> None:
        try:
            write_atomic(self.data_path, data_to_json(self.data))
        except Exception as e:
            QMessageBox.critical(self, APP_NAME, f"Could not save projects.json:\n{e}")

    def set_busy(self, busy: bool, status: Optional[str] = None) -> None:
        self.busy = busy
        self.add_btn.setEnabled(not busy)
        self.check_btn.setEnabled(not busy)
        if status:
            self.set_status(status)

    def on_selection_changed(self) -> None:
        if self.suppress_events:
            return
        keys = self.selected_keys()
        if len(keys) == 1:
            for p in self.data["projects"]:
                if project_key(p) == keys[0]:
                    if p.get("error"):
                        self.set_status(str(p["error"]))
                    elif not p.get("description"):
                        self.set_status(NO_DESCRIPTION)
                    else:
                        self.set_status(str(p["description"]))
                    break

    def add_project(self) -> None:
        if self.busy:
            return
        parsed = parse_repo(self.entry_edit.text())
        if not parsed:
            QMessageBox.critical(
                self,
                APP_NAME,
                "Enter a GitHub URL such as\nhttps://github.com/owner/repo\nor just owner/repo.",
            )
            return
        owner, repo = parsed
        key = f"{owner}/{repo}".lower()
        if any(project_key(p) == key for p in self.data["projects"]):
            QMessageBox.information(
                self, APP_NAME, f"{owner}/{repo} is already in the list."
            )
            return

        token = self.data["settings"].get("token", "").strip()
        self.set_busy(True, f"Adding {owner}/{repo} ...")
        worker = AddProjectWorker(self.net, owner, repo, token)
        worker.finished_add.connect(self._on_project_added)
        self.worker = worker
        worker.start()

    def _on_project_added(self, res: Any, err: Optional[str]) -> None:
        self.set_busy(False)
        if err is not None or res is None:
            self.set_status("Could not add project.")
            QMessageBox.critical(self, APP_NAME, str(err))
            return
        info, latest = res
        p: Dict[str, Any] = {
            "owner": info["owner"],
            "repo": info["repo"],
            "title": info["title"],
            "description": info["description"],
            "html_url": info["html_url"],
            "include_prereleases": True,
            "fmt": 2,
            "latest": latest,
            "seen_id": latest["id"] if isinstance(latest, dict) else None,
            "seen_tag": latest["tag"] if isinstance(latest, dict) else None,
            "last_checked": now_iso(),
            "error": None,
            "source": default_platform(),
            "target": default_platform(),
        }
        norm = normalize_project(p)
        if norm:
            p = norm
        if any(project_key(x) == project_key(p) for x in self.data["projects"]):
            self.set_status("Already in the list.")
            return

        self.data["projects"].append(p)
        self.persist()
        self.entry_edit.clear()
        self.render_table()
        if isinstance(latest, dict):
            rel_name = latest.get("tag") or latest.get("name")
            self.set_status(f"Added {p['title']} - current release {rel_name}.")
        else:
            self.set_status(f"Added {p['title']} - it has no published releases yet.")

    def check_updates(self) -> None:
        if self.busy:
            return
        snapshot = [
            (p["owner"], p["repo"], bool(p.get("include_prereleases", True)))
            for p in self.data["projects"]
        ]
        if not snapshot:
            self.set_status("Nothing to check - add a project first.")
            return
        token = self.data["settings"].get("token", "").strip()
        self.set_busy(True, f"Checking {len(snapshot)} project(s) ...")
        worker = CheckUpdatesWorker(self.net, snapshot, token)
        worker.finished_check.connect(self._on_updates_checked)
        self.worker = worker
        worker.start()

    def _on_updates_checked(
        self,
        results: List[Tuple[str, Optional[Dict[str, Any]], Optional[str]]],
        rate: Optional[int],
    ) -> None:
        self.set_busy(False)
        now = now_iso()
        errors = 0
        for key, latest, err in results:
            for p in self.data["projects"]:
                if project_key(p) == key:
                    if err:
                        errors += 1
                    apply_result(p, latest, err, now)
                    break
        self.persist()
        self.render_table()
        updates = sum(1 for p in self.data["projects"] if has_update(p))
        msg = f"Checked {len(results)} project(s): {updates} update(s) available"
        if errors > 0:
            msg += f", {errors} error(s)"
        if rate is not None:
            msg += f". API calls left this hour: {rate}"
        self.set_status(msg + ".")

    def mark_seen(self) -> None:
        keys = set(self.selected_keys())
        if not keys:
            self.set_status("Select one or more projects first.")
            return
        count = 0
        for p in self.data["projects"]:
            if project_key(p) in keys and has_update(p):
                latest = p.get("latest")
                if isinstance(latest, dict):
                    p["seen_id"] = latest.get("id")
                    p["seen_tag"] = latest.get("tag")
                    count += 1
        self.persist()
        self.render_table()
        self.set_status(
            f"Marked {count} project(s) as seen."
            if count > 0
            else "No updates to mark in the selection."
        )

    def first_selected(self) -> Optional[Dict[str, Any]]:
        keys = self.selected_keys()
        if not keys:
            return None
        for p in self.data["projects"]:
            if project_key(p) == keys[0]:
                return p
        return None

    def open_release(self) -> None:
        p = self.first_selected()
        if not p:
            self.set_status("Select a project first.")
            return
        fallback = f"https://github.com/{p['owner']}/{p['repo']}/releases"
        latest = p.get("latest")
        url = safe_github_url(
            latest.get("url") if isinstance(latest, dict) else None, fallback
        )
        QDesktopServices.openUrl(QUrl(url))

    def open_repo(self) -> None:
        p = self.first_selected()
        if not p:
            return
        url = safe_github_url(
            p.get("html_url"), f"https://github.com/{p['owner']}/{p['repo']}"
        )
        QDesktopServices.openUrl(QUrl(url))

    def toggle_prerelease(self) -> None:
        keys = set(self.selected_keys())
        if not keys:
            return
        first = self.first_selected()
        new_val = not bool(first.get("include_prereleases", True)) if first else True
        for p in self.data["projects"]:
            if project_key(p) in keys:
                p["include_prereleases"] = new_val
        self.persist()
        self.set_status(
            'Pre-releases included (uses the free release feed). Click "Check for updates" to apply.'
            if new_val
            else 'Stable-only mode uses the GitHub API, which is rate-limited without a token. Click "Check for updates" to apply.'
        )

    def remove_selected(self) -> None:
        keys = self.selected_keys()
        if not keys:
            self.set_status("Select a project first.")
            return
        names_list = [
            display_name(p) for p in self.data["projects"] if project_key(p) in keys
        ]
        names = ", ".join(names_list[:3]) + ("..." if len(names_list) > 3 else "")
        ans = QMessageBox.question(
            self,
            APP_NAME,
            f"Remove {len(keys)} project(s)?\n{names}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ans != QMessageBox.StandardButton.Yes:
            return
        key_set = set(keys)
        self.data["projects"] = [
            p for p in self.data["projects"] if project_key(p) not in key_set
        ]
        self.persist()
        self.render_table()
        self.set_status(f"Removed {len(keys)} project(s).")

    def rename_selected(self) -> None:
        rows = sorted({idx.row() for idx in self.table.selectedIndexes()})
        if len(rows) != 1:
            self.set_status("Select one project to rename.")
            return
        item = self.table.item(rows[0], 0)
        if item:
            self.table.editItem(item)

    def on_item_changed(self, item: QTableWidgetItem) -> None:
        if self.suppress_events or item.column() != 0:
            return
        row = item.row()
        if 0 <= row < len(self.view_indices):
            proj = self.data["projects"][self.view_indices[row]]
            msg = apply_rename(proj, item.text())
            self.persist()
            self.render_table()
            if msg:
                self.set_status(msg)

    def reset_names(self) -> None:
        keys = set(self.selected_keys())
        count = 0
        for p in self.data["projects"]:
            if project_key(p) in keys and "custom_name" in p:
                p.pop("custom_name", None)
                count += 1
        if count == 0:
            self.set_status("Nothing to reset: the selection has no custom name.")
            return
        self.persist()
        self.render_table()
        self.set_status(f"Reset {count} name(s) to the GitHub name.")

    def on_cell_double_clicked(self, row: int, col: int) -> None:
        if col == 0:
            item = self.table.item(row, 0)
            if item:
                self.table.editItem(item)
        elif col not in (2, 3):
            self.open_release()

    def on_table_context_menu(self, pos: Any) -> None:
        if not self.selected_keys():
            return
        menu = QMenu(self)
        act_open = QAction("Open release page", self)
        act_open.triggered.connect(self.open_release)
        menu.addAction(act_open)

        act_repo = QAction("Open repository", self)
        act_repo.triggered.connect(self.open_repo)
        menu.addAction(act_repo)

        act_seen = QAction("Mark as seen", self)
        act_seen.triggered.connect(self.mark_seen)
        menu.addAction(act_seen)

        menu.addSeparator()

        act_rename = QAction("Rename...\tF2", self)
        act_rename.setEnabled(len(self.selected_keys()) == 1)
        act_rename.triggered.connect(self.rename_selected)
        menu.addAction(act_rename)

        has_custom = any(
            "custom_name" in p
            for p in self.data["projects"]
            if project_key(p) in set(self.selected_keys())
        )
        act_reset = QAction("Reset name", self)
        act_reset.setEnabled(has_custom)
        act_reset.triggered.connect(self.reset_names)
        menu.addAction(act_reset)

        first = self.first_selected()
        act_pre = QAction("Include pre-releases", self)
        act_pre.setCheckable(True)
        act_pre.setChecked(bool(first.get("include_prereleases", True)) if first else True)
        act_pre.triggered.connect(self.toggle_prerelease)
        menu.addAction(act_pre)

        menu.addSeparator()

        act_rem = QAction("Remove", self)
        act_rem.triggered.connect(self.remove_selected)
        menu.addAction(act_rem)

        menu.exec(self.table.viewport().mapToGlobal(pos))

    def on_status_context_menu(self, pos: Any) -> None:
        menu = QMenu(self)
        act_copy = QAction("Copy", self)
        act_copy.triggered.connect(
            lambda: QApplication.clipboard().setText(self.status_lbl.text())
        )
        menu.addAction(act_copy)
        menu.exec(self.status_lbl.mapToGlobal(pos))

    def import_json(self) -> None:
        path_str, _ = QFileDialog.getOpenFileName(
            self, "Import projects (.json)", "", "JSON files (*.json);;All files (*.*)"
        )
        if not path_str:
            return
        p = Path(path_str)
        try:
            if p.stat().st_size > MAX_IMPORT_BYTES:
                QMessageBox.critical(
                    self,
                    APP_NAME,
                    "Could not read that file as JSON:\nThe file is larger than 5 MB.",
                )
                return
            raw = json.loads(p.read_text(encoding="utf-8").lstrip("\ufeff"))
        except Exception as e:
            QMessageBox.critical(
                self, APP_NAME, f"Could not read that file as JSON:\n{e}"
            )
            return

        parsed = parse_import(raw)
        if parsed is None:
            QMessageBox.critical(self, APP_NAME, "This file has no project list.")
            return
        projects, skipped = parsed
        if not projects:
            QMessageBox.critical(
                self, APP_NAME, "No valid projects found in this file."
            )
            return

        note = (
            f" ({skipped} entries skipped as invalid or duplicate)"
            if skipped > 0
            else ""
        )
        ans = QMessageBox.question(
            self,
            APP_NAME,
            f"Found {len(projects)} project(s){note}.\n\n"
            "Yes = Merge: keep your current list and add the new ones\n"
            "No = Replace: discard your current list and use this file\n"
            "Cancel = do nothing",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No
            | QMessageBox.StandardButton.Cancel,
        )
        if ans == QMessageBox.StandardButton.Yes:
            total = len(projects)
            added = merge_projects(self.data["projects"], projects)
            msg = f"Imported: {added} new project(s) added, {total - added} already in the list."
        elif ans == QMessageBox.StandardButton.No:
            self.data["projects"] = projects
            msg = f"Imported: list replaced with {len(projects)} project(s)."
        else:
            return

        self.persist()
        self.render_table()
        self.set_status(f'{msg} Click "Check for updates" to refresh them.')

    def export_json(self) -> None:
        if not self.data["projects"]:
            QMessageBox.information(
                self, APP_NAME, "There are no projects to export yet."
            )
            return
        default_name = f"github_release_tracker_{today_ymd()}.json"
        path_str, _ = QFileDialog.getSaveFileName(
            self,
            "Export projects (.json)",
            default_name,
            "JSON files (*.json);;All files (*.*)",
        )
        if not path_str:
            return
        payload = build_export(self.data["projects"], now_iso())
        try:
            write_atomic(Path(path_str), json.dumps(payload, indent=2, ensure_ascii=False))
            self.set_status(
                f"Exported {len(self.data['projects'])} project(s) to {path_str} (token not included)."
            )
        except Exception as e:
            QMessageBox.critical(self, APP_NAME, f"Could not write the file:\n{e}")

    def show_settings(self) -> None:
        dlg = SettingsDialog(
            self,
            self.pal(),
            self.data["settings"].get("token", ""),
            bool(self.data["settings"].get("check_on_launch", False)),
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.data["settings"]["token"] = dlg.saved_token
            self.data["settings"]["check_on_launch"] = dlg.saved_launch
            self.persist()
            self.set_status("Settings saved.")


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
