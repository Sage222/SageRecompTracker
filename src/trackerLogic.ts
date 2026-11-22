export const APP_NAME = 'GitHub Release Tracker';
export const APP_VERSION = '2.0.0';
export const REPO_URL = 'https://github.com/santosasarno-code/github-release-tracker-rs';
export const NO_DESCRIPTION = 'No description, website, or topics provided.';
export const MAX_PROJECTS = 500;
export const MAX_IMPORT_BYTES = 5 * 1024 * 1024;
export const MAX_CUSTOM_NAME = 80;
export const MAX_COMMENT_LEN = 300;
export const MAX_TITLE_LEN = 300;

export const SOURCE_PLATFORMS = [
  'PC',
  'Android',
  'Switch',
  'Switch 2',
  'PS5',
  'PS4',
  'PS3',
  'Xbox',
  'Wii',
  'Wii U',
] as const;
export type SourcePlatform = (typeof SOURCE_PLATFORMS)[number];

export const TARGET_PLATFORMS = [
  'PC',
  'Android',
  'Switch',
  'Switch 2',
  'PS5',
  'PS4',
  'PS3',
] as const;
export type TargetPlatform = (typeof TARGET_PLATFORMS)[number];

export const PLATFORMS = SOURCE_PLATFORMS;
export type Platform = SourcePlatform;

export const SORTABLE = [
  'user_title',
  'name',
  'repo',
  'source',
  'target',
  'published',
  'status',
  'comment',
] as const;

export const COLS: ReadonlyArray<{ id: string; title: string }> = [
  { id: 'user_title', title: 'Title' },
  { id: 'name', title: 'Project' },
  { id: 'repo', title: 'Repository' },
  { id: 'source', title: 'Source' },
  { id: 'target', title: 'Target' },
  { id: 'release', title: 'Current release' },
  { id: 'published', title: 'Published' },
  { id: 'status', title: 'Status' },
  { id: 'checked', title: 'Last checked' },
  { id: 'comment', title: 'Comment' },
];

export const COL_BASE: number[] = [150, 180, 210, 105, 105, 135, 110, 210, 125, 180];
export const COL_MIN: number[] = [90, 110, 110, 85, 85, 90, 100, 120, 100, 90];

export type ReleaseId = number | string;

export interface Release {
  id: ReleaseId;
  tag: string;
  name: string;
  published_at: string;
  url: string;
  prerelease: boolean;
  source: 'release' | 'tag' | 'feed';
}

export interface Project {
  owner: string;
  repo: string;
  title: string;
  user_title: string;
  description: string;
  html_url: string;
  include_prereleases: boolean;
  fmt: number | null;
  latest: Release | null;
  seen_id: ReleaseId | null;
  seen_tag: string | null;
  last_checked: string;
  error: string | null;
  custom_name?: string;
  comment: string;
  source: SourcePlatform;
  target: TargetPlatform;
}

export interface Settings {
  token: string;
  check_on_launch: boolean;
  theme: 'light' | 'dark' | '';
  sort_col: string;
  sort_asc: boolean;
  col_widths: number[];
}

export interface TrackerData {
  settings: Settings;
  projects: Project[];
}

export interface RepoInfo {
  owner: string;
  repo: string;
  title: string;
  description: string;
  html_url: string;
}

export interface ParsedProjectInput {
  kind: 'github' | 'forge' | 'web';
  host: string;
  owner: string;
  repo: string;
  html_url: string;
}

export class GitHubError extends Error {
  kind: 'NotFound' | 'RateLimit' | 'Other';
  constructor(kind: 'NotFound' | 'RateLimit' | 'Other', message: string) {
    super(message);
    this.kind = kind;
  }
  static notFound(): GitHubError {
    return new GitHubError('NotFound', 'Not found (wrong name, or a private repository).');
  }
}

export function defaultPlatform(): 'PC' {
  return 'PC';
}

export function normalizeSourcePlatform(raw: unknown): SourcePlatform {
  if (typeof raw === 'string') {
    const trimmed = raw.trim().toLowerCase();
    for (const p of SOURCE_PLATFORMS) {
      if (p.toLowerCase() === trimmed) {
        return p;
      }
    }
  }
  return defaultPlatform();
}

export function normalizeTargetPlatform(raw: unknown): TargetPlatform {
  if (typeof raw === 'string') {
    const trimmed = raw.trim().toLowerCase();
    for (const p of TARGET_PLATFORMS) {
      if (p.toLowerCase() === trimmed) {
        return p;
      }
    }
  }
  return defaultPlatform();
}

