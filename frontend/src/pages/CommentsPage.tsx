import React, { useEffect, useMemo, useState } from 'react'
import {
  Check,
  ChevronLeft,
  ChevronRight,
  Download,
  FileSpreadsheet,
  FolderOpen,
  Heart,
  Image as ImageIcon,
  Loader2,
  MapPin,
  Search,
  Sparkles,
  X,
} from 'lucide-react'
import type { CommentEntry, CommentImageEntry } from '../types/api'
import { api, nativePickDirectory, nativeSaveFileDialog } from '../lib/api'
import { proxyImageUrl } from '../lib/format'

interface CommentsPageProps {
  initialAwemeId: string
  initialTitle: string
  initialAuthor: string
  defaultDownloadDir: string
  onToast: (kind: 'info' | 'success' | 'warning' | 'error', title: string, detail?: string) => void
}

export const CommentsPage: React.FC<CommentsPageProps> = ({
  initialAwemeId,
  initialTitle,
  initialAuthor,
  defaultDownloadDir,
  onToast,
}) => {
  const [inputAweme, setInputAweme] = useState(initialAwemeId)
  const [awemeTitle, setAwemeTitle] = useState(initialTitle)
  const [awemeAuthor, setAwemeAuthor] = useState(initialAuthor)
  const [includeReplies, setIncludeReplies] = useState(false)

  const [loading, setLoading] = useState(false)
  const [comments, setComments] = useState<CommentEntry[]>([])
  const [images, setImages] = useState<CommentImageEntry[]>([])
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(new Set())
  const [highlightKey, setHighlightKey] = useState<string>('')

  const [search, setSearch] = useState('')
  const [onlyImages, setOnlyImages] = useState(false)
  const [sortBy, setSortBy] = useState<'default' | 'likes' | 'newest'>('default')

  const [saveDir, setSaveDir] = useState('')
  const [downloading, setDownloading] = useState(false)
  const [lightboxIndex, setLightboxIndex] = useState<number | null>(null)

  useEffect(() => {
    if (initialAwemeId) {
      setInputAweme(initialAwemeId)
      setAwemeTitle(initialTitle)
      setAwemeAuthor(initialAuthor)
      const base = defaultDownloadDir || './Downloaded'
      const sep = base.includes('\\') ? '\\' : '/'
      setSaveDir(`${base.replace(/[\\/]+$/, '')}${sep}评论图片${sep}${initialAuthor || 'unknown'}_${initialAwemeId}`)
      void handleLoad(initialAwemeId)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialAwemeId])

  const handleLoad = async (overrideId?: string) => {
    const target = (overrideId ?? inputAweme).trim()
    if (!target) {
      onToast('warning', '请输入作品 ID 或作品链接')
      return
    }
    setLoading(true)
    try {
      const res = await api.loadComments({ aweme_id: target, include_replies: includeReplies })
      setInputAweme(res.aweme_id)
      setComments(res.comments)
      setImages(res.images)
      setSelectedKeys(new Set())
      if (!saveDir) {
        const base = defaultDownloadDir || './Downloaded'
        const sep = base.includes('\\') ? '\\' : '/'
        setSaveDir(`${base.replace(/[\\/]+$/, '')}${sep}评论图片${sep}${res.aweme_id}`)
      }
      if (res.warning) {
        onToast(
          'warning',
          '部分评论加载完成',
          `共 ${res.total_comments} 条评论，${res.total_images} 张图片（${res.warning}）`
        )
      } else {
        onToast('success', `加载完成`, `共 ${res.total_comments} 条评论，${res.total_images} 张图片`)
      }
    } catch (err) {
      onToast('error', '评论加载失败', err instanceof Error ? err.message : String(err))
    } finally {
      setLoading(false)
    }
  }

  const filteredComments = useMemo(() => {
    const q = search.trim().toLowerCase()
    const matchesQuery = (entry: CommentEntry) =>
      entry.text.toLowerCase().includes(q) ||
      entry.nickname.toLowerCase().includes(q) ||
      entry.ip_label.toLowerCase().includes(q)
    const list = comments.filter((c) => {
      const hasImages = c.image_count > 0 || Boolean(c.replies?.some((r) => r.image_count > 0))
      if (onlyImages && !hasImages) return false
      if (!q) return true
      return matchesQuery(c) || Boolean(c.replies?.some(matchesQuery))
    })
    if (sortBy === 'likes') {
      return [...list].sort((a, b) => b.digg_count - a.digg_count)
    }
    if (sortBy === 'newest') {
      return [...list].sort((a, b) => b.create_time - a.create_time)
    }
    return list
  }, [comments, search, onlyImages, sortBy])

  const thumbByComment = useMemo(() => {
    const map = new Map<string, CommentImageEntry[]>()
    for (const img of images) {
      const arr = map.get(img.comment_id) || []
      arr.push(img)
      map.set(img.comment_id, arr)
    }
    return map
  }, [images])

  const toggleImage = (key: string) => {
    const next = new Set(selectedKeys)
    if (next.has(key)) next.delete(key)
    else next.add(key)
    setSelectedKeys(next)
  }

  const selectAllImages = () => {
    if (selectedKeys.size === images.length) {
      setSelectedKeys(new Set())
    } else {
      setSelectedKeys(new Set(images.map((i) => i.key)))
    }
  }

  const jumpToImage = (key: string) => {
    setHighlightKey(key)
    const el = document.getElementById(`comment-img-${key}`)
    el?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }

  const handleDownloadSelected = async () => {
    if (selectedKeys.size === 0 || downloading) return
    setDownloading(true)
    try {
      const res = await api.downloadCommentImages({
        aweme_id: inputAweme,
        keys: Array.from(selectedKeys),
        save_dir: saveDir,
      })
      onToast('success', `评论图片下载完成`, `成功 ${res.success} 个文件，失败 ${res.failed} 个`)
    } catch (err) {
      onToast('error', '评论图片下载失败', err instanceof Error ? err.message : String(err))
    } finally {
      setDownloading(false)
    }
  }

  const handleExportExcel = async () => {
    if (comments.length === 0) return
    try {
      const picked = await nativeSaveFileDialog(`${inputAweme || 'comments'}_评论.xlsx`)
      const res = await api.exportCommentsExcel({
        aweme_id: inputAweme,
        output_path: picked || '',
        aweme_title: awemeTitle,
      })
      onToast('success', 'Excel 导出成功', res.path)
    } catch (err) {
      onToast('error', '导出失败', err instanceof Error ? err.message : String(err))
    }
  }

  // Lightbox keyboard nav
  useEffect(() => {
    if (lightboxIndex === null) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setLightboxIndex(null)
      if (e.key === 'ArrowRight') setLightboxIndex((i) => (i === null ? null : (i + 1) % images.length))
      if (e.key === 'ArrowLeft') setLightboxIndex((i) => (i === null ? null : (i - 1 + images.length) % images.length))
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [lightboxIndex, images.length])

  const activeLightbox = lightboxIndex !== null ? images[lightboxIndex] : null

  return (
    <div className="flex flex-col h-full gap-4 p-6 pb-3 overflow-hidden">
      {/* Header + direct input */}
      <div className="flex flex-wrap items-center justify-between gap-3 shrink-0">
        <div className="min-w-0">
          <h1 className="text-xl font-bold tracking-tight">评论浏览与图库</h1>
          <p className="text-xs mt-0.5 truncate" style={{ color: 'var(--text-muted)' }}>
            {awemeTitle ? `${awemeAuthor ? `${awemeAuthor} · ` : ''}${awemeTitle}` : '支持原图预览、表情渲染、动图自动合并与 Excel 导出'}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <input
            value={inputAweme}
            onChange={(e) => setInputAweme(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleLoad()}
            placeholder="作品 ID 或链接…"
            className="w-56 px-3 py-1.5 rounded-xl border text-xs outline-none focus:border-[var(--accent)]"
            style={{
              backgroundColor: 'var(--bg-surface)',
              borderColor: 'var(--border-subtle)',
              color: 'var(--text-primary)',
            }}
          />
          <label className="flex items-center gap-1.5 text-xs cursor-pointer select-none">
            <input
              type="checkbox"
              checked={includeReplies}
              onChange={(e) => setIncludeReplies(e.target.checked)}
              className="accent-[var(--accent)]"
            />
            <span>含回复</span>
          </label>
          <button
            onClick={() => handleLoad()}
            disabled={loading}
            className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl text-xs font-semibold text-white cursor-pointer disabled:opacity-50"
            style={{ backgroundColor: 'var(--accent)' }}
          >
            {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5" />}
            <span>{loading ? '加载中…' : '加载评论'}</span>
          </button>
        </div>
      </div>

      {/* Split panes */}
      <div className="flex-1 min-h-0 grid grid-cols-1 lg:grid-cols-12 gap-4">
        {/* Left: Comments */}
        <div
          className="lg:col-span-5 rounded-2xl border flex flex-col min-h-0 overflow-hidden"
          style={{ backgroundColor: 'var(--bg-surface)', borderColor: 'var(--border-subtle)' }}
        >
          <div className="p-3 border-b space-y-2 shrink-0" style={{ borderColor: 'var(--border-subtle)' }}>
            <div className="flex items-center gap-2">
              <div className="relative flex-1">
                <Search className="w-3.5 h-3.5 absolute left-2.5 top-2.5" style={{ color: 'var(--text-muted)' }} />
                <input
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="搜索评论内容、用户、IP属地…"
                  className="w-full pl-8 pr-2.5 py-1.5 rounded-xl border text-xs outline-none focus:border-[var(--accent)]"
                  style={{
                    backgroundColor: 'var(--bg-app)',
                    borderColor: 'var(--border-subtle)',
                    color: 'var(--text-primary)',
                  }}
                />
              </div>
              <select
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value as typeof sortBy)}
                className="px-2 py-1.5 rounded-xl border text-xs outline-none"
                style={{
                  backgroundColor: 'var(--bg-app)',
                  borderColor: 'var(--border-subtle)',
                  color: 'var(--text-primary)',
                }}
              >
                <option value="default">默认</option>
                <option value="likes">高赞</option>
                <option value="newest">最新</option>
              </select>
            </div>
            <div className="flex items-center justify-between text-[11px]" style={{ color: 'var(--text-muted)' }}>
              <span className="tabular-nums">
                显示 {filteredComments.length} / {comments.length} 条评论
              </span>
              <button
                onClick={() => setOnlyImages((v) => !v)}
                className="px-2 py-0.5 rounded-lg font-medium cursor-pointer"
                style={{
                  backgroundColor: onlyImages ? 'var(--accent-soft)' : 'var(--bg-muted)',
                  color: onlyImages ? 'var(--accent)' : 'var(--text-secondary)',
                }}
              >
                仅看带图
              </button>
            </div>
          </div>

          <div className="flex-1 overflow-y-auto p-3 space-y-2.5">
            {filteredComments.length === 0 ? (
              <div className="py-16 text-center text-xs" style={{ color: 'var(--text-muted)' }}>
                {loading ? '正在拉取评论…' : '暂无评论数据'}
              </div>
            ) : (
              filteredComments.map((c) => {
                const imgs = thumbByComment.get(c.cid) || []
                return (
                  <div
                    key={c.cid}
                    className="p-3 rounded-xl border space-y-2"
                    style={{
                      backgroundColor: 'var(--bg-app)',
                      borderColor: 'var(--border-subtle)',
                    }}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2 min-w-0">
                        {c.avatar_url && (
                          <img
                            src={proxyImageUrl(c.avatar_url)}
                            alt=""
                            loading="lazy"
                            className="w-6 h-6 rounded-full object-cover shrink-0"
                          />
                        )}
                        <span className="text-xs font-semibold truncate" style={{ color: 'var(--accent)' }}>
                          {c.nickname}
                        </span>
                      </div>
                      <div className="flex items-center gap-2 text-[11px] shrink-0 tabular-nums" style={{ color: 'var(--text-muted)' }}>
                        {c.ip_label && (
                          <span className="flex items-center gap-0.5">
                            <MapPin className="w-3 h-3" />
                            {c.ip_label}
                          </span>
                        )}
                        <span className="flex items-center gap-0.5">
                          <Heart className="w-3 h-3" />
                          {c.digg_count}
                        </span>
                      </div>
                    </div>
                    {c.text && <div className="text-[12.5px] leading-relaxed break-words">{c.text}</div>}
                    {imgs.length > 0 && (
                      <div className="flex flex-wrap gap-1.5 pt-1">
                        {imgs.map((img) => (
                          <button
                            key={img.key}
                            onClick={() => jumpToImage(img.key)}
                            className="relative w-14 h-14 rounded-lg overflow-hidden border hover:ring-2 hover:ring-[var(--accent)] cursor-pointer"
                            style={{ borderColor: 'var(--border-subtle)' }}
                          >
                            <img
                              src={proxyImageUrl(img.preview_url)}
                              alt=""
                              loading="lazy"
                              className="w-full h-full object-cover"
                            />
                            {img.is_live && (
                              <span className="absolute bottom-0.5 right-0.5 px-1 rounded text-[9px] bg-amber-500 text-white font-semibold">
                                动图
                              </span>
                            )}
                          </button>
                        ))}
                      </div>
                    )}
                    {c.time && (
                      <div className="text-[10.5px] tabular-nums" style={{ color: 'var(--text-muted)' }}>
                        {c.time}
                      </div>
                    )}
                    {c.replies && c.replies.length > 0 && (
                      <div
                        className="mt-2 pl-3 border-l-2 space-y-2"
                        style={{ borderColor: 'var(--border-subtle)' }}
                      >
                        {c.replies.map((reply) => {
                          const replyImgs = thumbByComment.get(reply.cid) || []
                          return (
                            <div key={reply.cid} className="space-y-1 text-[11.5px]">
                              <div className="flex items-center justify-between gap-2">
                                <span className="font-semibold truncate" style={{ color: 'var(--text-secondary)' }}>
                                  {reply.nickname}
                                </span>
                                <div
                                  className="flex items-center gap-2 text-[10.5px] shrink-0 tabular-nums"
                                  style={{ color: 'var(--text-muted)' }}
                                >
                                  {reply.ip_label && <span>{reply.ip_label}</span>}
                                  <span className="flex items-center gap-0.5">
                                    <Heart className="w-2.5 h-2.5" />
                                    {reply.digg_count}
                                  </span>
                                </div>
                              </div>
                              {reply.text && <div className="leading-relaxed break-words">{reply.text}</div>}
                              {replyImgs.length > 0 && (
                                <div className="flex flex-wrap gap-1.5 pt-0.5">
                                  {replyImgs.map((img) => (
                                    <button
                                      key={img.key}
                                      onClick={() => jumpToImage(img.key)}
                                      className="relative w-12 h-12 rounded-lg overflow-hidden border hover:ring-2 hover:ring-[var(--accent)] cursor-pointer"
                                      style={{ borderColor: 'var(--border-subtle)' }}
                                    >
                                      <img
                                        src={proxyImageUrl(img.preview_url)}
                                        alt=""
                                        loading="lazy"
                                        className="w-full h-full object-cover"
                                      />
                                      {img.is_live && (
                                        <span className="absolute bottom-0.5 right-0.5 px-1 rounded text-[9px] bg-amber-500 text-white font-semibold">
                                          动图
                                        </span>
                                      )}
                                    </button>
                                  ))}
                                </div>
                              )}
                            </div>
                          )
                        })}
                      </div>
                    )}
                  </div>
                )
              })
            )}
          </div>
        </div>

        {/* Right: Image Gallery */}
        <div
          className="lg:col-span-7 rounded-2xl border flex flex-col min-h-0 overflow-hidden"
          style={{ backgroundColor: 'var(--bg-surface)', borderColor: 'var(--border-subtle)' }}
        >
          <div className="p-3 border-b flex items-center justify-between gap-2 shrink-0" style={{ borderColor: 'var(--border-subtle)' }}>
            <div className="flex items-center gap-2 text-xs">
              <ImageIcon className="w-4 h-4" style={{ color: 'var(--accent)' }} />
              <span className="font-semibold">评论图片</span>
              <span className="tabular-nums" style={{ color: 'var(--text-muted)' }}>
                {images.length} 张 · 已选 {selectedKeys.size}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={selectAllImages}
                disabled={images.length === 0}
                className="px-2.5 py-1 rounded-lg text-xs border hover:bg-[var(--bg-muted)] cursor-pointer disabled:opacity-40"
                style={{ borderColor: 'var(--border-subtle)' }}
              >
                {selectedKeys.size === images.length && images.length > 0 ? '清空选择' : '全选'}
              </button>
              <button
                onClick={handleExportExcel}
                disabled={comments.length === 0}
                className="flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs border hover:bg-[var(--bg-muted)] cursor-pointer disabled:opacity-40"
                style={{ borderColor: 'var(--border-subtle)' }}
              >
                <FileSpreadsheet className="w-3.5 h-3.5" style={{ color: 'var(--success)' }} />
                <span>导出 Excel</span>
              </button>
            </div>
          </div>

          <div className="flex-1 overflow-y-auto p-3">
            {images.length === 0 ? (
              <div className="h-full flex items-center justify-center text-xs" style={{ color: 'var(--text-muted)' }}>
                暂无评论图片
              </div>
            ) : (
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
                {images.map((img, idx) => {
                  const selected = selectedKeys.has(img.key)
                  const highlighted = highlightKey === img.key
                  return (
                    <div
                      id={`comment-img-${img.key}`}
                      key={img.key}
                      className="group relative rounded-xl border overflow-hidden transition-all"
                      style={{
                        borderColor: selected || highlighted ? 'var(--accent)' : 'var(--border-subtle)',
                        boxShadow: highlighted ? '0 0 0 3px var(--accent-ring)' : undefined,
                      }}
                    >
                      <div
                        onClick={() => setLightboxIndex(idx)}
                        className="aspect-square bg-[var(--bg-muted)] cursor-zoom-in overflow-hidden"
                      >
                        <img
                          src={proxyImageUrl(img.preview_url)}
                          alt={img.nickname}
                          loading="lazy"
                          className="w-full h-full object-cover transition-transform duration-200 group-hover:scale-105"
                        />
                      </div>

                      <button
                        onClick={() => toggleImage(img.key)}
                        className={`absolute top-2 right-2 w-6 h-6 rounded-lg flex items-center justify-center border cursor-pointer transition-all ${
                          selected
                            ? 'opacity-100'
                            : 'opacity-80 group-hover:opacity-100 bg-black/45 border-white/50 text-white'
                        }`}
                        style={
                          selected
                            ? { backgroundColor: 'var(--accent)', borderColor: 'var(--accent)', color: '#fff' }
                            : undefined
                        }
                      >
                        {selected && <Check className="w-3.5 h-3.5 stroke-[2.5]" />}
                      </button>

                      {img.is_live && (
                        <span className="absolute top-2 left-2 px-1.5 py-0.5 rounded text-[10px] font-semibold bg-amber-500/90 text-white">
                          实况动图
                        </span>
                      )}

                      <div
                        className="px-2 py-1.5 text-[11px] truncate"
                        style={{ backgroundColor: 'var(--bg-surface)', color: 'var(--text-secondary)' }}
                      >
                        {img.nickname}
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>

          {/* Bottom save bar */}
          <div
            className="p-3 border-t flex flex-wrap items-center gap-2 shrink-0"
            style={{ borderColor: 'var(--border-subtle)', backgroundColor: 'var(--bg-app)' }}
          >
            <input
              value={saveDir}
              onChange={(e) => setSaveDir(e.target.value)}
              placeholder="评论图片保存目录"
              className="flex-1 min-w-[200px] px-3 py-1.5 rounded-xl border text-xs outline-none"
              style={{
                backgroundColor: 'var(--bg-surface)',
                borderColor: 'var(--border-subtle)',
                color: 'var(--text-primary)',
              }}
            />
            <button
              onClick={async () => {
                const picked = await nativePickDirectory(saveDir)
                if (picked) setSaveDir(picked)
              }}
              className="px-2.5 py-1.5 rounded-xl text-xs border hover:bg-[var(--bg-muted)] cursor-pointer"
              style={{ borderColor: 'var(--border-subtle)' }}
            >
              选择目录
            </button>
            <button
              onClick={() => api.openPath(saveDir)}
              className="flex items-center gap-1 px-2.5 py-1.5 rounded-xl text-xs border hover:bg-[var(--bg-muted)] cursor-pointer"
              style={{ borderColor: 'var(--border-subtle)' }}
            >
              <FolderOpen className="w-3.5 h-3.5" />
              <span>打开</span>
            </button>
            <button
              onClick={handleDownloadSelected}
              disabled={selectedKeys.size === 0 || downloading}
              className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl text-xs font-semibold text-white cursor-pointer disabled:opacity-40"
              style={{ backgroundColor: 'var(--accent)' }}
            >
              {downloading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Download className="w-3.5 h-3.5" />}
              <span className="tabular-nums">下载选中 ({selectedKeys.size})</span>
            </button>
          </div>
        </div>
      </div>

      {/* Lightbox */}
      {activeLightbox && lightboxIndex !== null && (
        <div
          className="fixed inset-0 z-50 bg-black/85 backdrop-blur-sm flex items-center justify-center p-6"
          onClick={() => setLightboxIndex(null)}
        >
          <button
            onClick={(e) => {
              e.stopPropagation()
              setLightboxIndex((lightboxIndex - 1 + images.length) % images.length)
            }}
            className="absolute left-5 p-3 rounded-full bg-white/10 hover:bg-white/20 text-white cursor-pointer"
          >
            <ChevronLeft className="w-6 h-6" />
          </button>
          <div className="max-w-4xl max-h-[85vh] flex flex-col items-center gap-3" onClick={(e) => e.stopPropagation()}>
            <img
              src={proxyImageUrl(activeLightbox.origin_url || activeLightbox.preview_url)}
              alt=""
              className="max-h-[76vh] max-w-full rounded-xl object-contain shadow-2xl"
            />
            <div className="flex items-center gap-4 text-xs text-white/90">
              <span>@{activeLightbox.nickname}</span>
              <span className="tabular-nums">
                {lightboxIndex + 1} / {images.length}
              </span>
              <button
                onClick={() => toggleImage(activeLightbox.key)}
                className="px-3 py-1 rounded-lg bg-white/15 hover:bg-white/25 cursor-pointer"
              >
                {selectedKeys.has(activeLightbox.key) ? '✓ 已勾选下载' : '勾选下载'}
              </button>
            </div>
          </div>
          <button
            onClick={(e) => {
              e.stopPropagation()
              setLightboxIndex((lightboxIndex + 1) % images.length)
            }}
            className="absolute right-5 p-3 rounded-full bg-white/10 hover:bg-white/20 text-white cursor-pointer"
          >
            <ChevronRight className="w-6 h-6" />
          </button>
          <button
            onClick={() => setLightboxIndex(null)}
            className="absolute top-5 right-5 p-2 rounded-full bg-white/10 hover:bg-white/20 text-white cursor-pointer"
          >
            <X className="w-5 h-5" />
          </button>
        </div>
      )}
    </div>
  )
}
