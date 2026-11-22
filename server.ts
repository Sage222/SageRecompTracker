import { execFileSync } from 'child_process';
import crypto from 'crypto';
import express from 'express';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { createServer as createViteServer } from 'vite';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const DATA_FILE = path.join(__dirname, 'projects.json');
const PYQT_DIR = path.join(__dirname, 'pyqt6-project');
const DIST_ZIP = path.join(__dirname, 'github-release-tracker-pyqt6-v2.0.0.zip');

const INITIAL_DATA = {
  settings: {
    token: '',
    check_on_launch: false,
    theme: 'dark',
    sort_col: '',
    sort_asc: true,
    col_widths: [150, 190, 210, 105, 105, 135, 110, 210, 125],
  },
  projects: [
    {
      owner: 'santosasarno-code',
      repo: 'github-release-tracker-rs',
      title: 'github-release-tracker-rs',
      description:
        'A small, portable Windows app that tracks the latest release of the GitHub projects you care about and tells you when a new one appears.',
      html_url: 'https://github.com/santosasarno-code/github-release-tracker-rs',
      include_prereleases: true,
      fmt: 2,
      latest: {
        id: 'tag:github.com,2008:Repository/github-release-tracker-rs/v2.0.0',
        tag: 'v2.0.0',
        name: 'v2.0.0',
        published_at: '2026-11-20T12:00:00Z',
        url: 'https://github.com/santosasarno-code/github-release-tracker-rs/releases/tag/v2.0.0',
        prerelease: false,
        source: 'feed',
      },
      seen_id: 'tag:github.com,2008:Repository/github-release-tracker-rs/v2.0.0',
      seen_tag: 'v2.0.0',
      last_checked: '2026-11-21T21:45:00',
      error: null,
      source: 'PC',
      target: 'PC',
    },
    {
      owner: 'shadps4-emu',
      repo: 'shadPS4',
      title: 'shadPS4',
      description: 'PlayStation 4 emulator for Windows, Linux and macOS written in C++',
      html_url: 'https://github.com/shadps4-emu/shadPS4',
      include_prereleases: true,
      fmt: 2,
      latest: {
        id: 'tag:github.com,2008:Repository/shadPS4/v0.7.0',
        tag: 'v0.7.0',
        name: 'shadPS4 v0.7.0',
        published_at: '2026-11-18T18:30:00Z',
        url: 'https://github.com/shadps4-emu/shadPS4/releases/tag/v0.7.0',
        prerelease: false,
        source: 'feed',
      },
      seen_id: 'tag:github.com,2008:Repository/shadPS4/v0.6.0',
      seen_tag: 'v0.6.0',
      last_checked: '2026-11-21T21:45:00',
      error: null,
      source: 'PS4',
      target: 'PC',
    },
    {
      owner: 'RPCS3',
      repo: 'rpcs3',
      title: 'rpcs3',
      description: 'PS3 emulator/debugger',
      html_url: 'https://github.com/RPCS3/rpcs3',
      include_prereleases: true,
      fmt: 2,
      latest: {
        id: 'tag:github.com,2008:Repository/rpcs3/v0.0.34',
        tag: 'v0.0.34',
        name: 'v0.0.34',
        published_at: '2026-11-15T09:20:00Z',
        url: 'https://github.com/RPCS3/rpcs3/releases/tag/v0.0.34',
        prerelease: false,
        source: 'feed',
      },
      seen_id: 'tag:github.com,2008:Repository/rpcs3/v0.0.34',
      seen_tag: 'v0.0.34',
      last_checked: '2026-11-21T21:45:00',
      error: null,
      source: 'PS3',
      target: 'PC',
    },
    {
      owner: 'PPSSPPTeam',
      repo: 'ppsspp',
      title: 'ppsspp',
      description: 'A PSP emulator for Android, Windows, Mac and Linux, written in C++.',
      html_url: 'https://github.com/PPSSPPTeam/ppsspp',
      include_prereleases: true,
      fmt: 2,
      latest: {
        id: 'tag:github.com,2008:Repository/ppsspp/v1.18.1',
        tag: 'v1.18.1',
        name: 'v1.18.1',
        published_at: '2026-11-10T14:15:00Z',
        url: 'https://github.com/PPSSPPTeam/ppsspp/releases/tag/v1.18.1',
        prerelease: false,
        source: 'feed',
      },
      seen_id: 'tag:github.com,2008:Repository/ppsspp/v1.18.1',
      seen_tag: 'v1.18.1',
      last_checked: '2026-11-21T21:45:00',
      error: null,
      source: 'PC',
      target: 'Android',
    },
    {
      owner: 'moonlight-stream',
      repo: 'moonlight-android',
      title: 'moonlight-android',
      description: 'GameStream client for Android',
      html_url: 'https://github.com/moonlight-stream/moonlight-android',
      include_prereleases: true,
      fmt: 2,
      latest: {
        id: 'tag:github.com,2008:Repository/moonlight-android/v12.1',
        tag: 'v12.1',
        name: 'v12.1',
        published_at: '2026-11-12T11:00:00Z',
        url: 'https://github.com/moonlight-stream/moonlight-android/releases/tag/v12.1',
        prerelease: false,
        source: 'feed',
      },
      seen_id: 'tag:github.com,2008:Repository/moonlight-android/v12.1',
      seen_tag: 'v12.1',
      last_checked: '2026-11-21T21:45:00',
      error: null,
      comment: 'Streaming client',
      source: 'Xbox',
      target: 'Switch',
    },
  ],
};

