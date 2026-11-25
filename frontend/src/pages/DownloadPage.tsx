import React, { useEffect, useState } from 'react'
import {
  ArrowUpRight,
  ClipboardPaste,
  Download,
  FileUp,
  History,
  Loader2,
  Sparkles,
  Trash2,
  X,
} from 'lucide-react'
import type {
  JobItemState,
  ParseHistoryEntry,
  PreviewItem,
  PreviewMeta,
  ViewMode,
} from '../types/api'
import { api, nativeReadClipboard } from '../lib/api'
import { URL_TYPE_LABELS } from '../lib/format'
import { WorkBrowser } from '../components/WorkBrowser'

interface DownloadPageProps {
  items: PreviewItem[]
  previewId: string | null
  previewMeta: PreviewMeta | null
  previewLoading: boolean
  previewStatus: string
  selectedIds: Set<string>
  onChangeSelected: (next: Set<string>) => void
  viewMode: ViewMode
  onChangeViewMode: (mode: ViewMode) => void
  itemStatuses: Record<string, JobItemState>
  onStartPreview: (urls: string[]) => void
  onCancelPreview: () => void
  onStartDownload: (items: PreviewItem[]) => void
  onQuickDownloadUrls: (urls: string[]) => void
  onJumpToCreator: (url: string) => void
  onOpenComments: (item: PreviewItem) => void
  onToast: (kind: 'info' | 'success' | 'warning' | 'error', title: string, detail?: string) => void
}

