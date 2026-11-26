import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type {
  AuthStatus,
  DownloadJob,
  JobItemState,
  LogEntry,
  PageKey,
  PreviewItem,
  PreviewMeta,
  SettingsPayload,
  ThemeMode,
  ToastMessage,
  ViewMode,
} from './types/api'
import { api } from './lib/api'
import { eventsSocket } from './lib/ws'
import { Sidebar } from './components/Sidebar'
import { TransferDock } from './components/TransferDock'
import { LogDrawer } from './components/LogDrawer'
import { ToastContainer } from './components/ToastContainer'
import { MediaPreviewModal } from './components/MediaPreviewModal'
import { DownloadPage } from './pages/DownloadPage'
import { CreatorPage } from './pages/CreatorPage'
import { CommentsPage } from './pages/CommentsPage'
import { TasksPage } from './pages/TasksPage'
import { HistoryPage } from './pages/HistoryPage'
import { SettingsPage } from './pages/SettingsPage'

export function App() {
  const [activePage, setActivePage] = useState<PageKey>('download')
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [logOpen, setLogOpen] = useState(false)
  const [theme, setTheme] = useState<ThemeMode>('light')
  const [viewMode, setViewMode] = useState<ViewMode>('grid')

  const [settings, setSettings] = useState<SettingsPayload | null>(null)
  const [auth, setAuth] = useState<AuthStatus | null>(null)
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [jobs, setJobs] = useState<DownloadJob[]>([])
  const [toasts, setToasts] = useState<ToastMessage[]>([])

  // Link Preview State
  const [linkPreviewId, setLinkPreviewId] = useState<string | null>(null)
  const linkPreviewIdRef = useRef<string | null>(null)
  const [linkItems, setLinkItems] = useState<PreviewItem[]>([])
  const [linkMeta, setLinkMeta] = useState<PreviewMeta | null>(null)
  const [linkLoading, setLinkLoading] = useState(false)
  const [linkStatus, setLinkStatus] = useState('')
  const [linkSelected, setLinkSelected] = useState<Set<string>>(new Set())

  // Creator Preview State
  const [creatorUrl, setCreatorUrl] = useState('')
  const [creatorPreviewId, setCreatorPreviewId] = useState<string | null>(null)
  const creatorPreviewIdRef = useRef<string | null>(null)
  const [creatorItems, setCreatorItems] = useState<PreviewItem[]>([])
  const [creatorMeta, setCreatorMeta] = useState<PreviewMeta | null>(null)
  const [creatorLoading, setCreatorLoading] = useState(false)
  const [creatorStatus, setCreatorStatus] = useState('')
  const [creatorSelected, setCreatorSelected] = useState<Set<string>>(new Set())

  // Comments target
  const [commentsTarget, setCommentsTarget] = useState({ awemeId: '', title: '', author: '' })

  // Interactive media viewer modal
  const [previewModal, setPreviewModal] = useState<{
    scope: 'link' | 'creator'
    awemeId: string
  } | null>(null)

  const pushToast = useCallback(
    (
      kind: ToastMessage['kind'],
      title: string,
      detail?: string,
      extra?: { actionLabel?: string; onAction?: () => void }
    ) => {
      const id = `${Date.now()}_${Math.random().toString(36).slice(2, 7)}`
      setToasts((prev) => [...prev.slice(-3), { id, kind, title, detail, ...extra }])
      window.setTimeout(() => {
        setToasts((prev) => prev.filter((t) => t.id !== id))
      }, 5000)
    },
    []
  )

  // Global Ctrl+L shortcut for log drawer
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'l') {
        e.preventDefault()
        setLogOpen((v) => !v)
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [])

  // Apply theme class
  useEffect(() => {
    const apply = () => {
      const preferDark = window.matchMedia?.('(prefers-color-scheme: dark)').matches
      const isDark = theme === 'dark' || (theme === 'system' && preferDark)
      document.documentElement.classList.toggle('dark', isDark)
    }
    apply()
    const mq = window.matchMedia?.('(prefers-color-scheme: dark)')
    mq?.addEventListener?.('change', apply)
    return () => mq?.removeEventListener?.('change', apply)
  }, [theme])

  // Initial data load
  useEffect(() => {
    void (async () => {
      try {
        const [sett, authRes, taskRes, wsRes] = await Promise.all([
          api.getSettings(),
          api.getAuthStatus(false),
          api.getTasks(),
          api.getPreviewWorkspace().catch(() => null),
        ])
        setSettings(sett)
        setAuth(authRes)
        setJobs(taskRes.jobs)
        if (wsRes?.link) {
          linkPreviewIdRef.current = wsRes.link.preview_id
          setLinkPreviewId(wsRes.link.preview_id)
          setLinkItems(wsRes.link.items || [])
          setLinkMeta(wsRes.link.meta || null)
        }
        if (wsRes?.creator) {
          creatorPreviewIdRef.current = wsRes.creator.preview_id
          setCreatorPreviewId(wsRes.creator.preview_id)
          setCreatorItems(wsRes.creator.items || [])
          setCreatorMeta(wsRes.creator.meta || null)
          if (wsRes.creator.url) setCreatorUrl(wsRes.creator.url)
        }
        if (sett.preferences?.theme) setTheme(sett.preferences.theme)
        if (sett.preferences?.view_mode) setViewMode(sett.preferences.view_mode)
        if (!authRes.has_cookie) {
          setActivePage('settings')
        }
      } catch (err) {
        pushToast('error', '后端初始化失败', err instanceof Error ? err.message : String(err))
      }
    })()
  }, [pushToast])

  // Persistent WebSocket connection (mount-only; uses refs for preview IDs)
  useEffect(() => {
    eventsSocket.connect()
    const unsub = eventsSocket.subscribe((evt) => {
      const { type, data } = evt
      if (type === 'logs_snapshot') {
        setLogs(Array.isArray(data) ? (data as LogEntry[]) : [])
      } else if (type === 'log') {
        setLogs((prev) => [...prev.slice(-499), data as LogEntry])
      } else if (type === 'logs_cleared') {
        setLogs([])
      } else if (type === 'auth_login_state') {
        setAuth((prev) => (prev ? { ...prev, login_flow: data as AuthStatus['login_flow'] } : prev))
      } else if (type === 'auth_updated') {
        setAuth(data as AuthStatus)
        void api.getSettings().then(setSettings)
        pushToast('success', '账号登录成功')
      } else if (type === 'preview_status') {
        const d = data as { preview_id: string; message: string }
        if (d.preview_id === linkPreviewIdRef.current) setLinkStatus(d.message)
        if (d.preview_id === creatorPreviewIdRef.current) setCreatorStatus(d.message)
      } else if (type === 'preview_meta') {
        const d = data as PreviewMeta
        if (d.preview_id === linkPreviewIdRef.current) setLinkMeta(d)
        if (d.preview_id === creatorPreviewIdRef.current) setCreatorMeta(d)
      } else if (type === 'preview_item') {
        const d = data as { preview_id: string; item: PreviewItem; append?: boolean }
        if (d.preview_id === linkPreviewIdRef.current) {
          setLinkItems((prev) => {
            const without = prev.filter((it) => it.aweme_id !== d.item.aweme_id)
            return d.append ? [d.item, ...without] : [...without, d.item]
          })
        } else if (d.preview_id === creatorPreviewIdRef.current) {
          setCreatorItems((prev) => {
            const without = prev.filter((it) => it.aweme_id !== d.item.aweme_id)
            return [...without, d.item]
          })
        }
      } else if (type === 'preview_done') {
        const d = data as { preview_id: string; total: number; cancelled?: boolean }
        if (d.preview_id === linkPreviewIdRef.current) {
          setLinkLoading(false)
          if (!d.cancelled) pushToast('success', '解析完成', `共 ${d.total} 个作品`)
          void api.getPreviewWorkspace().then((ws) => {
            if (ws?.link?.items) setLinkItems(ws.link.items)
          }).catch(() => {})
        }
        if (d.preview_id === creatorPreviewIdRef.current) {
          setCreatorLoading(false)
          if (!d.cancelled) pushToast('success', '加载完成', `共 ${d.total} 个作品`)
        }
      } else if (type === 'preview_error') {
        const d = data as { preview_id: string; error: string }
        if (d.preview_id === linkPreviewIdRef.current) setLinkLoading(false)
        if (d.preview_id === creatorPreviewIdRef.current) setCreatorLoading(false)
        pushToast('error', '解析失败', d.error)
      } else if (type === 'job_update') {
        const job = data as DownloadJob
        setJobs((prev) => {
          const exists = prev.some((j) => j.job_id === job.job_id)
          const old = prev.find((j) => j.job_id === job.job_id)
          if (
            old &&
            ['running', 'paused', 'pending'].includes(old.status) &&
            ['success', 'failed'].includes(job.status)
          ) {
            pushToast(
              job.failed === 0 ? 'success' : 'warning',
              job.failed === 0 ? `下载完成：${job.title}` : `任务结束（部分失败）：${job.title}`,
              `成功 ${job.success} · 跳过 ${job.skipped} · 失败 ${job.failed}`,
              job.output_dir
                ? {
                    actionLabel: '打开目录',
                    onAction: () => void api.openPath(job.output_dir),
                  }
                : undefined
            )
          }
          if (exists) return prev.map((j) => (j.job_id === job.job_id ? job : j))
          return [job, ...prev]
        })
      } else if (type === 'job_deleted') {
        const d = data as { job_id: string }
        setJobs((prev) => prev.filter((j) => j.job_id !== d.job_id))
      }
    })
    return () => {
      unsub()
      eventsSocket.disconnect()
    }
  }, [pushToast])

  const activeJobs = useMemo(
    () => jobs.filter((j) => j.status === 'running' || j.status === 'paused' || j.status === 'pending'),
    [jobs]
  )

  const itemStatusMap = useMemo(() => {
    const map: Record<string, JobItemState> = {}
    for (let i = jobs.length - 1; i >= 0; i--) {
      for (const it of jobs[i].items || []) {
        map[it.aweme_id] = it
      }
    }
    return map
  }, [jobs])

  const errorLogCount = useMemo(
    () => logs.filter((l) => l.level === 'ERROR' || l.level === 'CRITICAL').length,
    [logs]
  )

  const handleThemeCycle = () => {
    const order: ThemeMode[] = ['light', 'dark', 'system']
    const next = order[(order.indexOf(theme) + 1) % order.length]
    setTheme(next)
    void api.saveSettings({ preferences: { theme: next } })
  }

  const handleViewModeChange = (mode: ViewMode) => {
    setViewMode(mode)
    void api.saveSettings({ preferences: { view_mode: mode } })
  }

  const startLinkPreview = async (urls: string[], autoDownload = false) => {
    const pid = linkPreviewIdRef.current || 'ws_link'
    linkPreviewIdRef.current = pid
    setLinkPreviewId(pid)
    setLinkStatus(autoDownload ? '正在解析并准备下载…' : '准备解析…')
    setLinkLoading(true)
    try {
      await api.startPreview({
        preview_id: pid,
        scope: 'link',
        append: true,
        auto_download: autoDownload,
        urls,
      })
    } catch (err) {
      setLinkLoading(false)
      pushToast('error', '启动解析失败', err instanceof Error ? err.message : String(err))
    }
  }

  const startCreatorPreview = async (params: {
    sec_uid: string
    mode: string
    limit: number
    start_time: string
    end_time: string
    increase: boolean
  }) => {
    const pid = creatorPreviewIdRef.current || 'ws_creator'
    creatorPreviewIdRef.current = pid
    setCreatorPreviewId(pid)
    setCreatorItems([])
    setCreatorMeta(null)
    setCreatorSelected(new Set())
    setCreatorStatus('正在获取博主资料与作品…')
    setCreatorLoading(true)
    try {
      await api.startPreview({
        preview_id: pid,
        scope: 'creator',
        append: false,
        ...params,
      })
    } catch (err) {
      setCreatorLoading(false)
      pushToast('error', '加载博主作品失败', err instanceof Error ? err.message : String(err))
    }
  }

  const startDownloadItems = async (previewId: string | null, chosen: PreviewItem[]) => {
    if (!previewId || chosen.length === 0) return
    try {
      await api.startDownload({
        preview_id: previewId,
        aweme_ids: chosen.map((c) => c.aweme_id),
      })
      pushToast('info', '已加入下载队列', `共 ${chosen.length} 个作品`)
    } catch (err) {
      pushToast('error', '创建下载任务失败', err instanceof Error ? err.message : String(err))
    }
  }

  const handleRemoveWorkspaceItem = async (scope: 'link' | 'creator', item: PreviewItem) => {
    if (scope === 'link') {
      setLinkItems((prev) => prev.filter((it) => it.aweme_id !== item.aweme_id))
      setLinkSelected((prev) => {
        const next = new Set(prev)
        next.delete(item.aweme_id)
        return next
      })
    } else {
      setCreatorItems((prev) => prev.filter((it) => it.aweme_id !== item.aweme_id))
      setCreatorSelected((prev) => {
        const next = new Set(prev)
        next.delete(item.aweme_id)
        return next
      })
    }
    try {
      await api.removePreviewWorkspaceItem(scope, item.aweme_id)
    } catch {
      // ignore
    }
  }

  const handleClearWorkspace = async (scope: 'link' | 'creator') => {
    if (scope === 'link') {
      setLinkItems([])
      setLinkMeta(null)
      setLinkSelected(new Set())
    } else {
      setCreatorItems([])
      setCreatorMeta(null)
      setCreatorSelected(new Set())
    }
    try {
      await api.clearPreviewWorkspace(scope)
    } catch {
      // ignore
    }
  }

  const openCommentsForItem = (item: PreviewItem) => {
    setCommentsTarget({
      awemeId: item.aweme_id,
      title: item.title,
      author: item.author_name,
    })
    setActivePage('comments')
  }

  return (
    <div
      className="flex h-screen w-screen overflow-hidden"
      style={{ backgroundColor: 'var(--bg-app)', color: 'var(--text-primary)' }}
    >
      <Sidebar
        activePage={activePage}
        onSelectPage={setActivePage}
        collapsed={sidebarCollapsed}
        onToggleCollapse={() => setSidebarCollapsed((v) => !v)}
        auth={auth}
        activeTaskCount={activeJobs.length}
        logCount={logs.length}
        errorLogCount={errorLogCount}
        logOpen={logOpen}
        onToggleLogs={() => setLogOpen((v) => !v)}
        theme={theme}
        onCycleTheme={handleThemeCycle}
      />

      <main className="flex-1 flex flex-col min-w-0 min-h-0 overflow-hidden">
        <div className="flex-1 min-h-0 overflow-hidden">
          {activePage === 'download' && (
            <DownloadPage
              items={linkItems}
              previewId={linkPreviewId}
              previewMeta={linkMeta}
              previewLoading={linkLoading}
              previewStatus={linkStatus}
              selectedIds={linkSelected}
              onChangeSelected={setLinkSelected}
              viewMode={viewMode}
              onChangeViewMode={handleViewModeChange}
              itemStatuses={itemStatusMap}
              onStartPreview={(urls, autoDl) => startLinkPreview(urls, Boolean(autoDl))}
              onCancelPreview={() => linkPreviewId && void api.cancelPreview(linkPreviewId)}
              onStartDownload={(chosen) => startDownloadItems(linkPreviewId, chosen)}
              onJumpToCreator={(url) => {
                setCreatorUrl(url)
                setActivePage('creator')
              }}
              onOpenComments={openCommentsForItem}
              onPreviewItem={(item) => setPreviewModal({ scope: 'link', awemeId: item.aweme_id })}
              onRemoveItem={(item) => void handleRemoveWorkspaceItem('link', item)}
              onClearItems={() => void handleClearWorkspace('link')}
              onToast={(k, t, d) => pushToast(k, t, d)}
            />
          )}

          {activePage === 'creator' && (
            <CreatorPage
              url={creatorUrl}
              onChangeUrl={setCreatorUrl}
              items={creatorItems}
              previewMeta={creatorMeta}
              previewLoading={creatorLoading}
              previewStatus={creatorStatus}
              selectedIds={creatorSelected}
              onChangeSelected={setCreatorSelected}
              viewMode={viewMode}
              onChangeViewMode={handleViewModeChange}
              itemStatuses={itemStatusMap}
              onLoadCreator={startCreatorPreview}
              onCancelPreview={() => creatorPreviewId && void api.cancelPreview(creatorPreviewId)}
              onStartDownload={(chosen) => startDownloadItems(creatorPreviewId, chosen)}
              onOpenComments={openCommentsForItem}
              onPreviewItem={(item) => setPreviewModal({ scope: 'creator', awemeId: item.aweme_id })}
              onRemoveItem={(item) => void handleRemoveWorkspaceItem('creator', item)}
              onClearItems={() => void handleClearWorkspace('creator')}
              onToast={(k, t, d) => pushToast(k, t, d)}
            />
          )}

          {activePage === 'comments' && (
            <CommentsPage
              initialAwemeId={commentsTarget.awemeId}
              initialTitle={commentsTarget.title}
              initialAuthor={commentsTarget.author}
              defaultDownloadDir={settings?.config.path || ''}
              onToast={(k, t, d) => pushToast(k, t, d)}
            />
          )}

          {activePage === 'tasks' && (
            <TasksPage
              jobs={jobs}
              onRetrySuccess={() => {}}
              onToast={(k, t, d) => pushToast(k, t, d)}
            />
          )}

          {activePage === 'history' && <HistoryPage onToast={(k, t, d) => pushToast(k, t, d)} />}

          {activePage === 'settings' && (
            <SettingsPage
              settings={settings}
              auth={auth}
              onSaved={(updatedSettings, updatedAuth) => {
                setSettings(updatedSettings)
                if (updatedAuth) setAuth(updatedAuth)
              }}
              onThemeChange={setTheme}
              onToast={(k, t, d) => pushToast(k, t, d)}
            />
          )}
        </div>

        <TransferDock activeJobs={activeJobs} onOpenTasks={() => setActivePage('tasks')} />
      </main>

      <LogDrawer
        open={logOpen}
        logs={logs}
        onClose={() => setLogOpen(false)}
        onClear={() => void api.clearLogs()}
      />

      <ToastContainer
        toasts={toasts}
        onDismiss={(id) => setToasts((prev) => prev.filter((t) => t.id !== id))}
      />

      {previewModal && (
        <MediaPreviewModal
          previewId={
            previewModal.scope === 'link'
              ? linkPreviewId || 'ws_link'
              : creatorPreviewId || 'ws_creator'
          }
          items={previewModal.scope === 'link' ? linkItems : creatorItems}
          activeAwemeId={previewModal.awemeId}
          onSelectAweme={(awemeId) =>
            setPreviewModal((prev) => (prev ? { ...prev, awemeId } : null))
          }
          onClose={() => setPreviewModal(null)}
          onDownloadItem={(item) =>
            void startDownloadItems(
              previewModal.scope === 'link'
                ? linkPreviewId || 'ws_link'
                : creatorPreviewId || 'ws_creator',
              [item]
            )
          }
          onOpenComments={openCommentsForItem}
        />
      )}
    </div>
  )
}

export default App
