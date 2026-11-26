import React, { useMemo, useState } from 'react'
import {
  Check,
  Copy,
  Download,
  Heart,
  LayoutGrid,
  List,
  MessageSquare,
  Search,
  Sparkles,
} from 'lucide-react'
import type { JobItemState, PreviewItem, ViewMode } from '../types/api'
import { formatCount, proxyImageUrl } from '../lib/format'
import { CoverImage } from './CoverImage'

interface WorkBrowserProps {
  items: PreviewItem[]
  selectedIds: Set<string>
  onChangeSelected: (next: Set<string>) => void
  viewMode: ViewMode
  onChangeViewMode: (mode: ViewMode) => void
  onDownloadSelected: (items: PreviewItem[]) => void
  onOpenComments: (item: PreviewItem) => void
  itemStatuses?: Record<string, JobItemState>
  loading?: boolean
  emptyHint?: string
}

export const WorkBrowser: React.FC<WorkBrowserProps> = ({
  items,
  selectedIds,
  onChangeSelected,
  viewMode,
  onChangeViewMode,
  onDownloadSelected,
  onOpenComments,
  itemStatuses = {},
  loading = false,
  emptyHint = '输入抖音链接或博主主页后，解析结果将实时展示在这里',
}) => {
  const [search, setSearch] = useState('')
  const [mediaFilter, setMediaFilter] = useState<string>('全部')
  const [collectionFilter, setCollectionFilter] = useState<string>('全部')
  const [sortBy, setSortBy] = useState<'default' | 'time' | 'likes' | 'duration'>('default')
  const [copiedId, setCopiedId] = useState<string | null>(null)

  const collections = useMemo(() => {
    const counts = new Map<string, number>()
    for (const item of items) {
      if (item.collection_name) {
        counts.set(item.collection_name, (counts.get(item.collection_name) || 0) + 1)
      }
    }
    return Array.from(counts.entries())
  }, [items])

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    const list = items.filter((item) => {
      if (mediaFilter !== '全部' && item.media_type !== mediaFilter) return false
      if (collectionFilter !== '全部' && item.collection_name !== collectionFilter) return false
      if (!q) return true
      return (
        item.title.toLowerCase().includes(q) ||
        item.author_name.toLowerCase().includes(q) ||
        item.aweme_id.includes(q) ||
        item.collection_name.toLowerCase().includes(q)
      )
    })

    if (sortBy === 'time') {
      return [...list].sort((a, b) => (b.create_time || 0) - (a.create_time || 0))
    }
    if (sortBy === 'likes') {
      return [...list].sort((a, b) => (b.like_count || 0) - (a.like_count || 0))
    }
    if (sortBy === 'duration') {
      return [...list].sort((a, b) => (b.duration_ms || 0) - (a.duration_ms || 0))
    }
    return list
  }, [items, search, mediaFilter, collectionFilter, sortBy])

  const selectedVisibleCount = useMemo(
    () => filtered.filter((it) => selectedIds.has(it.aweme_id)).length,
    [filtered, selectedIds]
  )

  const allVisibleSelected = filtered.length > 0 && selectedVisibleCount === filtered.length

  const toggleAllVisible = () => {
    const next = new Set(selectedIds)
    if (allVisibleSelected) {
      for (const it of filtered) next.delete(it.aweme_id)
    } else {
      for (const it of filtered) next.add(it.aweme_id)
    }
    onChangeSelected(next)
  }

  const toggleOne = (id: string) => {
    const next = new Set(selectedIds)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    onChangeSelected(next)
  }

  const handleCopyId = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation()
    await navigator.clipboard?.writeText(id)
    setCopiedId(id)
    window.setTimeout(() => setCopiedId(null), 1200)
  }

  const downloadTargets = useMemo(() => {
    if (selectedIds.size > 0) {
      return items.filter((it) => selectedIds.has(it.aweme_id))
    }
    return filtered
  }, [items, filtered, selectedIds])

  const statusBadge = (st?: JobItemState) => {
    if (!st) return null
    const map: Record<string, { label: string; bg: string; fg: string }> = {
      pending: { label: '排队中', bg: 'var(--bg-muted)', fg: 'var(--text-muted)' },
      downloading: {
        label: st.progress > 0 ? `${Math.round(st.progress)}%` : '下载中',
        bg: 'var(--accent-soft)',
        fg: 'var(--accent)',
      },
      success: { label: '已完成', bg: 'var(--success-soft)', fg: 'var(--success)' },
      skipped: { label: '已存在', bg: 'var(--bg-muted)', fg: 'var(--text-secondary)' },
      failed: { label: '失败', bg: 'var(--danger-soft)', fg: 'var(--danger)' },
      cancelled: { label: '已取消', bg: 'var(--warning-soft)', fg: 'var(--warning)' },
    }
    return map[st.status] || null
  }

  return (
    <div className="flex flex-col flex-1 min-h-0 gap-3">
      {/* Toolbar */}
      <div
        className="flex flex-wrap items-center justify-between gap-2.5 p-3 rounded-2xl border"
        style={{
          backgroundColor: 'var(--bg-surface)',
          borderColor: 'var(--border-subtle)',
          boxShadow: 'var(--shadow-sm)',
        }}
      >
        <div className="flex flex-wrap items-center gap-2 flex-1 min-w-[260px]">
          <div className="relative w-52">
            <Search className="w-3.5 h-3.5 absolute left-2.5 top-2.5" style={{ color: 'var(--text-muted)' }} />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="搜索标题、作者、合集…"
              className="w-full pl-8 pr-2.5 py-1.5 text-xs rounded-xl border outline-none focus:border-[var(--accent)]"
              style={{
                backgroundColor: 'var(--bg-app)',
                borderColor: 'var(--border-subtle)',
                color: 'var(--text-primary)',
              }}
            />
          </div>

          {/* Media filter pills */}
          <div
            className="flex items-center p-0.5 rounded-xl border"
            style={{ backgroundColor: 'var(--bg-app)', borderColor: 'var(--border-subtle)' }}
          >
            {['全部', '视频', '图文', '直播'].map((m) => (
              <button
                key={m}
                onClick={() => setMediaFilter(m)}
                className="px-2.5 py-1 rounded-lg text-xs font-medium transition-colors cursor-pointer"
                style={{
                  backgroundColor: mediaFilter === m ? 'var(--bg-surface)' : 'transparent',
                  color: mediaFilter === m ? 'var(--accent)' : 'var(--text-muted)',
                  boxShadow: mediaFilter === m ? 'var(--shadow-sm)' : 'none',
                }}
              >
                {m}
              </button>
            ))}
          </div>

          {collections.length > 0 && (
            <select
              value={collectionFilter}
              onChange={(e) => setCollectionFilter(e.target.value)}
              className="text-xs px-2.5 py-1.5 rounded-xl border outline-none cursor-pointer"
              style={{
                backgroundColor: 'var(--bg-app)',
                borderColor: 'var(--border-subtle)',
                color: 'var(--text-primary)',
              }}
            >
              <option value="全部">全部合集 ({items.length})</option>
              {collections.map(([name, cnt]) => (
                <option key={name} value={name}>
                  {name} ({cnt})
                </option>
              ))}
            </select>
          )}

          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as typeof sortBy)}
            className="text-xs px-2.5 py-1.5 rounded-xl border outline-none cursor-pointer"
            style={{
              backgroundColor: 'var(--bg-app)',
              borderColor: 'var(--border-subtle)',
              color: 'var(--text-primary)',
            }}
          >
            <option value="default">默认排序</option>
            <option value="time">最新发布</option>
            <option value="likes">点赞最多</option>
            <option value="duration">时长最长</option>
          </select>
        </div>

        {/* Right actions */}
        <div className="flex items-center gap-2">
          <button
            onClick={toggleAllVisible}
            disabled={filtered.length === 0}
            className="px-2.5 py-1.5 rounded-xl text-xs font-medium border transition-colors hover:bg-[var(--bg-muted)] cursor-pointer disabled:opacity-40"
            style={{
              borderColor: 'var(--border-subtle)',
              color: 'var(--text-secondary)',
            }}
          >
            {allVisibleSelected ? '取消全选' : `全选 (${filtered.length})`}
          </button>

          <div
            className="flex p-0.5 rounded-xl border"
            style={{ backgroundColor: 'var(--bg-app)', borderColor: 'var(--border-subtle)' }}
          >
            <button
              onClick={() => onChangeViewMode('grid')}
              title="卡片视图"
              className="p-1.5 rounded-lg cursor-pointer"
              style={{
                backgroundColor: viewMode === 'grid' ? 'var(--bg-surface)' : 'transparent',
                color: viewMode === 'grid' ? 'var(--accent)' : 'var(--text-muted)',
              }}
            >
              <LayoutGrid className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={() => onChangeViewMode('table')}
              title="列表视图"
              className="p-1.5 rounded-lg cursor-pointer"
              style={{
                backgroundColor: viewMode === 'table' ? 'var(--bg-surface)' : 'transparent',
                color: viewMode === 'table' ? 'var(--accent)' : 'var(--text-muted)',
              }}
            >
              <List className="w-3.5 h-3.5" />
            </button>
          </div>

          <button
            onClick={() => onDownloadSelected(downloadTargets)}
            disabled={downloadTargets.length === 0}
            className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl text-xs font-semibold text-white transition-all cursor-pointer disabled:opacity-40 shadow-xs"
            style={{ backgroundColor: 'var(--accent)' }}
          >
            <Download className="w-3.5 h-3.5" />
            <span className="tabular-nums">
              {selectedIds.size > 0
                ? `下载选中 (${selectedIds.size})`
                : `全部下载 (${filtered.length})`}
            </span>
          </button>
        </div>
      </div>

      {/* Content area */}
      {items.length === 0 && !loading ? (
        <div
          className="flex-1 rounded-2xl border border-dashed flex flex-col items-center justify-center p-10 text-center"
          style={{
            backgroundColor: 'var(--bg-surface)',
            borderColor: 'var(--border-strong)',
          }}
        >
          <div
            className="w-12 h-12 rounded-2xl flex items-center justify-center mb-3"
            style={{ backgroundColor: 'var(--accent-soft)', color: 'var(--accent)' }}
          >
            <Sparkles className="w-6 h-6" />
          </div>
          <div className="text-sm font-semibold mb-1">等待解析作品</div>
          <div className="text-xs max-w-md" style={{ color: 'var(--text-muted)' }}>
            {emptyHint}
          </div>
        </div>
      ) : viewMode === 'grid' ? (
        <div className="flex-1 overflow-y-auto pr-1">
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3.5 pb-2">
            {filtered.map((item) => {
              const selected = selectedIds.has(item.aweme_id)
              const st = itemStatuses[item.aweme_id]
              const badge = statusBadge(st)
              const canComment = item.media_type === '视频' || item.media_type === '图文'
              return (
                <div
                  key={item.aweme_id}
                  onClick={() => toggleOne(item.aweme_id)}
                  className="group rounded-2xl border overflow-hidden cursor-pointer transition-all duration-150 flex flex-col hover:-translate-y-0.5"
                  style={{
                    backgroundColor: 'var(--bg-surface)',
                    borderColor: selected ? 'var(--accent)' : 'var(--border-subtle)',
                    boxShadow: selected ? '0 0 0 2px var(--accent-ring)' : 'var(--shadow-sm)',
                  }}
                >
                  {/* Thumbnail */}
                  <div className="relative aspect-[3/4] bg-[var(--bg-muted)] overflow-hidden">
                    <CoverImage
                      url={item.cover_url}
                      alt={item.title}
                      mediaType={item.media_type}
                      className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-[1.03]"
                    />

                    {/* Top-left selection checkbox */}
                    <div
                      className={`absolute top-2.5 left-2.5 w-6 h-6 rounded-lg flex items-center justify-center transition-all border ${
                        selected
                          ? 'opacity-100 scale-100'
                          : 'opacity-0 group-hover:opacity-100 bg-black/45 border-white/50 text-white'
                      }`}
                      style={
                        selected
                          ? { backgroundColor: 'var(--accent)', borderColor: 'var(--accent)', color: '#fff' }
                          : undefined
                      }
                    >
                      {selected && <Check className="w-3.5 h-3.5 stroke-[2.5]" />}
                    </div>

                    {/* Top-right media pill */}
                    <div className="absolute top-2.5 right-2.5 flex items-center gap-1">
                      {item.is_live_photo && (
                        <span className="px-1.5 py-0.5 rounded-md text-[10px] font-semibold bg-amber-500/90 text-white backdrop-blur-xs">
                          实况
                        </span>
                      )}
                      <span className="px-2 py-0.5 rounded-md text-[10.5px] font-semibold bg-black/55 text-white backdrop-blur-xs">
                        {item.media_type === '图文' && item.image_count > 0
                          ? `图文 ${item.image_count}P`
                          : item.media_type}
                      </span>
                    </div>

                    {/* Bottom overlay */}
                    <div className="absolute inset-x-0 bottom-0 p-2.5 bg-gradient-to-t from-black/75 via-black/30 to-transparent flex items-end justify-between text-white text-[11px]">
                      <div className="flex items-center gap-2 tabular-nums">
                        {item.like_count > 0 && (
                          <span className="flex items-center gap-0.5">
                            <Heart className="w-3 h-3 fill-current opacity-90" />
                            {formatCount(item.like_count)}
                          </span>
                        )}
                        {item.resolution && (
                          <span className="px-1 py-0.2 rounded bg-white/20 text-[10px]">
                            {item.resolution}
                          </span>
                        )}
                      </div>
                      <span className="tabular-nums font-medium">
                        {item.duration !== '未知' ? item.duration : item.size_text}
                      </span>
                    </div>

                    {/* Active download progress overlay */}
                    {badge && (
                      <div
                        className="absolute inset-x-2 top-1/2 -translate-y-1/2 text-center py-1 px-2 rounded-xl text-xs font-semibold backdrop-blur-md shadow-sm"
                        style={{ backgroundColor: badge.bg, color: badge.fg }}
                      >
                        {badge.label}
                      </div>
                    )}
                  </div>

                  {/* Body */}
                  <div className="p-2.5 flex-1 flex flex-col justify-between gap-2">
                    <div>
                      <div className="text-[12.5px] font-medium leading-snug line-clamp-2" title={item.title}>
                        {item.title}
                      </div>
                      {item.collection_name && (
                        <div
                          className="inline-block mt-1 px-1.5 py-0.5 rounded text-[10.5px] truncate max-w-full"
                          style={{ backgroundColor: 'var(--bg-muted)', color: 'var(--text-secondary)' }}
                        >
                          合集 · {item.collection_name}
                        </div>
                      )}
                    </div>

                    <div className="flex items-center justify-between gap-1 pt-1 border-t text-[11px]" style={{ borderColor: 'var(--border-subtle)', color: 'var(--text-muted)' }}>
                      <span className="truncate">{item.author_name}</span>
                      <div className="flex items-center gap-0.5 shrink-0">
                        <button
                          onClick={(e) => {
                            e.stopPropagation()
                            onDownloadSelected([item])
                          }}
                          disabled={st?.status === 'downloading'}
                          title="单独下载此作品"
                          aria-label="单独下载此作品"
                          className="p-1 rounded-md hover:bg-[var(--accent-soft)] hover:text-[var(--accent)] disabled:opacity-40 cursor-pointer"
                        >
                          <Download className="w-3.5 h-3.5" />
                        </button>
                        {canComment && (
                          <button
                            onClick={(e) => {
                              e.stopPropagation()
                              onOpenComments(item)
                            }}
                            title="查看评论与图片"
                            className="p-1 rounded-md hover:bg-[var(--accent-soft)] hover:text-[var(--accent)] cursor-pointer"
                          >
                            <MessageSquare className="w-3.5 h-3.5" />
                          </button>
                        )}
                        <button
                          onClick={(e) => handleCopyId(e, item.aweme_id)}
                          title="复制作品 ID"
                          className="p-1 rounded-md hover:bg-[var(--bg-muted)] cursor-pointer"
                        >
                          {copiedId === item.aweme_id ? (
                            <Check className="w-3.5 h-3.5" style={{ color: 'var(--success)' }} />
                          ) : (
                            <Copy className="w-3.5 h-3.5" />
                          )}
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
              )
            })}
            {loading &&
              Array.from({ length: 5 }).map((_, i) => (
                <div
                  key={`sk-${i}`}
                  className="rounded-2xl border overflow-hidden"
                  style={{ borderColor: 'var(--border-subtle)', backgroundColor: 'var(--bg-surface)' }}
                >
                  <div className="aspect-[3/4] skeleton-shimmer" />
                  <div className="p-2.5 space-y-2">
                    <div className="h-3.5 rounded skeleton-shimmer" />
                    <div className="h-3 w-2/3 rounded skeleton-shimmer" />
                  </div>
                </div>
              ))}
          </div>
        </div>
      ) : (
        /* Compact Table View */
        <div
          className="flex-1 rounded-2xl border overflow-auto"
          style={{
            backgroundColor: 'var(--bg-surface)',
            borderColor: 'var(--border-subtle)',
            boxShadow: 'var(--shadow-sm)',
          }}
        >
          <table className="w-full text-left border-collapse text-xs">
            <thead
              className="sticky top-0 z-10 border-b"
              style={{ backgroundColor: 'var(--bg-muted)', borderColor: 'var(--border-subtle)' }}
            >
              <tr style={{ color: 'var(--text-secondary)' }}>
                <th className="py-2.5 px-3 w-10">
                  <input
                    type="checkbox"
                    checked={allVisibleSelected}
                    onChange={toggleAllVisible}
                    className="accent-[var(--accent)] cursor-pointer"
                  />
                </th>
                <th className="py-2.5 px-2">作品</th>
                <th className="py-2.5 px-2 w-24">作者</th>
                <th className="py-2.5 px-2 w-24">合集</th>
                <th className="py-2.5 px-2 w-20">类型</th>
                <th className="py-2.5 px-2 w-20 tabular-nums">时长/大小</th>
                <th className="py-2.5 px-2 w-36 tabular-nums">发布时间</th>
                <th className="py-2.5 px-2 w-24">状态</th>
                <th className="py-2.5 px-3 w-20 text-right">操作</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((item) => {
                const selected = selectedIds.has(item.aweme_id)
                const badge = statusBadge(itemStatuses[item.aweme_id])
                const canComment = item.media_type === '视频' || item.media_type === '图文'
                return (
                  <tr
                    key={item.aweme_id}
                    onClick={() => toggleOne(item.aweme_id)}
                    className="border-b transition-colors cursor-pointer hover:bg-[var(--bg-muted)]"
                    style={{
                      borderColor: 'var(--border-subtle)',
                      backgroundColor: selected ? 'var(--accent-soft)' : undefined,
                    }}
                  >
                    <td className="py-2 px-3">
                      <input
                        type="checkbox"
                        checked={selected}
                        onChange={() => toggleOne(item.aweme_id)}
                        onClick={(e) => e.stopPropagation()}
                        className="accent-[var(--accent)] cursor-pointer"
                      />
                    </td>
                    <td className="py-2 px-2">
                      <div className="flex items-center gap-2.5 min-w-0">
                        {item.cover_url && (
                          <img
                            src={proxyImageUrl(item.cover_url)}
                            alt=""
                            loading="lazy"
                            className="w-9 h-12 rounded-md object-cover shrink-0 bg-[var(--bg-muted)]"
                          />
                        )}
                        <div className="min-w-0">
                          <div className="font-medium truncate max-w-[340px]" title={item.title}>
                            {item.title}
                          </div>
                          <div className="text-[11px] tabular-nums" style={{ color: 'var(--text-muted)' }}>
                            ID: {item.aweme_id}
                            {item.like_count > 0 ? ` · ♥ ${formatCount(item.like_count)}` : ''}
                          </div>
                        </div>
                      </div>
                    </td>
                    <td className="py-2 px-2 truncate max-w-[110px]" style={{ color: 'var(--text-secondary)' }}>
                      {item.author_name}
                    </td>
                    <td className="py-2 px-2 truncate max-w-[110px]" style={{ color: 'var(--text-muted)' }}>
                      {item.collection_name || '—'}
                    </td>
                    <td className="py-2 px-2">
                      <span
                        className="px-2 py-0.5 rounded-md text-[11px] font-medium"
                        style={{ backgroundColor: 'var(--bg-muted)', color: 'var(--text-secondary)' }}
                      >
                        {item.media_type}
                      </span>
                    </td>
                    <td className="py-2 px-2 tabular-nums" style={{ color: 'var(--text-muted)' }}>
                      <div>{item.duration}</div>
                      <div className="text-[10.5px]">{item.size_text}</div>
                    </td>
                    <td className="py-2 px-2 tabular-nums" style={{ color: 'var(--text-muted)' }}>
                      {item.publish_time}
                    </td>
                    <td className="py-2 px-2">
                      {badge ? (
                        <span
                          className="px-2 py-0.5 rounded-full text-[11px] font-semibold"
                          style={{ backgroundColor: badge.bg, color: badge.fg }}
                        >
                          {badge.label}
                        </span>
                      ) : (
                        <span style={{ color: 'var(--text-muted)' }}>待下载</span>
                      )}
                    </td>
                    <td className="py-2 px-3 text-right">
                      <div className="flex items-center justify-end gap-1">
                        <button
                          onClick={(e) => {
                            e.stopPropagation()
                            onDownloadSelected([item])
                          }}
                          disabled={itemStatuses[item.aweme_id]?.status === 'downloading'}
                          title="单独下载此作品"
                          aria-label="单独下载此作品"
                          className="p-1.5 rounded-lg hover:bg-[var(--accent-soft)] hover:text-[var(--accent)] disabled:opacity-40 cursor-pointer"
                        >
                          <Download className="w-3.5 h-3.5" />
                        </button>
                        {canComment && (
                          <button
                            onClick={(e) => {
                              e.stopPropagation()
                              onOpenComments(item)
                            }}
                            title="评论与图库"
                            className="p-1.5 rounded-lg hover:bg-[var(--accent-soft)] hover:text-[var(--accent)] cursor-pointer"
                          >
                            <MessageSquare className="w-3.5 h-3.5" />
                          </button>
                        )}
                        <button
                          onClick={(e) => handleCopyId(e, item.aweme_id)}
                          title="复制 ID"
                          className="p-1.5 rounded-lg hover:bg-[var(--bg-hover)] cursor-pointer"
                        >
                          <Copy className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
