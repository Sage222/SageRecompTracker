import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ArrowLeftRight,
  CheckSquare,
  Download,
  ExternalLink,
  FileText,
  Hammer,
  Moon,
  Pencil,
  Plus,
  RefreshCw,
  Settings as SettingsIcon,
  Sun,
  Trash2,
  Upload,
} from 'lucide-react';
import {
  APP_NAME,
  APP_VERSION,
  COL_BASE,
  COL_MIN,
  COLS,
  DEFAULT_COL_ORDER,
  MAX_COMMENT_LEN,
  MAX_CUSTOM_NAME,
  MAX_IMPORT_BYTES,
  MAX_TITLE_LEN,
  NO_DESCRIPTION,
  Project,
  REPO_URL,
  SORTABLE,
  SOURCE_PLATFORMS,
  SourcePlatform,
  TARGET_PLATFORMS,
  TargetPlatform,
  TrackerData,
  applyRename,
  applyResult,
  buildExport,
  checkedLabel,
  cleanComment,
  cleanUserTitle,
  defaultPlatform,
  displayName,
  fetchRepoInfo,
  getLatest,
  getRateRemaining,
  GitHubError,
  hasUpdate,
  mergeProjects,
  normalizeColOrder,
  normalizeColWidths,
  normalizeProject,
  normalizeSourcePlatform,
  normalizeTargetPlatform,
  nowIso,
  parseImport,
  parseProjectInput,
  projectKey,
  publishedLabel,
  releaseLabel,
  repoDisplayLabel,
  safeHttpUrl,
  sortOrder,
  statusText,
  todayYmd,
} from './trackerLogic';

interface Palette {
  bg: string;
  fg: string;
  field: string;
  sel_bg: string;
  sel_fg: string;
  btn_bg: string;
  btn_active: string;
  border: string;
  update_bg: string;
  update_fg: string;
  error_fg: string;
  none_fg: string;
  sub_fg: string;
  line: string;
  link: string;
  head_bg: string;
}

function getPalette(dark: boolean): Palette {
  if (dark) {
    return {
      bg: '#202124',
      fg: '#e8eaed',
      field: '#2b2d31',
      sel_bg: '#2f6fbf',
      sel_fg: '#ffffff',
      btn_bg: '#3a3d42',
      btn_active: '#4a4d52',
      border: '#4a4d52',
      update_bg: '#4d4210',
      update_fg: '#ffe9a6',
      error_fg: '#ff8a80',
      none_fg: '#9aa0a6',
      sub_fg: '#9aa0a6',
      line: '#3d4046',
      link: '#4da3ff',
      head_bg: '#33363b',
    };
  }
  return {
    bg: '#f3f3f3',
    fg: '#1b1b1b',
    field: '#ffffff',
    sel_bg: '#0078d4',
    sel_fg: '#ffffff',
    btn_bg: '#e1e1e1',
    btn_active: '#d0d0d0',
    border: '#bdbdbd',
    update_bg: '#fff3cd',
    update_fg: '#1b1b1b',
    error_fg: '#b00020',
    none_fg: '#777777',
    sub_fg: '#666666',
    line: '#d4d4d4',
    link: '#0b57d0',
    head_bg: '#e5e5e5',
  };
}

type ModalState =
  | { type: 'none' }
  | { type: 'message'; title: string; text: string; icon: 'error' | 'info' }
  | { type: 'confirm_remove'; count: number; names: string; keys: string[] }
  | { type: 'confirm_import'; projects: Project[]; skipped: number }
  | { type: 'column_order' }
  | { type: 'settings' }
  | { type: 'about'; fromSettings?: boolean }
  | { type: 'exe_builder'; initialTab?: 'builder' | 'readme' | 'source' };

interface ContextMenuState {
  x: number;
  y: number;
  kind: 'row' | 'status' | 'header';
  colId?: string;
}

const STORAGE_KEY = 'github_release_tracker_projects_json_v3';

function openExternalUrl(url: string) {
  const a = document.createElement('a');
  a.href = url;
  a.target = '_blank';
  a.rel = 'noopener noreferrer';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}

