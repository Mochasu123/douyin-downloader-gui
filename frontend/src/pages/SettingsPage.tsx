import React, { useEffect, useState } from 'react'
import {
  CheckCircle2,
  Eye,
  EyeOff,
  FolderOpen,
  Globe,
  KeyRound,
  Loader2,
  RefreshCw,
  Save,
  ShieldCheck,
  Wifi,
} from 'lucide-react'
import type { AuthStatus, SettingsPayload, ThemeMode } from '../types/api'
import { api, nativePickDirectory } from '../lib/api'
import { proxyImageUrl } from '../lib/format'

interface SettingsPageProps {
  settings: SettingsPayload | null
  auth: AuthStatus | null
  onSaved: (updated: SettingsPayload, updatedAuth?: AuthStatus) => void
  onThemeChange: (theme: ThemeMode) => void
  onToast: (kind: 'info' | 'success' | 'warning' | 'error', title: string, detail?: string) => void
}

const QUALITY_OPTIONS = [
  { value: 'original', label: '原画探测 (最高上传原片，速度较慢)' },
  { value: 'highest', label: '最高画质 (推荐 · 极速)' },
  { value: '1440p', label: '1440p (2K)' },
  { value: '1080p', label: '1080p (高清)' },
  { value: '720p', label: '720p' },
  { value: '540p', label: '540p' },
  { value: '480p', label: '480p' },
  { value: '360p', label: '360p' },
  { value: 'lowest', label: '最低画质 (省流量)' },
]

