# GitHub Release Tracker (Python / PyQt6 edition)

A small, portable Windows app written in **Python 3** and **PyQt6** that tracks the latest release of the GitHub projects you care about and tells you when a new one appears. No account, no login, and no token needed.

> **PyQt6 edition:** Based on **[github-release-tracker-rs](https://github.com/santosasarno-code/github-release-tracker-rs)**, ported to **Python + PyQt6** with full `projects.json` compatibility and configurable **Source** and **Target** platform columns (`PC`, `Android`, `Switch`, `Switch 2`, `PS5`, `PS4`, `PS3`) via drop-down box.

It can be run directly with Python (`python github_release_tracker.py`) or compiled into a single standalone `.exe` (`dist\GitHubReleaseTracker.exe`) using the included **PyInstaller EXE Builder** (`build.bat` / `build-exe.ps1`).

## Features

- Add a project by pasting a GitHub URL or `owner/repo`
- See the project name, repository, **Source** platform, **Target** platform, current release, publish date, status, and last checked timestamp at a glance
- **Configurable Source & Target columns**: Configure both **Source** and **Target** for every tracked project via an inline `QComboBox` drop-down box with options:
  - `PC`
  - `Android`
  - `Switch`
  - `Switch 2`
  - `PS5`
  - `PS4`
  - `PS3`
- **Check for updates** refreshes every project on a background `QThread`; a newer release is highlighted as `Update available: v1.0 -> v1.1`
- **Mark as seen** clears the highlight once you have dealt with an update
- Double-click a project row (or use **Open release page**) to open its release page in your browser; double-clicking the **Project** name renames it instead
- **Rename** a project: select it and press **F2**, right-click > Rename, or double-click the name. *Reset name* brings the GitHub name back
- Click the **Project**, **Repository**, **Source**, **Target**, **Published** or **Status** header to sort (click again to reverse)
- **Import / Export** the list as `.json` (merge or replace on import; preserves `source` and `target` platform selections; the token is never exported)
- **Light / dark** mode: click the moon / sun icon at the bottom right (starts with your Windows theme)
- Columns resize in proportion when you resize the window; drag a column border to change the proportions
- Portable: data is stored in `projects.json` next to the script/exe (falls back to `%APPDATA%\GitHubReleaseTracker` if that folder is read-only)

The app only reads release information. It never downloads or installs anything.

## What you need

| I want to... | You need |
|---|---|
| **Run the compiled `.exe`** | Windows 10 or 11 and an internet connection. Nothing else. |
| **Run from source or build the `.exe` (`build.bat`)** | [Python 3.10+](https://www.python.org/downloads/) (with `"Add python.exe to PATH"` checked). `build.bat` automatically creates a `.venv` and installs `PyQt6` and `pyinstaller`. |

## Run from Python Source

```bash
pip install -r requirements.txt
python github_release_tracker.py
```

## Build the `.exe` (PyInstaller EXE Builder)

1. Double-click `build.bat` (or run `powershell -NoProfile -ExecutionPolicy Bypass -File build-exe.ps1`).
2. The result is in `dist\`:
   - `GitHubReleaseTracker.exe`
   - `GitHubReleaseTracker.exe.sha256`
   - `release-notes-v2.0.0.md`

## Project layout

| Path | What it is |
|---|---|
| `tracker_core.py` | Pure Python core logic: repo parsing, Atom feed & REST API release lookup, update detection, `Source`/`Target` platform validation, import/export, sorting |
| `github_release_tracker.py` | PyQt6 GUI (`QMainWindow`, 8-column `QTableWidget` with `QComboBox` dropdowns for `Source` and `Target`, `QThread` workers, Settings & About `QDialog`s, dark/light stylesheet) |
| `test_tracker.py` | Unit tests for `tracker_core.py` (`python -m unittest test_tracker.py -v`) |
| `requirements.txt` | Python dependencies (`PyQt6>=6.6.0`, `pyinstaller>=6.0.0`) |
| `build.bat`, `build-exe.ps1`, `tools/release-notes.ps1` | One-click PyInstaller `.exe` builders and SHA-256 release notes generator |
| `.github/workflows/build.yml` | Manual cloud `.exe` build via GitHub Actions |

## License

MIT. See [LICENSE](LICENSE).
