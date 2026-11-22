# GitHub Release Tracker (Rust edition)

A small, portable Windows app that tracks the latest release of the GitHub projects you care about and tells you when a new one appears. No account, no login, and no token needed.

> **Rewrite notice:** this project is a complete rewrite, in Rust with a native Win32 interface, of the earlier Python / tkinter app **[github-release-tracker](https://github.com/santosasarno-code/github-release-tracker)**. It has the same features and uses the same `projects.json`, plus configurable **Source** and **Target** platform columns (`PC`, `Android`, `Switch`, `Switch 2`, `PS5`, `PS4`, `PS3`).

It ships as one small `.exe` with nothing to install.

## Features

- Add a project by pasting a GitHub URL or `owner/repo`
- See the project name, repository, **Source** platform, **Target** platform, current release, publish date, status, and last checked timestamp at a glance
- **Configurable Source & Target columns**: Configure both **Source** and **Target** for every tracked project via an inline drop-down box with options:
  - `PC`
  - `Android`
  - `Switch`
  - `Switch 2`
  - `PS5`
  - `PS4`
  - `PS3`
- **Check for updates** refreshes every project; a newer release is highlighted as `Update available: v1.0 -> v1.1`
- **Mark as seen** clears the highlight once you have dealt with an update
- Double-click a project row (or use **Open release page**) to open its release page in your browser; double-clicking the **Project** name renames it instead
- **Rename** a project: click the pencil that appears when you hover it, or select it and press **F2**, or right-click > Rename, or double-click the name. *Reset name* brings the GitHub name back
- Click the **Project**, **Repository**, **Source**, **Target**, **Published** or **Status** header to sort (click again to reverse)
- **Import / Export** the list as `.json` (merge or replace on import; preserves `source` and `target` platform selections; the token is never exported)
- **Light / dark** mode: click the moon / sun icon at the bottom right (starts with your Windows theme)
- Columns resize in proportion when you resize the window; drag a column border to change the proportions
- Per-monitor DPI aware; thin separator lines between rows and columns
- Portable: one `.exe`, no installer, no registry entries. Data is `projects.json` next to the exe (falls back to `%APPDATA%\GitHubReleaseTracker` if that folder is read-only)

The app only reads release information. It never downloads or installs anything.

## What you need

| I want to... | You need |
|---|---|
| **Just use the app** | Windows 10 or 11 and an internet connection. Nothing else. |
| **Build the `.exe` myself** (`build.bat` or `build-exe.ps1`) | [Rust](https://rustup.rs) (default "MSVC" option) and **Build Tools for Visual Studio** with the workload *Desktop development with C++* (it includes the Windows SDK). Internet for the first build (downloads a few crates). |

## Build it

1. Install the two things above, then open a **new** window.
2. Double-click `build.bat` (or run `powershell -NoProfile -ExecutionPolicy Bypass -File build-exe.ps1`).
3. The result is in `dist\`:
   - `GitHubReleaseTracker.exe`
   - `GitHubReleaseTracker.exe.sha256`
   - `release-notes-vX.Y.Z.md` (paste into the GitHub release)

See [RELEASING.md](RELEASING.md) for the release steps, including the GitHub Actions option.

By hand: `cargo test --lib` runs the logic tests, `cargo build --release` builds `target\release\github-release-tracker.exe`.

## Settings and data

- `projects.json` stores your tracked projects, including `"source"` and `"target"` platform selections (`"PC"`, `"Android"`, `"Switch"`, `"Switch 2"`, `"PS5"`, `"PS4"`, `"PS3"`).
- The optional GitHub token (Settings) is stored in plain text in `projects.json` and never exported. Normal use does not need it: releases are read from GitHub's public feed.

## Project layout

| Path | What it is |
|---|---|
| `src/lib.rs` | All logic without Windows code: parsing, release lookup, update detection, `Source`/`Target` platform validation, import/export, sorting. Unit-tested (`src/tests.rs`) |
| `src/ui.rs`, `src/dialogs.rs` | The Win32 windows, 8-column `SysListView32` with inline `COMBOBOX` dropdowns for `Source` and `Target` |
| `src/http.rs` | HTTPS with WinHTTP |
| `app.rc`, `app.manifest`, `icon.ico`, `build.rs` | Icon, version info, DPI and modern-controls manifest |
| `build.bat`, `build-exe.ps1`, `tools/release-notes.ps1` | Local build and release notes |
| `.github/workflows/build.yml` | Manual cloud build |

## License

MIT. See [LICENSE](LICENSE).
