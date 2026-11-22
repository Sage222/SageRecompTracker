import express from 'express';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { createServer as createViteServer } from 'vite';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const DATA_FILE = path.join(__dirname, 'projects.json');

const INITIAL_DATA = {
  settings: {
    token: '',
    check_on_launch: false,
    theme: 'dark',
    sort_col: '',
    sort_asc: true,
  },
  projects: [
    {
      owner: 'santosasarno-code',
      repo: 'github-release-tracker-rs',
      title: 'github-release-tracker-rs',
      description: 'A small, portable Windows app that tracks the latest release of the GitHub projects you care about and tells you when a new one appears.',
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
      owner: ' moonlight-stream',
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
      source: 'PC',
      target: 'Switch',
    },
  ].map((p) => ({ ...p, owner: p.owner.trim() })),
};

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

  // Endpoint to view/download the modified Rust source files
  app.get('/api/rust-source', (_req, res) => {
    try {
      const rustDir = path.join(__dirname, 'rust-project');
      const files: Record<string, string> = {};
      for (const rel of ['Cargo.toml', 'src/lib.rs', 'src/ui.rs', 'src/dialogs.rs', 'src/http.rs', 'src/main.rs', 'src/winutil.rs', 'src/tests.rs']) {
        const full = path.join(rustDir, rel);
        if (fs.existsSync(full)) {
          files[rel] = fs.readFileSync(full, 'utf-8');
        }
      }
      res.json({ files });
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      res.status(500).json({ error: msg });
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