export function normalizePlatform(raw: unknown, isSource = true): Platform {
  return isSource ? normalizeSourcePlatform(raw) : normalizeTargetPlatform(raw);
}

export function normalizeColWidths(raw: unknown): number[] {
  if (Array.isArray(raw)) {
    let items = [...raw];
    if (items.length === 8) {
      items = [COL_BASE[0], ...items, COL_BASE[9]];
    } else if (items.length === 9) {
      items = [COL_BASE[0], ...items];
    }
    if (items.length === COLS.length) {
      const out: number[] = [];
      for (let i = 0; i < COLS.length; i++) {
        const val = items[i];
        if (typeof val === 'number' && Number.isFinite(val)) {
          out.push(Math.max(COL_MIN[i], Math.min(1600, Math.round(val))));
        } else {
          return [...COL_BASE];
        }
      }
      return out;
    }
  }
  return [...COL_BASE];
}

export function cleanComment(raw: unknown): string {
  if (typeof raw !== 'string') return '';
  return Array.from(raw.replace(/[\r\n]+/g, ' ').trim())
    .slice(0, MAX_COMMENT_LEN)
    .join('');
}

export function cleanUserTitle(raw: unknown): string {
  if (typeof raw !== 'string') return '';
  return Array.from(raw.replace(/[\r\n]+/g, ' ').trim())
    .slice(0, MAX_TITLE_LEN)
    .join('');
}

function isNameChar(c: string): boolean {
  return /^[A-Za-z0-9_.-]$/.test(c);
}

export function validName(s: string): boolean {
  return s.length >= 1 && s.length <= 100 && /^[A-Za-z0-9_.-]+$/.test(s);
}

function takeName(s: string): [string, string] {
  let i = 0;
  while (i < s.length && isNameChar(s[i])) {
    i++;
  }
  return [s.slice(0, i), s.slice(i)];
}

