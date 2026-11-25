import React, { useEffect, useState } from 'react'
import {
  ChevronLeft,
  ChevronRight,
  Copy,
  ExternalLink,
  FolderOpen,
  LayoutGrid,
  List,
  RefreshCw,
  Search,
  Trash2,
} from 'lucide-react'
import type { HistoryItem, HistoryStats, ViewMode } from '../types/api'
import { api } from '../lib/api'
import { formatTimestamp } from '../lib/format'
import { CoverImage } from '../components/CoverImage'

interface HistoryPageProps {
  onToast: (kind: 'info' | 'success' | 'warning' | 'error', title: string, detail?: string) => void
}

const TYPE_LABELS: Record<string, string> = {
  video: '视频',
  gallery: '图文',
  music: '音乐',
  live: '直播',
  live_replay: '直播回放',
}

export const HistoryPage: React.FC<HistoryPageProps> = ({ onToast }) => {
  const [items, setItems] = useState<HistoryItem[]>([])
  const [stats, setStats] = useState<HistoryStats | null>(null)
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [viewMode, setViewMode] = useState<ViewMode>('grid')

  const [q, setQ] = useState('')
  const [author, setAuthor] = useState('')
  const [awemeType, setAwemeType] = useState('')
  const [sort, setSort] = useState<'download_time' | 'create_time'>('download_time')

  const pageSize = 40

  const load = async (targetPage = page) => {
    setLoading(true)
    try {
      const [histRes, statsRes] = await Promise.all([
        api.getHistory({ page: targetPage, size: pageSize, q, author, aweme_type: awemeType, sort }),
        api.getHistoryStats(),
      ])
      setItems(histRes.items)
      setTotal(histRes.total)
      setStats(statsRes)
    } catch (err) {
      onToast('error', '加载历史记录失败', err instanceof Error ? err.message : String(err))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load(1)
    setPage(1)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [awemeType, sort])

  const maxPage = Math.max(1, Math.ceil(total / pageSize))

  const handleDelete = async (awemeId: string) => {
    try {
      await api.deleteHistory([awemeId], false)
      onToast('info', '已从下载记录移除')
      void load(page)
    } catch (err) {
      onToast('error', '删除失败', err instanceof Error ? err.message : String(err))
    }
  }

  return (
    <div className="flex flex-col h-full gap-4 p-6 pb-3 overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between gap-4 shrink-0">
        <div>
          <h1 className="text-xl font-bold tracking-tight">下载历史与媒体库</h1>
          <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>
            浏览已归档的本地作品，支持快速打开播放、在资源管理器中定位与按作者筛选
          </p>
        </div>
        <button
          onClick={() => load(page)}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-medium border hover:bg-[var(--bg-muted)] cursor-pointer"
          style={{
            backgroundColor: 'var(--bg-surface)',
            borderColor: 'var(--border-subtle)',
            color: 'var(--text-secondary)',
          }}
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          <span>刷新</span>
        </button>
      </div>

      {/* Stats Strip */}
      {stats && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 shrink-0">
          {[
            { label: '累计已下载', value: stats.total_count, sub: `涉及 ${stats.author_count} 位作者` },
            { label: '视频作品', value: stats.video_count, sub: 'MP4 高清归档' },
            { label: '图文作品', value: stats.gallery_count, sub: '无水印图集 / 实况' },
            { label: '近 7 天新增', value: stats.recent_7d_count, sub: '持续增量同步' },
          ].map((card) => (
            <div
              key={card.label}
              className="rounded-2xl border px-4 py-3"
              style={{
                backgroundColor: 'var(--bg-surface)',
                borderColor: 'var(--border-subtle)',
                boxShadow: 'var(--shadow-sm)',
              }}
            >
              <div className="text-[11.5px]" style={{ color: 'var(--text-muted)' }}>
                {card.label}
              </div>
              <div className="text-xl font-bold tabular-nums mt-0.5">{card.value}</div>
              <div className="text-[11px] mt-0.5" style={{ color: 'var(--text-muted)' }}>
                {card.sub}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Top Authors quick filter chips */}
      {stats && stats.top_authors && stats.top_authors.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5 shrink-0 text-xs">
          <span style={{ color: 'var(--text-muted)' }}>常下博主：</span>
          {stats.top_authors.map((a) => {
            const active = author === a.author_name
            return (
              <button
                key={a.author_name}
                onClick={() => {
                  const next = active ? '' : a.author_name
                  setAuthor(next)
                  setPage(1)
                  void api
                    .getHistory({ page: 1, size: pageSize, q, author: next, aweme_type: awemeType, sort })
                    .then((r) => {
                      setItems(r.items)
                      setTotal(r.total)
                    })
                }}
                className="px-2.5 py-1 rounded-full border text-[11px] font-medium cursor-pointer transition-colors"
                style={{
                  backgroundColor: active ? 'var(--accent-soft)' : 'var(--bg-surface)',
                  borderColor: active ? 'var(--accent)' : 'var(--border-subtle)',
                  color: active ? 'var(--accent)' : 'var(--text-secondary)',
                }}
              >
                {a.author_name} ({a.count})
              </button>
            )
          })}
        </div>
      )}

      {/* Filter Toolbar */}
      <div
        className="flex flex-wrap items-center justify-between gap-2.5 p-3 rounded-2xl border shrink-0"
        style={{ backgroundColor: 'var(--bg-surface)', borderColor: 'var(--border-subtle)' }}
      >
        <div className="flex flex-wrap items-center gap-2 flex-1">
          <div className="relative w-48">
            <Search className="w-3.5 h-3.5 absolute left-2.5 top-2.5" style={{ color: 'var(--text-muted)' }} />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && (setPage(1), load(1))}
              placeholder="搜索作品标题…"
              className="w-full pl-8 pr-2.5 py-1.5 rounded-xl border text-xs outline-none focus:border-[var(--accent)]"
              style={{
                backgroundColor: 'var(--bg-app)',
                borderColor: 'var(--border-subtle)',
                color: 'var(--text-primary)',
              }}
            />
          </div>
          <input
            value={author}
            onChange={(e) => setAuthor(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && (setPage(1), load(1))}
            placeholder="筛选作者…"
            className="w-36 px-3 py-1.5 rounded-xl border text-xs outline-none focus:border-[var(--accent)]"
            style={{
              backgroundColor: 'var(--bg-app)',
              borderColor: 'var(--border-subtle)',
              color: 'var(--text-primary)',
            }}
          />
          <button
            onClick={() => {
              setPage(1)
              void load(1)
            }}
            className="px-3 py-1.5 rounded-xl text-xs font-semibold text-white cursor-pointer"
            style={{ backgroundColor: 'var(--accent)' }}
          >
            搜索
          </button>

          <div
            className="flex p-0.5 rounded-xl border"
            style={{ backgroundColor: 'var(--bg-app)', borderColor: 'var(--border-subtle)' }}
          >
            {[
              { value: '', label: '全部' },
              { value: 'video', label: '视频' },
              { value: 'gallery', label: '图文' },
              { value: 'music', label: '音乐' },
            ].map((t) => (
              <button
                key={t.value}
                onClick={() => setAwemeType(t.value)}
                className="px-2.5 py-1 rounded-lg text-xs font-medium cursor-pointer"
                style={{
                  backgroundColor: awemeType === t.value ? 'var(--bg-surface)' : 'transparent',
                  color: awemeType === t.value ? 'var(--accent)' : 'var(--text-muted)',
                }}
              >
                {t.label}
              </button>
            ))}
          </div>
        </div>

        <div className="flex items-center gap-2">
          <select
            value={sort}
            onChange={(e) => setSort(e.target.value as typeof sort)}
            className="text-xs px-2.5 py-1.5 rounded-xl border outline-none"
            style={{
              backgroundColor: 'var(--bg-app)',
              borderColor: 'var(--border-subtle)',
              color: 'var(--text-primary)',
            }}
          >
            <option value="download_time">按下载时间</option>
            <option value="create_time">按发布时间</option>
          </select>

          <div
            className="flex p-0.5 rounded-xl border"
            style={{ backgroundColor: 'var(--bg-app)', borderColor: 'var(--border-subtle)' }}
          >
            <button
              onClick={() => setViewMode('grid')}
              className="p-1.5 rounded-lg cursor-pointer"
              style={{
                backgroundColor: viewMode === 'grid' ? 'var(--bg-surface)' : 'transparent',
                color: viewMode === 'grid' ? 'var(--accent)' : 'var(--text-muted)',
              }}
            >
              <LayoutGrid className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={() => setViewMode('table')}
              className="p-1.5 rounded-lg cursor-pointer"
              style={{
                backgroundColor: viewMode === 'table' ? 'var(--bg-surface)' : 'transparent',
                color: viewMode === 'table' ? 'var(--accent)' : 'var(--text-muted)',
              }}
            >
              <List className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </div>

      {/* Items */}
      <div className="flex-1 min-h-0 overflow-y-auto pr-1">
        {items.length === 0 ? (
          <div
            className="h-full min-h-[220px] rounded-2xl border border-dashed flex flex-col items-center justify-center text-center"
            style={{ backgroundColor: 'var(--bg-surface)', borderColor: 'var(--border-strong)' }}
          >
            <div className="text-sm font-semibold">暂无下载记录</div>
            <div className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>
              下载完成后会自动记录到这里
            </div>
          </div>
        ) : viewMode === 'grid' ? (
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3.5">
            {items.map((item) => (
              <div
                key={item.aweme_id}
                className="group rounded-2xl border overflow-hidden flex flex-col transition-all hover:-translate-y-0.5"
                style={{
                  backgroundColor: 'var(--bg-surface)',
                  borderColor: 'var(--border-subtle)',
                  boxShadow: 'var(--shadow-sm)',
                }}
              >
                <div className="relative aspect-[3/4] bg-[var(--bg-muted)] overflow-hidden">
                  <CoverImage
                    url={item.cover_url}
                    alt={item.title}
                    mediaType={item.aweme_type}
                    className="w-full h-full object-cover"
                  />
                  <span className="absolute top-2.5 right-2.5 px-2 py-0.5 rounded-md text-[10.5px] font-semibold bg-black/55 text-white">
                    {TYPE_LABELS[item.aweme_type] || item.aweme_type}
                  </span>
                  <span
                    className="absolute bottom-2.5 left-2.5 px-2 py-0.5 rounded-md text-[10px] font-medium backdrop-blur-xs"
                    style={{
                      backgroundColor: item.file_exists ? 'rgba(16,185,129,0.85)' : 'rgba(100,116,139,0.8)',
                      color: '#fff',
                    }}
                  >
                    {item.file_exists ? '本地有效' : '文件已移动'}
                  </span>
                </div>

                <div className="p-2.5 flex-1 flex flex-col justify-between gap-2">
                  <div>
                    <div className="text-[12.5px] font-medium line-clamp-2" title={item.title}>
                      {item.title || '无标题'}
                    </div>
                    <div className="text-[11px] mt-1 truncate" style={{ color: 'var(--text-muted)' }}>
                      {item.author_name || '未知作者'}
                    </div>
                  </div>
                  <div className="flex items-center justify-between pt-1.5 border-t" style={{ borderColor: 'var(--border-subtle)' }}>
                    <span className="text-[10.5px] tabular-nums" style={{ color: 'var(--text-muted)' }}>
                      {formatTimestamp(item.download_time)}
                    </span>
                    <div className="flex items-center gap-0.5">
                      {item.file_exists && (
                        <>
                          <button
                            onClick={() => api.openPath(item.primary_file || item.file_path, false)}
                            title="打开文件"
                            className="p-1 rounded hover:bg-[var(--accent-soft)] hover:text-[var(--accent)] cursor-pointer"
                          >
                            <ExternalLink className="w-3.5 h-3.5" />
                          </button>
                          <button
                            onClick={() => api.openPath(item.primary_file || item.file_path, true)}
                            title="在资源管理器中定位"
                            className="p-1 rounded hover:bg-[var(--bg-muted)] cursor-pointer"
                          >
                            <FolderOpen className="w-3.5 h-3.5" />
                          </button>
                        </>
                      )}
                      <button
                        onClick={() => handleDelete(item.aweme_id)}
                        title="移除记录"
                        className="p-1 rounded hover:bg-[var(--danger-soft)] hover:text-[var(--danger)] cursor-pointer"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div
            className="rounded-2xl border overflow-auto"
            style={{ backgroundColor: 'var(--bg-surface)', borderColor: 'var(--border-subtle)' }}
          >
            <table className="w-full text-left border-collapse text-xs">
              <thead className="border-b" style={{ backgroundColor: 'var(--bg-muted)', borderColor: 'var(--border-subtle)' }}>
                <tr>
                  <th className="py-2.5 px-3">名称</th>
                  <th className="py-2.5 px-2 w-28">作者</th>
                  <th className="py-2.5 px-2 w-20">类型</th>
                  <th className="py-2.5 px-2 w-36">下载时间</th>
                  <th className="py-2.5 px-2 w-24">文件状态</th>
                  <th className="py-2.5 px-3 w-28 text-right">操作</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.aweme_id} className="border-b hover:bg-[var(--bg-muted)]" style={{ borderColor: 'var(--border-subtle)' }}>
                    <td className="py-2 px-3">
                      <div className="font-medium truncate max-w-[360px]">{item.title || '无标题'}</div>
                      <div className="text-[10.5px] tabular-nums" style={{ color: 'var(--text-muted)' }}>
                        {item.aweme_id}
                      </div>
                    </td>
                    <td className="py-2 px-2 truncate max-w-[120px]">{item.author_name}</td>
                    <td className="py-2 px-2">{TYPE_LABELS[item.aweme_type] || item.aweme_type}</td>
                    <td className="py-2 px-2 tabular-nums" style={{ color: 'var(--text-muted)' }}>
                      {formatTimestamp(item.download_time)}
                    </td>
                    <td className="py-2 px-2">
                      <span
                        className="px-2 py-0.5 rounded-full text-[11px]"
                        style={{
                          backgroundColor: item.file_exists ? 'var(--success-soft)' : 'var(--bg-muted)',
                          color: item.file_exists ? 'var(--success)' : 'var(--text-muted)',
                        }}
                      >
                        {item.file_exists ? '有效' : '缺失'}
                      </span>
                    </td>
                    <td className="py-2 px-3 text-right">
                      <div className="flex items-center justify-end gap-1">
                        {item.file_exists && (
                          <button
                            onClick={() => api.openPath(item.primary_file || item.file_path, true)}
                            title="打开目录"
                            className="p-1.5 rounded-lg hover:bg-[var(--bg-hover)] cursor-pointer"
                          >
                            <FolderOpen className="w-3.5 h-3.5" />
                          </button>
                        )}
                        <button
                          onClick={async () => {
                            await navigator.clipboard?.writeText(item.aweme_id)
                            onToast('info', '已复制作品 ID')
                          }}
                          title="复制 ID"
                          className="p-1.5 rounded-lg hover:bg-[var(--bg-hover)] cursor-pointer"
                        >
                          <Copy className="w-3.5 h-3.5" />
                        </button>
                        <button
                          onClick={() => handleDelete(item.aweme_id)}
                          title="移除记录"
                          className="p-1.5 rounded-lg hover:bg-[var(--danger-soft)] cursor-pointer"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Pagination */}
      <div className="flex items-center justify-between text-xs shrink-0 pt-1">
        <span className="tabular-nums" style={{ color: 'var(--text-muted)' }}>
          共 {total} 条 · 第 {page} / {maxPage} 页
        </span>
        <div className="flex items-center gap-2">
          <button
            onClick={() => {
              const p = Math.max(1, page - 1)
              setPage(p)
              void load(p)
            }}
            disabled={page <= 1}
            className="flex items-center gap-1 px-3 py-1 rounded-xl border hover:bg-[var(--bg-muted)] cursor-pointer disabled:opacity-40"
            style={{ borderColor: 'var(--border-subtle)' }}
          >
            <ChevronLeft className="w-3.5 h-3.5" />
            <span>上一页</span>
          </button>
          <button
            onClick={() => {
              const p = Math.min(maxPage, page + 1)
              setPage(p)
              void load(p)
            }}
            disabled={page >= maxPage}
            className="flex items-center gap-1 px-3 py-1 rounded-xl border hover:bg-[var(--bg-muted)] cursor-pointer disabled:opacity-40"
            style={{ borderColor: 'var(--border-subtle)' }}
          >
            <span>下一页</span>
            <ChevronRight className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    </div>
  )
}
