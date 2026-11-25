import type {
  AuthStatus,
  CommentEntry,
  CommentImageEntry,
  DownloadJob,
  HistoryItem,
  HistoryStats,
  LoginFlowState,
  ParseHistoryEntry,
  SettingsPayload,
} from '../types/api'

declare global {
  interface Window {
    pywebview?: {
      api?: {
        pick_directory?: (initialDir?: string) => Promise<string | null>
        save_file_dialog?: (defaultName?: string) => Promise<string | null>
        open_path?: (path: string) => Promise<boolean>
        reveal_in_explorer?: (path: string) => Promise<boolean>
        read_clipboard?: () => Promise<string>
      }
    }
  }
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
    ...init,
  })
  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try {
      const data = await res.json()
      if (data?.detail) detail = String(data.detail)
    } catch {
      // ignore
    }
    throw new Error(detail)
  }
  return (await res.json()) as T
}

export const api = {
  health: () => request<{ status: string; version: string; project_root: string }>('/api/health'),

  getAuthStatus: (verify = false) =>
    request<AuthStatus>(`/api/auth/status?verify=${verify ? 'true' : 'false'}`),
  saveCookie: (cookie: string) =>
    request<AuthStatus>('/api/auth/cookie', {
      method: 'POST',
      body: JSON.stringify({ cookie }),
    }),
  startBrowserLogin: () =>
    request<LoginFlowState>('/api/auth/browser-login/start', { method: 'POST' }),
  extractBrowserLogin: () =>
    request<LoginFlowState>('/api/auth/browser-login/extract', { method: 'POST' }),
  cancelBrowserLogin: () =>
    request<LoginFlowState>('/api/auth/browser-login/cancel', { method: 'POST' }),

  getSettings: () => request<SettingsPayload>('/api/settings'),
  saveSettings: (payload: Partial<{ config: unknown; cookie_raw: string; preferences: unknown }>) =>
    request<SettingsPayload>('/api/settings', {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),
  testProxy: (proxy: string) =>
    request<{ ok: boolean; status?: number; latency_ms: number; error?: string }>(
      '/api/settings/test-proxy',
      { method: 'POST', body: JSON.stringify({ proxy }) }
    ),
  openPath: (path: string, reveal = false) =>
    request<{ ok: boolean; path: string }>('/api/system/open-path', {
      method: 'POST',
      body: JSON.stringify({ path, reveal }),
    }),

  inspectUrls: (text: string) =>
    request<{ urls: { url: string; type: string }[] }>('/api/urls/inspect', {
      method: 'POST',
      body: JSON.stringify({ text }),
    }),
  startPreview: (payload: {
    preview_id?: string
    urls?: string[]
    sec_uid?: string
    mode?: string
    limit?: number
    start_time?: string
    end_time?: string
    increase?: boolean | null
  }) =>
    request<{ preview_id: string }>('/api/preview/start', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  cancelPreview: (previewId: string) =>
    request<{ cancelled: boolean }>(`/api/preview/cancel/${previewId}`, { method: 'POST' }),
  getParseHistory: (scope: 'link' | 'user') =>
    request<{ items: ParseHistoryEntry[] }>(`/api/preview/history?scope=${scope}`),
  deleteParseHistory: (payload: { ids?: number[]; scope?: 'link' | 'user' }) =>
    request<{ deleted: number }>('/api/preview/history', {
      method: 'DELETE',
      body: JSON.stringify(payload),
    }),

  startDownload: (payload: {
    preview_id?: string
    aweme_ids?: string[]
    urls?: string[]
    mode?: string
    title?: string
    overrides?: Record<string, unknown>
  }) =>
    request<{ job: DownloadJob }>('/api/tasks/download', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  getTasks: () => request<{ jobs: DownloadJob[] }>('/api/tasks'),
  pauseTask: (jobId: string) => request<{ ok: boolean }>(`/api/tasks/${jobId}/pause`, { method: 'POST' }),
  resumeTask: (jobId: string) => request<{ ok: boolean }>(`/api/tasks/${jobId}/resume`, { method: 'POST' }),
  cancelTask: (jobId: string) => request<{ ok: boolean }>(`/api/tasks/${jobId}/cancel`, { method: 'POST' }),
  retryFailedTask: (jobId: string) =>
    request<{ job: DownloadJob }>(`/api/tasks/${jobId}/retry-failed`, { method: 'POST' }),
  deleteTask: (jobId: string) => request<{ ok: boolean }>(`/api/tasks/${jobId}`, { method: 'DELETE' }),

  loadComments: (payload: { aweme_id: string; include_replies?: boolean; max_comments?: number }) =>
    request<{
      aweme_id: string
      comments: CommentEntry[]
      images: CommentImageEntry[]
      total_comments: number
      total_images: number
    }>('/api/comments/load', { method: 'POST', body: JSON.stringify(payload) }),
  downloadCommentImages: (payload: { aweme_id: string; keys: string[]; save_dir: string }) =>
    request<{ success: number; failed: number; save_dir: string }>('/api/comments/download-images', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  exportCommentsExcel: async (payload: { aweme_id: string; output_path?: string; aweme_title?: string }) => {
    if (payload.output_path) {
      return request<{ ok: boolean; path: string }>('/api/comments/export-excel', {
        method: 'POST',
        body: JSON.stringify(payload),
      })
    }
    const res = await fetch('/api/comments/export-excel', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    if (!res.ok) {
      throw new Error(`导出失败 (${res.status})`)
    }
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${payload.aweme_id}_评论.xlsx`
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
    return { ok: true, path: `${payload.aweme_id}_评论.xlsx` }
  },

  getHistory: (params: {
    page?: number
    size?: number
    q?: string
    author?: string
    aweme_type?: string
    sort?: string
  }) => {
    const qs = new URLSearchParams()
    if (params.page) qs.set('page', String(params.page))
    if (params.size) qs.set('size', String(params.size))
    if (params.q) qs.set('q', params.q)
    if (params.author) qs.set('author', params.author)
    if (params.aweme_type) qs.set('aweme_type', params.aweme_type)
    if (params.sort) qs.set('sort', params.sort)
    return request<{ total: number; page: number; size: number; items: HistoryItem[] }>(
      `/api/history?${qs.toString()}`
    )
  },
  getHistoryStats: () => request<HistoryStats>('/api/history/stats'),
  deleteHistory: (aweme_ids: string[], delete_files = false) =>
    request<{ deleted: number }>('/api/history', {
      method: 'DELETE',
      body: JSON.stringify({ aweme_ids, delete_files }),
    }),

  clearLogs: () => request<{ ok: boolean }>('/api/logs', { method: 'DELETE' }),
}

export async function nativePickDirectory(initialDir?: string): Promise<string | null> {
  if (window.pywebview?.api?.pick_directory) {
    return window.pywebview.api.pick_directory(initialDir)
  }
  return null
}

export async function nativeSaveFileDialog(defaultName?: string): Promise<string | null> {
  if (window.pywebview?.api?.save_file_dialog) {
    return window.pywebview.api.save_file_dialog(defaultName)
  }
  return null
}

export async function nativeReadClipboard(): Promise<string> {
  if (window.pywebview?.api?.read_clipboard) {
    try {
      const txt = await window.pywebview.api.read_clipboard()
      if (txt) return txt
    } catch {
      // fall through
    }
  }
  if (navigator.clipboard?.readText) {
    return navigator.clipboard.readText()
  }
  return ''
}
