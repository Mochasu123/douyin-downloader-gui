import React, { useCallback, useEffect, useRef, useState } from 'react'
import {
  ChevronLeft,
  ChevronRight,
  Download,
  Heart,
  Image as ImageIcon,
  Loader2,
  Maximize2,
  MessageSquare,
  Music,
  Pause,
  Play,
  RefreshCw,
  RotateCcw,
  Sparkles,
  X,
  ZoomIn,
  ZoomOut,
} from 'lucide-react'
import type { PreviewItem, PreviewMediaDetail } from '../types/api'
import { api } from '../lib/api'
import { formatCount, proxyImageUrl, proxyMediaUrl } from '../lib/format'

interface MediaPreviewModalProps {
  previewId: string
  items: PreviewItem[]
  activeAwemeId: string
  onSelectAweme: (awemeId: string) => void
  onClose: () => void
  onDownloadItem: (item: PreviewItem) => void
  onOpenComments: (item: PreviewItem) => void
}

export const MediaPreviewModal: React.FC<MediaPreviewModalProps> = ({
  previewId,
  items,
  activeAwemeId,
  onSelectAweme,
  onClose,
  onDownloadItem,
  onOpenComments,
}) => {
  const currentIndex = items.findIndex((it) => it.aweme_id === activeAwemeId)
  const item = currentIndex >= 0 ? items[currentIndex] : items[0]

  const [detail, setDetail] = useState<PreviewMediaDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState('')

  // Video candidate fallback
  const [videoCandIdx, setVideoCandIdx] = useState(0)
  const retriedRefreshRef = useRef(false)

  // Gallery slides & live-photo mode
  const [slideIdx, setSlideIdx] = useState(0)
  const [showLiveVideo, setShowLiveVideo] = useState(true)
  const [imgCandIdx, setImgCandIdx] = useState(0)

  // Zoom & Pan state
  const [scale, setScale] = useState(1)
  const [offset, setOffset] = useState({ x: 0, y: 0 })
  const [dragging, setDragging] = useState(false)
  const dragOriginRef = useRef<{ startX: number; startY: number; origX: number; origY: number } | null>(null)

  // Background music
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const [bgmPlaying, setBgmPlaying] = useState(false)

  const resetZoomPan = useCallback(() => {
    setScale(1)
    setOffset({ x: 0, y: 0 })
  }, [])

  const loadMedia = useCallback(
    async (forceRefresh = false) => {
      if (!item) return
      if (forceRefresh) setRefreshing(true)
      else setLoading(true)
      setError('')
      try {
        const res = await api.getPreviewItemMedia(previewId, item.aweme_id, forceRefresh)
        setDetail(res)
        setVideoCandIdx(0)
        setSlideIdx(0)
        setImgCandIdx(0)
        setShowLiveVideo(true)
        resetZoomPan()
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err))
      } finally {
        setLoading(false)
        setRefreshing(false)
      }
    },
    [item, previewId, resetZoomPan]
  )

  useEffect(() => {
    retriedRefreshRef.current = false
    setBgmPlaying(false)
    if (audioRef.current) {
      audioRef.current.pause()
      audioRef.current.currentTime = 0
    }
    void loadMedia(false)
  }, [activeAwemeId, loadMedia])

  useEffect(() => {
    resetZoomPan()
    setImgCandIdx(0)
    setShowLiveVideo(true)
  }, [slideIdx, resetZoomPan])

  const slides = detail?.slides || []
  const currentSlide = slides[slideIdx]
  const hasPrevWork = currentIndex > 0
  const hasNextWork = currentIndex >= 0 && currentIndex < items.length - 1

  const goPrevWork = useCallback(() => {
    if (hasPrevWork) onSelectAweme(items[currentIndex - 1].aweme_id)
  }, [hasPrevWork, items, currentIndex, onSelectAweme])

  const goNextWork = useCallback(() => {
    if (hasNextWork) onSelectAweme(items[currentIndex + 1].aweme_id)
  }, [hasNextWork, items, currentIndex, onSelectAweme])

  // Keyboard navigation
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose()
      } else if (e.key === 'ArrowLeft') {
        if (slides.length > 1) {
          setSlideIdx((i) => (i - 1 + slides.length) % slides.length)
        } else {
          goPrevWork()
        }
      } else if (e.key === 'ArrowRight') {
        if (slides.length > 1) {
          setSlideIdx((i) => (i + 1) % slides.length)
        } else {
          goNextWork()
        }
      } else if (e.key === '[') {
        goPrevWork()
      } else if (e.key === ']') {
        goNextWork()
      } else if (e.key === '+' || e.key === '=') {
        setScale((s) => Math.min(5, Number((s + 0.35).toFixed(2))))
      } else if (e.key === '-') {
        setScale((s) => {
          const next = Math.max(0.5, Number((s - 0.35).toFixed(2)))
          if (next <= 1) setOffset({ x: 0, y: 0 })
          return next
        })
      } else if (e.key === '0') {
        resetZoomPan()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose, slides.length, goPrevWork, goNextWork, resetZoomPan])

  if (!item) return null

  const videoCandidates = detail?.video_candidates || []
  const activeVideoUrl = videoCandidates[videoCandIdx] || detail?.video_url || ''
  const isVideoWork = Boolean(activeVideoUrl) && slides.length === 0

  const imgCandidates = currentSlide?.image_candidates || (currentSlide?.image_url ? [currentSlide.image_url] : [])
  const activeSlideImageUrl = imgCandidates[imgCandIdx] || currentSlide?.image_url || detail?.cover_url || item.cover_url
  const isShowingLiveVideo = Boolean(currentSlide?.is_live && currentSlide.live_video_url && showLiveVideo)

  const handleVideoError = () => {
    if (videoCandIdx + 1 < videoCandidates.length) {
      setVideoCandIdx((i) => i + 1)
    } else if (!retriedRefreshRef.current) {
      retriedRefreshRef.current = true
      void loadMedia(true)
    }
  }

  const handleImageError = () => {
    if (imgCandIdx + 1 < imgCandidates.length) {
      setImgCandIdx((i) => i + 1)
    }
  }

  const handleWheel = (e: React.WheelEvent) => {
    if (isVideoWork || isShowingLiveVideo) return
    e.preventDefault()
    const delta = e.deltaY < 0 ? 0.25 : -0.25
    setScale((prev) => {
      const next = Math.min(5, Math.max(0.5, Number((prev + delta).toFixed(2))))
      if (next <= 1) setOffset({ x: 0, y: 0 })
      return next
    })
  }

  const handlePointerDown = (e: React.PointerEvent) => {
    if (isVideoWork || isShowingLiveVideo || scale <= 1) return
    e.currentTarget.setPointerCapture(e.pointerId)
    setDragging(true)
    dragOriginRef.current = {
      startX: e.clientX,
      startY: e.clientY,
      origX: offset.x,
      origY: offset.y,
    }
  }

  const handlePointerMove = (e: React.PointerEvent) => {
    if (!dragging || !dragOriginRef.current) return
    setOffset({
      x: dragOriginRef.current.origX + (e.clientX - dragOriginRef.current.startX),
      y: dragOriginRef.current.origY + (e.clientY - dragOriginRef.current.startY),
    })
  }

  const handlePointerUp = () => {
    setDragging(false)
    dragOriginRef.current = null
  }

  const toggleBgm = () => {
    const el = audioRef.current
    if (!el) return
    if (bgmPlaying) {
      el.pause()
      setBgmPlaying(false)
    } else {
      void el.play().then(() => setBgmPlaying(true)).catch(() => setBgmPlaying(false))
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 bg-black/90 backdrop-blur-md flex flex-col text-white select-none"
      onClick={onClose}
    >
      {/* Top Bar */}
      <div
        className="flex items-center justify-between gap-4 px-5 py-3 border-b border-white/10 bg-black/40 shrink-0"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-3 min-w-0 flex-1">
          {item.author_avatar_url && (
            <img
              src={proxyImageUrl(item.author_avatar_url)}
              alt=""
              className="w-8 h-8 rounded-full object-cover border border-white/20 shrink-0"
            />
          )}
          <div className="min-w-0">
            <div className="text-sm font-semibold truncate" title={item.title}>
              {item.title || `作品 ${item.aweme_id}`}
            </div>
            <div className="flex flex-wrap items-center gap-2.5 text-[11px] text-white/65 tabular-nums">
              <span>{item.author_name}</span>
              <span>· {item.publish_time}</span>
              {item.like_count > 0 && (
                <span className="inline-flex items-center gap-1">
                  <Heart className="w-3 h-3 fill-current" />
                  {formatCount(item.like_count)}
                </span>
              )}
              {item.resolution && (
                <span className="px-1.5 py-0.2 rounded bg-white/15 text-[10px]">
                  {item.resolution}
                </span>
              )}
              {slides.length > 0 && (
                <span className="px-1.5 py-0.2 rounded bg-white/15 text-[10px]">
                  {slideIdx + 1} / {slides.length}
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-1.5 shrink-0">
          {detail?.music_url && (
            <>
              <audio
                ref={audioRef}
                src={proxyMediaUrl(detail.music_url)}
                loop
                onEnded={() => setBgmPlaying(false)}
              />
              <button
                onClick={toggleBgm}
                title={detail.music_title ? `配乐：${detail.music_title}` : '播放/暂停背景音乐'}
                className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-xl text-xs transition-colors cursor-pointer ${
                  bgmPlaying ? 'bg-amber-500/85 text-white' : 'bg-white/10 hover:bg-white/20 text-white/85'
                }`}
              >
                {bgmPlaying ? <Pause className="w-3.5 h-3.5" /> : <Music className="w-3.5 h-3.5" />}
                <span className="max-w-[110px] truncate">
                  {bgmPlaying ? '暂停配乐' : detail.music_title || '背景音乐'}
                </span>
              </button>
            </>
          )}

          {currentSlide?.is_live && currentSlide.live_video_url && (
            <button
              onClick={() => setShowLiveVideo((v) => !v)}
              className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-xl text-xs font-medium transition-colors cursor-pointer ${
                showLiveVideo ? 'bg-amber-500 text-white' : 'bg-white/10 hover:bg-white/20 text-white/85'
              }`}
              title="在实况动态播放与高清静图放大模式之间切换"
            >
              {showLiveVideo ? <ImageIcon className="w-3.5 h-3.5" /> : <Sparkles className="w-3.5 h-3.5" />}
              <span>{showLiveVideo ? '看高清静图' : '播放实况'}</span>
            </button>
          )}

          {!isVideoWork && !isShowingLiveVideo && (
            <div className="hidden sm:flex items-center gap-0.5 bg-white/10 rounded-xl p-0.5">
              <button
                onClick={() =>
                  setScale((s) => {
                    const next = Math.max(0.5, Number((s - 0.35).toFixed(2)))
                    if (next <= 1) setOffset({ x: 0, y: 0 })
                    return next
                  })
                }
                title="缩小 (-)"
                className="p-1.5 rounded-lg hover:bg-white/15 cursor-pointer"
              >
                <ZoomOut className="w-3.5 h-3.5" />
              </button>
              <span className="text-[11px] tabular-nums px-1.5 min-w-[44px] text-center">
                {Math.round(scale * 100)}%
              </span>
              <button
                onClick={() => setScale((s) => Math.min(5, Number((s + 0.35).toFixed(2))))}
                title="放大 (+)"
                className="p-1.5 rounded-lg hover:bg-white/15 cursor-pointer"
              >
                <ZoomIn className="w-3.5 h-3.5" />
              </button>
              <button
                onClick={resetZoomPan}
                title="重置缩放 (0)"
                className="p-1.5 rounded-lg hover:bg-white/15 cursor-pointer"
              >
                <RotateCcw className="w-3.5 h-3.5" />
              </button>
            </div>
          )}

          <button
            onClick={() => void loadMedia(true)}
            disabled={refreshing}
            title="刷新播放地址"
            className="p-2 rounded-xl bg-white/10 hover:bg-white/20 disabled:opacity-40 cursor-pointer"
          >
            <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
          </button>

          {(item.media_type === '视频' || item.media_type === '图文') && (
            <button
              onClick={() => {
                onClose()
                onOpenComments(item)
              }}
              title="查看评论与图库"
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs bg-white/10 hover:bg-white/20 cursor-pointer"
            >
              <MessageSquare className="w-3.5 h-3.5" />
              <span>评论</span>
            </button>
          )}

          <button
            onClick={() => onDownloadItem(item)}
            className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl text-xs font-semibold text-white cursor-pointer"
            style={{ backgroundColor: 'var(--accent)' }}
          >
            <Download className="w-3.5 h-3.5" />
            <span>下载此作品</span>
          </button>

          <button
            onClick={onClose}
            title="关闭 (Esc)"
            className="p-2 rounded-xl bg-white/10 hover:bg-white/20 cursor-pointer ml-1"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Main Viewer Viewport */}
      <div
        className="flex-1 min-h-0 relative flex items-center justify-center overflow-hidden p-4"
        onClick={(e) => e.stopPropagation()}
        onWheel={handleWheel}
      >
        {/* Work switcher (left / right edge when list has >1 work) */}
        {hasPrevWork && (
          <button
            onClick={goPrevWork}
            title="上一个作品 ([)"
            className="absolute left-3 top-1/2 -translate-y-1/2 z-20 p-2.5 rounded-full bg-black/55 hover:bg-black/80 border border-white/15 cursor-pointer"
          >
            <ChevronLeft className="w-5 h-5" />
          </button>
        )}
        {hasNextWork && (
          <button
            onClick={goNextWork}
            title="下一个作品 (])"
            className="absolute right-3 top-1/2 -translate-y-1/2 z-20 p-2.5 rounded-full bg-black/55 hover:bg-black/80 border border-white/15 cursor-pointer"
          >
            <ChevronRight className="w-5 h-5" />
          </button>
        )}

        {/* Gallery slide switcher */}
        {slides.length > 1 && (
          <>
            <button
              onClick={() => setSlideIdx((i) => (i - 1 + slides.length) % slides.length)}
              title="上一张 (←)"
              className="absolute left-16 top-1/2 -translate-y-1/2 z-20 p-2 rounded-full bg-white/15 hover:bg-white/30 backdrop-blur-sm cursor-pointer"
            >
              <ChevronLeft className="w-5 h-5" />
            </button>
            <button
              onClick={() => setSlideIdx((i) => (i + 1) % slides.length)}
              title="下一张 (→)"
              className="absolute right-16 top-1/2 -translate-y-1/2 z-20 p-2 rounded-full bg-white/15 hover:bg-white/30 backdrop-blur-sm cursor-pointer"
            >
              <ChevronRight className="w-5 h-5" />
            </button>
          </>
        )}

        {loading ? (
          <div className="flex flex-col items-center gap-3 text-white/75 text-xs">
            <Loader2 className="w-8 h-8 animate-spin" />
            <span>正在加载媒体流与高清大图…</span>
          </div>
        ) : error ? (
          <div className="flex flex-col items-center gap-3 text-center max-w-md">
            <div className="text-sm text-rose-300">媒体预览加载失败：{error}</div>
            <button
              onClick={() => void loadMedia(true)}
              className="flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs bg-white/15 hover:bg-white/25 cursor-pointer"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              <span>重新获取链接</span>
            </button>
          </div>
        ) : isVideoWork ? (
          <video
            key={activeVideoUrl}
            src={proxyMediaUrl(activeVideoUrl)}
            poster={proxyImageUrl(detail?.cover_url || item.cover_url)}
            controls
            autoPlay
            loop
            playsInline
            onError={handleVideoError}
            className="max-h-full max-w-full rounded-xl shadow-2xl bg-black"
          />
        ) : isShowingLiveVideo && currentSlide ? (
          <div className="relative flex items-center justify-center max-h-full max-w-full">
            <video
              key={currentSlide.live_video_url}
              src={proxyMediaUrl(currentSlide.live_video_url)}
              poster={proxyImageUrl(activeSlideImageUrl)}
              controls
              autoPlay
              loop
              playsInline
              onError={() => setShowLiveVideo(false)}
              className="max-h-[calc(100vh-190px)] max-w-full rounded-xl shadow-2xl bg-black"
            />
            <span className="absolute top-3 left-3 px-2 py-0.5 rounded-md text-[11px] font-semibold bg-amber-500/90 text-white inline-flex items-center gap-1">
              <Play className="w-3 h-3 fill-current" />
              实况播放中 · 滚轮放大可切换静图
            </span>
          </div>
        ) : (
          <div
            className={`w-full h-full flex items-center justify-center overflow-hidden ${
              scale > 1 ? (dragging ? 'cursor-grabbing' : 'cursor-grab') : 'cursor-zoom-in'
            }`}
            onPointerDown={handlePointerDown}
            onPointerMove={handlePointerMove}
            onPointerUp={handlePointerUp}
            onPointerCancel={handlePointerUp}
            onDoubleClick={() => {
              if (scale > 1.05) {
                resetZoomPan()
              } else {
                setScale(2.2)
              }
            }}
          >
            <img
              key={activeSlideImageUrl}
              src={proxyImageUrl(activeSlideImageUrl)}
              alt={item.title}
              draggable={false}
              onError={handleImageError}
              style={{
                transform: `translate3d(${offset.x}px, ${offset.y}px, 0) scale(${scale})`,
                transition: dragging ? 'none' : 'transform 120ms ease-out',
              }}
              className="max-h-[calc(100vh-190px)] max-w-full object-contain rounded-lg shadow-2xl"
            />
            {!isVideoWork && scale === 1 && (
              <div className="pointer-events-none absolute bottom-3 px-3 py-1 rounded-full bg-black/55 text-[11px] text-white/75 flex items-center gap-1.5">
                <Maximize2 className="w-3 h-3" />
                <span>滚轮或双击可放大并拖拽查看细节</span>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Gallery Filmstrip */}
      {slides.length > 1 && (
        <div
          className="px-5 py-2.5 border-t border-white/10 bg-black/45 flex items-center justify-center gap-2 overflow-x-auto shrink-0"
          onClick={(e) => e.stopPropagation()}
        >
          {slides.map((s, idx) => (
            <button
              key={`${s.index}-${idx}`}
              onClick={() => setSlideIdx(idx)}
              className={`relative w-12 h-14 rounded-lg overflow-hidden border-2 shrink-0 transition-all cursor-pointer ${
                idx === slideIdx
                  ? 'border-white scale-105 opacity-100'
                  : 'border-transparent opacity-55 hover:opacity-90'
              }`}
            >
              <img
                src={proxyImageUrl(s.image_url)}
                alt=""
                loading="lazy"
                className="w-full h-full object-cover"
              />
              {s.is_live && (
                <span className="absolute top-0.5 right-0.5 w-2 h-2 rounded-full bg-amber-400" />
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
