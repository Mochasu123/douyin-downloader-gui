import React, { useState } from 'react'
import { Calendar, History, Loader2, Sparkles, Trash2, UserCheck, Users, X } from 'lucide-react'
import type {
  JobItemState,
  ParseHistoryEntry,
  PreviewItem,
  PreviewMeta,
  ViewMode,
} from '../types/api'
import { api } from '../lib/api'
import { formatCount, proxyImageUrl } from '../lib/format'
import { WorkBrowser } from '../components/WorkBrowser'

interface CreatorPageProps {
  url: string
  onChangeUrl: (url: string) => void
  items: PreviewItem[]
  previewMeta: PreviewMeta | null
  previewLoading: boolean
  previewStatus: string
  selectedIds: Set<string>
  onChangeSelected: (next: Set<string>) => void
  viewMode: ViewMode
  onChangeViewMode: (mode: ViewMode) => void
  itemStatuses: Record<string, JobItemState>
  onLoadCreator: (params: {
    sec_uid: string
    mode: string
    limit: number
    start_time: string
    end_time: string
    increase: boolean
  }) => void
  onCancelPreview: () => void
  onStartDownload: (items: PreviewItem[]) => void
  onOpenComments: (item: PreviewItem) => void
  onPreviewItem: (item: PreviewItem) => void
  onRemoveItem: (item: PreviewItem) => void
  onClearItems: () => void
  onToast: (kind: 'info' | 'success' | 'warning' | 'error', title: string, detail?: string) => void
}

const CREATOR_MODES = [
  { value: 'post', label: '主页作品' },
  { value: 'like', label: '喜欢' },
  { value: 'mix', label: '合集' },
  { value: 'music', label: '音乐' },
  { value: 'collect', label: '我的收藏' },
  { value: 'collectmix', label: '收藏夹合集' },
]