export const DownloadPage: React.FC<DownloadPageProps> = ({
  items,
  previewId,
  previewMeta,
  previewLoading,
  previewStatus,
  selectedIds,
  onChangeSelected,
  viewMode,
  onChangeViewMode,
  itemStatuses,
  onStartPreview,
  onCancelPreview,
  onStartDownload,
  onQuickDownloadUrls,
  onJumpToCreator,
  onOpenComments,
  onToast,
}) => {
  const [rawText, setRawText] = useState('')
  const [detected, setDetected] = useState<{ url: string; type: string }[]>([])
  const [historyOpen, setHistoryOpen] = useState(false)
  const [historyRows, setHistoryRows] = useState<ParseHistoryEntry[]>([])

  useEffect(() => {
    const timer = window.setTimeout(async () => {
      if (!rawText.trim()) {
        setDetected([])
        return
      }
      try {
        const res = await api.inspectUrls(rawText)
        setDetected(res.urls)
      } catch {
        setDetected([])
      }
    }, 180)
    return () => window.clearTimeout(timer)
  }, [rawText])

  const handlePaste = async () => {
    try {
      const txt = await nativeReadClipboard()
      if (!txt.trim()) {
        onToast('info', '剪贴板为空')
        return
      }
      setRawText((prev) => (prev.trim() ? `${prev.trim()}\n${txt.trim()}` : txt.trim()))
    } catch {
      onToast('warning', '无法读取剪贴板', '请使用 Ctrl+V 手动粘贴')
    }
  }

  const handleImportTxt = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = () => {
      const content = String(reader.result || '')
      if (content.trim()) {
        setRawText((prev) => (prev.trim() ? `${prev.trim()}\n${content.trim()}` : content.trim()))
      }
    }
    reader.readAsText(file)
    e.target.value = ''
  }

  const openHistory = async () => {
    setHistoryOpen(true)
    try {
      const res = await api.getParseHistory('link')
      setHistoryRows(res.items)
    } catch {
      setHistoryRows([])
    }
  }

  const userDetected = detected.find((d) => d.type === 'user')
  const validUrls = detected.map((d) => d.url)

  const handlePreviewClick = () => {
    const targets = validUrls.length > 0 ? validUrls : rawText.split(/\r?\n/).map((s) => s.trim()).filter(Boolean)
    if (targets.length === 0) {
      onToast('warning', '请先输入或粘贴至少一个抖音链接')
      return
    }
    onStartPreview(targets)
  }

  const handleDirectDownload = () => {
    const targets = validUrls.length > 0 ? validUrls : rawText.split(/\r?\n/).map((s) => s.trim()).filter(Boolean)
    if (targets.length === 0) {
      onToast('warning', '请先输入或粘贴至少一个抖音链接')
      return
    }
    onQuickDownloadUrls(targets)
  }

  return (
    <div className="flex flex-col h-full gap-4 p-6 pb-3 overflow-hidden relative">
      {/* Header */}
      <div className="flex items-center justify-between gap-4 shrink-0">
        <div>
          <h1 className="text-xl font-bold tracking-tight">链接下载工作台</h1>
          <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>
            支持直接粘贴抖音分享口令、视频、图文、合集、音乐、直播间及直播回放链接
          </p>
        </div>
        <div className="flex items-center gap-2">
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
            <span>历史链接</span>
          </button>
        </div>
      </div>

      {/* Input Card */}
      <div
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault()
          const file = e.dataTransfer?.files?.[0]
          if (file && file.name.toLowerCase().endsWith('.txt')) {
            const reader = new FileReader()
            reader.onload = () => {
              const content = String(reader.result || '').trim()
              if (content) setRawText((p) => (p.trim() ? `${p.trim()}\n${content}` : content))
            }
            reader.readAsText(file)
            return
          }
          const dropped = e.dataTransfer?.getData('text/plain')
          if (dropped?.trim()) {
            setRawText((p) => (p.trim() ? `${p.trim()}\n${dropped.trim()}` : dropped.trim()))
          }
        }}
        className="rounded-2xl border p-4 shrink-0 space-y-3"
        style={{
          backgroundColor: 'var(--bg-surface)',
          borderColor: 'var(--border-subtle)',
          boxShadow: 'var(--shadow-sm)',
        }}
      >
        <div className="relative">
          <textarea
            value={rawText}
            onChange={(e) => setRawText(e.target.value)}
            rows={3}
            placeholder="在此粘贴抖音链接或分享文案（自动提取其中的链接，支持多行批量解析）…"
            className="w-full rounded-xl border p-3 text-[13px] leading-relaxed outline-none resize-none transition-colors focus:border-[var(--accent)]"
            style={{
              backgroundColor: 'var(--bg-app)',
              borderColor: 'var(--border-subtle)',
              color: 'var(--text-primary)',
            }}
          />
          {rawText && (
            <button
              onClick={() => setRawText('')}
              title="清空"
              className="absolute top-2.5 right-2.5 p-1 rounded-lg hover:bg-[var(--bg-hover)] cursor-pointer"
              style={{ color: 'var(--text-muted)' }}
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>

        {/* Detected link badges */}
        {detected.length > 0 && (
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-[11px] font-medium" style={{ color: 'var(--text-muted)' }}>
              已识别 {detected.length} 条：
            </span>
            {detected.slice(0, 6).map((item, idx) => (
              <span
                key={`${item.url}-${idx}`}
                className="inline-flex items-center gap-1 px-2 py-0.5 rounded-lg text-[11px] font-medium border"
                style={{
                  backgroundColor: 'var(--accent-soft)',
                  borderColor: 'transparent',
                  color: 'var(--accent)',
                }}
              >
                <span>{URL_TYPE_LABELS[item.type] || item.type}</span>
                <span className="opacity-70 max-w-[160px] truncate">{item.url.replace(/^https?:\/\//, '')}</span>
              </span>
            ))}
            {detected.length > 6 && (
              <span className="text-[11px]" style={{ color: 'var(--text-muted)' }}>
                +{detected.length - 6} 条
              </span>
            )}
          </div>
        )}

        {/* Contextual user-homepage jump prompt */}
        {userDetected && (
          <div
            className="flex items-center justify-between gap-3 px-3 py-2 rounded-xl text-xs"
            style={{ backgroundColor: 'var(--accent-soft)', color: 'var(--accent)' }}
          >
            <span>检测到博主主页链接，可在「博主主页」按发布/喜欢/收藏/合集模式及时间范围筛选下载</span>
            <button
              onClick={() => onJumpToCreator(userDetected.url)}
              className="flex items-center gap-1 font-semibold px-2.5 py-1 rounded-lg text-white shrink-0 cursor-pointer"
              style={{ backgroundColor: 'var(--accent)' }}
            >
              <span>前往博主主页</span>
              <ArrowUpRight className="w-3.5 h-3.5" />
            </button>
          </div>
        )}

        {/* Action row */}
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <button
              onClick={handlePaste}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-medium border hover:bg-[var(--bg-muted)] cursor-pointer"
              style={{
                borderColor: 'var(--border-subtle)',
                color: 'var(--text-secondary)',
              }}
            >
              <ClipboardPaste className="w-3.5 h-3.5" />
              <span>粘贴剪贴板</span>
            </button>
            <label
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-medium border hover:bg-[var(--bg-muted)] cursor-pointer"
              style={{
                borderColor: 'var(--border-subtle)',
                color: 'var(--text-secondary)',
              }}
            >
              <FileUp className="w-3.5 h-3.5" />
              <span>导入 .txt</span>
              <input type="file" accept=".txt" onChange={handleImportTxt} className="hidden" />
            </label>
            {previewLoading && (
              <span className="flex items-center gap-1.5 text-xs ml-2" style={{ color: 'var(--accent)' }}>
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                <span className="truncate max-w-[260px]">{previewStatus || '正在解析…'}</span>
              </span>
            )}
          </div>

          <div className="flex items-center gap-2">
            {previewLoading ? (
              <button
                onClick={onCancelPreview}
                className="px-3.5 py-1.5 rounded-xl text-xs font-semibold cursor-pointer"
                style={{ backgroundColor: 'var(--danger-soft)', color: 'var(--danger)' }}
              >
                停止解析
              </button>
            ) : (
              <button
                onClick={handlePreviewClick}
                className="flex items-center gap-1.5 px-4 py-1.5 rounded-xl text-xs font-semibold border cursor-pointer hover:bg-[var(--bg-muted)]"
                style={{
                  borderColor: 'var(--border-strong)',
                  color: 'var(--text-primary)',
                }}
              >
                <Sparkles className="w-3.5 h-3.5" style={{ color: 'var(--accent)' }} />
                <span>解析预览</span>
              </button>
            )}
            <button
              onClick={handleDirectDownload}
              className="flex items-center gap-1.5 px-4 py-1.5 rounded-xl text-xs font-semibold text-white cursor-pointer shadow-xs"
              style={{ backgroundColor: 'var(--accent)' }}
            >
              <Download className="w-3.5 h-3.5" />
              <span>直接下载</span>
            </button>
          </div>
        </div>
      </div>

      {/* Preview WorkBrowser */}
      <WorkBrowser
        items={items}
        selectedIds={selectedIds}
        onChangeSelected={onChangeSelected}
        viewMode={viewMode}
        onChangeViewMode={onChangeViewMode}
        onDownloadSelected={onStartDownload}
        onOpenComments={onOpenComments}
        itemStatuses={itemStatuses}
        loading={previewLoading}
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
              <span className="font-semibold text-sm">历史解析链接</span>
              <div className="flex items-center gap-2">
                {historyRows.length > 0 && (
                  <button
                    onClick={async () => {
                      await api.deleteParseHistory({ scope: 'link' })
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
                  暂无历史解析链接
                </div>
              ) : (
                historyRows.map((row) => (
                  <div
                    key={row.id}
                    className="px-5 py-3 flex items-center justify-between gap-3 hover:bg-[var(--bg-muted)] transition-colors"
                  >
                    <div
                      className="min-w-0 flex-1 cursor-pointer"
                      onClick={() => {
                        setRawText((prev) =>
                          prev.trim() ? `${prev.trim()}\n${row.original_url}` : row.original_url
                        )
                        setHistoryOpen(false)
                      }}
                    >
                      <div className="flex items-center gap-2">
                        <span
                          className="px-1.5 py-0.5 rounded text-[10.5px] font-medium"
                          style={{ backgroundColor: 'var(--accent-soft)', color: 'var(--accent)' }}
                        >
                          {URL_TYPE_LABELS[row.kind] || row.kind}
                        </span>
                        <span className="text-xs font-medium truncate">{row.name}</span>
                      </div>
                      <div className="text-[11px] truncate mt-0.5" style={{ color: 'var(--text-muted)' }}>
                        {row.author_name ? `${row.author_name} · ` : ''}
                        {row.original_url}
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
