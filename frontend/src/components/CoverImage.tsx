import React, { useState } from 'react'
import { Film, Image as ImageIcon, Music, Radio } from 'lucide-react'
import { proxyImageUrl } from '../lib/format'

interface CoverImageProps {
  url?: string | null
  alt?: string
  mediaType?: string
  className?: string
}

export const CoverImage: React.FC<CoverImageProps> = ({
  url,
  alt = '',
  mediaType = 'video',
  className = '',
}) => {
  const [failed, setFailed] = useState(false)

  if (url && !failed) {
    return (
      <img
        src={proxyImageUrl(url)}
        alt={alt}
        loading="lazy"
        onError={() => setFailed(true)}
        className={className}
      />
    )
  }

  const Icon =
    mediaType === '图文' || mediaType === 'gallery'
      ? ImageIcon
      : mediaType === '音乐' || mediaType === 'music'
        ? Music
        : mediaType === '直播' || mediaType === 'live'
          ? Radio
          : Film

  return (
    <div
      className="w-full h-full flex flex-col items-center justify-center gap-1.5"
      style={{
        background:
          'linear-gradient(145deg, var(--bg-muted) 0%, var(--bg-hover) 100%)',
        color: 'var(--text-muted)',
      }}
    >
      <Icon className="w-8 h-8 opacity-40" />
    </div>
  )
}