export const CreatorPage: React.FC<CreatorPageProps> = ({
  url,
  onChangeUrl,
  items,
  previewMeta,
  previewLoading,
  previewStatus,
  selectedIds,
  onChangeSelected,
  viewMode,
  onChangeViewMode,
  itemStatuses,
  onLoadCreator,
  onCancelPreview,
  onStartDownload,
  onOpenComments,
  onPreviewItem,
  onRemoveItem,
  onClearItems,
  onToast,
}) => {
  const [mode, setMode] = useState('post')
  const [limit, setLimit] = useState(0)
  const [startTime, setStartTime] = useState('')
  const [endTime, setEndTime] = useState('')
  const [increase, setIncrease] = useState(false)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [historyRows, setHistoryRows] = useState<ParseHistoryEntry[]>([])

  const handleLoad = () => {
    const trimmed = url.trim()
    if (!trimmed) {
      onToast('warning', '请输入博主主页链接、sec_uid 或 self')
      return
    }
    onLoadCreator({
      sec_uid: trimmed,
      mode,
      limit: Math.max(0, limit),
      start_time: startTime,
      end_time: endTime,
      increase,
    })
  }

  const openHistory = async () => {
    setHistoryOpen(true)
    try {
      const res = await api.getParseHistory('user')
      setHistoryRows(res.items)
    } catch {
      setHistoryRows([])
    }
  }

  return (
    <div className="flex flex-col h-full gap-4 p-6 pb-3 overflow-hidden relative">
      {/* Header */}
      <div className="flex items-center justify-between gap-4 shrink-0">
        <div>
          <h1 className="text-xl font-bold tracking-tight">博主主页工作台</h1>
          <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>
            按发布作品、喜欢、合集、音乐或自己的收藏加载，支持时间范围精准停页与增量筛选
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => onChangeUrl('self')}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-medium border hover:bg-[var(--bg-muted)] cursor-pointer"
            style={{
              backgroundColor: 'var(--bg-surface)',
              borderColor: 'var(--border-subtle)',
              color: 'var(--accent)',
            }}
          >
            <UserCheck className="w-3.5 h-3.5" />
            <span>我的主页 (self)</span>
          </button>
          <button
            onClick={openHistory}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-medium border hover:bg-[var(--bg-muted)] cursor-pointer"
            style={{
              backgroundColor: 'var(--bg-surface)',
              borderColor: 'var(--border-subtle)',
              color: 'var(--text-secondary)',
            }}
          >
            <History className="w-3.5 h-3.5" />
            <span>历史博主</span>
          </button>
        </div>
      </div>

      {/* Query & Filter Card */}
      <div
        className="rounded-2xl border p-4 shrink-0 space-y-3"
        style={{
          backgroundColor: 'var(--bg-surface)',
          borderColor: 'var(--border-subtle)',
          boxShadow: 'var(--shadow-sm)',
        }}
      >
        <div className="flex flex-wrap items-center gap-2.5">
          <input
            value={url}
            onChange={(e) => onChangeUrl(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleLoad()}
            placeholder="粘贴博主主页链接 (https://www.douyin.com/user/...)、分享口令或 self"
            className="flex-1 min-w-[260px] px-3.5 py-2 rounded-xl border text-[13px] outline-none focus:border-[var(--accent)]"
            style={{
              backgroundColor: 'var(--bg-app)',
              borderColor: 'var(--border-subtle)',
              color: 'var(--text-primary)',
            }}
          />
          {previewLoading ? (
            <button
              onClick={onCancelPreview}
              className="px-4 py-2 rounded-xl text-xs font-semibold cursor-pointer"
              style={{ backgroundColor: 'var(--danger-soft)', color: 'var(--danger)' }}
            >
              停止加载
            </button>
          ) : (
            <button
              onClick={handleLoad}
              className="flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-semibold text-white cursor-pointer shadow-xs"
              style={{ backgroundColor: 'var(--accent)' }}
            >
              <Sparkles className="w-3.5 h-3.5" />
              <span>加载作品</span>
            </button>
          )}
        </div>

        {/* Modes + Filters */}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div
            className="flex flex-wrap p-0.5 rounded-xl border"
            style={{ backgroundColor: 'var(--bg-app)', borderColor: 'var(--border-subtle)' }}
          >
            {CREATOR_MODES.map((m) => (
              <button
                key={m.value}
                onClick={() => setMode(m.value)}
                className="px-3 py-1 rounded-lg text-xs font-medium transition-colors cursor-pointer"
                style={{
                  backgroundColor: mode === m.value ? 'var(--bg-surface)' : 'transparent',
                  color: mode === m.value ? 'var(--accent)' : 'var(--text-muted)',
                  boxShadow: mode === m.value ? 'var(--shadow-sm)' : 'none',
                }}
              >
                {m.label}
              </button>
            ))}
          </div>

          <div className="flex flex-wrap items-center gap-3 text-xs">
            <div className="flex items-center gap-1.5">
              <Calendar className="w-3.5 h-3.5" style={{ color: 'var(--text-muted)' }} />
              <input
                type="date"
                value={startTime}
                onChange={(e) => setStartTime(e.target.value)}
                title="开始日期"
                className="px-2 py-1 rounded-lg border text-xs outline-none"
                style={{
                  backgroundColor: 'var(--bg-app)',
                  borderColor: 'var(--border-subtle)',
                  color: 'var(--text-primary)',
                }}
              />
              <span style={{ color: 'var(--text-muted)' }}>至</span>
              <input
                type="date"
                value={endTime}
                onChange={(e) => setEndTime(e.target.value)}
                title="结束日期"
                className="px-2 py-1 rounded-lg border text-xs outline-none"
                style={{
                  backgroundColor: 'var(--bg-app)',
                  borderColor: 'var(--border-subtle)',
                  color: 'var(--text-primary)',
                }}
              />
            </div>

            <div className="flex items-center gap-1.5">
              <span style={{ color: 'var(--text-muted)' }}>数量上限</span>
              <input
                type="number"
                min={0}
                value={limit}
                onChange={(e) => setLimit(Math.max(0, Number(e.target.value) || 0))}
                className="w-20 px-2 py-1 rounded-lg border text-xs tabular-nums outline-none"
                style={{
                  backgroundColor: 'var(--bg-app)',
                  borderColor: 'var(--border-subtle)',
                  color: 'var(--text-primary)',
                }}
              />
            </div>

            <label className="flex items-center gap-1.5 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={increase}
                onChange={(e) => setIncrease(e.target.checked)}
                className="accent-[var(--accent)]"
              />
              <span>增量下载</span>
            </label>
          </div>
        </div>

        {/* Creator Profile Banner if resolved */}
        {(previewMeta?.url_type === 'user' || previewLoading) && (
          <div
            className="flex items-center justify-between gap-3 pt-2.5 border-t"
            style={{ borderColor: 'var(--border-subtle)' }}
          >
            {previewMeta?.url_type === 'user' ? (
              <div className="flex items-center gap-3 min-w-0">
                {previewMeta.avatar_url ? (
                  <img
                    src={proxyImageUrl(previewMeta.avatar_url)}
                    alt=""
                    className="w-10 h-10 rounded-full object-cover border shrink-0"
                    style={{ borderColor: 'var(--border-subtle)' }}
                  />
                ) : (
                  <div
                    className="w-10 h-10 rounded-full flex items-center justify-center shrink-0"
                    style={{ backgroundColor: 'var(--accent-soft)', color: 'var(--accent)' }}
                  >
                    <Users className="w-5 h-5" />
                  </div>
                )}
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-sm truncate">{previewMeta.author_name}</span>
                    {previewMeta.follower_count > 0 && (
                      <span className="text-[11px] tabular-nums" style={{ color: 'var(--text-muted)' }}>
                        粉丝 {formatCount(previewMeta.follower_count)}
                      </span>
                    )}
                    {previewMeta.aweme_count > 0 && (
                      <span className="text-[11px] tabular-nums" style={{ color: 'var(--text-muted)' }}>
                        · 作品 {previewMeta.aweme_count}
                      </span>
                    )}
                  </div>
                  {previewMeta.signature && (
                    <div className="text-[11.5px] truncate max-w-2xl" style={{ color: 'var(--text-muted)' }}>
                      {previewMeta.signature}
                    </div>
                  )}
                </div>
              </div>
            ) : (
              <div className="flex items-center gap-2 text-xs" style={{ color: 'var(--accent)' }}>
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                <span>{previewStatus || '正在获取博主资料与作品列表…'}</span>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Works browser */}
      <WorkBrowser
        items={items}
        selectedIds={selectedIds}
        onChangeSelected={onChangeSelected}
        viewMode={viewMode}
        onChangeViewMode={onChangeViewMode}
        onDownloadSelected={onStartDownload}
        onOpenComments={onOpenComments}
        onPreviewItem={onPreviewItem}
        onRemoveItem={onRemoveItem}
        onClearItems={onClearItems}
        itemStatuses={itemStatuses}
        loading={previewLoading}
        emptyHint="输入博主主页链接或点击「我的主页 (self)」，然后点击「加载作品」"
      />

      {/* History Modal */}
      {historyOpen && (
        <div className="fixed inset-0 z-40 bg-black/40 backdrop-blur-xs flex items-center justify-center p-4">
          <div
            className="w-full max-w-2xl max-h-[80vh] rounded-2xl border flex flex-col overflow-hidden animate-fade-up"
            style={{
              backgroundColor: 'var(--bg-surface)',
              borderColor: 'var(--border-strong)',
              boxShadow: 'var(--shadow-lg)',
            }}
          >
            <div
              className="px-5 py-3.5 border-b flex items-center justify-between"
              style={{ borderColor: 'var(--border-subtle)' }}
            >
              <span className="font-semibold text-sm">历史博主</span>
              <div className="flex items-center gap-2">
                {historyRows.length > 0 && (
                  <button
                    onClick={async () => {
                      await api.deleteParseHistory({ scope: 'user' })
                      setHistoryRows([])
                    }}
                    className="flex items-center gap-1 text-xs px-2.5 py-1 rounded-lg hover:bg-[var(--danger-soft)] cursor-pointer"
                    style={{ color: 'var(--danger)' }}
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                    <span>清空</span>
                  </button>
                )}
                <button
                  onClick={() => setHistoryOpen(false)}
                  className="p-1 rounded-lg hover:bg-[var(--bg-muted)] cursor-pointer"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            </div>
            <div className="flex-1 overflow-y-auto divide-y" style={{ borderColor: 'var(--border-subtle)' }}>
              {historyRows.length === 0 ? (
                <div className="py-16 text-center text-xs" style={{ color: 'var(--text-muted)' }}>
                  暂无历史博主记录
                </div>
              ) : (
                historyRows.map((row) => (
                  <div
                    key={row.id}
                    className="px-5 py-3 flex items-center justify-between gap-3 hover:bg-[var(--bg-muted)] transition-colors"
                  >
                    <div
                      className="flex items-center gap-3 min-w-0 flex-1 cursor-pointer"
                      onClick={() => {
                        onChangeUrl(row.original_url)
                        setHistoryOpen(false)
                      }}
                    >
                      <img
                        src={`/api/local-avatar/${encodeURIComponent(row.content_id)}`}
                        onError={(e) => {
                          const img = e.currentTarget
                          if (row.avatar_url && !img.dataset.fallback) {
                            img.dataset.fallback = '1'
                            img.src = proxyImageUrl(row.avatar_url)
                          } else {
                            img.style.display = 'none'
                          }
                        }}
                        alt=""
                        className="w-9 h-9 rounded-full object-cover shrink-0 bg-[var(--bg-muted)]"
                      />
                      <div className="min-w-0">
                        <div className="text-xs font-semibold truncate">{row.name}</div>
                        <div className="text-[11px] truncate" style={{ color: 'var(--text-muted)' }}>
                          {row.original_url}
                        </div>
                      </div>
                    </div>
                    <button
                      onClick={async () => {
                        await api.deleteParseHistory({ ids: [row.id] })
                        setHistoryRows((prev) => prev.filter((r) => r.id !== row.id))
                      }}
                      className="p-1.5 rounded-lg hover:bg-[var(--danger-soft)] cursor-pointer"
                      style={{ color: 'var(--text-muted)' }}
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