export const SettingsPage: React.FC<SettingsPageProps> = ({
  settings,
  auth,
  onSaved,
  onThemeChange,
  onToast,
}) => {
  const [draft, setDraft] = useState<SettingsPayload | null>(settings)
  const [cookieInput, setCookieInput] = useState(settings?.cookie.raw || '')
  const [showCookie, setShowCookie] = useState(false)
  const [saving, setSaving] = useState(false)
  const [verifying, setVerifying] = useState(false)
  const [testingProxy, setTestingProxy] = useState(false)
  const [dirty, setDirty] = useState(false)

  useEffect(() => {
    if (settings) {
      setDraft(JSON.parse(JSON.stringify(settings)))
      setCookieInput(settings.cookie.raw || '')
      setDirty(false)
    }
  }, [settings])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's' && dirty && !saving) {
        e.preventDefault()
        void handleSave()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dirty, saving, draft, cookieInput])

  if (!draft) {
    return (
      <div className="p-8 text-xs" style={{ color: 'var(--text-muted)' }}>
        正在加载设置…
      </div>
    )
  }

  const updateCfg = <K extends keyof SettingsPayload['config']>(
    key: K,
    value: SettingsPayload['config'][K]
  ) => {
    setDraft((prev) =>
      prev ? { ...prev, config: { ...prev.config, [key]: value } } : prev
    )
    setDirty(true)
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      const saved = await api.saveSettings({
        config: draft.config,
        cookie_raw: cookieInput,
        preferences: draft.preferences,
      })
      const refreshedAuth = await api.getAuthStatus(false)
      onSaved(saved, refreshedAuth)
      setDirty(false)
      onToast('success', '配置已保存')
    } catch (err) {
      onToast('error', '保存失败', err instanceof Error ? err.message : String(err))
    } finally {
      setSaving(false)
    }
  }

  const handleVerifyAuth = async () => {
    setVerifying(true)
    try {
      const res = await api.getAuthStatus(true)
      onSaved(draft, res)
      if (res.logged_in) {
        onToast('success', 'Cookie 有效', `已登录：${res.user?.nickname || ''}`)
      } else {
        onToast('warning', 'Cookie 未通过校验', res.error || '请重新登录获取新 Cookie')
      }
    } catch (err) {
      onToast('error', '校验出错', err instanceof Error ? err.message : String(err))
    } finally {
      setVerifying(false)
    }
  }

  const handleTestProxy = async () => {
    setTestingProxy(true)
    try {
      const res = await api.testProxy(draft.config.proxy)
      if (res.ok) {
        onToast('success', '代理连接成功', `响应 ${res.status} · 延迟 ${res.latency_ms} ms`)
      } else {
        onToast('error', '代理连接失败', res.error || '无法连接抖音')
      }
    } finally {
      setTestingProxy(false)
    }
  }

  const loginFlow = auth?.login_flow

  return (
    <div className="flex flex-col h-full overflow-hidden relative">
      <div className="flex-1 overflow-y-auto p-6 pb-20 space-y-5 max-w-4xl">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold tracking-tight">设置中心</h1>
            <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>
              管理登录凭据、画质偏好、存储命名模板与下载并发策略
            </p>
          </div>
          <button
            onClick={handleSave}
            disabled={!dirty || saving}
            className="flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-semibold text-white cursor-pointer disabled:opacity-40 shadow-xs"
            style={{ backgroundColor: 'var(--accent)' }}
          >
            {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
            <span>保存配置</span>
          </button>
        </div>

        {/* 1. Account & Cookie */}
        <section
          className="rounded-2xl border p-5 space-y-4"
          style={{ backgroundColor: 'var(--bg-surface)', borderColor: 'var(--border-subtle)' }}
        >
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2.5">
              <KeyRound className="w-4 h-4" style={{ color: 'var(--accent)' }} />
              <h2 className="font-semibold text-sm">账号登录与 Cookie</h2>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={handleVerifyAuth}
                disabled={verifying}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-medium border hover:bg-[var(--bg-muted)] cursor-pointer"
                style={{ borderColor: 'var(--border-subtle)' }}
              >
                <ShieldCheck className={`w-3.5 h-3.5 ${verifying ? 'animate-spin' : ''}`} />
                <span>检测有效性</span>
              </button>
              {loginFlow?.status === 'waiting' ? (
                <>
                  <button
                    onClick={() => api.extractBrowserLogin()}
                    className="px-3 py-1.5 rounded-xl text-xs font-semibold text-white cursor-pointer"
                    style={{ backgroundColor: 'var(--success)' }}
                  >
                    我已登录，立即提取
                  </button>
                  <button
                    onClick={() => api.cancelBrowserLogin()}
                    className="px-3 py-1.5 rounded-xl text-xs font-medium cursor-pointer"
                    style={{ backgroundColor: 'var(--danger-soft)', color: 'var(--danger)' }}
                  >
                    取消
                  </button>
                </>
              ) : (
                <button
                  onClick={() => api.startBrowserLogin()}
                  className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl text-xs font-semibold text-white cursor-pointer"
                  style={{ backgroundColor: 'var(--accent)' }}
                >
                  <Globe className="w-3.5 h-3.5" />
                  <span>一键浏览器登录</span>
                </button>
              )}
            </div>
          </div>

          {loginFlow?.status === 'waiting' && (
            <div
              className="px-3.5 py-2.5 rounded-xl text-xs flex items-center gap-2"
              style={{ backgroundColor: 'var(--accent-soft)', color: 'var(--accent)' }}
            >
              <Loader2 className="w-3.5 h-3.5 animate-spin shrink-0" />
              <span>{loginFlow.message}</span>
            </div>
          )}

          {auth?.user && (
            <div
              className="flex items-center gap-3 p-3 rounded-xl border"
              style={{ backgroundColor: 'var(--bg-app)', borderColor: 'var(--border-subtle)' }}
            >
              {auth.user.avatar_url && (
                <img
                  src={proxyImageUrl(auth.user.avatar_url)}
                  alt=""
                  className="w-10 h-10 rounded-full object-cover"
                />
              )}
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-1.5 text-sm font-semibold">
                  <span>{auth.user.nickname}</span>
                  <CheckCircle2 className="w-4 h-4" style={{ color: 'var(--success)' }} />
                </div>
                <div className="text-[11px] tabular-nums" style={{ color: 'var(--text-muted)' }}>
                  UID: {auth.user.uid}
                </div>
              </div>
            </div>
          )}

          <div className="space-y-1.5">
            <div className="flex items-center justify-between text-xs">
              <span style={{ color: 'var(--text-secondary)' }}>
                手动 Cookie（包含 sessionid、odin_tt、passport_csrf_token 等字段）
              </span>
              <button
                onClick={() => setShowCookie((v) => !v)}
                className="flex items-center gap-1 text-xs cursor-pointer"
                style={{ color: 'var(--accent)' }}
              >
                {showCookie ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                <span>{showCookie ? '隐藏' : '显示明文'}</span>
              </button>
            </div>
            <textarea
              rows={3}
              value={showCookie ? cookieInput : cookieInput ? '●'.repeat(Math.min(cookieInput.length, 96)) : ''}
              readOnly={!showCookie}
              onChange={(e) => {
                setCookieInput(e.target.value)
                setDirty(true)
              }}
              placeholder={showCookie ? '在此粘贴完整 Cookie 字符串…' : '点击右上角「显示明文」可查看或编辑 Cookie'}
              className="w-full p-3 rounded-xl border font-mono text-xs outline-none resize-none focus:border-[var(--accent)]"
              style={{
                backgroundColor: 'var(--bg-app)',
                borderColor: 'var(--border-subtle)',
                color: 'var(--text-primary)',
              }}
            />
          </div>
        </section>

        {/* 2. Storage & Naming */}
        <section
          className="rounded-2xl border p-5 space-y-4"
          style={{ backgroundColor: 'var(--bg-surface)', borderColor: 'var(--border-subtle)' }}
        >
          <h2 className="font-semibold text-sm">存储路径与命名规则</h2>

          <div className="flex items-center gap-2">
            <span className="text-xs w-24 shrink-0" style={{ color: 'var(--text-secondary)' }}>
              下载目录
            </span>
            <input
              value={draft.config.path}
              onChange={(e) => updateCfg('path', e.target.value)}
              className="flex-1 px-3 py-1.5 rounded-xl border text-xs outline-none focus:border-[var(--accent)]"
              style={{
                backgroundColor: 'var(--bg-app)',
                borderColor: 'var(--border-subtle)',
                color: 'var(--text-primary)',
              }}
            />
            <button
              onClick={async () => {
                const picked = await nativePickDirectory(draft.config.path)
                if (picked) updateCfg('path', picked)
              }}
              className="px-3 py-1.5 rounded-xl text-xs border hover:bg-[var(--bg-muted)] cursor-pointer"
              style={{ borderColor: 'var(--border-subtle)' }}
            >
              选择
            </button>
            <button
              onClick={() => api.openPath(draft.config.path)}
              className="flex items-center gap-1 px-3 py-1.5 rounded-xl text-xs border hover:bg-[var(--bg-muted)] cursor-pointer"
              style={{ borderColor: 'var(--border-subtle)' }}
            >
              <FolderOpen className="w-3.5 h-3.5" />
              <span>打开</span>
            </button>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
            <label className="space-y-1">
              <span style={{ color: 'var(--text-secondary)' }}>作者目录命名方式</span>
              <select
                value={draft.config.author_dir}
                onChange={(e) => updateCfg('author_dir', e.target.value)}
                className="w-full px-3 py-1.5 rounded-xl border outline-none"
                style={{
                  backgroundColor: 'var(--bg-app)',
                  borderColor: 'var(--border-subtle)',
                  color: 'var(--text-primary)',
                }}
              >
                <option value="nickname">仅作者昵称 (nickname)</option>
                <option value="nickname_uid">昵称_sec_uid (唯一推荐)</option>
                <option value="sec_uid">仅 sec_uid</option>
              </select>
            </label>

            <label className="space-y-1">
              <span style={{ color: 'var(--text-secondary)' }}>文件命名模板</span>
              <input
                value={draft.config.filename_template}
                onChange={(e) => updateCfg('filename_template', e.target.value)}
                className="w-full px-3 py-1.5 rounded-xl border font-mono outline-none focus:border-[var(--accent)]"
                style={{
                  backgroundColor: 'var(--bg-app)',
                  borderColor: 'var(--border-subtle)',
                  color: 'var(--text-primary)',
                }}
              />
            </label>
          </div>

          <div className="flex flex-wrap gap-5 text-xs">
            {[
              { key: 'folderstyle', label: '每个作品单独建子文件夹' },
              { key: 'group_by_mode', label: '按模式分组 (post / like / mix)' },
            ].map(({ key, label }) => (
              <label key={key} className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={Boolean(draft.config[key as keyof typeof draft.config])}
                  onChange={(e) => updateCfg(key as keyof typeof draft.config, e.target.checked as never)}
                  className="accent-[var(--accent)]"
                />
                <span>{label}</span>
              </label>
            ))}
          </div>
        </section>

        {/* 3. Quality & Assets */}
        <section
          className="rounded-2xl border p-5 space-y-4"
          style={{ backgroundColor: 'var(--bg-surface)', borderColor: 'var(--border-subtle)' }}
        >
          <h2 className="font-semibold text-sm">画质与附带资源</h2>

          <div className="flex items-center gap-3 text-xs">
            <span className="w-24 shrink-0" style={{ color: 'var(--text-secondary)' }}>
              视频画质
            </span>
            <select
              value={draft.config.video_quality}
              onChange={(e) => updateCfg('video_quality', e.target.value)}
              className="flex-1 max-w-md px-3 py-1.5 rounded-xl border outline-none"
              style={{
                backgroundColor: 'var(--bg-app)',
                borderColor: 'var(--border-subtle)',
                color: 'var(--text-primary)',
              }}
            >
              {QUALITY_OPTIONS.map((q) => (
                <option key={q.value} value={q.value}>
                  {q.label}
                </option>
              ))}
            </select>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-xs pt-1">
            {[
              { key: 'video', label: '下载视频本体' },
              { key: 'cover', label: '保存高清封面' },
              { key: 'music', label: '提取原声音乐' },
              { key: 'avatar', label: '保存作者头像' },
              { key: 'json', label: '保存元数据 JSON' },
              { key: 'live_photo_merge', label: '实况动图自动合并' },
              { key: 'homepage_screenshot', label: '保存博主主页截图' },
              { key: 'author_url', label: '保存博主主页地址文件' },
              { key: 'download_pinned', label: '包含主页置顶作品' },
            ].map(({ key, label }) => (
              <label key={key} className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={Boolean(draft.config[key as keyof typeof draft.config])}
                  onChange={(e) => updateCfg(key as keyof typeof draft.config, e.target.checked as never)}
                  className="accent-[var(--accent)]"
                />
                <span>{label}</span>
              </label>
            ))}
          </div>
        </section>

        {/* 4. Performance & Network */}
        <section
          className="rounded-2xl border p-5 space-y-4"
          style={{ backgroundColor: 'var(--bg-surface)', borderColor: 'var(--border-subtle)' }}
        >
          <h2 className="font-semibold text-sm">性能、网络与策略</h2>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs">
            <div className="space-y-1.5">
              <div className="flex justify-between">
                <span style={{ color: 'var(--text-secondary)' }}>并发下载线程数</span>
                <span className="font-semibold tabular-nums" style={{ color: 'var(--accent)' }}>
                  {draft.config.thread} 线程
                </span>
              </div>
              <input
                type="range"
                min={1}
                max={8}
                value={draft.config.thread}
                onChange={(e) => updateCfg('thread', Number(e.target.value))}
                className="w-full accent-[var(--accent)] cursor-pointer"
              />
            </div>

            <label className="space-y-1.5">
              <span style={{ color: 'var(--text-secondary)' }}>失败重试次数</span>
              <input
                type="number"
                min={0}
                max={15}
                value={draft.config.retry_times}
                onChange={(e) => updateCfg('retry_times', Math.max(0, Number(e.target.value) || 0))}
                className="w-full px-3 py-1.5 rounded-xl border tabular-nums outline-none"
                style={{
                  backgroundColor: 'var(--bg-app)',
                  borderColor: 'var(--border-subtle)',
                  color: 'var(--text-primary)',
                }}
              />
            </label>
          </div>

          <div className="flex items-center gap-2 text-xs">
            <span className="w-24 shrink-0" style={{ color: 'var(--text-secondary)' }}>
              HTTP 代理
            </span>
            <input
              value={draft.config.proxy}
              onChange={(e) => updateCfg('proxy', e.target.value)}
              placeholder="例如 http://127.0.0.1:7897（留空直连）"
              className="flex-1 px-3 py-1.5 rounded-xl border outline-none focus:border-[var(--accent)]"
              style={{
                backgroundColor: 'var(--bg-app)',
                borderColor: 'var(--border-subtle)',
                color: 'var(--text-primary)',
              }}
            />
            <button
              onClick={handleTestProxy}
              disabled={testingProxy}
              className="flex items-center gap-1 px-3 py-1.5 rounded-xl border hover:bg-[var(--bg-muted)] cursor-pointer"
              style={{ borderColor: 'var(--border-subtle)' }}
            >
              {testingProxy ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Wifi className="w-3.5 h-3.5" />}
              <span>测试连通性</span>
            </button>
          </div>

          <div className="flex flex-wrap gap-5 text-xs">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={draft.config.redownload_missing_files}
                onChange={(e) => updateCfg('redownload_missing_files', e.target.checked)}
                className="accent-[var(--accent)]"
              />
              <span>增量下载时若本地文件缺失则补下</span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={Boolean(draft.config.browser_fallback?.enabled)}
                onChange={(e) =>
                  updateCfg('browser_fallback', {
                    ...draft.config.browser_fallback,
                    enabled: e.target.checked,
                  })
                }
                className="accent-[var(--accent)]"
              />
              <span>启用浏览器兜底（反爬拦截时自动补全）</span>
            </label>
          </div>
        </section>

        {/* 4.5 Comments Collection */}
        <section
          className="rounded-2xl border p-5 space-y-3"
          style={{ backgroundColor: 'var(--bg-surface)', borderColor: 'var(--border-subtle)' }}
        >
          <h2 className="font-semibold text-sm">自动评论采集（批量下载时生效）</h2>
          <div className="flex flex-wrap gap-5 text-xs">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={Boolean(draft.config.comments?.enabled)}
                onChange={(e) =>
                  updateCfg('comments', { ...draft.config.comments, enabled: e.target.checked })
                }
                className="accent-[var(--accent)]"
              />
              <span>下载作品时自动导出 *_comments.json</span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={Boolean(draft.config.comments?.include_replies)}
                onChange={(e) =>
                  updateCfg('comments', {
                    ...draft.config.comments,
                    include_replies: e.target.checked,
                  })
                }
                className="accent-[var(--accent)]"
              />
              <span>包含二级回复</span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={Boolean(draft.config.comments?.download_media)}
                onChange={(e) =>
                  updateCfg('comments', {
                    ...draft.config.comments,
                    download_media: e.target.checked,
                  })
                }
                className="accent-[var(--accent)]"
              />
              <span>同时下载评论区图片与实况动图</span>
            </label>
          </div>
        </section>

        {/* 5. Theme */}
        <section
          className="rounded-2xl border p-5 flex items-center justify-between"
          style={{ backgroundColor: 'var(--bg-surface)', borderColor: 'var(--border-subtle)' }}
        >
          <div>
            <h2 className="font-semibold text-sm">界面外观</h2>
            <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>
              切换浅色、深色或跟随 Windows 系统主题
            </p>
          </div>
          <div
            className="flex p-0.5 rounded-xl border text-xs"
            style={{ backgroundColor: 'var(--bg-app)', borderColor: 'var(--border-subtle)' }}
          >
            {([
              { value: 'light', label: '浅色' },
              { value: 'dark', label: '深色' },
              { value: 'system', label: '跟随系统' },
            ] as const).map((t) => (
              <button
                key={t.value}
                onClick={() => {
                  setDraft((p) => (p ? { ...p, preferences: { ...p.preferences, theme: t.value } } : p))
                  onThemeChange(t.value)
                  setDirty(true)
                }}
                className="px-3 py-1 rounded-lg font-medium cursor-pointer"
                style={{
                  backgroundColor: draft.preferences.theme === t.value ? 'var(--bg-surface)' : 'transparent',
                  color: draft.preferences.theme === t.value ? 'var(--accent)' : 'var(--text-muted)',
                }}
              >
                {t.label}
              </button>
            ))}
          </div>
        </section>
      </div>

      {/* Floating Unsaved Changes Bar */}
      {dirty && (
        <div
          className="absolute bottom-4 left-6 right-6 max-w-4xl px-4 py-2.5 rounded-2xl border backdrop-blur-md flex items-center justify-between animate-fade-up"
          style={{
            backgroundColor: 'var(--bg-glass)',
            borderColor: 'var(--accent-ring)',
            boxShadow: 'var(--shadow-lg)',
          }}
        >
          <span className="text-xs font-medium">检测到未保存的配置更改</span>
          <div className="flex items-center gap-2">
            <button
              onClick={() => {
                if (settings) {
                  setDraft(JSON.parse(JSON.stringify(settings)))
                  setCookieInput(settings.cookie.raw || '')
                  setDirty(false)
                }
              }}
              className="px-3 py-1 rounded-lg text-xs hover:bg-[var(--bg-muted)] cursor-pointer"
            >
              还原
            </button>
            <button
              onClick={handleSave}
              disabled={saving}
              className="px-3.5 py-1 rounded-lg text-xs font-semibold text-white cursor-pointer"
              style={{ backgroundColor: 'var(--accent)' }}
            >
              立即保存
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