export default function App() {
  const [data, setData] = useState<TrackerData>({
    settings: {
      token: '',
      check_on_launch: false,
      theme: 'dark',
      sort_col: '',
      sort_asc: true,
      col_widths: [...COL_BASE],
      col_order: [...DEFAULT_COL_ORDER],
    },
    projects: [],
  });
  const [loaded, setLoaded] = useState(false);
  const [entryText, setEntryText] = useState('');
  const [entryFocused, setEntryFocused] = useState(false);
  const [busy, setBusy] = useState(false);
  const [statusMsg, setStatusMsg] = useState('Add a project to get started.');
  const [selectedKeys, setSelectedKeys] = useState<string[]>([]);
  const [lastClickedKey, setLastClickedKey] = useState<string | null>(null);
  const [hoveredRowKey, setHoveredRowKey] = useState<string | null>(null);
  const [hoveredHeaderIdx, setHoveredHeaderIdx] = useState<number | null>(null);
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [editingValue, setEditingValue] = useState('');
  const [colBase, setColBase] = useState<number[]>(() => [...COL_BASE]);
  const [modal, setModal] = useState<ModalState>({ type: 'none' });
  const [contextMenu, setContextMenu] = useState<ContextMenuState | null>(null);
  const [draggingColId, setDraggingColId] = useState<string | null>(null);
  const [dragOverColId, setDragOverColId] = useState<string | null>(null);
  const [dialogColOrder, setDialogColOrder] = useState<string[]>(() => [...DEFAULT_COL_ORDER]);
  const [dialogSelectedColId, setDialogSelectedColId] = useState<string>(DEFAULT_COL_ORDER[0]);

  // Settings form state
  const [settingsToken, setSettingsToken] = useState('');
  const [settingsCheckOnLaunch, setSettingsCheckOnLaunch] = useState(false);

  // EXE Builder & README state
  const [builderTab, setBuilderTab] = useState<'builder' | 'readme' | 'source'>('builder');
  const [builderRunning, setBuilderRunning] = useState(false);
  const [builderResult, setBuilderResult] = useState<{
    version: string;
    zipSize: number;
    zipSha256: string;
    logs: string[];
    manifest: Array<{ file: string; bytes: number; sha256: string }>;
  } | null>(null);
  const [rustFiles, setRustFiles] = useState<Record<string, string>>({});
  const [selectedSourceFile, setSelectedSourceFile] = useState<string>('github_release_tracker.py');

  const listContainerRef = useRef<HTMLDivElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const renameInputRef = useRef<HTMLInputElement | null>(null);
  const dragColRef = useRef<{ colIdx: number; startX: number; startWidths: number[] } | null>(null);

  const isDark = useMemo(() => {
    if (data.settings.theme === 'light') return false;
    if (data.settings.theme === 'dark') return true;
    return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
  }, [data.settings.theme]);

  const pal = useMemo(() => getPalette(isDark), [isDark]);

  useEffect(() => {
    if (isDark) {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
  }, [isDark]);

  // Persist helper
  const persistData = useCallback((nextData: TrackerData) => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(nextData, null, 2));
    } catch {
      // ignore storage quota errors
    }
    fetch('/api/projects', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(nextData),
    }).catch(() => {});
  }, []);

  // Initial load from server or localStorage
  useEffect(() => {
    let cancelled = false;
    async function init() {
      let parsedData: TrackerData | null = null;
      const localRaw = localStorage.getItem(STORAGE_KEY);
      if (localRaw) {
        try {
          const obj = JSON.parse(localRaw);
          const imported = parseImport(obj);
          if (imported) {
            parsedData = {
              settings: {
                token: typeof obj.settings?.token === 'string' ? obj.settings.token.slice(0, 200) : '',
                check_on_launch: Boolean(obj.settings?.check_on_launch),
                theme:
                  obj.settings?.theme === 'light' || obj.settings?.theme === 'dark'
                    ? obj.settings.theme
                    : 'dark',
                sort_col:
                  typeof obj.settings?.sort_col === 'string' &&
                  (SORTABLE as readonly string[]).includes(obj.settings.sort_col)
                    ? obj.settings.sort_col
                    : '',
                sort_asc: obj.settings?.sort_asc !== false,
                col_widths: normalizeColWidths(obj.settings?.col_widths),
                col_order: normalizeColOrder(obj.settings?.col_order),
              },
              projects: imported.projects,
            };
          }
        } catch {
          // fall back to server
        }
      }

      if (!parsedData) {
        try {
          const res = await fetch('/api/projects');
          if (res.ok) {
            const obj = await res.json();
            const imported = parseImport(obj);
            if (imported) {
              parsedData = {
                settings: {
                  token: typeof obj.settings?.token === 'string' ? obj.settings.token.slice(0, 200) : '',
                  check_on_launch: Boolean(obj.settings?.check_on_launch),
                  theme:
                    obj.settings?.theme === 'light' || obj.settings?.theme === 'dark'
                      ? obj.settings.theme
                      : 'dark',
                  sort_col:
                    typeof obj.settings?.sort_col === 'string' &&
                    (SORTABLE as readonly string[]).includes(obj.settings.sort_col)
                      ? obj.settings.sort_col
                      : '',
                  sort_asc: obj.settings?.sort_asc !== false,
                  col_widths: normalizeColWidths(obj.settings?.col_widths),
                  col_order: normalizeColOrder(obj.settings?.col_order),
                },
                projects: imported.projects,
              };
            }
          }
        } catch {
          // ignore
        }
      }

      if (!cancelled && parsedData) {
        setData(parsedData);
        setColBase(normalizeColWidths(parsedData.settings.col_widths));
        if (parsedData.projects.length > 0) {
          const updates = parsedData.projects.filter(hasUpdate).length;
          setStatusMsg(
            updates > 0
              ? `${parsedData.projects.length} project(s) loaded: ${updates} update(s) available.`
              : `${parsedData.projects.length} project(s) loaded.`
          );
        }
      }
      if (!cancelled) {
        setLoaded(true);
      }
    }
    init();
    return () => {
      cancelled = true;
    };
  }, []);

  // Use exact saved pixel column widths and column order
  const colWidths = useMemo(() => normalizeColWidths(colBase), [colBase]);
  const colOrder = useMemo(
    () => normalizeColOrder(data.settings.col_order),
    [data.settings.col_order]
  );

  const applyNewColOrder = useCallback(
    (nextOrderRaw: string[], statusTextMsg?: string) => {
      const normalized = normalizeColOrder(nextOrderRaw);
      setData((prev) => {
        const next: TrackerData = {
          ...prev,
          settings: {
            ...prev.settings,
            col_order: normalized,
          },
        };
        persistData(next);
        return next;
      });
      if (statusTextMsg) {
        setStatusMsg(statusTextMsg);
      }
    },
    [persistData]
  );

  const moveColumnByOffset = (colId: string, direction: -1 | 1 | 'start' | 'end') => {
    const cur = [...colOrder];
    const fromIdx = cur.indexOf(colId);
    if (fromIdx === -1) return;
    const targetVisualIdx =
      direction === 'start'
        ? 0
        : direction === 'end'
        ? cur.length - 1
        : fromIdx + direction;
    const clampedTo = Math.max(0, Math.min(cur.length - 1, targetVisualIdx));
    if (fromIdx === clampedTo) return;
    cur.splice(fromIdx, 1);
    cur.splice(clampedTo, 0, colId);
    const colTitle = COLS.find((c) => c.id === colId)?.title || colId;
    applyNewColOrder(cur, `Moved '${colTitle}' column to position ${clampedTo + 1}.`);
  };

  const openColumnOrderModal = () => {
    const cur = normalizeColOrder(data.settings.col_order);
    setDialogColOrder(cur);
    setDialogSelectedColId(cur[0] || DEFAULT_COL_ORDER[0]);
    setModal({ type: 'column_order' });
  };

  // Sorted view indices
  const viewIndices = useMemo(
    () => sortOrder(data.projects, data.settings.sort_col, data.settings.sort_asc),
    [data.projects, data.settings.sort_col, data.settings.sort_asc]
  );

  // Close context menu on window click
  useEffect(() => {
    if (!contextMenu) return;
    const close = () => setContextMenu(null);
    window.addEventListener('click', close);
    return () => window.removeEventListener('click', close);
  }, [contextMenu]);

  // Focus inline rename input when opened
  useEffect(() => {
    if (editingKey && renameInputRef.current) {
      renameInputRef.current.focus();
      renameInputRef.current.select();
    }
  }, [editingKey]);

  // Save column widths and order on page unload / exit
  useEffect(() => {
    const onBeforeUnload = () => {
      const normalized = normalizeColWidths(colBase);
      const next: TrackerData = {
        ...data,
        settings: {
          ...data.settings,
          col_widths: normalized,
          col_order: normalizeColOrder(data.settings.col_order),
        },
      };
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(next, null, 2));
      } catch {
        // ignore
      }
    };
    window.addEventListener('beforeunload', onBeforeUnload);
    return () => window.removeEventListener('beforeunload', onBeforeUnload);
  }, [colBase, data]);

  // Column divider dragging — resizes only the dragged column and saves immediately
  const handleColResizeStart = (e: React.MouseEvent, colIdx: number) => {
    e.preventDefault();
    e.stopPropagation();
    let latestWidths = [...colWidths];
    dragColRef.current = {
      colIdx,
      startX: e.clientX,
      startWidths: [...colWidths],
    };

    const onMouseMove = (ev: MouseEvent) => {
      const drag = dragColRef.current;
      if (!drag) return;
      const delta = ev.clientX - drag.startX;
      const cur = [...drag.startWidths];
      cur[drag.colIdx] = Math.max(
        COL_MIN[drag.colIdx],
        Math.min(1600, Math.round(drag.startWidths[drag.colIdx] + delta))
      );
      latestWidths = cur;
      setColBase(cur);
    };

    const onMouseUp = () => {
      dragColRef.current = null;
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);
      const normalized = normalizeColWidths(latestWidths);
      setColBase(normalized);
      setData((prev) => {
        const next: TrackerData = {
          ...prev,
          settings: {
            ...prev.settings,
            col_widths: normalized,
          },
        };
        persistData(next);
        return next;
      });
    };

    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);
  };

  // Sort by column
  const handleSortBy = (colIdx: number) => {
    const colId = COLS[colIdx].id;
    if (!(SORTABLE as readonly string[]).includes(colId)) return;
    setData((prev) => {
      let nextAsc: boolean;
      if (prev.settings.sort_col === colId) {
        nextAsc = !prev.settings.sort_asc;
      } else {
        nextAsc = colId !== 'published';
      }
      const next: TrackerData = {
        ...prev,
        settings: {
          ...prev.settings,
          sort_col: colId,
          sort_asc: nextAsc,
        },
      };
      persistData(next);
      return next;
    });
  };

  // Toggle light/dark theme
  const handleToggleTheme = () => {
    const nextDark = !isDark;
    const nextTheme = nextDark ? 'dark' : 'light';
    const next: TrackerData = {
      ...data,
      settings: {
        ...data.settings,
        theme: nextTheme,
      },
    };
    setData(next);
    persistData(next);
    setStatusMsg(nextDark ? 'Dark mode' : 'Light mode');
  };

  // Update free-text Title column (Column 0 at very left)
  const handleUserTitleChange = (key: string, value: string) => {
    const cleaned = Array.from(value.replace(/[\r\n]+/g, ' '))
      .slice(0, MAX_TITLE_LEN)
      .join('');
    const nextProjects = data.projects.map((p) => {
      if (projectKey(p) !== key) return p;
      return { ...p, user_title: cleaned };
    });
    const next: TrackerData = { ...data, projects: nextProjects };
    setData(next);
    persistData(next);
  };

  const handleUserTitleBlur = (key: string, value: string) => {
    const cleaned = cleanUserTitle(value);
    const nextProjects = data.projects.map((p) => {
      if (projectKey(p) !== key) return p;
      return { ...p, user_title: cleaned };
    });
    const next: TrackerData = { ...data, projects: nextProjects };
    setData(next);
    persistData(next);
  };

  // Update free-text Comment column (Column 9 at far right)
  const handleCommentChange = (key: string, value: string) => {
    const cleaned = Array.from(value.replace(/[\r\n]+/g, ' '))
      .slice(0, MAX_COMMENT_LEN)
      .join('');
    const nextProjects = data.projects.map((p) => {
      if (projectKey(p) !== key) return p;
      return { ...p, comment: cleaned };
    });
    const next: TrackerData = { ...data, projects: nextProjects };
    setData(next);
    persistData(next);
  };

  const handleCommentBlur = (key: string, value: string) => {
    const cleaned = cleanComment(value);
    const nextProjects = data.projects.map((p) => {
      if (projectKey(p) !== key) return p;
      return { ...p, comment: cleaned };
    });
    const next: TrackerData = { ...data, projects: nextProjects };
    setData(next);
    persistData(next);
  };

  // Update Source or Target platform via dropdown box
  const handlePlatformChange = (key: string, field: 'source' | 'target', value: string) => {
    if (field === 'source') {
      const normalized = normalizeSourcePlatform(value);
      const nextProjects = data.projects.map((p) => {
        if (projectKey(p) !== key) return p;
        return { ...p, source: normalized };
      });
      const next: TrackerData = { ...data, projects: nextProjects };
      setData(next);
      persistData(next);
      setStatusMsg(`Source set to ${normalized}.`);
    } else {
      const normalized = normalizeTargetPlatform(value);
      const nextProjects = data.projects.map((p) => {
        if (projectKey(p) !== key) return p;
        return { ...p, target: normalized };
      });
      const next: TrackerData = { ...data, projects: nextProjects };
      setData(next);
      persistData(next);
      setStatusMsg(`Target set to ${normalized}.`);
    }
  };

  // Add project (supports GitHub URLs, owner/repo, Forgejo/Gitea repos like git.magicbean.dev, and download pages like eden-emu.dev/downloads/)
  const handleAddProject = async () => {
    if (busy) return;
    const parsed = parseProjectInput(entryText);
    if (!parsed) {
      setModal({
        type: 'message',
        title: APP_NAME,
        text: 'Enter a GitHub or Forgejo URL such as\nhttps://github.com/owner/repo\nhttps://git.magicbean.dev/MagicBeanDev/Longshot\nhttps://eden-emu.dev/downloads/\nor just owner/repo.',
        icon: 'error',
      });
      return;
    }
    const { owner, repo, html_url } = parsed;
    const candidateKey = projectKey({ owner, repo, html_url });
    const displayRepo = repoDisplayLabel({ owner, repo, html_url });
    if (data.projects.some((p) => projectKey(p) === candidateKey)) {
      setModal({
        type: 'message',
        title: APP_NAME,
        text: `${displayRepo} is already in the list.`,
        icon: 'info',
      });
      return;
    }

    const token = data.settings.token.trim();
    setBusy(true);
    setStatusMsg(`Adding ${displayRepo} ...`);

    try {
      const latest = await getLatest(owner, repo, token, true, html_url);
      let info = {
        owner,
        repo,
        title: repo,
        description: '',
        html_url,
      };
      try {
        info = await fetchRepoInfo(owner, repo, token, html_url);
      } catch (e) {
        if (e instanceof GitHubError && e.kind === 'NotFound') {
          throw e;
        }
        // API unavailable (e.g. rate-limited): the release feed is enough
      }

      let newProj: Project = {
        owner: info.owner,
        repo: info.repo,
        title: info.title,
        user_title: '',
        description: info.description,
        html_url: info.html_url,
        include_prereleases: true,
        fmt: 2,
        seen_id: latest ? latest.id : null,
        seen_tag: latest ? latest.tag : null,
        latest,
        last_checked: nowIso(),
        error: null,
        comment: '',
        source: defaultPlatform(),
        target: defaultPlatform(),
      };
      const cleaned = normalizeProject(newProj);
      if (cleaned) newProj = cleaned;

      setData((prev) => {
        if (prev.projects.some((x) => projectKey(x) === projectKey(newProj))) {
          setStatusMsg('Already in the list.');
          return prev;
        }
        const next: TrackerData = {
          ...prev,
          projects: [...prev.projects, newProj],
        };
        persistData(next);
        return next;
      });
      setEntryText('');
      const msg = newProj.latest
        ? `Added ${newProj.title} - current release ${newProj.latest.tag || newProj.latest.name}.`
        : `Added ${newProj.title} - it has no published releases yet.`;
      setStatusMsg(msg);
    } catch (e) {
      const errMsg = e instanceof Error ? e.message : String(e);
      setStatusMsg('Could not add project.');
      setModal({
        type: 'message',
        title: APP_NAME,
        text: errMsg,
        icon: 'error',
      });
    } finally {
      setBusy(false);
    }
  };

  // Check for updates
  const handleCheckUpdates = useCallback(async () => {
    if (busy) return;
    const snapshot = data.projects.map((p) => ({
      key: projectKey(p),
      owner: p.owner,
      repo: p.repo,
      html_url: p.html_url,
      include_prereleases: p.include_prereleases,
    }));
    if (snapshot.length === 0) {
      setStatusMsg('Nothing to check - add a project first.');
      return;
    }

    const token = data.settings.token.trim();
    setBusy(true);
    setStatusMsg(`Checking ${snapshot.length} project(s) ...`);

    const results: Array<{ key: string; latest: Project['latest']; err: string | null }> = [];
    for (const item of snapshot) {
      try {
        const r = await getLatest(
          item.owner,
          item.repo,
          token,
          item.include_prereleases,
          item.html_url
        );
        results.push({ key: item.key, latest: r, err: null });
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e);
        results.push({ key: item.key, latest: null, err: msg });
        if (e instanceof GitHubError && e.kind === 'RateLimit') {
          break;
        }
      }
    }

    const now = nowIso();
    let errors = 0;
    const nextProjects = data.projects.map((p) => {
      const match = results.find((r) => r.key === projectKey(p));
      if (!match) return p;
      if (match.err) errors++;
      return applyResult(p, match.latest, match.err, now);
    });

    const next: TrackerData = { ...data, projects: nextProjects };
    setData(next);
    persistData(next);
    setBusy(false);

    const updates = nextProjects.filter(hasUpdate).length;
    let msg = `Checked ${results.length} project(s): ${updates} update(s) available`;
    if (errors > 0) {
      msg += `, ${errors} error(s)`;
    }
    const rate = getRateRemaining();
    if (rate !== null) {
      msg += `. API calls left this hour: ${rate}`;
    }
    setStatusMsg(`${msg}.`);
  }, [busy, data, persistData]);

  // Run check on launch if enabled
  const launchCheckedRef = useRef(false);
  useEffect(() => {
    if (loaded && !launchCheckedRef.current) {
      launchCheckedRef.current = true;
      if (data.settings.check_on_launch && data.projects.length > 0) {
        handleCheckUpdates();
      }
    }
  }, [loaded, data.settings.check_on_launch, data.projects.length, handleCheckUpdates]);

  // Mark as seen
  const handleMarkSeen = () => {
    if (selectedKeys.length === 0) {
      setStatusMsg('Select one or more projects first.');
      return;
    }
    let count = 0;
    const nextProjects = data.projects.map((p) => {
      if (!selectedKeys.includes(projectKey(p))) return p;
      if (hasUpdate(p) && p.latest) {
        count++;
        return {
          ...p,
          seen_id: p.latest.id,
          seen_tag: p.latest.tag,
        };
      }
      return p;
    });
    const next: TrackerData = { ...data, projects: nextProjects };
    setData(next);
    persistData(next);
    setStatusMsg(
      count > 0 ? `Marked ${count} project(s) as seen.` : 'No updates to mark in the selection.'
    );
  };

  const firstSelectedProject = useMemo(() => {
    if (selectedKeys.length === 0) return null;
    return data.projects.find((p) => projectKey(p) === selectedKeys[0]) || null;
  }, [data.projects, selectedKeys]);

  // Open release page
  const handleOpenRelease = (proj?: Project | null) => {
    const target = proj ?? firstSelectedProject;
    if (!target) {
      setStatusMsg('Select a project first.');
      return;
    }
    const baseHtml = target.html_url || `https://github.com/${target.owner}/${target.repo}`;
    const fallback =
      baseHtml.endsWith('/downloads/') || baseHtml.endsWith('/downloads')
        ? baseHtml
        : `${baseHtml.replace(/\/+$/, '')}/releases`;
    const url = safeHttpUrl(target.latest?.url, fallback);
    openExternalUrl(url);
  };

  // Open repository
  const handleOpenRepo = () => {
    if (!firstSelectedProject) {
      setStatusMsg('Select a project first.');
      return;
    }
    const url = safeHttpUrl(
      firstSelectedProject.html_url,
      `https://github.com/${firstSelectedProject.owner}/${firstSelectedProject.repo}`
    );
    openExternalUrl(url);
  };

  // Toggle include pre-releases
  const handleTogglePrerelease = () => {
    if (selectedKeys.length === 0) return;
    const first = data.projects.find((p) => selectedKeys.includes(projectKey(p)));
    const nextInclude = !(first ? first.include_prereleases : true);
    const nextProjects = data.projects.map((p) =>
      selectedKeys.includes(projectKey(p)) ? { ...p, include_prereleases: nextInclude } : p
    );
    const next: TrackerData = { ...data, projects: nextProjects };
    setData(next);
    persistData(next);
    setStatusMsg(
      nextInclude
        ? 'Pre-releases included (uses the free release feed). Click "Check for updates" to apply.'
        : 'Stable-only mode uses the REST API. Click "Check for updates" to apply.'
    );
  };

  // Remove selected projects (with confirmation dialog)
  const handlePromptRemove = () => {
    if (selectedKeys.length === 0) {
      setStatusMsg('Select a project first.');
      return;
    }
    const selList = data.projects
      .filter((p) => selectedKeys.includes(projectKey(p)))
      .map(displayName);
    const names = selList.slice(0, 3).join(', ') + (selList.length > 3 ? '...' : '');
    setModal({
      type: 'confirm_remove',
      count: selectedKeys.length,
      names,
      keys: [...selectedKeys],
    });
  };

  // Remove a specific row directly with confirmation dialog
  const handlePromptRemoveRow = (key: string) => {
    const p = data.projects.find((x) => projectKey(x) === key);
    if (!p) return;
    setSelectedKeys([key]);
    setModal({
      type: 'confirm_remove',
      count: 1,
      names: displayName(p),
      keys: [key],
    });
  };

  const confirmRemoveProjects = (keysToRemove: string[]) => {
    const nextProjects = data.projects.filter((p) => !keysToRemove.includes(projectKey(p)));
    const next: TrackerData = { ...data, projects: nextProjects };
    setData(next);
    persistData(next);
    setSelectedKeys([]);
    if (editingKey && keysToRemove.includes(editingKey)) {
      setEditingKey(null);
    }
    if (lastClickedKey && keysToRemove.includes(lastClickedKey)) {
      setLastClickedKey(null);
    }
    if (hoveredRowKey && keysToRemove.includes(hoveredRowKey)) {
      setHoveredRowKey(null);
    }
    setModal({ type: 'none' });
    setStatusMsg(`Removed ${keysToRemove.length} project(s).`);
  };

  // Rename selected project
  const startRenameKey = (key: string) => {
    const p = data.projects.find((x) => projectKey(x) === key);
    if (!p) return;
    setSelectedKeys([key]);
    setEditingKey(key);
    setEditingValue(displayName(p));
  };

  const handleRenameSelected = () => {
    if (selectedKeys.length !== 1) {
      setStatusMsg('Select one project to rename.');
      return;
    }
    startRenameKey(selectedKeys[0]);
  };

  const commitRename = () => {
    if (!editingKey) return;
    const key = editingKey;
    const val = editingValue;
    setEditingKey(null);
    let msg: string | null = null;
    const nextProjects = data.projects.map((p) => {
      if (projectKey(p) !== key) return p;
      const res = applyRename(p, val);
      msg = res.message;
      return res.project;
    });
    if (msg) {
      const next: TrackerData = { ...data, projects: nextProjects };
      setData(next);
      persistData(next);
      setStatusMsg(msg);
    }
  };

  // Reset custom names
  const handleResetNames = () => {
    let count = 0;
    const nextProjects = data.projects.map((p) => {
      if (!selectedKeys.includes(projectKey(p))) return p;
      if (p.custom_name) {
        count++;
        const copy = { ...p };
        delete copy.custom_name;
        return copy;
      }
      return p;
    });
    if (count === 0) {
      setStatusMsg('Nothing to reset: the selection has no custom name.');
      return;
    }
    const next: TrackerData = { ...data, projects: nextProjects };
    setData(next);
    persistData(next);
    setStatusMsg(`Reset ${count} name(s) to the GitHub name.`);
  };

  // Export JSON
  const handleExportJson = () => {
    if (data.projects.length === 0) {
      setModal({
        type: 'message',
        title: APP_NAME,
        text: 'There are no projects to export yet.',
        icon: 'info',
      });
      return;
    }
    const filename = `github_release_tracker_${todayYmd()}.json`;
    const payload = buildExport(data.projects, nowIso());
    const text = JSON.stringify(payload, null, 2);
    const blob = new Blob([text], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    setStatusMsg(
      `Exported ${data.projects.length} project(s) to ${filename} (token not included).`
    );
  };

  // Import JSON
  const handleImportFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    if (file.size > MAX_IMPORT_BYTES) {
      setModal({
        type: 'message',
        title: APP_NAME,
        text: 'Could not read that file as JSON:\nThe file is larger than 5 MB.',
        icon: 'error',
      });
      return;
    }
    try {
      const text = (await file.text()).replace(/^\uFEFF/, '');
      const raw = JSON.parse(text);
      const parsed = parseImport(raw);
      if (!parsed) {
        setModal({
          type: 'message',
          title: APP_NAME,
          text: 'This file has no project list.',
          icon: 'error',
        });
        return;
      }
      if (parsed.projects.length === 0) {
        setModal({
          type: 'message',
          title: APP_NAME,
          text: 'No valid projects found in this file.',
          icon: 'error',
        });
        return;
      }
      setModal({
        type: 'confirm_import',
        projects: parsed.projects,
        skipped: parsed.skipped,
      });
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setModal({
        type: 'message',
        title: APP_NAME,
        text: `Could not read that file as JSON:\n${msg}`,
        icon: 'error',
      });
    }
  };

  const applyImportChoice = (mode: 'merge' | 'replace', incoming: Project[]) => {
    setModal({ type: 'none' });
    if (mode === 'merge') {
      const total = incoming.length;
      const { merged, added } = mergeProjects(data.projects, incoming);
      const next: TrackerData = { ...data, projects: merged };
      setData(next);
      persistData(next);
      setStatusMsg(
        `Imported: ${added} new project(s) added, ${total - added} already in the list. Click "Check for updates" to refresh them.`
      );
    } else {
      const next: TrackerData = { ...data, projects: incoming };
      setData(next);
      persistData(next);
      setSelectedKeys([]);
      setStatusMsg(
        `Imported: list replaced with ${incoming.length} project(s). Click "Check for updates" to refresh them.`
      );
    }
  };

  // Row selection
  const selectRow = (key: string, e?: React.MouseEvent) => {
    let nextSel: string[];
    if (e && (e.ctrlKey || e.metaKey)) {
      nextSel = selectedKeys.includes(key)
        ? selectedKeys.filter((k) => k !== key)
        : [...selectedKeys, key];
      setLastClickedKey(key);
    } else if (e && e.shiftKey && lastClickedKey) {
      const orderedKeys = viewIndices
        .map((ix) => data.projects[ix])
        .filter((proj): proj is Project => Boolean(proj))
        .map((proj) => projectKey(proj));
      const i1 = orderedKeys.indexOf(lastClickedKey);
      const i2 = orderedKeys.indexOf(key);
      if (i1 !== -1 && i2 !== -1) {
        const [lo, hi] = i1 < i2 ? [i1, i2] : [i2, i1];
        nextSel = orderedKeys.slice(lo, hi + 1);
      } else {
        nextSel = [key];
      }
    } else {
      nextSel = [key];
      setLastClickedKey(key);
    }
    setSelectedKeys(nextSel);

    if (nextSel.length === 1) {
      const p = data.projects.find((x) => projectKey(x) === nextSel[0]);
      if (p) {
        if (p.error) setStatusMsg(p.error);
        else if (!p.description) setStatusMsg(NO_DESCRIPTION);
        else setStatusMsg(p.description);
      }
    }
  };

  // Download ready-to-build ZIP package
  const handleDownloadZip = () => {
    const a = document.createElement('a');
    a.href = '/api/download-zip';
    a.download = `github-release-tracker-pyqt6-v${APP_VERSION}.zip`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setStatusMsg(`Downloading github-release-tracker-pyqt6-v${APP_VERSION}.zip ...`);
  };

  // Download single portable .py file directly
  const handleDownloadPy = () => {
    const a = document.createElement('a');
    a.href = '/api/download-py';
    a.download = 'github_release_tracker.py';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setStatusMsg('Downloading portable single-file github_release_tracker.py ...');
  };

  // Download single file from rustFiles
  const handleDownloadSingleFile = (filename: string, content: string) => {
    const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename.split('/').pop() || filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    setStatusMsg(`Downloaded ${filename}.`);
  };

  // Run EXE Builder verification & packaging
  const handleRunExeBuilder = useCallback(async () => {
    setBuilderRunning(true);
    try {
      const [buildRes, srcRes] = await Promise.all([
        fetch('/api/build-exe', { method: 'POST' }),
        fetch('/api/python-source'),
      ]);
      if (buildRes.ok) {
        const bJson = await buildRes.json();
        if (bJson.ok) {
          setBuilderResult(bJson);
          setStatusMsg(`PyQt6 EXE Builder package ready (v${bJson.version}, SHA-256: ${bJson.zipSha256.slice(0, 12)}...).`);
        }
      }
      if (srcRes.ok) {
        const sJson = await srcRes.json();
        if (sJson.files) {
          setRustFiles(sJson.files);
        }
      }
    } catch {
      // ignore
    } finally {
      setBuilderRunning(false);
    }
  }, []);

  const openExeBuilderModal = (tab: 'builder' | 'readme' | 'source' = 'builder') => {
    setBuilderTab(tab);
    setModal({ type: 'exe_builder', initialTab: tab });
    handleRunExeBuilder();
  };

  // Keyboard shortcuts on list view (Delete, F2)
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (modal.type !== 'none' || editingKey) return;
      const activeTag = document.activeElement?.tagName.toLowerCase();
      if (activeTag === 'input' || activeTag === 'select' || activeTag === 'textarea') return;
      if (e.key === 'Delete' && selectedKeys.length > 0) {
        e.preventDefault();
        handlePromptRemove();
      } else if (e.key === 'F2' && selectedKeys.length === 1) {
        e.preventDefault();
        startRenameKey(selectedKeys[0]);
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  });

  const openSettingsModal = () => {
    setSettingsToken(data.settings.token);
    setSettingsCheckOnLaunch(data.settings.check_on_launch);
    setModal({ type: 'settings' });
  };

  const saveSettingsModal = () => {
    const next: TrackerData = {
      ...data,
      settings: {
        ...data.settings,
        token: settingsToken.trim().slice(0, 200),
        check_on_launch: settingsCheckOnLaunch,
      },
    };
    setData(next);
    persistData(next);
    setStatusMsg('Settings saved.');
    setModal({ type: 'none' });
  };

  // Win32 Button helper
  const WinButton = ({
    onClick,
    disabled,
    icon,
    label,
    title,
  }: {
    onClick: () => void;
    disabled?: boolean;
    icon: React.ReactNode;
    label: string;
    title?: string;
  }) => (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={title}
      style={{
        backgroundColor: pal.btn_bg,
        color: disabled ? pal.none_fg : pal.fg,
        borderColor: pal.border,
        height: 30,
      }}
      className="inline-flex items-center justify-center gap-1.5 px-3 rounded-[4px] border text-[13px] whitespace-nowrap shrink-0 transition-colors cursor-pointer disabled:cursor-default active:brightness-95 focus-visible:outline-1"
    >
      <span className="shrink-0 flex items-center">{icon}</span>
      <span>{label}</span>
    </button>
  );

  // Ordered columns resolved from colOrder -> logicalIdx + col definition
  const orderedCols = useMemo(
    () =>
      colOrder
        .map((colId) => {
          const logicalIdx = COLS.findIndex((c) => c.id === colId);
          return logicalIdx >= 0 ? { col: COLS[logicalIdx], logicalIdx } : null;
        })
        .filter((x): x is { col: (typeof COLS)[number]; logicalIdx: number } => x !== null),
    [colOrder]
  );

  return (
    <div
      style={{ backgroundColor: pal.bg, color: pal.fg }}
      className="h-screen w-screen flex flex-col overflow-hidden p-[10px] select-none"
    >
      {/* Hidden file input for JSON import */}
      <input
        ref={fileInputRef}
        type="file"
        accept=".json,application/json"
        className="hidden"
        onChange={handleImportFileChange}
      />

      {/* Row 1: GitHub project label + entry box + Add project button */}
      <div className="flex items-center gap-[8px] h-[28px] shrink-0">
        <label
          htmlFor="repo-entry"
          style={{ color: pal.fg }}
          className="text-[13px] whitespace-nowrap shrink-0"
        >
          Project (GitHub/Forgejo URL, download page, or owner/repo):
        </label>

        <div
          style={{
            backgroundColor: pal.field,
            borderColor: entryFocused ? pal.sel_bg : pal.border,
          }}
          className="flex-1 h-[28px] rounded-[4px] border flex items-center px-[8px]"
        >
          <input
            id="repo-entry"
            type="text"
            maxLength={300}
            value={entryText}
            disabled={busy}
            onFocus={() => setEntryFocused(true)}
            onBlur={() => setEntryFocused(false)}
            onChange={(e) => setEntryText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                handleAddProject();
              }
            }}
            placeholder="owner/repo, https://git.magicbean.dev/MagicBeanDev/Longshot, or https://eden-emu.dev/downloads/"
            style={{
              backgroundColor: 'transparent',
              color: pal.fg,
            }}
            className="w-full h-[20px] outline-none border-none text-[13px] select-text placeholder:opacity-45"
          />
        </div>

        <button
          type="button"
          onClick={handleAddProject}
          disabled={busy}
          style={{
            backgroundColor: pal.btn_bg,
            color: busy ? pal.none_fg : pal.fg,
            borderColor: pal.border,
            height: 28,
          }}
          className="inline-flex items-center justify-center gap-1.5 px-3 rounded-[4px] border text-[13px] whitespace-nowrap shrink-0 cursor-pointer disabled:cursor-default active:brightness-95"
        >
          <Plus size={14} />
          <span>Add project</span>
        </button>
      </div>

      {/* Row 2: Toolbar buttons (Left: Check, Mark as seen, Open release page, Remove | Right: Columns, README, Build .exe, Import, Export, Settings) */}
      <div className="flex items-center justify-between gap-[8px] mt-[6px] h-[30px] shrink-0">
        <div className="flex items-center gap-[8px]">
          <WinButton
            onClick={handleCheckUpdates}
            disabled={busy}
            icon={<RefreshCw size={14} className={busy ? 'animate-spin' : ''} />}
            label="Check for updates"
          />
          <WinButton
            onClick={handleMarkSeen}
            icon={<CheckSquare size={14} />}
            label="Mark as seen"
          />
          <WinButton
            onClick={() => handleOpenRelease()}
            icon={<ExternalLink size={14} />}
            label="Open release page"
          />
          <WinButton
            onClick={handlePromptRemove}
            icon={<Trash2 size={14} />}
            label="Remove"
          />
        </div>

        <div className="flex items-center gap-[8px]">
          <WinButton
            onClick={openColumnOrderModal}
            icon={<ArrowLeftRight size={14} />}
            label="Columns"
            title="Change column order (or drag column headers)"
          />
          <WinButton
            onClick={() => openExeBuilderModal('readme')}
            icon={<FileText size={14} />}
            label="README.md"
            title="View README.md"
          />
          <WinButton
            onClick={() => openExeBuilderModal('builder')}
            icon={<Hammer size={14} />}
            label="Build .exe"
            title="Open Windows EXE Builder"
          />
          <WinButton
            onClick={() => fileInputRef.current?.click()}
            icon={<Download size={14} />}
            label="Import"
          />
          <WinButton
            onClick={handleExportJson}
            icon={<Upload size={14} />}
            label="Export"
          />
          <WinButton
            onClick={openSettingsModal}
            icon={<SettingsIcon size={14} />}
            label="Settings"
          />
        </div>
      </div>

      {/* Row 3: Table with 10 reorderable columns */}
      <div
        ref={listContainerRef}
        onClick={(e) => {
          if (e.target === e.currentTarget) {
            setSelectedKeys([]);
          }
        }}
        style={{
          backgroundColor: pal.field,
          borderColor: pal.border,
        }}
        className="flex-1 mt-[8px] border overflow-auto relative flex flex-col"
      >
        {/* Table Header (drag-and-drop reorderable + right-click menu) */}
        <div
          style={{
            backgroundColor: pal.head_bg,
            borderBottom: `1px solid ${pal.line}`,
            minWidth: colWidths.reduce((a, b) => a + b, 0),
          }}
          className="flex items-center h-[26px] shrink-0 sticky top-0 z-10"
        >
          {orderedCols.map(({ col, logicalIdx }) => {
            const isSortable = (SORTABLE as readonly string[]).includes(col.id);
            const isSorted = data.settings.sort_col === col.id;
            const isHot = hoveredHeaderIdx === logicalIdx;
            const width = colWidths[logicalIdx];
            const isDragTarget = dragOverColId === col.id && draggingColId !== col.id;
            return (
              <div
                key={col.id}
                draggable
                title={`${col.title} — Drag to reorder, right-click for column order options${isSortable ? ', click to sort' : ''}`}
                onDragStart={(e) => {
                  setDraggingColId(col.id);
                  e.dataTransfer.effectAllowed = 'move';
                  e.dataTransfer.setData('text/plain', col.id);
                }}
                onDragOver={(e) => {
                  e.preventDefault();
                  e.dataTransfer.dropEffect = 'move';
                  if (dragOverColId !== col.id) {
                    setDragOverColId(col.id);
                  }
                }}
                onDragLeave={() => {
                  if (dragOverColId === col.id) {
                    setDragOverColId(null);
                  }
                }}
                onDrop={(e) => {
                  e.preventDefault();
                  const fromId = draggingColId || e.dataTransfer.getData('text/plain');
                  setDraggingColId(null);
                  setDragOverColId(null);
                  if (!fromId || fromId === col.id) return;
                  const fromIdx = colOrder.indexOf(fromId);
                  const toIdx = colOrder.indexOf(col.id);
                  if (fromIdx < 0 || toIdx < 0) return;
                  const next = [...colOrder];
                  const [moved] = next.splice(fromIdx, 1);
                  next.splice(toIdx, 0, moved);
                  const colTitle = COLS.find((c) => c.id === fromId)?.title || fromId;
                  applyNewColOrder(next, `Moved "${colTitle}" column.`);
                }}
                onDragEnd={() => {
                  setDraggingColId(null);
                  setDragOverColId(null);
                }}
                onContextMenu={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  setContextMenu({
                    x: e.clientX,
                    y: e.clientY,
                    kind: 'header',
                    colId: col.id,
                  });
                }}
                onMouseEnter={() => setHoveredHeaderIdx(logicalIdx)}
                onMouseLeave={() => setHoveredHeaderIdx(null)}
                onClick={() => handleSortBy(logicalIdx)}
                style={{
                  width,
                  backgroundColor: isDragTarget
                    ? pal.sel_bg
                    : isHot && isSortable
                    ? pal.btn_bg
                    : pal.head_bg,
                  color: isDragTarget ? pal.sel_fg : pal.fg,
                  opacity: draggingColId === col.id ? 0.55 : 1,
                }}
                className={`h-full flex items-center justify-between px-[6px] font-bold text-[13px] relative shrink-0 ${
                  isSortable ? 'cursor-pointer' : 'cursor-grab'
                }`}
              >
                <span className="truncate">{col.title}</span>
                {isSorted && (
                  <span className="text-[9px] ml-1 shrink-0">
                    {data.settings.sort_asc ? '▲' : '▼'}
                  </span>
                )}
                {/* Column separator & resize handle */}
                <div
                  draggable={false}
                  onMouseDown={(e) => {
                    e.stopPropagation();
                    handleColResizeStart(e, logicalIdx);
                  }}
                  onClick={(e) => e.stopPropagation()}
                  style={{ backgroundColor: pal.line }}
                  className="absolute right-0 top-[2px] bottom-[2px] w-[1px] cursor-col-resize after:content-[''] after:absolute after:-left-[3px] after:-right-[3px] after:top-0 after:bottom-0"
                />
              </div>
            );
          })}
        </div>

        {/* Table Rows */}
        <div
          style={{ minWidth: colWidths.reduce((a, b) => a + b, 0) }}
          className="flex-1 flex flex-col"
          onClick={(e) => {
            if (e.target === e.currentTarget) {
              setSelectedKeys([]);
            }
          }}
        >
          {viewIndices.map((projIdx) => {
            const p = data.projects[projIdx];
            if (!p) return null;
            const key = projectKey(p);
            const isSelected = selectedKeys.includes(key);
            const isUpdate = hasUpdate(p);
            const isHovered = hoveredRowKey === key;
            const isEditing = editingKey === key;

            let rowBg = pal.field;
            let rowFg = pal.fg;
            if (isSelected) {
              rowBg = pal.sel_bg;
              rowFg = pal.sel_fg;
            } else if (p.error) {
              rowBg = pal.field;
              rowFg = pal.error_fg;
            } else if (isUpdate) {
              rowBg = pal.update_bg;
              rowFg = pal.update_fg;
            } else if (!p.latest) {
              rowBg = pal.field;
              rowFg = pal.none_fg;
            }

            return (
              <div
                key={key}
                onMouseEnter={() => setHoveredRowKey(key)}
                onMouseLeave={() => setHoveredRowKey((prev) => (prev === key ? null : prev))}
                onClick={(e) => selectRow(key, e)}
                onContextMenu={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  if (!selectedKeys.includes(key)) {
                    selectRow(key);
                  }
                  setContextMenu({
                    x: e.clientX,
                    y: e.clientY,
                    kind: 'row',
                  });
                }}
                style={{
                  backgroundColor: rowBg,
                  color: rowFg,
                  borderBottom: `1px solid ${pal.line}`,
                }}
                className="flex items-center h-[26px] shrink-0 text-[13px]"
              >
                {orderedCols.map(({ col, logicalIdx }, visualPos) => {
                  const isLastVisualCol = visualPos === orderedCols.length - 1;
                  const cellBorderRight = isLastVisualCol ? undefined : `1px solid ${pal.line}`;
                  const cellWidth = colWidths[logicalIdx];

                  if (col.id === 'user_title') {
                    return (
                      <div
                        key={col.id}
                        style={{
                          width: cellWidth,
                          borderRight: cellBorderRight,
                        }}
                        onClick={(e) => {
                          e.stopPropagation();
                          selectRow(key);
                        }}
                        onDoubleClick={(e) => e.stopPropagation()}
                        className="h-full flex items-center px-[4px] shrink-0"
                      >
                        <input
                          type="text"
                          maxLength={MAX_TITLE_LEN}
                          aria-label={`Title for ${displayName(p)}`}
                          placeholder="Add title..."
                          value={p.user_title || ''}
                          onChange={(e) => handleUserTitleChange(key, e.target.value)}
                          onBlur={(e) => handleUserTitleBlur(key, e.target.value)}
                          style={{
                            backgroundColor: 'transparent',
                            color: rowFg,
                          }}
                          className="w-full h-[21px] px-1 outline-none border-none text-[12.5px] select-text placeholder:opacity-45"
                        />
                      </div>
                    );
                  }

                  if (col.id === 'name') {
                    return (
                      <div
                        key={col.id}
                        style={{
                          width: cellWidth,
                          borderRight: cellBorderRight,
                        }}
                        onDoubleClick={(e) => {
                          e.stopPropagation();
                          startRenameKey(key);
                        }}
                        className="h-full flex items-center justify-between px-[6px] shrink-0 relative overflow-hidden"
                      >
                        {isEditing ? (
                          <input
                            ref={renameInputRef}
                            type="text"
                            maxLength={MAX_CUSTOM_NAME}
                            value={editingValue}
                            onChange={(e) => setEditingValue(e.target.value)}
                            onBlur={commitRename}
                            onClick={(e) => e.stopPropagation()}
                            onDoubleClick={(e) => e.stopPropagation()}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter') {
                                e.preventDefault();
                                commitRename();
                              } else if (e.key === 'Escape') {
                                e.preventDefault();
                                setEditingKey(null);
                              }
                            }}
                            style={{
                              backgroundColor: pal.field,
                              color: pal.fg,
                              borderColor: pal.sel_bg,
                            }}
                            className="w-full h-[20px] px-1 border outline-none text-[13px] select-text"
                          />
                        ) : (
                          <>
                            <span className="truncate pr-10">{displayName(p)}</span>
                            {isHovered && (
                              <div className="flex items-center gap-0.5 absolute right-[4px]">
                                <button
                                  type="button"
                                  title="Rename project (F2)"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    startRenameKey(key);
                                  }}
                                  style={{
                                    backgroundColor: rowBg,
                                    color: rowFg,
                                  }}
                                  className="w-[20px] h-[20px] flex items-center justify-center rounded-[2px] cursor-pointer hover:opacity-80"
                                >
                                  <Pencil size={12} />
                                </button>
                                <button
                                  type="button"
                                  title="Remove project (Del)"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    handlePromptRemoveRow(key);
                                  }}
                                  style={{
                                    backgroundColor: rowBg,
                                    color: isSelected ? rowFg : pal.error_fg,
                                  }}
                                  className="w-[20px] h-[20px] flex items-center justify-center rounded-[2px] cursor-pointer hover:opacity-80"
                                >
                                  <Trash2 size={12} />
                                </button>
                              </div>
                            )}
                          </>
                        )}
                      </div>
                    );
                  }

                  if (col.id === 'repo') {
                    return (
                      <div
                        key={col.id}
                        style={{
                          width: cellWidth,
                          borderRight: cellBorderRight,
                        }}
                        onDoubleClick={() => handleOpenRelease(p)}
                        className="h-full flex items-center px-[6px] shrink-0 truncate"
                      >
                        <span className="truncate">{repoDisplayLabel(p)}</span>
                      </div>
                    );
                  }

                  if (col.id === 'source') {
                    return (
                      <div
                        key={col.id}
                        style={{
                          width: cellWidth,
                          borderRight: cellBorderRight,
                        }}
                        onClick={(e) => {
                          e.stopPropagation();
                          selectRow(key);
                        }}
                        onDoubleClick={(e) => e.stopPropagation()}
                        className="h-full flex items-center px-[4px] shrink-0"
                      >
                        <select
                          aria-label={`Source platform for ${displayName(p)}`}
                          value={p.source}
                          onChange={(e) => handlePlatformChange(key, 'source', e.target.value)}
                          style={{
                            backgroundColor: isSelected ? pal.sel_bg : rowBg,
                            color: rowFg,
                            borderColor: isSelected ? 'rgba(255,255,255,0.35)' : pal.border,
                          }}
                          className="w-full h-[21px] px-1 rounded-[3px] border text-[12px] outline-none cursor-pointer"
                        >
                          {SOURCE_PLATFORMS.map((plat: SourcePlatform) => (
                            <option
                              key={plat}
                              value={plat}
                              style={{
                                backgroundColor: pal.field,
                                color: pal.fg,
                              }}
                            >
                              {plat}
                            </option>
                          ))}
                        </select>
                      </div>
                    );
                  }

                  if (col.id === 'target') {
                    return (
                      <div
                        key={col.id}
                        style={{
                          width: cellWidth,
                          borderRight: cellBorderRight,
                        }}
                        onClick={(e) => {
                          e.stopPropagation();
                          selectRow(key);
                        }}
                        onDoubleClick={(e) => e.stopPropagation()}
                        className="h-full flex items-center px-[4px] shrink-0"
                      >
                        <select
                          aria-label={`Target platform for ${displayName(p)}`}
                          value={p.target}
                          onChange={(e) => handlePlatformChange(key, 'target', e.target.value)}
                          style={{
                            backgroundColor: isSelected ? pal.sel_bg : rowBg,
                            color: rowFg,
                            borderColor: isSelected ? 'rgba(255,255,255,0.35)' : pal.border,
                          }}
                          className="w-full h-[21px] px-1 rounded-[3px] border text-[12px] outline-none cursor-pointer"
                        >
                          {TARGET_PLATFORMS.map((plat: TargetPlatform) => (
                            <option
                              key={plat}
                              value={plat}
                              style={{
                                backgroundColor: pal.field,
                                color: pal.fg,
                              }}
                            >
                              {plat}
                            </option>
                          ))}
                        </select>
                      </div>
                    );
                  }

                  if (col.id === 'release') {
                    return (
                      <div
                        key={col.id}
                        style={{
                          width: cellWidth,
                          borderRight: cellBorderRight,
                        }}
                        onDoubleClick={() => handleOpenRelease(p)}
                        className="h-full flex items-center px-[6px] shrink-0 truncate tabular-nums"
                      >
                        <span className="truncate">{releaseLabel(p)}</span>
                      </div>
                    );
                  }

                  if (col.id === 'published') {
                    return (
                      <div
                        key={col.id}
                        style={{
                          width: cellWidth,
                          borderRight: cellBorderRight,
                        }}
                        onDoubleClick={() => handleOpenRelease(p)}
                        className="h-full flex items-center px-[6px] shrink-0 truncate tabular-nums"
                      >
                        <span className="truncate">{publishedLabel(p)}</span>
                      </div>
                    );
                  }

                  if (col.id === 'status') {
                    return (
                      <div
                        key={col.id}
                        style={{
                          width: cellWidth,
                          borderRight: cellBorderRight,
                        }}
                        onDoubleClick={() => handleOpenRelease(p)}
                        className="h-full flex items-center px-[6px] shrink-0 truncate"
                      >
                        <span className="truncate">{statusText(p)}</span>
                      </div>
                    );
                  }

                  if (col.id === 'checked') {
                    return (
                      <div
                        key={col.id}
                        style={{
                          width: cellWidth,
                          borderRight: cellBorderRight,
                        }}
                        onDoubleClick={() => handleOpenRelease(p)}
                        className="h-full flex items-center px-[6px] shrink-0 truncate tabular-nums"
                      >
                        <span className="truncate">{checkedLabel(p)}</span>
                      </div>
                    );
                  }

                  // col.id === 'comment'
                  return (
                    <div
                      key={col.id}
                      style={{
                        width: cellWidth,
                        borderRight: cellBorderRight,
                      }}
                      onClick={(e) => {
                        e.stopPropagation();
                        selectRow(key);
                      }}
                      onDoubleClick={(e) => e.stopPropagation()}
                      className="h-full flex items-center px-[4px] shrink-0"
                    >
                      <input
                        type="text"
                        maxLength={MAX_COMMENT_LEN}
                        aria-label={`Comment for ${displayName(p)}`}
                        placeholder="Add comment..."
                        value={p.comment || ''}
                        onChange={(e) => handleCommentChange(key, e.target.value)}
                        onBlur={(e) => handleCommentBlur(key, e.target.value)}
                        style={{
                          backgroundColor: 'transparent',
                          color: rowFg,
                        }}
                        className="w-full h-[21px] px-1 outline-none border-none text-[12.5px] select-text placeholder:opacity-45"
                      />
                    </div>
                  );
                })}
              </div>
            );
          })}
        </div>
      </div>

      {/* Row 4: Status bar + icon-only theme button */}
      <div className="flex items-center justify-between gap-[8px] h-[28px] mt-[2px] shrink-0">
        <div
          onContextMenu={(e) => {
            e.preventDefault();
            setContextMenu({
              x: e.clientX,
              y: e.clientY,
              kind: 'status',
            });
          }}
          style={{ color: pal.fg }}
          className="flex-1 truncate text-[13px] h-full flex items-center"
        >
          {statusMsg}
        </div>

        <button
          type="button"
          onClick={handleToggleTheme}
          title={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
          style={{
            color: pal.fg,
            width: 28,
            height: 28,
          }}
          className="flex items-center justify-center rounded-[4px] cursor-pointer hover:opacity-80 active:brightness-90 shrink-0"
        >
          {isDark ? <Sun size={15} /> : <Moon size={15} />}
        </button>
      </div>

      {/* Right-click Popup Context Menu */}
      {contextMenu && (
        <div
          style={{
            left: Math.min(contextMenu.x, window.innerWidth - 235),
            top: Math.min(contextMenu.y, window.innerHeight - 250),
            backgroundColor: pal.field,
            color: pal.fg,
            borderColor: pal.border,
          }}
          onClick={(e) => e.stopPropagation()}
          className="fixed z-50 border rounded-[4px] shadow-lg py-1 min-w-[215px] text-[13px]"
        >
          {contextMenu.kind === 'status' ? (
            <button
              type="button"
              onClick={() => {
                navigator.clipboard?.writeText(statusMsg);
                setContextMenu(null);
              }}
              className="w-full text-left px-3 py-1.5 hover:bg-[#0078d4] hover:text-white cursor-pointer"
            >
              Copy
            </button>
          ) : contextMenu.kind === 'header' && contextMenu.colId ? (
            (() => {
              const targetColId = contextMenu.colId;
              const targetColTitle = COLS.find((c) => c.id === targetColId)?.title || targetColId;
              const visIdx = colOrder.indexOf(targetColId);
              const canMoveLeft = visIdx > 0;
              const canMoveRight = visIdx >= 0 && visIdx < colOrder.length - 1;
              return (
                <>
                  <button
                    type="button"
                    disabled={!canMoveLeft}
                    onClick={() => {
                      setContextMenu(null);
                      moveColumnByOffset(targetColId, -1);
                    }}
                    style={{ color: canMoveLeft ? pal.fg : pal.none_fg }}
                    className="w-full text-left px-3 py-1.5 enabled:hover:bg-[#0078d4] enabled:hover:text-white cursor-pointer disabled:cursor-default"
                  >
                    Move &apos;{targetColTitle}&apos; Left
                  </button>
                  <button
                    type="button"
                    disabled={!canMoveRight}
                    onClick={() => {
                      setContextMenu(null);
                      moveColumnByOffset(targetColId, 1);
                    }}
                    style={{ color: canMoveRight ? pal.fg : pal.none_fg }}
                    className="w-full text-left px-3 py-1.5 enabled:hover:bg-[#0078d4] enabled:hover:text-white cursor-pointer disabled:cursor-default"
                  >
                    Move &apos;{targetColTitle}&apos; Right
                  </button>
                  <button
                    type="button"
                    disabled={!canMoveLeft}
                    onClick={() => {
                      setContextMenu(null);
                      moveColumnByOffset(targetColId, 'start');
                    }}
                    style={{ color: canMoveLeft ? pal.fg : pal.none_fg }}
                    className="w-full text-left px-3 py-1.5 enabled:hover:bg-[#0078d4] enabled:hover:text-white cursor-pointer disabled:cursor-default"
                  >
                    Move &apos;{targetColTitle}&apos; to Far Left
                  </button>
                  <button
                    type="button"
                    disabled={!canMoveRight}
                    onClick={() => {
                      setContextMenu(null);
                      moveColumnByOffset(targetColId, 'end');
                    }}
                    style={{ color: canMoveRight ? pal.fg : pal.none_fg }}
                    className="w-full text-left px-3 py-1.5 enabled:hover:bg-[#0078d4] enabled:hover:text-white cursor-pointer disabled:cursor-default"
                  >
                    Move &apos;{targetColTitle}&apos; to Far Right
                  </button>
                  <div style={{ backgroundColor: pal.line }} className="my-1 h-[1px]" />
                  <button
                    type="button"
                    onClick={() => {
                      setContextMenu(null);
                      openColumnOrderModal();
                    }}
                    className="w-full text-left px-3 py-1.5 hover:bg-[#0078d4] hover:text-white cursor-pointer"
                  >
                    Configure Column Order...
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setContextMenu(null);
                      applyNewColOrder([...DEFAULT_COL_ORDER], 'Column order reset to default.');
                    }}
                    className="w-full text-left px-3 py-1.5 hover:bg-[#0078d4] hover:text-white cursor-pointer"
                  >
                    Reset Column Order to Default
                  </button>
                </>
              );
            })()
          ) : (
            <>
              <button
                type="button"
                onClick={() => {
                  setContextMenu(null);
                  handleOpenRelease();
                }}
                className="w-full text-left px-3 py-1.5 hover:bg-[#0078d4] hover:text-white cursor-pointer"
              >
                Open release page
              </button>
              <button
                type="button"
                onClick={() => {
                  setContextMenu(null);
                  handleOpenRepo();
                }}
                className="w-full text-left px-3 py-1.5 hover:bg-[#0078d4] hover:text-white cursor-pointer"
              >
                Open repository
              </button>
              <button
                type="button"
                onClick={() => {
                  setContextMenu(null);
                  handleMarkSeen();
                }}
                className="w-full text-left px-3 py-1.5 hover:bg-[#0078d4] hover:text-white cursor-pointer"
              >
                Mark as seen
              </button>
              <div style={{ backgroundColor: pal.line }} className="my-1 h-[1px]" />
              <button
                type="button"
                disabled={selectedKeys.length !== 1}
                onClick={() => {
                  setContextMenu(null);
                  handleRenameSelected();
                }}
                style={{ color: selectedKeys.length === 1 ? pal.fg : pal.none_fg }}
                className="w-full flex items-center justify-between px-3 py-1.5 enabled:hover:bg-[#0078d4] enabled:hover:text-white cursor-pointer disabled:cursor-default"
              >
                <span>Rename...</span>
                <span className="text-[11px] opacity-75">F2</span>
              </button>
              <button
                type="button"
                disabled={
                  !data.projects.some(
                    (p) => selectedKeys.includes(projectKey(p)) && Boolean(p.custom_name)
                  )
                }
                onClick={() => {
                  setContextMenu(null);
                  handleResetNames();
                }}
                style={{
                  color: data.projects.some(
                    (p) => selectedKeys.includes(projectKey(p)) && Boolean(p.custom_name)
                  )
                    ? pal.fg
                    : pal.none_fg,
                }}
                className="w-full text-left px-3 py-1.5 enabled:hover:bg-[#0078d4] enabled:hover:text-white cursor-pointer disabled:cursor-default"
              >
                Reset name
              </button>
              <button
                type="button"
                onClick={() => {
                  setContextMenu(null);
                  handleTogglePrerelease();
                }}
                className="w-full flex items-center justify-between px-3 py-1.5 hover:bg-[#0078d4] hover:text-white cursor-pointer"
              >
                <span>Include pre-releases</span>
                <span>{firstSelectedProject?.include_prereleases ? '✓' : ''}</span>
              </button>
              <div style={{ backgroundColor: pal.line }} className="my-1 h-[1px]" />
              <button
                type="button"
                onClick={() => {
                  setContextMenu(null);
                  handlePromptRemove();
                }}
                className="w-full text-left px-3 py-1.5 hover:bg-[#0078d4] hover:text-white cursor-pointer"
              >
                Remove
              </button>
            </>
          )}
        </div>
      )}

      {/* Modals (Column Order, Settings, About, MessageBox, Remove Confirm, Import Confirm) */}
      {modal.type !== 'none' && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
          onClick={() => setModal({ type: 'none' })}
        >
          {/* Column Order Dialog (matches PyQt6 ColumnOrderDialog) */}
          {modal.type === 'column_order' && (
            <div
              onClick={(e) => e.stopPropagation()}
              style={{
                backgroundColor: pal.bg,
                color: pal.fg,
                borderColor: pal.border,
                width: 440,
              }}
              className="border rounded-[6px] shadow-2xl overflow-hidden"
            >
              <div
                style={{ backgroundColor: pal.head_bg, borderBottom: `1px solid ${pal.line}` }}
                className="px-3.5 py-2 flex items-center justify-between text-[13px] font-semibold"
              >
                <span>Column Order</span>
                <button
                  type="button"
                  onClick={() => setModal({ type: 'none' })}
                  className="opacity-70 hover:opacity-100 cursor-pointer px-1"
                >
                  ✕
                </button>
              </div>

              <div className="p-[14px] flex flex-col gap-3">
                <p style={{ color: pal.sub_fg }} className="text-[12px] leading-relaxed">
                  Arrange the left-to-right display order of columns (top = far left, bottom = far
                  right). You can also drag and drop column headers directly in the table.
                </p>

                <div className="flex gap-2.5">
                  <div
                    style={{
                      backgroundColor: pal.field,
                      borderColor: pal.border,
                    }}
                    className="flex-1 border rounded-[4px] overflow-hidden flex flex-col"
                  >
                    {dialogColOrder.map((cid, idx) => {
                      const colDef = COLS.find((c) => c.id === cid);
                      const isSel = dialogSelectedColId === cid;
                      return (
                        <button
                          key={cid}
                          type="button"
                          onClick={() => setDialogSelectedColId(cid)}
                          style={{
                            backgroundColor: isSel ? pal.sel_bg : 'transparent',
                            color: isSel ? pal.sel_fg : pal.fg,
                            borderBottom:
                              idx < dialogColOrder.length - 1 ? `1px solid ${pal.line}` : undefined,
                          }}
                          className="w-full text-left px-2.5 py-1.5 text-[13px] flex items-center justify-between cursor-pointer"
                        >
                          <span>
                            {idx + 1}. {colDef?.title || cid}
                          </span>
                          <span className="text-[11px] opacity-65">{cid}</span>
                        </button>
                      );
                    })}
                  </div>

                  <div className="flex flex-col gap-1.5 w-[124px] shrink-0">
                    <button
                      type="button"
                      disabled={dialogColOrder.indexOf(dialogSelectedColId) <= 0}
                      onClick={() => {
                        const i = dialogColOrder.indexOf(dialogSelectedColId);
                        if (i <= 0) return;
                        const next = [...dialogColOrder];
                        [next[i - 1], next[i]] = [next[i], next[i - 1]];
                        setDialogColOrder(next);
                      }}
                      style={{
                        backgroundColor: pal.btn_bg,
                        color:
                          dialogColOrder.indexOf(dialogSelectedColId) > 0 ? pal.fg : pal.none_fg,
                        borderColor: pal.border,
                        height: 28,
                      }}
                      className="rounded-[4px] border text-[12.5px] px-2 cursor-pointer disabled:cursor-default"
                    >
                      ↑ Move Left
                    </button>
                    <button
                      type="button"
                      disabled={
                        dialogColOrder.indexOf(dialogSelectedColId) < 0 ||
                        dialogColOrder.indexOf(dialogSelectedColId) >= dialogColOrder.length - 1
                      }
                      onClick={() => {
                        const i = dialogColOrder.indexOf(dialogSelectedColId);
                        if (i < 0 || i >= dialogColOrder.length - 1) return;
                        const next = [...dialogColOrder];
                        [next[i + 1], next[i]] = [next[i], next[i + 1]];
                        setDialogColOrder(next);
                      }}
                      style={{
                        backgroundColor: pal.btn_bg,
                        color:
                          dialogColOrder.indexOf(dialogSelectedColId) >= 0 &&
                          dialogColOrder.indexOf(dialogSelectedColId) < dialogColOrder.length - 1
                            ? pal.fg
                            : pal.none_fg,
                        borderColor: pal.border,
                        height: 28,
                      }}
                      className="rounded-[4px] border text-[12.5px] px-2 cursor-pointer disabled:cursor-default"
                    >
                      ↓ Move Right
                    </button>
                    <button
                      type="button"
                      disabled={dialogColOrder.indexOf(dialogSelectedColId) <= 0}
                      onClick={() => {
                        const i = dialogColOrder.indexOf(dialogSelectedColId);
                        if (i <= 0) return;
                        const next = [...dialogColOrder];
                        const [moved] = next.splice(i, 1);
                        next.unshift(moved);
                        setDialogColOrder(next);
                      }}
                      style={{
                        backgroundColor: pal.btn_bg,
                        color:
                          dialogColOrder.indexOf(dialogSelectedColId) > 0 ? pal.fg : pal.none_fg,
                        borderColor: pal.border,
                        height: 28,
                      }}
                      className="rounded-[4px] border text-[12.5px] px-2 cursor-pointer disabled:cursor-default"
                    >
                      ⤒ Far Left
                    </button>
                    <button
                      type="button"
                      disabled={
                        dialogColOrder.indexOf(dialogSelectedColId) < 0 ||
                        dialogColOrder.indexOf(dialogSelectedColId) >= dialogColOrder.length - 1
                      }
                      onClick={() => {
                        const i = dialogColOrder.indexOf(dialogSelectedColId);
                        if (i < 0 || i >= dialogColOrder.length - 1) return;
                        const next = [...dialogColOrder];
                        const [moved] = next.splice(i, 1);
                        next.push(moved);
                        setDialogColOrder(next);
                      }}
                      style={{
                        backgroundColor: pal.btn_bg,
                        color:
                          dialogColOrder.indexOf(dialogSelectedColId) >= 0 &&
                          dialogColOrder.indexOf(dialogSelectedColId) < dialogColOrder.length - 1
                            ? pal.fg
                            : pal.none_fg,
                        borderColor: pal.border,
                        height: 28,
                      }}
                      className="rounded-[4px] border text-[12.5px] px-2 cursor-pointer disabled:cursor-default"
                    >
                      ⤓ Far Right
                    </button>
                    <div className="flex-1" />
                    <button
                      type="button"
                      onClick={() => {
                        setDialogColOrder([...DEFAULT_COL_ORDER]);
                        setDialogSelectedColId(DEFAULT_COL_ORDER[0]);
                      }}
                      style={{
                        backgroundColor: pal.btn_bg,
                        color: pal.fg,
                        borderColor: pal.border,
                        height: 28,
                      }}
                      className="rounded-[4px] border text-[12.5px] px-2 cursor-pointer"
                    >
                      Reset Default
                    </button>
                  </div>
                </div>

                <div className="flex items-center justify-end gap-2 pt-1">
                  <button
                    type="button"
                    onClick={() => {
                      applyNewColOrder(dialogColOrder, 'Column order saved.');
                      setModal({ type: 'none' });
                    }}
                    style={{
                      backgroundColor: pal.sel_bg,
                      color: pal.sel_fg,
                      borderColor: pal.sel_bg,
                      width: 84,
                      height: 28,
                    }}
                    className="rounded-[4px] border text-[13px] font-medium cursor-pointer"
                  >
                    Save
                  </button>
                  <button
                    type="button"
                    onClick={() => setModal({ type: 'none' })}
                    style={{
                      backgroundColor: pal.btn_bg,
                      color: pal.fg,
                      borderColor: pal.border,
                      width: 84,
                      height: 28,
                    }}
                    className="rounded-[4px] border text-[13px] cursor-pointer"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* Settings Dialog (matches src/dialogs.rs show_settings) */}
          {modal.type === 'settings' && (
            <div
              onClick={(e) => e.stopPropagation()}
              style={{
                backgroundColor: pal.bg,
                color: pal.fg,
                borderColor: pal.border,
                width: 440,
              }}
              className="border rounded-[6px] shadow-2xl overflow-hidden"
            >
              <div
                style={{ backgroundColor: pal.head_bg, borderBottom: `1px solid ${pal.line}` }}
                className="px-3.5 py-2 flex items-center justify-between text-[13px] font-semibold"
              >
                <span>Settings</span>
                <button
                  type="button"
                  onClick={() => setModal({ type: 'none' })}
                  className="opacity-70 hover:opacity-100 cursor-pointer px-1"
                >
                  ✕
                </button>
              </div>

              <div className="p-[14px] flex flex-col gap-3">
                <div>
                  <label className="block text-[13px] mb-1.5">
                    GitHub personal access token (optional)
                  </label>
                  <div
                    style={{
                      backgroundColor: pal.field,
                      borderColor: pal.border,
                    }}
                    className="h-[28px] rounded-[4px] border px-2 flex items-center"
                  >
                    <input
                      type="password"
                      maxLength={200}
                      value={settingsToken}
                      onChange={(e) => setSettingsToken(e.target.value)}
                      style={{ color: pal.fg }}
                      className="w-full bg-transparent outline-none border-none text-[13px] select-text"
                    />
                  </div>
                </div>

                <p style={{ color: pal.sub_fg }} className="text-[12px] leading-relaxed">
                  Not needed for normal use: releases are read from GitHub&apos;s public feed. A
                  token only helps if the feed is blocked or for stable-only mode. It is stored in
                  plain text in projects.json and is never written to exported files.
                </p>

                <label className="inline-flex items-center gap-2 text-[13px] cursor-pointer">
                  <input
                    type="checkbox"
                    checked={settingsCheckOnLaunch}
                    onChange={(e) => setSettingsCheckOnLaunch(e.target.checked)}
                    className="w-4 h-4 cursor-pointer"
                  />
                  <span>Check for updates when the app starts</span>
                </label>

                <div className="flex items-center justify-between pt-2">
                  <button
                    type="button"
                    onClick={() => setModal({ type: 'about', fromSettings: true })}
                    style={{
                      backgroundColor: pal.btn_bg,
                      color: pal.fg,
                      borderColor: pal.border,
                      width: 84,
                      height: 28,
                    }}
                    className="rounded-[4px] border text-[13px] cursor-pointer"
                  >
                    About
                  </button>

                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={saveSettingsModal}
                      style={{
                        backgroundColor: pal.sel_bg,
                        color: pal.sel_fg,
                        borderColor: pal.sel_bg,
                        width: 84,
                        height: 28,
                      }}
                      className="rounded-[4px] border text-[13px] font-medium cursor-pointer"
                    >
                      Save
                    </button>
                    <button
                      type="button"
                      onClick={() => setModal({ type: 'none' })}
                      style={{
                        backgroundColor: pal.btn_bg,
                        color: pal.fg,
                        borderColor: pal.border,
                        width: 84,
                        height: 28,
                      }}
                      className="rounded-[4px] border text-[13px] cursor-pointer"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* About Dialog (matches src/dialogs.rs show_about) */}
          {modal.type === 'about' && (
            <div
              onClick={(e) => e.stopPropagation()}
              style={{
                backgroundColor: pal.bg,
                color: pal.fg,
                borderColor: pal.border,
                width: 440,
              }}
              className="border rounded-[6px] shadow-2xl overflow-hidden"
            >
              <div
                style={{ backgroundColor: pal.head_bg, borderBottom: `1px solid ${pal.line}` }}
                className="px-3.5 py-2 flex items-center justify-between text-[13px] font-semibold"
              >
                <span>{`About ${APP_NAME}`}</span>
                <button
                  type="button"
                  onClick={() =>
                    setModal(modal.fromSettings ? { type: 'settings' } : { type: 'none' })
                  }
                  className="opacity-70 hover:opacity-100 cursor-pointer px-1"
                >
                  ✕
                </button>
              </div>

              <div className="p-4 flex flex-col gap-3">
                <div className="flex items-start gap-4">
                  <div
                    style={{ backgroundColor: pal.sel_bg, color: pal.sel_fg }}
                    className="w-12 h-12 rounded-[8px] flex items-center justify-center font-bold text-lg shrink-0"
                  >
                    GRT
                  </div>
                  <div className="flex flex-col gap-1">
                    <div className="text-[16px] font-bold">{APP_NAME}</div>
                    <div className="text-[13px]">{`Version ${APP_VERSION}`}</div>
                    <p style={{ color: pal.sub_fg }} className="text-[12px] mt-1 leading-relaxed">
                      Tracks the latest release of the GitHub projects you follow. No account,
                      login or token needed. MIT License.
                    </p>
                    <a
                      href={REPO_URL}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{ color: pal.link }}
                      className="text-[12px] hover:underline mt-1 break-all"
                    >
                      {REPO_URL}
                    </a>
                  </div>
                </div>

                <div className="flex items-center justify-between pt-2">
                  <button
                    type="button"
                    onClick={() => openExeBuilderModal('builder')}
                    style={{
                      backgroundColor: pal.btn_bg,
                      color: pal.fg,
                      borderColor: pal.border,
                      height: 28,
                    }}
                    className="px-3 rounded-[4px] border text-[12px] cursor-pointer"
                  >
                    Open EXE Builder (.zip / .bat)
                  </button>

                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => {
                        const t = `${APP_NAME} v${APP_VERSION}`;
                        navigator.clipboard?.writeText(t);
                        setStatusMsg(`Copied: ${t}`);
                      }}
                      style={{
                        backgroundColor: pal.btn_bg,
                        color: pal.fg,
                        borderColor: pal.border,
                        width: 96,
                        height: 28,
                      }}
                      className="rounded-[4px] border text-[13px] cursor-pointer"
                    >
                      Copy version
                    </button>
                    <button
                      type="button"
                      onClick={() =>
                        setModal(modal.fromSettings ? { type: 'settings' } : { type: 'none' })
                      }
                      style={{
                        backgroundColor: pal.sel_bg,
                        color: pal.sel_fg,
                        borderColor: pal.sel_bg,
                        width: 84,
                        height: 28,
                      }}
                      className="rounded-[4px] border text-[13px] font-medium cursor-pointer"
                    >
                      Close
                    </button>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Message Box Modal */}
          {modal.type === 'message' && (
            <div
              onClick={(e) => e.stopPropagation()}
              style={{
                backgroundColor: pal.bg,
                color: pal.fg,
                borderColor: pal.border,
                width: 380,
              }}
              className="border rounded-[6px] shadow-2xl overflow-hidden"
            >
              <div
                style={{ backgroundColor: pal.head_bg, borderBottom: `1px solid ${pal.line}` }}
                className="px-3.5 py-2 flex items-center justify-between text-[13px] font-semibold"
              >
                <span>{modal.title}</span>
                <button
                  type="button"
                  onClick={() => setModal({ type: 'none' })}
                  className="opacity-70 hover:opacity-100 cursor-pointer px-1"
                >
                  ✕
                </button>
              </div>
              <div className="p-4 flex flex-col gap-4">
                <div className="whitespace-pre-line text-[13px] leading-relaxed">{modal.text}</div>
                <div className="flex justify-end">
                  <button
                    type="button"
                    onClick={() => setModal({ type: 'none' })}
                    style={{
                      backgroundColor: pal.sel_bg,
                      color: pal.sel_fg,
                      borderColor: pal.sel_bg,
                      width: 80,
                      height: 28,
                    }}
                    className="rounded-[4px] border text-[13px] font-medium cursor-pointer"
                  >
                    OK
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* Confirm Remove Modal */}
          {modal.type === 'confirm_remove' && (
            <div
              onClick={(e) => e.stopPropagation()}
              style={{
                backgroundColor: pal.bg,
                color: pal.fg,
                borderColor: pal.border,
                width: 380,
              }}
              className="border rounded-[6px] shadow-2xl overflow-hidden"
            >
              <div
                style={{ backgroundColor: pal.head_bg, borderBottom: `1px solid ${pal.line}` }}
                className="px-3.5 py-2 flex items-center justify-between text-[13px] font-semibold"
              >
                <span>{APP_NAME}</span>
                <button
                  type="button"
                  onClick={() => setModal({ type: 'none' })}
                  className="opacity-70 hover:opacity-100 cursor-pointer px-1"
                >
                  ✕
                </button>
              </div>
              <div className="p-4 flex flex-col gap-4">
                <div className="whitespace-pre-line text-[13px] leading-relaxed">
                  {`Remove ${modal.count} project(s)?\n${modal.names}`}
                </div>
                <div className="flex justify-end gap-2">
                  <button
                    type="button"
                    onClick={() => confirmRemoveProjects(modal.keys)}
                    style={{
                      backgroundColor: pal.sel_bg,
                      color: pal.sel_fg,
                      borderColor: pal.sel_bg,
                      width: 80,
                      height: 28,
                    }}
                    className="rounded-[4px] border text-[13px] font-medium cursor-pointer"
                  >
                    Yes
                  </button>
                  <button
                    type="button"
                    onClick={() => setModal({ type: 'none' })}
                    style={{
                      backgroundColor: pal.btn_bg,
                      color: pal.fg,
                      borderColor: pal.border,
                      width: 80,
                      height: 28,
                    }}
                    className="rounded-[4px] border text-[13px] cursor-pointer"
                  >
                    No
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* Confirm Import Modal (Merge / Replace / Cancel) */}
          {modal.type === 'confirm_import' && (
            <div
              onClick={(e) => e.stopPropagation()}
              style={{
                backgroundColor: pal.bg,
                color: pal.fg,
                borderColor: pal.border,
                width: 440,
              }}
              className="border rounded-[6px] shadow-2xl overflow-hidden"
            >
              <div
                style={{ backgroundColor: pal.head_bg, borderBottom: `1px solid ${pal.line}` }}
                className="px-3.5 py-2 flex items-center justify-between text-[13px] font-semibold"
              >
                <span>{APP_NAME}</span>
                <button
                  type="button"
                  onClick={() => setModal({ type: 'none' })}
                  className="opacity-70 hover:opacity-100 cursor-pointer px-1"
                >
                  ✕
                </button>
              </div>
              <div className="p-4 flex flex-col gap-4">
                <div className="whitespace-pre-line text-[13px] leading-relaxed">
                  {`Found ${modal.projects.length} project(s)${
                    modal.skipped > 0
                      ? ` (${modal.skipped} entries skipped as invalid or duplicate)`
                      : ''
                  }.\n\nYes = Merge: keep your current list and add the new ones\nNo = Replace: discard your current list and use this file\nCancel = do nothing`}
                </div>
                <div className="flex justify-end gap-2">
                  <button
                    type="button"
                    onClick={() => applyImportChoice('merge', modal.projects)}
                    style={{
                      backgroundColor: pal.sel_bg,
                      color: pal.sel_fg,
                      borderColor: pal.sel_bg,
                      width: 80,
                      height: 28,
                    }}
                    className="rounded-[4px] border text-[13px] font-medium cursor-pointer"
                  >
                    Yes
                  </button>
                  <button
                    type="button"
                    onClick={() => applyImportChoice('replace', modal.projects)}
                    style={{
                      backgroundColor: pal.btn_bg,
                      color: pal.fg,
                      borderColor: pal.border,
                      width: 80,
                      height: 28,
                    }}
                    className="rounded-[4px] border text-[13px] cursor-pointer"
                  >
                    No
                  </button>
                  <button
                    type="button"
                    onClick={() => setModal({ type: 'none' })}
                    style={{
                      backgroundColor: pal.btn_bg,
                      color: pal.fg,
                      borderColor: pal.border,
                      width: 80,
                      height: 28,
                    }}
                    className="rounded-[4px] border text-[13px] cursor-pointer"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* EXE Builder & README.md Modal */}
          {modal.type === 'exe_builder' && (
            <div
              onClick={(e) => e.stopPropagation()}
              style={{
                backgroundColor: pal.bg,
                color: pal.fg,
                borderColor: pal.border,
                width: 780,
                maxWidth: '95vw',
                maxHeight: '88vh',
              }}
              className="border rounded-[6px] shadow-2xl overflow-hidden flex flex-col"
            >
              {/* Title bar */}
              <div
                style={{ backgroundColor: pal.head_bg, borderBottom: `1px solid ${pal.line}` }}
                className="px-3.5 py-2 flex items-center justify-between text-[13px] font-semibold shrink-0"
              >
                <span>{`${APP_NAME} v${APP_VERSION} — EXE Builder & README.md`}</span>
                <button
                  type="button"
                  onClick={() => setModal({ type: 'none' })}
                  className="opacity-70 hover:opacity-100 cursor-pointer px-1"
                >
                  ✕
                </button>
              </div>

              {/* Tabs bar */}
              <div
                style={{ borderBottom: `1px solid ${pal.line}`, backgroundColor: pal.head_bg }}
                className="flex items-center gap-1 px-3 pt-1.5 shrink-0"
              >
                {(
                  [
                    { id: 'builder', label: 'PyInstaller EXE Builder (build.bat / .zip)' },
                    { id: 'readme', label: 'README.md' },
                    { id: 'source', label: 'Python / PyQt6 Source & Build Scripts' },
                  ] as const
                ).map((t) => {
                  const active = builderTab === t.id;
                  return (
                    <button
                      key={t.id}
                      type="button"
                      onClick={() => setBuilderTab(t.id)}
                      style={{
                        backgroundColor: active ? pal.bg : 'transparent',
                        color: pal.fg,
                        borderColor: active ? pal.line : 'transparent',
                        borderBottomColor: active ? pal.bg : 'transparent',
                      }}
                      className="px-3 py-1.5 text-[12px] font-medium rounded-t-[4px] border cursor-pointer"
                    >
                      {t.label}
                    </button>
                  );
                })}
              </div>

              {/* Tab Content */}
              <div className="p-4 overflow-y-auto flex-1 flex flex-col gap-3">
                {builderTab === 'builder' && (
                  <>
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div>
                        <div className="text-[14px] font-bold">
                          Portable Single-File PyQt6 App (`github_release_tracker.py`) &amp; EXE Builder
                        </div>
                        <div style={{ color: pal.sub_fg }} className="text-[12px] mt-0.5">
                          100% self-contained in a single `.py` file. Automatically creates `projects.json` &amp; `icon.ico` next to `github_release_tracker.py` in its own directory.
                        </div>
                      </div>

                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          onClick={handleRunExeBuilder}
                          disabled={builderRunning}
                          style={{
                            backgroundColor: pal.btn_bg,
                            color: pal.fg,
                            borderColor: pal.border,
                            height: 28,
                          }}
                          className="px-3 rounded-[4px] border text-[12px] inline-flex items-center gap-1.5 cursor-pointer"
                        >
                          <RefreshCw size={12} className={builderRunning ? 'animate-spin' : ''} />
                          <span>Run Python Tests</span>
                        </button>
                        <button
                          type="button"
                          onClick={handleDownloadPy}
                          style={{
                            backgroundColor: pal.sel_bg,
                            color: pal.sel_fg,
                            borderColor: pal.sel_bg,
                            height: 28,
                          }}
                          className="px-3 rounded-[4px] border text-[12px] font-medium inline-flex items-center gap-1.5 cursor-pointer"
                        >
                          <Download size={13} />
                          <span>Download Portable Single .py (`github_release_tracker.py`)</span>
                        </button>
                      </div>
                    </div>

                    {/* Quick script download buttons */}
                    <div className="flex flex-wrap items-center gap-2">
                      <button
                        type="button"
                        onClick={handleDownloadZip}
                        style={{
                          backgroundColor: pal.btn_bg,
                          color: pal.fg,
                          borderColor: pal.border,
                          height: 26,
                        }}
                        className="px-2.5 rounded-[4px] border text-[12px] cursor-pointer"
                      >
                        Download Full EXE Builder Bundle (.zip)
                      </button>
                      {rustFiles['build.bat'] && (
                        <button
                          type="button"
                          onClick={() =>
                            handleDownloadSingleFile('build.bat', rustFiles['build.bat'])
                          }
                          style={{
                            backgroundColor: pal.btn_bg,
                            color: pal.fg,
                            borderColor: pal.border,
                            height: 26,
                          }}
                          className="px-2.5 rounded-[4px] border text-[12px] cursor-pointer"
                        >
                          Download build.bat
                        </button>
                      )}
                      {rustFiles['build-exe.ps1'] && (
                        <button
                          type="button"
                          onClick={() =>
                            handleDownloadSingleFile('build-exe.ps1', rustFiles['build-exe.ps1'])
                          }
                          style={{
                            backgroundColor: pal.btn_bg,
                            color: pal.fg,
                            borderColor: pal.border,
                            height: 26,
                          }}
                          className="px-2.5 rounded-[4px] border text-[12px] cursor-pointer"
                        >
                          Download build-exe.ps1
                        </button>
                      )}
                      {rustFiles['README.md'] && (
                        <button
                          type="button"
                          onClick={() =>
                            handleDownloadSingleFile('README.md', rustFiles['README.md'])
                          }
                          style={{
                            backgroundColor: pal.btn_bg,
                            color: pal.fg,
                            borderColor: pal.border,
                            height: 26,
                          }}
                          className="px-2.5 rounded-[4px] border text-[12px] cursor-pointer"
                        >
                          Download README.md
                        </button>
                      )}
                    </div>

                    {/* Console Output */}
                    <div>
                      <div className="text-[12px] font-semibold mb-1">EXE Builder Output Log:</div>
                      <pre
                        style={{
                          backgroundColor: pal.field,
                          color: pal.fg,
                          borderColor: pal.border,
                        }}
                        className="p-3 rounded-[4px] border font-mono text-[11.5px] leading-relaxed overflow-x-auto select-text whitespace-pre-wrap max-h-[210px] overflow-y-auto"
                      >
                        {builderRunning
                          ? 'Running EXE Builder verification and packaging ...'
                          : builderResult
                            ? builderResult.logs.join('\n')
                            : 'Click "Re-verify & Build Package" to run.'}
                      </pre>
                    </div>

                    {/* File Manifest Table */}
                    {builderResult && (
                      <div>
                        <div className="text-[12px] font-semibold mb-1">
                          Verified Source &amp; Resource Manifest ({builderResult.manifest.length}{' '}
                          files):
                        </div>
                        <div
                          style={{
                            backgroundColor: pal.field,
                            borderColor: pal.border,
                          }}
                          className="border rounded-[4px] max-h-[140px] overflow-y-auto text-[11.5px] font-mono tabular-nums"
                        >
                          {builderResult.manifest.map((item) => (
                            <div
                              key={item.file}
                              style={{ borderBottom: `1px solid ${pal.line}` }}
                              className="flex items-center justify-between px-2.5 py-1 gap-4"
                            >
                              <span className="font-semibold">{item.file}</span>
                              <span style={{ color: pal.sub_fg }} className="truncate">
                                {item.sha256.slice(0, 16)}... ({item.bytes.toLocaleString()} B)
                              </span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </>
                )}

                {builderTab === 'readme' && (
                  <div className="flex flex-col gap-2 flex-1">
                    <div className="flex items-center justify-between">
                      <span className="text-[13px] font-bold">README.md</span>
                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          onClick={() => {
                            if (rustFiles['README.md']) {
                              navigator.clipboard?.writeText(rustFiles['README.md']);
                              setStatusMsg('Copied README.md to clipboard.');
                            }
                          }}
                          style={{
                            backgroundColor: pal.btn_bg,
                            color: pal.fg,
                            borderColor: pal.border,
                            height: 26,
                          }}
                          className="px-2.5 rounded-[4px] border text-[12px] cursor-pointer"
                        >
                          Copy README.md
                        </button>
                        {rustFiles['README.md'] && (
                          <button
                            type="button"
                            onClick={() =>
                              handleDownloadSingleFile('README.md', rustFiles['README.md'])
                            }
                            style={{
                              backgroundColor: pal.sel_bg,
                              color: pal.sel_fg,
                              borderColor: pal.sel_bg,
                              height: 26,
                            }}
                            className="px-2.5 rounded-[4px] border text-[12px] cursor-pointer"
                          >
                            Download README.md
                          </button>
                        )}
                      </div>
                    </div>
                    <pre
                      style={{
                        backgroundColor: pal.field,
                        color: pal.fg,
                        borderColor: pal.border,
                      }}
                      className="p-3 rounded-[4px] border font-mono text-[12px] leading-relaxed overflow-auto select-text whitespace-pre-wrap max-h-[380px]"
                    >
                      {rustFiles['README.md'] || 'Loading README.md ...'}
                    </pre>
                  </div>
                )}

                {builderTab === 'source' && (
                  <div className="flex flex-col gap-2 flex-1">
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <span className="text-[12px] font-semibold">File:</span>
                        <select
                          value={selectedSourceFile}
                          onChange={(e) => setSelectedSourceFile(e.target.value)}
                          style={{
                            backgroundColor: pal.field,
                            color: pal.fg,
                            borderColor: pal.border,
                          }}
                          className="h-[26px] px-2 rounded-[4px] border text-[12px] outline-none cursor-pointer"
                        >
                          {Object.keys(rustFiles).map((k) => (
                            <option
                              key={k}
                              value={k}
                              style={{ backgroundColor: pal.field, color: pal.fg }}
                            >
                              {k}
                            </option>
                          ))}
                        </select>
                      </div>

                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          onClick={() => {
                            const txt = rustFiles[selectedSourceFile] || '';
                            navigator.clipboard?.writeText(txt);
                            setStatusMsg(`Copied ${selectedSourceFile} to clipboard.`);
                          }}
                          style={{
                            backgroundColor: pal.btn_bg,
                            color: pal.fg,
                            borderColor: pal.border,
                            height: 26,
                          }}
                          className="px-2.5 rounded-[4px] border text-[12px] cursor-pointer"
                        >
                          Copy file
                        </button>
                        <button
                          type="button"
                          onClick={() =>
                            handleDownloadSingleFile(
                              selectedSourceFile,
                              rustFiles[selectedSourceFile] || ''
                            )
                          }
                          style={{
                            backgroundColor: pal.sel_bg,
                            color: pal.sel_fg,
                            borderColor: pal.sel_bg,
                            height: 26,
                          }}
                          className="px-2.5 rounded-[4px] border text-[12px] cursor-pointer"
                        >
                          Download file
                        </button>
                      </div>
                    </div>

                    <pre
                      style={{
                        backgroundColor: pal.field,
                        color: pal.fg,
                        borderColor: pal.border,
                      }}
                      className="p-3 rounded-[4px] border font-mono text-[11.5px] leading-relaxed overflow-auto select-text whitespace-pre max-h-[380px]"
                    >
                      {rustFiles[selectedSourceFile] || 'Loading ...'}
                    </pre>
                  </div>
                )}
              </div>

              {/* Footer */}
              <div
                style={{ borderTop: `1px solid ${pal.line}`, backgroundColor: pal.head_bg }}
                className="px-4 py-2 flex items-center justify-between shrink-0"
              >
                <span style={{ color: pal.sub_fg }} className="text-[12px]">
                  Extract the ZIP and double-click build.bat (or run build-exe.ps1) on Windows 10/11.
                </span>
                <button
                  type="button"
                  onClick={() => setModal({ type: 'none' })}
                  style={{
                    backgroundColor: pal.btn_bg,
                    color: pal.fg,
                    borderColor: pal.border,
                    width: 84,
                    height: 28,
                  }}
                  className="rounded-[4px] border text-[13px] cursor-pointer"
                >
                  Close
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