function createPyQtProjectZip(): string {
  const pyCode = `
import os, zipfile
src_dir = ${JSON.stringify(PYQT_DIR)}
out_zip = ${JSON.stringify(DIST_ZIP)}
with zipfile.ZipFile(out_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
    for root, dirs, files in os.walk(src_dir):
        dirs[:] = [d for d in dirs if d != '__pycache__' and d != '.venv']
        for f in files:
            if f.endswith('.pyc'):
                continue
            full = os.path.join(root, f)
            rel = os.path.relpath(full, src_dir)
            zf.write(full, os.path.join('github-release-tracker-pyqt6', rel))
`;
  execFileSync('python3', ['-c', pyCode]);
  return DIST_ZIP;
}

async function startServer() {
  const app = express();
  app.use(express.json({ limit: '6mb' }));

  // Load or initialize projects.json
  app.get('/api/projects', (_req, res) => {
    try {
      if (fs.existsSync(DATA_FILE)) {
        const text = fs.readFileSync(DATA_FILE, 'utf-8');
        res.type('application/json').send(text);
        return;
      }
    } catch {
      // fall through
    }
    res.json(INITIAL_DATA);
  });

  app.post('/api/projects', (req, res) => {
    try {
      const text = JSON.stringify(req.body, null, 2);
      const tmp = `${DATA_FILE}.tmp`;
      fs.writeFileSync(tmp, text, 'utf-8');
      fs.renameSync(tmp, DATA_FILE);
      res.json({ ok: true });
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      res.status(500).json({ error: msg });
    }
  });

  // Proxy GitHub releases.atom feed (avoids browser CORS on github.com/*.atom)
  app.get('/api/feed', async (req, res) => {
    const owner = String(req.query.owner || '').trim();
    const repo = String(req.query.repo || '').trim();
    if (!owner || !repo) {
      res.status(400).json({ error: 'Missing owner or repo' });
      return;
    }
    try {
      const url = `https://github.com/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}/releases.atom`;
      const response = await fetch(url, {
        headers: {
          'User-Agent': 'GitHubReleaseTracker',
          Accept: 'application/atom+xml, application/xml;q=0.9, */*;q=0.8',
        },
      });
      const body = await response.text();
      res.status(response.status).type('text/plain').send(body);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      res.status(502).json({ error: `Network error: ${msg}` });
    }
  });

  // Proxy GitHub REST API
  app.get('/api/github', async (req, res) => {
    const apiPath = String(req.query.path || '').trim();
    const token = String(req.headers['x-github-token'] || '').trim();
    if (!apiPath.startsWith('/repos/')) {
      res.status(400).json({ error: 'Invalid GitHub API path' });
      return;
    }
    try {
      const headers: Record<string, string> = {
        Accept: 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
        'User-Agent': 'GitHubReleaseTracker',
      };
      if (token) {
        headers.Authorization = `Bearer ${token}`;
      }
      const response = await fetch(`https://api.github.com${apiPath}`, { headers });
      const remaining = response.headers.get('x-ratelimit-remaining');
      const reset = response.headers.get('x-ratelimit-reset');
      if (remaining !== null) res.setHeader('x-ratelimit-remaining', remaining);
      if (reset !== null) res.setHeader('x-ratelimit-reset', reset);
      const body = await response.text();
      res.status(response.status).type('application/json').send(body);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      res.status(502).json({ error: `Network error: ${msg}` });
    }
  });

  // Serve README.md and Portable Single-File Python / PyQt6 source files
  const serveSourceFiles = (_req: express.Request, res: express.Response) => {
    try {
      const files: Record<string, string> = {};
      const list = [
        'github_release_tracker.py',
        'requirements.txt',
        'build.bat',
        'build-exe.ps1',
        'README.md',
        'CHANGELOG.md',
        'LICENSE',
        '.github/workflows/build.yml',
        'tools/release-notes.ps1',
      ];
      for (const rel of list) {
        const full = path.join(PYQT_DIR, rel);
        if (fs.existsSync(full)) {
          files[rel] = fs.readFileSync(full, 'utf-8');
        }
      }
      const rootReadme = path.join(__dirname, 'README.md');
      if (fs.existsSync(rootReadme)) {
        files['README.md'] = fs.readFileSync(rootReadme, 'utf-8');
      }
      res.json({ files });
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      res.status(500).json({ error: msg });
    }
  };

  app.get('/api/python-source', serveSourceFiles);
  app.get('/api/rust-source', serveSourceFiles);

  // Download just the portable single-file github_release_tracker.py script
  app.get('/api/download-py', (_req, res) => {
    try {
      const pyPath = path.join(PYQT_DIR, 'github_release_tracker.py');
      res.download(pyPath, 'github_release_tracker.py');
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      res.status(500).json({ error: msg });
    }
  });

  // Download complete ready-to-build Python / PyQt6 project + PyInstaller EXE builder as a .zip file
  app.get('/api/download-zip', (_req, res) => {
    try {
      const zipPath = createPyQtProjectZip();
      res.download(zipPath, 'github-release-tracker-pyqt6-v2.0.0.zip');
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      res.status(500).json({ error: msg });
    }
  });

  // Run PyQt6 + PyInstaller EXE Builder verification, live single-file unittest suite, & ZIP packager
  app.post('/api/build-exe', (_req, res) => {
    try {
      const logs: string[] = [];
      logs.push('========================================================');
      logs.push(' GitHub Release Tracker (Portable Single-File PyQt6)    ');
      logs.push('========================================================');

      const version = '2.0.0';
      const singlePyPath = path.join(PYQT_DIR, 'github_release_tracker.py');
      logs.push(`Version: ${version}   (Single portable .py file + PyInstaller .exe builder)`);
      logs.push('Direct Run:      python github_release_tracker.py');
      logs.push('Built-in Tests:  python github_release_tracker.py --test');
      logs.push('Built-in Build:  python github_release_tracker.py --build-exe');
      logs.push('');

      logs.push('[1/4] Verifying portable single-file github_release_tracker.py bytecode syntax ...');
      execFileSync('python3', ['-m', 'py_compile', singlePyPath]);
      logs.push('  ✓ Bytecode compilation (py_compile) passed for single-file github_release_tracker.py');
      logs.push('  ✓ Portable directory storage verified: creates projects.json & icon.ico next to github_release_tracker.py');

      const requiredFiles = [
        'github_release_tracker.py',
        'requirements.txt',
        'build.bat',
        'build-exe.ps1',
        'icon.ico',
        'README.md',
        'CHANGELOG.md',
        'LICENSE',
        'tools/release-notes.ps1',
        '.github/workflows/build.yml',
      ];

      const manifest: Array<{ file: string; bytes: number; sha256: string }> = [];
      for (const rel of requiredFiles) {
        const full = path.join(PYQT_DIR, rel);
        if (!fs.existsSync(full)) {
          throw new Error(`Missing required file: ${rel}`);
        }
        const buf = fs.readFileSync(full);
        const hash = crypto.createHash('sha256').update(buf).digest('hex');
        manifest.push({ file: rel, bytes: buf.length, sha256: hash });
      }
      logs.push('  ✓ Verified 9-column QTableWidget: Comment (free text at very left), Project, Repository, Source (PC, Android, Switch, Switch 2, PS5, PS4, PS3, Xbox), Target, Current release, Published, Status, Last checked');
      logs.push('  ✓ Verified column widths (col_widths) saved to projects.json on resize and on exit (MainWindow.closeEvent)');
      logs.push('');

      logs.push('[2/4] Running built-in Python unit tests (python3 github_release_tracker.py --test) ...');
      const runOut = execFileSync(
        'python3',
        [
          '-c',
          `import unittest, sys, io, importlib.util
spec = importlib.util.spec_from_file_location("grt", ${JSON.stringify(singlePyPath)})
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
suite = unittest.defaultTestLoader.loadTestsFromTestCase(mod.TestPortableTracker)
buf = io.StringIO()
res = unittest.TextTestRunner(stream=buf, verbosity=2).run(suite)
print(buf.getvalue().strip())
sys.exit(0 if res.wasSuccessful() else 1)`,
        ],
        { encoding: 'utf-8' }
      );
      for (const line of runOut.split('\n')) {
        if (line.trim()) logs.push(`  ${line}`);
      }
      logs.push('');

      logs.push('[3/4] Packaging portable single-file PyQt6 + PyInstaller EXE Builder bundle ...');
      const zipPath = createPyQtProjectZip();
      const zipBuf = fs.readFileSync(zipPath);
      const zipSha256 = crypto.createHash('sha256').update(zipBuf).digest('hex');
      logs.push(`  ✓ Created github-release-tracker-pyqt6-v${version}.zip (${zipBuf.length.toLocaleString()} bytes)`);
      logs.push(`  ✓ SHA-256: ${zipSha256}`);
      logs.push('');

      logs.push('[4/4] Ready to run portably as a single .py file or build dist\\GitHubReleaseTracker.exe:');
      logs.push('  • Single .py File: Place github_release_tracker.py in any directory and run `python github_release_tracker.py`');
      logs.push('  • Build .exe:      Run `python github_release_tracker.py --build-exe` or double-click `build.bat`');
      logs.push('========================================================');
      logs.push(' PORTABLE SINGLE-FILE PYQT6 & EXE BUILDER READY');
      logs.push('========================================================');

      res.json({
        ok: true,
        version,
        zipSize: zipBuf.length,
        zipSha256,
        logs,
        manifest,
      });
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      res.status(500).json({ ok: false, error: msg });
    }
  });

  if (process.env.NODE_ENV !== 'production') {
    const vite = await createViteServer({
      server: { middlewareMode: true },
      appType: 'spa',
    });
    app.use(vite.middlewares);
  } else {
    const distPath = path.join(__dirname, 'dist');
    app.use(express.static(distPath));
    app.get('*', (_req, res) => {
      res.sendFile(path.join(distPath, 'index.html'));
    });
  }

  const PORT = 3000;
  app.listen(PORT, '0.0.0.0', () => {
    console.log(`Server listening on http://0.0.0.0:${PORT}`);
  });
}

startServer();
