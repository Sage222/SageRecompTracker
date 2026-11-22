# GitHub Release Tracker (Portable Single-File Python / PyQt6 Edition)

A small, portable desktop app contained in a **single Python file (`github_release_tracker.py`)** using **Python 3** and **PyQt6** that tracks the latest release of the GitHub projects you care about and tells you when a new one appears. No account, no login, and no token needed.

> **Portable Single-File PyQt6 Edition:** Based on **[github-release-tracker-rs](https://github.com/santosasarno-code/github-release-tracker-rs)**, ported to a single self-contained **Python + PyQt6** file (`github_release_tracker.py`) with full `projects.json` compatibility, a free-text **Title** column at the very left, a free-text **Comment** column at the far right, configurable **Source** and **Target** platform columns via drop-down box, multi-site release tracking (GitHub, Forgejo/Gitea, and download pages), and row removal with confirmation.

## Portable Single-File Design

- **Single `.py` File**: All core logic (GitHub, Forgejo/Gitea, and download page release & feed parsers, `Source` & `Target` platform validation, atomic JSON persistence, sorting), the full **PyQt6 GUI**, an automatic `icon.ico` generator, a built-in PyInstaller `.exe` builder (`--build-exe`), and an 11-test `unittest` suite (`--test`) live inside one standalone file: **`github_release_tracker.py`**.
- **Self-Contained Directory Storage**: You can drop `github_release_tracker.py` into any folder on your computer or USB drive and run it. It automatically creates and updates its runtime files (`projects.json`, atomic `projects.json.tmp`, `projects.json.bak`, and `icon.ico`) right next to `github_release_tracker.py` in its own directory (falling back to `%APPDATA%\GitHubReleaseTracker` only if the folder is read-only).

## Features

- **Multi-Site Release Tracking**: Add a project by pasting:
  - A GitHub URL or `owner/repo` (e.g. `https://github.com/Ryubing/Ryujinx` or `Ryubing/Ryujinx`)
  - A Forgejo / Gitea / Codeberg repository URL (e.g. `https://git.magicbean.dev/MagicBeanDev/Longshot`)
  - A project downloads page URL (e.g. `https://eden-emu.dev/downloads/`)
- **10-Column Overview**: See the free-text **Title** (very left, Column 0), **Project** name, **Repository**, **Source** platform, **Target** platform, **Current release**, **Published** date, **Status**, **Last checked** timestamp, and free-text **Comment** (far right, Column 9) at a glance
- **Free-text `Title` column at the very left (Column 0)**: Type a custom free-text title directly in the leftmost column of any project row; titles are saved automatically to `projects.json` and can be sorted by clicking the **Title** header
- **Configurable Source & Target columns**: Configure both **Source** and **Target** for every tracked project via an inline `QComboBox` drop-down box:
  - **Source options**: `PC`, `Android`, `Switch`, `Switch 2`, `PS5`, `PS4`, `PS3`, `Xbox`, `Wii`, `Wii U`
  - **Target options**: `PC`, `Android`, `Switch`, `Switch 2`, `PS5`, `PS4`, `PS3`
- **Free-text `Comment` column at the far right (Column 9)**: Type free-text notes or comments directly in the rightmost column of any project row; comments are saved automatically to `projects.json` and can be sorted by clicking the **Comment** header
- **Remove rows with confirmation**: Remove any tracked project row via the toolbar **Remove** button, right-click context menu > **Remove**, or the **Delete** key—always protected by a confirmation dialog (`Remove 'name' (repo) from the list?`) before deletion
- **Column widths saved on exit**: Dragging any column border saves your custom pixel column widths into `settings.col_widths` in `projects.json` both immediately on resize and on exit (`closeEvent` + `aboutToQuit`), and restores them on launch without overwriting them on window resize
- **Check for updates** refreshes every project on a background `QThread`; a newer release is highlighted as `Update available: v1.0 -> v1.1`
- **Mark as seen** clears the highlight once you have dealt with an update
- Double-click a project row (or use **Open release page**) to open its release page in your browser; double-clicking the **Project** name renames it instead
- **Rename** a project: select it and press **F2**, right-click > Rename, or double-click the name. *Reset name* brings the repository name back
- Click the **Title**, **Project**, **Repository**, **Source**, **Target**, **Published**, **Status** or **Comment** header to sort (click again to reverse)
- **Import / Export** the list as `.json` (merge or replace on import; preserves `user_title`, `comment`, `source`, and `target` selections; the token is never exported)
- **Light / dark** mode: click the moon / sun icon at the bottom right (starts with your Windows theme)

## Run the Portable Single `.py` File Directly

Place `github_release_tracker.py` in any folder of its own and run:

```bash
pip install PyQt6
python github_release_tracker.py
```

### Built-in CLI Commands in `github_release_tracker.py`

| Command | Description |
|---|---|
| `python github_release_tracker.py` | Launch the PyQt6 desktop GUI (creates `projects.json` & `icon.ico` next to `github_release_tracker.py`) |
| `python github_release_tracker.py --test` | Run the built-in 11-test `unittest` suite |
| `python github_release_tracker.py --build-exe` | Build a standalone `dist/GitHubReleaseTracker.exe` next to `github_release_tracker.py` using PyInstaller |

## Build a Standalone `.exe` (PyInstaller EXE Builder)

### Option A: Built-in `--build-exe` Flag (Single `.py` File Only)

```bash
pip install PyQt6 pyinstaller
python github_release_tracker.py --build-exe
```

### Option B: One-Click `build.bat` / `build-exe.ps1`

1. Double-click `build.bat` (or run `powershell -ExecutionPolicy Bypass -File build-exe.ps1`).
2. `build.bat` automatically:
   - Creates a local `.venv` virtual environment and installs `PyQt6` + `pyinstaller`
   - Runs `python github_release_tracker.py --test`
   - Runs PyInstaller to produce:
     - `dist\GitHubReleaseTracker.exe`
     - `dist\GitHubReleaseTracker.exe.sha256`
     - `dist\release-notes-v2.0.0.md`

## Project Layout

| Path | What it is |
|---|---|
| `github_release_tracker.py` | **Complete portable single-file application**: PyQt6 GUI, GitHub Atom feed & REST API logic, `Source`/`Target` platform validation, portable `projects.json` & `icon.ico` creation in its own directory, built-in unit tests (`--test`), and built-in PyInstaller builder (`--build-exe`) |
| `requirements.txt` | Optional pip requirements file (`PyQt6>=6.6.0`, `pyinstaller>=6.0.0`) |
| `build.bat`, `build-exe.ps1`, `tools/release-notes.ps1` | Optional 1-click Windows `.exe` builder scripts and SHA-256 release notes generator |
| `.github/workflows/build.yml` | Optional manual cloud `.exe` build via GitHub Actions |

## License

MIT. See [LICENSE](LICENSE).
