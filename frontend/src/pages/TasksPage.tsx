import React, { useState } from 'react'
import {
  Activity,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  FolderOpen,
  Pause,
  Play,
  RotateCcw,
  Square,
  Trash2,
  XCircle,
} from 'lucide-react'
import type { DownloadJob } from '../types/api'
import { api } from '../lib/api'
import { formatBytes, formatEta, formatSpeed } from '../lib/format'

interface TasksPageProps {
  jobs: DownloadJob[]
  onRetrySuccess: () => void
  onToast: (kind: 'info' | 'success' | 'warning' | 'error', title: string, detail?: string) => void
}

export const TasksPage: React.FC<TasksPageProps> = ({ jobs, onToast }) => {
  const [expanded, setExpanded] = useState<Set<string>>(new Set())

  const toggleExpand = (id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const clearCompleted = async () => {
    const doneJobs = jobs.filter((j) => ['success', 'failed', 'cancelled'].includes(j.status))
    for (const j of doneJobs) {
      await api.deleteTask(j.job_id)
    }
    if (doneJobs.length > 0) {
      onToast('info', `已清理 ${doneJobs.length} 条已完成任务`)
    }
  }

  const statusPill = (status: DownloadJob['status']) => {
    const map: Record<string, { label: string; bg: string; fg: string }> = {
      pending: { label: '排队中', bg: 'var(--bg-muted)', fg: 'var(--text-secondary)' },
      running: { label: '下载中', bg: 'var(--accent-soft)', fg: 'var(--accent)' },
      paused: { label: '已暂停', bg: 'var(--warning-soft)', fg: 'var(--warning)' },
      success: { label: '已完成', bg: 'var(--success-soft)', fg: 'var(--success)' },
      failed: { label: '有失败', bg: 'var(--danger-soft)', fg: 'var(--danger)' },
      cancelled: { label: '已终止', bg: 'var(--warning-soft)', fg: 'var(--warning)' },
    }
    return map[status] || map.pending
  }

  return (
    <div className="flex flex-col h-full gap-4 p-6 pb-3 overflow-hidden">
      <div className="flex items-center justify-between gap-4 shrink-0">
        <div>
          <h1 className="text-xl font-bold tracking-tight">任务中心</h1>
          <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>
            实时查看下载速率、单文件进度、暂停恢复与失败项一键重试
          </p>
        </div>
        {jobs.some((j) => ['success', 'failed', 'cancelled'].includes(j.status)) && (
          <button
            onClick={clearCompleted}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-medium border hover:bg-[var(--bg-muted)] cursor-pointer"
            style={{
              backgroundColor: 'var(--bg-surface)',
              borderColor: 'var(--border-subtle)',
              color: 'var(--text-secondary)',
            }}
          >
            <Trash2 className="w-3.5 h-3.5" />
            <span>清理已结束任务</span>
          </button>
        )}
      </div>

      <div className="flex-1 overflow-y-auto space-y-3 pr-1">
        {jobs.length === 0 ? (
          <div
            className="h-full min-h-[260px] rounded-2xl border border-dashed flex flex-col items-center justify-center p-10 text-center"
            style={{ backgroundColor: 'var(--bg-surface)', borderColor: 'var(--border-strong)' }}
          >
            <Activity className="w-10 h-10 mb-3 opacity-30" style={{ color: 'var(--accent)' }} />
            <div className="text-sm font-semibold">暂无下载任务</div>
            <div className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>
              在「链接下载」或「博主主页」发起下载后，任务进度会展示在这里
            </div>
          </div>
        ) : (
          jobs.map((job) => {
            const pill = statusPill(job.status)
            const isActive = job.status === 'running' || job.status === 'paused' || job.status === 'pending'
            const pct = job.total > 0 ? Math.min(100, Math.round((job.completed / job.total) * 100)) : 0
            const isOpen = expanded.has(job.job_id)

            return (
              <div
                key={job.job_id}
                className="rounded-2xl border p-4 space-y-3 transition-all"
                style={{
                  backgroundColor: 'var(--bg-surface)',
                  borderColor: isActive ? 'var(--accent-ring)' : 'var(--border-subtle)',
                  boxShadow: 'var(--shadow-sm)',
                }}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span
                        className="px-2 py-0.5 rounded-full text-[11px] font-semibold shrink-0"
                        style={{ backgroundColor: pill.bg, color: pill.fg }}
                      >
                        {pill.label}
                      </span>
                      <span className="font-semibold text-sm truncate">{job.title}</span>
                    </div>
                    <div className="text-[11.5px] mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 tabular-nums" style={{ color: 'var(--text-muted)' }}>
                      <span>共 {job.total} 项</span>
                      <span style={{ color: 'var(--success)' }}>成功 {job.success}</span>
                      {job.skipped > 0 && <span>跳过 {job.skipped}</span>}
                      {job.failed > 0 && <span style={{ color: 'var(--danger)' }}>失败 {job.failed}</span>}
                      {isActive && job.speed_bps > 0 && (
                        <span style={{ color: 'var(--accent)' }}>{formatSpeed(job.speed_bps)}</span>
                      )}
                      {isActive && job.eta_seconds != null && (
                        <span>剩余 {formatEta(job.eta_seconds)}</span>
                      )}
                      {job.step && <span>· {job.step}</span>}
                    </div>
                  </div>

                  <div className="flex items-center gap-1.5 shrink-0">
                    {job.status === 'running' && (
                      <button
                        onClick={() => api.pauseTask(job.job_id)}
                        title="暂停"
                        className="p-1.5 rounded-lg border hover:bg-[var(--bg-muted)] cursor-pointer"
                        style={{ borderColor: 'var(--border-subtle)' }}
                      >
                        <Pause className="w-3.5 h-3.5" />
                      </button>
                    )}
                    {job.status === 'paused' && (
                      <button
                        onClick={() => api.resumeTask(job.job_id)}
                        title="继续"
                        className="p-1.5 rounded-lg border hover:bg-[var(--bg-muted)] cursor-pointer"
                        style={{ borderColor: 'var(--border-subtle)', color: 'var(--accent)' }}
                      >
                        <Play className="w-3.5 h-3.5" />
                      </button>
                    )}
                    {isActive && (
                      <button
                        onClick={() => api.cancelTask(job.job_id)}
                        title="终止"
                        className="p-1.5 rounded-lg border hover:bg-[var(--danger-soft)] cursor-pointer"
                        style={{ borderColor: 'var(--border-subtle)', color: 'var(--danger)' }}
                      >
                        <Square className="w-3.5 h-3.5" />
                      </button>
                    )}
                    {job.can_retry_failed && (
                      <button
                        onClick={async () => {
                          try {
                            await api.retryFailedTask(job.job_id)
                            onToast('info', '已创建重试任务')
                          } catch (err) {
                            onToast('error', '重试失败', err instanceof Error ? err.message : String(err))
                          }
                        }}
                        className="flex items-center gap-1 px-2.5 py-1.5 rounded-xl text-xs font-medium cursor-pointer"
                        style={{ backgroundColor: 'var(--warning-soft)', color: 'var(--warning)' }}
                      >
                        <RotateCcw className="w-3.5 h-3.5" />
                        <span>重试失败</span>
                      </button>
                    )}
                    {job.output_dir && (
                      <button
                        onClick={() => api.openPath(job.output_dir)}
                        title="打开输出目录"
                        className="p-1.5 rounded-lg border hover:bg-[var(--bg-muted)] cursor-pointer"
                        style={{ borderColor: 'var(--border-subtle)' }}
                      >
                        <FolderOpen className="w-3.5 h-3.5" />
                      </button>
                    )}
                    {!isActive && (
                      <button
                        onClick={() => api.deleteTask(job.job_id)}
                        title="删除记录"
                        className="p-1.5 rounded-lg hover:bg-[var(--danger-soft)] cursor-pointer"
                        style={{ color: 'var(--text-muted)' }}
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    )}
                  </div>
                </div>

                {/* Progress bar */}
                <div className="space-y-1">
                  <div className="h-2 rounded-full overflow-hidden" style={{ backgroundColor: 'var(--bg-muted)' }}>
                    <div
                      className="h-full rounded-full transition-all duration-200"
                      style={{
                        width: `${job.status === 'success' ? 100 : Math.max(isActive ? 3 : 0, pct)}%`,
                        backgroundColor:
                          job.status === 'failed'
                            ? 'var(--danger)'
                            : job.status === 'success'
                              ? 'var(--success)'
                              : job.status === 'paused'
                                ? 'var(--warning)'
                                : 'var(--accent)',
                      }}
                    />
                  </div>
                  {isActive && job.current_file && (
                    <div className="flex items-center justify-between text-[11px] tabular-nums" style={{ color: 'var(--text-muted)' }}>
                      <span className="truncate">当前：{job.current_file}</span>
                      {job.current_total > 0 && (
                        <span>
                          {formatBytes(job.current_written)} / {formatBytes(job.current_total)}
                        </span>
                      )}
                    </div>
                  )}
                  {job.error && (
                    <div className="text-[11px] px-2.5 py-1.5 rounded-lg" style={{ backgroundColor: 'var(--danger-soft)', color: 'var(--danger)' }}>
                      {job.error}
                    </div>
                  )}
                </div>

                {/* Expandable item list */}
                {job.items && job.items.length > 0 && (
                  <div>
                    <button
                      onClick={() => toggleExpand(job.job_id)}
                      className="flex items-center gap-1 text-[11.5px] font-medium cursor-pointer"
                      style={{ color: 'var(--text-secondary)' }}
                    >
                      {isOpen ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
                      <span>作品明细 ({job.items.length})</span>
                    </button>
                    {isOpen && (
                      <div className="mt-2 max-h-56 overflow-y-auto rounded-xl border divide-y text-xs" style={{ borderColor: 'var(--border-subtle)' }}>
                        {job.items.map((it) => (
                          <div key={it.aweme_id} className="px-3 py-1.5 flex items-center justify-between gap-3">
                            <span className="truncate flex-1">{it.title}</span>
                            <span className="text-[11px] tabular-nums shrink-0" style={{ color: 'var(--text-muted)' }}>
                              {it.status === 'downloading' && it.progress > 0
                                ? `${Math.round(it.progress)}%`
                                : it.status === 'success'
                                  ? '已完成'
                                  : it.status === 'skipped'
                                    ? '已存在'
                                    : it.status === 'failed'
                                      ? '失败'
                                      : '等待中'}
                            </span>
                            {it.status === 'success' ? (
                              <CheckCircle2 className="w-3.5 h-3.5 shrink-0" style={{ color: 'var(--success)' }} />
                            ) : it.status === 'failed' ? (
                              <XCircle className="w-3.5 h-3.5 shrink-0" style={{ color: 'var(--danger)' }} />
                            ) : null}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}
