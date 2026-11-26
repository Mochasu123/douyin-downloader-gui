export type PageKey = 'download' | 'creator' | 'comments' | 'tasks' | 'history' | 'settings'
export type ThemeMode = 'light' | 'dark' | 'system'
export type ViewMode = 'grid' | 'table'

export interface UserInfo {
  uid: string
  sec_uid: string
  nickname: string
  avatar_url: string
}

export interface LoginFlowState {
  status: 'idle' | 'waiting' | 'success' | 'failed'
  message: string
}

export interface AuthStatus {
  has_cookie: boolean
  cookie_count: number
  missing_keys: string[]
  logged_in: boolean
  verified: boolean
  user: UserInfo | null
  error?: string
  login_flow: LoginFlowState
}

export interface PreviewItem {
  aweme_id: string
  title: string
  publish_time: string
  duration: string
  media_type: string
  author_name: string
  author_sec_uid: string
  size_text: string
  source_type: string
  collection_name: string
  cover_url: string
  like_count: number
  comment_count: number
  share_count: number
  collect_count: number
  is_live_photo: boolean
  image_count: number
  resolution: string
  share_url: string
  author_avatar_url: string
  create_time: number
  duration_ms: number
}

export interface PreviewMeta {
  preview_id: string
  url: string
  resolved_url: string
  url_type: string
  source_type: string
  author_name: string
  avatar_url: string
  sec_uid: string
  signature: string
  follower_count: number
  aweme_count: number
}

export interface ParseHistoryEntry {
  id: number
  kind: string
  content_id: string
  name: string
  original_url: string
  resolved_url: string
  author_name: string
  avatar_url: string
  created_at: string
}

export interface JobItemState {
  aweme_id: string
  title: string
  media_type: string
  author_name: string
  status: 'pending' | 'downloading' | 'success' | 'skipped' | 'failed' | 'cancelled'
  progress: number
  written: number
  total_bytes: number
  error: string
}

export interface DownloadJob {
  job_id: string
  title: string
  url: string
  source_kind: string
  status: 'pending' | 'running' | 'paused' | 'success' | 'failed' | 'cancelled'
  created_at: string
  started_at: string | null
  finished_at: string | null
  total: number
  completed: number
  success: number
  failed: number
  skipped: number
  error: string | null
  author_nickname: string | null
  author_sec_uid: string | null
  output_dir: string
  current_file: string
  current_written: number
  current_total: number
  speed_bps: number
  eta_seconds: number | null
  step: string
  items: JobItemState[]
  can_retry_failed: boolean
}

export interface CommentEntry {
  cid: string
  nickname: string
  avatar_url: string
  time: string
  create_time: number
  ip_label: string
  digg_count: number
  text: string
  image_count: number
  live_image_count: number
}

export interface CommentImageEntry {
  key: string
  comment_id: string
  index: number
  nickname: string
  preview_url: string
  origin_url: string
  is_live: boolean
  width: number
  height: number
}

export interface HistoryItem {
  aweme_id: string
  aweme_type: string
  title: string
  author_id: string
  author_name: string
  author_sec_uid: string
  create_time: number
  download_time: number
  file_path: string
  primary_file: string
  file_exists: boolean
  cover_url: string
  cover_urls: string[]
  job_id: string
}

export interface HistoryStats {
  total_count: number
  video_count: number
  gallery_count: number
  music_count: number
  live_count: number
  author_count: number
  recent_7d_count: number
  top_authors: { author_name: string; count: number }[]
}

export interface AppConfigPayload {
  path: string
  thread: number
  retry_times: number
  rate_limit: number
  proxy: string
  video_quality: string
  video: boolean
  cover: boolean
  music: boolean
  avatar: boolean
  json: boolean
  live_photo_merge: boolean
  live_photo_format: string
  homepage_screenshot: boolean
  author_url: boolean
  download_pinned: boolean
  folderstyle: boolean
  group_by_mode: boolean
  author_dir: string
  filename_template: string
  folder_template: string
  redownload_missing_files: boolean
  increase: Record<string, boolean>
  browser_fallback: {
    enabled: boolean
    headless: boolean
    max_scrolls: number
    idle_rounds: number
    wait_timeout_seconds: number
  }
  comments: {
    enabled: boolean
    include_replies: boolean
    max_comments: number
    page_size: number
    download_media: boolean
  }
  live: {
    max_duration_seconds: number
    chunk_size: number
    segment_seconds: number
    idle_timeout_seconds: number
  }
  notifications: {
    enabled: boolean
    on_success: boolean
    on_failure: boolean
    providers: unknown[]
  }
  transcript: {
    enabled: boolean
    model: string
    output_dir: string
    api_url: string
    api_key: string
  }
}

export interface SettingsPayload {
  config: AppConfigPayload
  cookie: {
    has_cookie: boolean
    count: number
    essential_present: number
    raw: string
  }
  preferences: {
    theme: ThemeMode
    view_mode: ViewMode
    clipboard_watch: boolean
  }
}

export interface LogEntry {
  ts: string
  level: string
  logger: string
  message: string
}

export interface ToastMessage {
  id: string
  kind: 'info' | 'success' | 'warning' | 'error'
  title: string
  detail?: string
  actionLabel?: string
  onAction?: () => void
}
