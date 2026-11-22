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

## Build the `.exe` (EXE Builder)

### Option A: One-Click Local Build (`build.bat`)

1. Download and extract the project archive (via **Build .exe > Download Ready-to-Build Project (.zip)** in the toolbar, or clone the repository).
2. Install [Rust (`rustup-init.exe`)](https://rustup.rs) and **Build Tools for Visual Studio** (*Desktop development with C++* workload), then open a **new** terminal/Explorer window.
3. Double-click `build.bat` (or run `powershell -ExecutionPolicy Bypass -File build-exe.ps1`).
4. The compiled executable and artifacts are written to `dist\`:
   - `dist\GitHubReleaseTracker.exe` (statically linked CRT via `.cargo/config.toml`)
   - `dist\GitHubReleaseTracker.exe.sha256`
   - `dist\release-notes-v2.0.0.md`

### Option B: Automated PowerShell EXE Builder (`build-exe.ps1`)

Run `build-exe.ps1` in PowerShell:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\build-exe.ps1
```

If Rust (`cargo`) is not yet installed, passing `-InstallRust` will automatically download and install `rustup-init.exe` for `x86_64-pc-windows-msvc` before running the unit tests and building `dist\GitHubReleaseTracker.exe`:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\build-exe.ps1 -InstallRust
```

### Option C: GitHub Actions Cloud Builder (No Local Tools Needed)

1. Push the project files to a GitHub repository.
2. Open the **Actions** tab on GitHub -> select **Build Windows exe** -> click **Run workflow**.
3. Download the compiled `GitHubReleaseTracker-windows` artifact containing `GitHubReleaseTracker.exe` and its `.sha256` checksum.

### Manual Cargo Commands

- Run logic unit tests (including `Source` and `Target` column tests):
  ```bash
  cargo test --lib --locked
  ```
- Build release executable:
  ```bash
  cargo build --release --locked
  ```
  Output binary: `target\release\github-release-tracker.exe`

## Settings and data

- `projects.json` stores your tracked projects, including `"source"` and `"target"` platform selections (`"PC"`, `"Android"`, `"Switch"`, `"Switch 2"`, `"PS5"`, `"PS4"`, `"PS3"`).
- Backward-compatible with existing `projects.json` files (projects without `"source"` or `"target"` default to `"PC"`).
- The optional GitHub token (Settings) is stored in plain text in `projects.json` and never exported. Normal use does not need it: releases are read from GitHub's public feed.

## Project layout

| Path | What it is |
|---|---|
| `src/lib.rs` | All logic without Windows code: parsing, release lookup, update detection, `Source`/`Target` platform validation, import/export, sorting. Unit-tested (`src/tests.rs`) |
| `src/ui.rs`, `src/dialogs.rs` | The Win32 windows, 8-column `SysListView32` with inline `COMBOBOX` dropdowns for `Source` and `Target` |
| `src/http.rs` | HTTPS with WinHTTP |
| `app.rc`, `app.manifest`, `icon.ico`, `build.rs` | Icon, version info, DPI and modern-controls manifest |
| `build.bat`, `build-exe.ps1`, `tools/release-notes.ps1` | Local `.exe` builders and release notes generator |
| `.github/workflows/build.yml` | Manual cloud `.exe` build via GitHub Actions |

## License

MIT. See [LICENSE](rust-project/LICENSE).