export function parseProjectInput(text: string): ParsedProjectInput | null {
  const trimmed = text.trim();
  if (!trimmed) return null;

  const hasScheme = trimmed.startsWith('https://') || trimmed.startsWith('http://');
  let rest = trimmed;
  let scheme = 'https';
  if (rest.startsWith('https://')) {
    rest = rest.slice(8);
    scheme = 'https';
  } else if (rest.startsWith('http://')) {
    rest = rest.slice(7);
    scheme = 'http';
  }
  if (rest.startsWith('www.')) {
    rest = rest.slice(4);
  }

  // Case 1: github.com/<owner>/<repo>
  if (rest.startsWith('github.com/')) {
    const afterDomain = rest.slice('github.com/'.length);
    const [owner, r1] = takeName(afterDomain);
    if (owner && r1.startsWith('/')) {
      let [repo] = takeName(r1.slice(1));
      if (repo.endsWith('.git')) repo = repo.slice(0, -4);
      if (repo && validName(owner) && validName(repo)) {
        return {
          kind: 'github',
          host: 'github.com',
          owner,
          repo,
          html_url: `https://github.com/${owner}/${repo}`,
        };
      }
    }
    return null;
  }

  // Case 2: External HTTP(S) URL (e.g. https://git.magicbean.dev/MagicBeanDev/Longshot or https://eden-emu.dev/downloads/)
  if (hasScheme) {
    const parts = rest.split('/');
    const host = (parts[0] || '').trim().toLowerCase();
    if (!host || !host.includes('.') || !validName(host)) return null;
    let segs = parts.slice(1).filter(Boolean);
    if (segs.length > 0) {
      segs[segs.length - 1] = segs[segs.length - 1].split(/[?#]/)[0];
      segs = segs.filter(Boolean);
    }

    if (segs.length >= 2 && validName(segs[0]) && validName(segs[1])) {
      const owner = segs[0];
      const repo = segs[1].endsWith('.git') ? segs[1].slice(0, -4) : segs[1];
      if (repo && validName(repo)) {
        return {
          kind: 'forge',
          host,
          owner,
          repo,
          html_url: `${scheme}://${host}/${owner}/${repo}`,
        };
      }
    }

    let slug = segs.length > 0 && validName(segs[0]) ? segs[0] : host.split('.')[0];
    if (!validName(slug)) slug = 'releases';
    const cleanPath = segs.join('/');
    const trailing = trimmed.endsWith('/') && cleanPath ? '/' : '';
    const fullUrl = cleanPath ? `${scheme}://${host}/${cleanPath}${trailing}` : `${scheme}://${host}`;
    return {
      kind: 'web',
      host,
      owner: host,
      repo: slug,
      html_url: fullUrl,
    };
  }

  // Case 3: Plain owner/repo shorthand
  const [o, r1] = takeName(trimmed);
  if (!r1.startsWith('/')) return null;
  const [rRaw, tail] = takeName(r1.slice(1));
  if (!o || !rRaw || tail.length > 0) return null;
  const repo = rRaw.endsWith('.git') ? rRaw.slice(0, -4) : rRaw;
  if (!repo || !validName(o) || !validName(repo)) return null;
  return {
    kind: 'github',
    host: 'github.com',
    owner: o,
    repo,
    html_url: `https://github.com/${o}/${repo}`,
  };
}

export function parseRepo(text: string): [string, string] | null {
  const parsed = parseProjectInput(text);
  if (!parsed) return null;
  return [parsed.owner, parsed.repo];
}

function trimChars(s: unknown, limit: number): string {
  if (typeof s !== 'string') return '';
  return Array.from(s.trim()).slice(0, limit).join('');
}

export function safeHttpUrl(url: unknown, fallback: string): string {
  if (
    typeof url === 'string' &&
    (url.startsWith('https://') || url.startsWith('http://')) &&
    url.length < 500 &&
    !/\s/.test(url)
  ) {
    return url;
  }
  return fallback;
}

export function safeGithubUrl(url: unknown, fallback: string): string {
  return safeHttpUrl(url, fallback);
}

function idValue(v: unknown): ReleaseId | null {
  if (typeof v === 'number' && Number.isInteger(v)) {
    return v;
  }
  if (typeof v === 'string') {
    return Array.from(v).slice(0, 300).join('');
  }
  return null;
}

export function cleanName(s: string): string {
  const joined = s.trim().split(/\s+/).filter(Boolean).join(' ');
  return Array.from(joined).slice(0, MAX_CUSTOM_NAME).join('').trim();
}

export function projectKey(p: Pick<Project, 'owner' | 'repo'> & { html_url?: string }): string {
  const htmlUrl = (p.html_url || '').trim().toLowerCase();
  if (
    htmlUrl &&
    !htmlUrl.startsWith('https://github.com/') &&
    !htmlUrl.startsWith('http://github.com/')
  ) {
    const cleaned = htmlUrl.replace(/^https?:\/\/(?:www\.)?/, '').replace(/\/+$/, '');
    if (cleaned) return cleaned;
  }
  return `${p.owner}/${p.repo}`.toLowerCase();
}

export function repoDisplayLabel(p: Pick<Project, 'owner' | 'repo'> & { html_url?: string }): string {
  const htmlUrl = (p.html_url || '').trim();
  if (
    htmlUrl &&
    !htmlUrl.startsWith('https://github.com/') &&
    !htmlUrl.startsWith('http://github.com/')
  ) {
    const cleaned = htmlUrl.replace(/^https?:\/\/(?:www\.)?/, '').replace(/\/+$/, '');
    if (cleaned) return cleaned;
  }
  return `${p.owner}/${p.repo}`;
}

export function displayName(p: Project): string {
  if (p.custom_name && p.custom_name.length > 0) {
    return p.custom_name;
  }
  return p.title || p.repo;
}

export function hasUpdate(p: Project): boolean {
  if (!p.latest) return false;
  return p.latest.id !== p.seen_id;
}

export function statusText(p: Project): string {
  if (p.error) {
    return `Error: ${p.error}`;
  }
  if (!p.latest) {
    return 'No releases published';
  }
  if (hasUpdate(p)) {
    const newLabel = p.latest.tag || p.latest.name || 'new release';
    if (p.seen_tag && p.seen_tag.length > 0) {
      return `Update available: ${p.seen_tag} -> ${newLabel}`;
    }
    return `Update available: ${newLabel}`;
  }
  return 'Up to date';
}

export function statusRank(p: Project): number {
  if (p.error) return 1;
  if (!p.latest) return 2;
  if (hasUpdate(p)) return 0;
  return 3;
}

export function releaseLabel(p: Project): string {
  if (!p.latest) return '-';
  let s = p.latest.tag || p.latest.name;
  if (p.latest.source === 'tag') {
    s += ' (tag)';
  } else if (p.latest.prerelease) {
    s += ' (pre-release)';
  }
  return s || '-';
}

export function publishedLabel(p: Project): string {
  const d = p.latest ? p.latest.published_at.slice(0, 10) : '';
  return d || '-';
}

export function checkedLabel(p: Project): string {
  const s = (p.last_checked || '').slice(0, 16).replace('T', ' ');
  return s || 'never';
}

export function nowIso(): string {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

export function todayYmd(): string {
  return nowIso().slice(0, 10);
}

export function applyResult(
  p: Project,
  latest: Release | null,
  err: string | null,
  now: string
): Project {
  const next: Project = { ...p, last_checked: now };
  if (err) {
    next.error = err;
    return next;
  }
  next.error = null;
  if (latest) {
    if (next.seen_tag && next.seen_tag === latest.tag) {
      next.seen_id = latest.id;
    } else if (next.fmt !== 2 && next.seen_id === null) {
      next.seen_id = latest.id;
      next.seen_tag = latest.tag;
    }
  }
  next.latest = latest;
  next.fmt = 2;
  return next;
}

function truthy(v: unknown): boolean {
  if (typeof v === 'boolean') return v;
  if (v === null || v === undefined) return false;
  if (typeof v === 'number') return v !== 0;
  if (typeof v === 'string') return v.length > 0;
  if (Array.isArray(v)) return v.length > 0;
  if (typeof v === 'object') return Object.keys(v as object).length > 0;
  return false;
}

function normalizeRelease(v: unknown, owner: string, repo: string, baseHtmlUrl = ''): Release | null {
  if (!v || typeof v !== 'object' || Array.isArray(v)) return null;
  const r = v as Record<string, unknown>;
  const tag = trimChars(r.tag, 200);
  let id = idValue(r.id);
  if (id === null) {
    if (tag) id = tag;
    else return null;
  }
  const srcRaw = r.source;
  const source: 'release' | 'tag' | 'feed' =
    srcRaw === 'release' || srcRaw === 'tag' || srcRaw === 'feed' ? srcRaw : 'release';
  const fallbackUrl = baseHtmlUrl
    ? `${baseHtmlUrl.replace(/\/+$/, '')}/releases`
    : `https://github.com/${owner}/${repo}/releases`;
  return {
    id,
    tag,
    name: trimChars(r.name, 300),
    published_at: trimChars(r.published_at, 40),
    url: safeHttpUrl(r.url, fallbackUrl),
    prerelease: r.prerelease !== undefined ? truthy(r.prerelease) : false,
    source,
  };
}

export function normalizeProject(raw: unknown): Project | null {
  let o: Record<string, unknown>;
  if (typeof raw === 'string') {
    const parsed = parseProjectInput(raw);
    if (!parsed) return null;
    o = { owner: parsed.owner, repo: parsed.repo, html_url: parsed.html_url };
  } else if (raw && typeof raw === 'object' && !Array.isArray(raw)) {
    o = raw as Record<string, unknown>;
  } else {
    return null;
  }

  const owner = typeof o.owner === 'string' ? o.owner : '';
  const repo = typeof o.repo === 'string' ? o.repo : '';
  if (!validName(owner) || !validName(repo)) return null;

  const title = trimChars(o.title, 200);
  const custom = typeof o.custom_name === 'string' ? cleanName(o.custom_name) : '';
  const error = trimChars(o.error, 300);
  const seenTag = trimChars(o.seen_tag, 200);
  const comment = cleanComment(o.comment);
  const userTitle = cleanUserTitle(o.user_title);
  const htmlUrl = safeHttpUrl(o.html_url, `https://github.com/${owner}/${repo}`);

  const proj: Project = {
    owner,
    repo,
    title: title || repo,
    user_title: userTitle,
    description: trimChars(o.description, 500),
    html_url: htmlUrl,
    include_prereleases: o.include_prereleases !== undefined ? truthy(o.include_prereleases) : true,
    fmt: o.fmt === 2 ? 2 : null,
    latest: normalizeRelease(o.latest, owner, repo, htmlUrl),
    seen_id: idValue(o.seen_id),
    seen_tag: seenTag || null,
    last_checked: trimChars(o.last_checked, 40),
    error: error || null,
    comment,
    source: normalizeSourcePlatform(o.source),
    target: normalizeTargetPlatform(o.target),
  };
  if (custom) {
    proj.custom_name = custom;
  }
  return proj;
}

export function parseImport(raw: unknown): { projects: Project[]; skipped: number } | null {
  let items: unknown[];
  if (Array.isArray(raw)) {
    items = raw;
  } else if (raw && typeof raw === 'object') {
    const p = (raw as Record<string, unknown>).projects;
    if (!Array.isArray(p)) return null;
    items = p;
  } else {
    return null;
  }

  const seen = new Set<string>();
  const out: Project[] = [];
  let skipped = Math.max(0, items.length - MAX_PROJECTS);
  for (const item of items.slice(0, MAX_PROJECTS)) {
    const p = normalizeProject(item);
    if (p) {
      const k = projectKey(p);
      if (!seen.has(k)) {
        seen.add(k);
        out.push(p);
        continue;
      }
    }
    skipped++;
  }
  return { projects: out, skipped };
}

export function mergeProjects(existing: Project[], incoming: Project[]): { merged: Project[]; added: number } {
  const keys = new Set(existing.map(projectKey));
  const merged = [...existing];
  let added = 0;
  for (const p of incoming) {
    const k = projectKey(p);
    if (!keys.has(k)) {
      keys.add(k);
      merged.push(p);
      added++;
    }
  }
  return { merged, added };
}

export function buildExport(projects: Project[], now: string): Record<string, unknown> {
  return {
    app: APP_NAME,
    format: 2,
    exported_at: now,
    projects,
  };
}

export function sortOrder(projects: Project[], col: string, asc: boolean): number[] {
  const idx = projects.map((_, i) => i);
  const dir = (n: number) => (asc ? n : -n);
  const titleKey = (p: Project) => displayName(p).toLowerCase();
  const pubKey = (p: Project) => (p.latest ? p.latest.published_at : '');

  const cmpTuple = (a: (string | number | boolean)[], b: (string | number | boolean)[]): number => {
    for (let i = 0; i < a.length; i++) {
      if (a[i] < b[i]) return -1;
      if (a[i] > b[i]) return 1;
    }
    return 0;
  };

  if (col === 'status') {
    const sign = asc ? 1 : -1;
    idx.sort((a, b) => {
      const pa = projects[a];
      const pb = projects[b];
      return cmpTuple(
        [sign * statusRank(pa), titleKey(pa), projectKey(pa)],
        [sign * statusRank(pb), titleKey(pb), projectKey(pb)]
      );
    });
  } else if (col === 'user_title') {
    idx.sort((a, b) => {
      const pa = projects[a];
      const pb = projects[b];
      return dir(
        cmpTuple(
          [(pa.user_title || '').toLowerCase(), titleKey(pa), projectKey(pa)],
          [(pb.user_title || '').toLowerCase(), titleKey(pb), projectKey(pb)]
        )
      );
    });
  } else if (col === 'comment') {
    idx.sort((a, b) => {
      const pa = projects[a];
      const pb = projects[b];
      return dir(
        cmpTuple(
          [(pa.comment || '').toLowerCase(), titleKey(pa), projectKey(pa)],
          [(pb.comment || '').toLowerCase(), titleKey(pb), projectKey(pb)]
        )
      );
    });
  } else if (col === 'name') {
    idx.sort((a, b) => {
      const pa = projects[a];
      const pb = projects[b];
      return dir(cmpTuple([titleKey(pa), projectKey(pa)], [titleKey(pb), projectKey(pb)]));
    });
  } else if (col === 'repo') {
    idx.sort((a, b) =>
      dir(repoDisplayLabel(projects[a]).toLowerCase().localeCompare(repoDisplayLabel(projects[b]).toLowerCase()))
    );
  } else if (col === 'source') {
    idx.sort((a, b) => {
      const pa = projects[a];
      const pb = projects[b];
      return dir(
        cmpTuple(
          [pa.source.toLowerCase(), titleKey(pa), projectKey(pa)],
          [pb.source.toLowerCase(), titleKey(pb), projectKey(pb)]
        )
      );
    });
  } else if (col === 'target') {
    idx.sort((a, b) => {
      const pa = projects[a];
      const pb = projects[b];
      return dir(
        cmpTuple(
          [pa.target.toLowerCase(), titleKey(pa), projectKey(pa)],
          [pb.target.toLowerCase(), titleKey(pb), projectKey(pb)]
        )
      );
    });
  } else if (col === 'published') {
    const dated = idx.filter((i) => pubKey(projects[i]).length > 0);
    const undated = idx.filter((i) => pubKey(projects[i]).length === 0);
    dated.sort((a, b) => {
      const pa = projects[a];
      const pb = projects[b];
      return dir(cmpTuple([pubKey(pa), titleKey(pa)], [pubKey(pb), titleKey(pb)]));
    });
    undated.sort((a, b) => cmpTuple([titleKey(projects[a])], [titleKey(projects[b])]));
    return [...dated, ...undated];
  } else {
    idx.sort((a, b) => {
      const pa = projects[a];
      const pb = projects[b];
      return cmpTuple([!hasUpdate(pa), titleKey(pa)], [!hasUpdate(pb), titleKey(pb)]);
    });
  }
  return idx;
}

export function layoutColumns(base: number[], low: number[], avail: number): number[] {
  const totalPref = base.reduce((a, b) => a + b, 0);
  const totalLow = low.reduce((a, b) => a + b, 0);
  let target: number[];
  if (avail >= totalPref) {
    target = base.map((p) => (p * avail) / totalPref);
  } else {
    const t = Math.max(0, (avail - totalLow) / Math.max(1, totalPref - totalLow));
    target = base.map((p, i) => low[i] + (p - low[i]) * t);
  }
  const sizes = target.map((x, i) => Math.max(low[i], Math.floor(x)));
  const statusIdx = sizes.length > 7 ? 7 : sizes.length - 2;
  if (avail >= totalLow && sizes.length > statusIdx) {
    const sum = sizes.reduce((a, b) => a + b, 0);
    sizes[statusIdx] += Math.max(0, avail - sum);
  }
  return sizes;
}

export function applyRename(p: Project, typed: string): { project: Project; message: string | null } {
  const text = cleanName(typed);
  const original = p.title || p.repo;
  const before = displayName(p);
  const next: Project = { ...p };
  if (text && text !== original) {
    next.custom_name = text;
  } else {
    delete next.custom_name;
  }
  const after = displayName(next);
  if (after === before) {
    return { project: next, message: null };
  }
  if (next.custom_name) {
    return { project: next, message: `Renamed to ${after}.` };
  }
  return { project: next, message: `Name reset to ${after}.` };
}

// ---------------------------------------------------------------------------
// Atom Feed & GitHub / Forgejo / Downloads API parsing
// ---------------------------------------------------------------------------
function decodeEntities(s: string): string {
  return s
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&apos;/g, "'")
    .replace(/&#x([0-9a-fA-F]+);/g, (_, hex) => String.fromCodePoint(parseInt(hex, 16)))
    .replace(/&#([0-9]+);/g, (_, dec) => String.fromCodePoint(parseInt(dec, 10)));
}

export function parseFeed(body: string, owner: string, repo: string, baseUrl = ''): Release | null {
  if (!/<feed[\s>/]/.test(body)) {
    throw new GitHubError('Other', 'Release feed was not valid XML.');
  }
  const entryMatch = body.match(/<entry[\s>][\s\S]*?<\/entry>/);
  if (!entryMatch) return null;
  const entry = entryMatch[0];

  const getElem = (name: string): string => {
    const re = new RegExp(`<${name}(?:\\s[^>]*)?>([\\s\\S]*?)<\\/${name}>`);
    const m = entry.match(re);
    return m ? decodeEntities(m[1].trim()) : '';
  };

  const entryId = getElem('id');
  const title = getElem('title');
  const updated = getElem('updated') || getElem('published');

  let href = '';
  const linkRe = /<link\s+([^>]+?)\/?>/g;
  let lm: RegExpExecArray | null;
  while ((lm = linkRe.exec(entry)) !== null) {
    const attrs = lm[1];
    const relMatch = attrs.match(/\brel\s*=\s*["']([^"']*)["']/);
    const rel = relMatch ? relMatch[1] : 'alternate';
    if (rel === 'alternate') {
      const hrefMatch = attrs.match(/\bhref\s*=\s*["']([^"']*)["']/);
      if (hrefMatch) {
        href = decodeEntities(hrefMatch[1]);
        break;
      }
    }
  }

  // Forgejo / Gitea feeds put the release URL inside <id>
  if (!href && (entryId.includes('https://') || entryId.includes('http://'))) {
    const urlMatch = entryId.match(/https?:\/\/[^\s<>"']+/);
    if (urlMatch) {
      href = urlMatch[0];
    }
  }

  const marker = '/releases/tag/';
  let tag = '';
  const markerIdx = href.indexOf(marker);
  if (markerIdx !== -1) {
    try {
      tag = decodeURIComponent(href.slice(markerIdx + marker.length));
    } catch {
      tag = href.slice(markerIdx + marker.length);
    }
  } else if (entryId.includes(marker)) {
    const eIdx = entryId.indexOf(marker);
    try {
      tag = decodeURIComponent(entryId.slice(eIdx + marker.length));
    } catch {
      tag = entryId.slice(eIdx + marker.length);
    }
  } else {
    const repoMarker = 'Repository/';
    const rIdx = entryId.indexOf(repoMarker);
    if (rIdx !== -1) {
      const r = entryId.slice(rIdx + repoMarker.length);
      const slashIdx = r.indexOf('/');
      if (slashIdx > 0 && slashIdx + 1 < r.length) {
        tag = r.slice(slashIdx + 1);
      }
    }
  }

  if (!tag && title) {
    const verMatch = title.match(/\b(v?\d+\.\d+(?:\.\d+)*(?:-[0-9A-Za-z._-]+)?)\b/);
    if (verMatch) {
      tag = verMatch[1];
    }
  }

  if (!entryId && !tag) return null;

  const fallbackUrl = baseUrl
    ? `${baseUrl.replace(/\/+$/, '')}/releases`
    : `https://github.com/${owner}/${repo}/releases`;

  return {
    id: entryId || tag,
    tag,
    name: title,
    published_at: updated,
    url: href || fallbackUrl,
    prerelease: false,
    source: 'feed',
  };
}

let lastRateRemaining: number | null = null;

export function getRateRemaining(): number | null {
  return lastRateRemaining;
}

async function apiGet(path: string, token: string): Promise<unknown> {
  const headers: Record<string, string> = {};
  if (token) headers['x-github-token'] = token;
  const res = await fetch(`/api/github?path=${encodeURIComponent(path)}`, { headers });
  const rem = res.headers.get('x-ratelimit-remaining');
  const reset = res.headers.get('x-ratelimit-reset');
  if (rem !== null) {
    const parsed = parseInt(rem, 10);
    if (!Number.isNaN(parsed)) lastRateRemaining = parsed;
  }

  if (res.status >= 200 && res.status <= 299) {
    return await res.json();
  }
  if ((res.status === 403 || res.status === 429) && rem?.trim() === '0') {
    lastRateRemaining = 0;
    let when = '';
    if (reset) {
      const epoch = parseInt(reset, 10);
      if (!Number.isNaN(epoch)) {
        const d = new Date(epoch * 1000);
        const hh = String(d.getHours()).padStart(2, '0');
        const mm = String(d.getMinutes()).padStart(2, '0');
        when = ` Resets at ${hh}:${mm}.`;
      }
    }
    throw new GitHubError(
      'RateLimit',
      `GitHub API rate limit reached.${when} Add a token in Settings for a higher limit.`
    );
  }
  if (res.status === 404) {
    throw GitHubError.notFound();
  }
  if (res.status === 401) {
    throw new GitHubError('Other', 'GitHub rejected the token (401). Check it in Settings.');
  }
  throw new GitHubError('Other', `GitHub returned HTTP ${res.status}.`);
}

async function feedGet(owner: string, repo: string): Promise<string> {
  const res = await fetch(`/api/feed?owner=${encodeURIComponent(owner)}&repo=${encodeURIComponent(repo)}`);
  if (res.status >= 200 && res.status <= 299) {
    return await res.text();
  }
  if (res.status === 404) {
    throw GitHubError.notFound();
  }
  if (res.status === 429) {
    throw new GitHubError('Other', 'GitHub is rate-limiting the release feed (429). Try again later.');
  }
  throw new GitHubError('Other', `Release feed returned HTTP ${res.status}.`);
}

function isExternalUrl(htmlUrl?: string): boolean {
  if (!htmlUrl) return false;
  const lower = htmlUrl.trim().toLowerCase();
  return (
    (lower.startsWith('https://') || lower.startsWith('http://')) &&
    !lower.startsWith('https://github.com/') &&
    !lower.startsWith('http://github.com/')
  );
}

async function fetchExternalCheck(
  htmlUrl: string,
  includePre: boolean
): Promise<{ info: RepoInfo; latest: Release | null }> {
  const res = await fetch(
    `/api/external-check?url=${encodeURIComponent(htmlUrl)}&include_pre=${includePre ? '1' : '0'}`
  );
  if (res.status === 404) {
    throw GitHubError.notFound();
  }
  if (!res.ok) {
    let errText = `Server returned HTTP ${res.status}.`;
    try {
      const j = await res.json();
      if (j && typeof j.error === 'string') errText = j.error;
    } catch {
      // ignore
    }
    throw new GitHubError('Other', errText);
  }
  const data = (await res.json()) as {
    info: RepoInfo;
    latest: Release | null;
  };
  return data;
}

function releaseFromApi(r: Record<string, unknown>): Release {
  const s = (k: string) => (typeof r[k] === 'string' ? (r[k] as string) : '');
  const tag = s('tag_name');
  const published = s('published_at') || s('created_at');
  return {
    id: idValue(r.id) ?? tag,
    tag,
    name: s('name'),
    published_at: published,
    url: s('html_url'),
    prerelease: truthy(r.prerelease),
    source: 'release',
  };
}

export async function fetchRepoInfo(
  owner: string,
  repo: string,
  token: string,
  htmlUrl?: string
): Promise<RepoInfo> {
  if (isExternalUrl(htmlUrl)) {
    const ext = await fetchExternalCheck(htmlUrl!, true);
    return ext.info;
  }
  const d = (await apiGet(`/repos/${owner}/${repo}`, token)) as Record<string, unknown>;
  const s = (k: string) => (typeof d[k] === 'string' ? (d[k] as string) : '');
  const full = s('full_name') || `${owner}/${repo}`;
  const parts = full.split('/');
  const ro = parts[0] || owner;
  const rr = parts[1] || repo;
  return {
    owner: ro,
    repo: rr,
    title: s('name') || rr,
    description: s('description'),
    html_url: s('html_url') || `https://github.com/${full}`,
  };
}

async function newestRelease(owner: string, repo: string, token: string): Promise<Release | null> {
  try {
    const data = await apiGet(`/repos/${owner}/${repo}/releases?per_page=10`, token);
    if (Array.isArray(data)) {
      for (const r of data) {
        if (r && typeof r === 'object' && !truthy((r as Record<string, unknown>).draft)) {
          return releaseFromApi(r as Record<string, unknown>);
        }
      }
    }
    return null;
  } catch (e) {
    if (e instanceof GitHubError && e.kind === 'NotFound') return null;
    throw e;
  }
}

async function newestTag(owner: string, repo: string, token: string): Promise<Release | null> {
  try {
    const data = await apiGet(`/repos/${owner}/${repo}/tags?per_page=1`, token);
    if (!Array.isArray(data) || data.length === 0) return null;
    const t = data[0] as Record<string, unknown>;
    const name = typeof t.name === 'string' ? t.name : '';
    const commit = t.commit as Record<string, unknown> | undefined;
    const sha = commit && typeof commit.sha === 'string' && commit.sha ? commit.sha : name;
    return {
      id: sha,
      url: `https://github.com/${owner}/${repo}/releases/tag/${encodeURIComponent(name)}`,
      tag: name,
      name: '',
      published_at: '',
      prerelease: false,
      source: 'tag',
    };
  } catch (e) {
    if (e instanceof GitHubError && e.kind === 'NotFound') return null;
    throw e;
  }
}

export async function fetchLatestRelease(
  owner: string,
  repo: string,
  token: string,
  includePre: boolean
): Promise<Release | null> {
  if (!includePre) {
    try {
      const v = (await apiGet(`/repos/${owner}/${repo}/releases/latest`, token)) as Record<string, unknown>;
      return releaseFromApi(v);
    } catch (e) {
      if (!(e instanceof GitHubError && e.kind === 'NotFound')) {
        throw e;
      }
    }
  }
  const rel = await newestRelease(owner, repo, token);
  if (rel) return rel;
  return await newestTag(owner, repo, token);
}

export async function getLatest(
  owner: string,
  repo: string,
  token: string,
  includePre: boolean,
  htmlUrl?: string
): Promise<Release | null> {
  if (isExternalUrl(htmlUrl)) {
    const ext = await fetchExternalCheck(htmlUrl!, includePre);
    return ext.latest;
  }
  if (includePre) {
    try {
      const body = await feedGet(owner, repo);
      const r = parseFeed(body, owner, repo);
      if (r) return r;
    } catch {
      // Fall back to GitHub API
    }
  }
  return await fetchLatestRelease(owner, repo, token, includePre);
}
