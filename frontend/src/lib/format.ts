export function formatBytes(bytes: number | null | undefined): string {
  if (!bytes || bytes <= 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let val = bytes
  let idx = 0
  while (val >= 1024 && idx < units.length - 1) {
    val /= 1024
    idx += 1
  }
  return idx === 0 ? `${Math.round(val)} B` : `${val.toFixed(1)} ${units[idx]}`
}

export function formatSpeed(bps: number | null | undefined): string {
  if (!bps || bps <= 0) return '0 B/s'
  return `${formatBytes(bps)}/s`
}

export function formatEta(seconds: number | null | undefined): string {
  if (seconds == null || seconds <= 0 || !Number.isFinite(seconds)) return '--'
  const s = Math.round(seconds)
  if (s < 60) return `${s}s`
  const m = Math.floor(s / 60)
  const rem = s % 60
  if (m < 60) return `${m}m ${rem}s`
  const h = Math.floor(m / 60)
  return `${h}h ${m % 60}m`
}

export function formatCount(val: number | null | undefined): string {
  if (!val || val <= 0) return '0'
  if (val >= 100000000) return `${(val / 100000000).toFixed(1)}亿`
  if (val >= 10000) return `${(val / 10000).toFixed(1)}万`
  return String(val)
}

export function formatTimestamp(ts: number | null | undefined): string {
  if (!ts || ts <= 0) return '未知'
  try {
    const d = new Date(ts * 1000)
    const pad = (n: number) => String(n).padStart(2, '0')
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
  } catch {
    return '未知'
  }
}

export function proxyImageUrl(url: string | null | undefined): string {
  if (!url) return ''
  if (url.startsWith('/api/')) return url
  return `/api/proxy/image?url=${encodeURIComponent(url)}`
}

export const URL_TYPE_LABELS: Record<string, string> = {
  video: '单个视频',
  gallery: '图文作品',
  user: '博主主页',
  collection: '合集',
  music: '音乐原声',
  live: '直播间',
  live_replay: '直播回放',
  lvdetail: '放映厅(DRM)',
  short: '短链接',
  unknown: '待识别',
}
