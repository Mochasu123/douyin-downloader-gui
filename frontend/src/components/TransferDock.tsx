import React from 'react'
import { Activity, ArrowRight, Pause, Play, Square } from 'lucide-react'
import type { DownloadJob } from '../types/api'
import { formatBytes, formatEta, formatSpeed } from '../lib/format'
import { api } from '../lib/api'

interface TransferDockProps {
  activeJobs: DownloadJob[]
  onOpenTasks: () => void
}

export const TransferDock: React.FC<TransferDockProps> = ({ activeJobs, onOpenTasks }) => {
  if (activeJobs.length === 0) return null

  const primary = activeJobs[0]
  const total = activeJobs.reduce((acc, j) => acc + Math.max(j.total, 0), 0)
  const completed = activeJobs.reduce((acc, j) => acc + Math.max(j.completed, 0), 0)
  const totalSpeed = activeJobs.reduce((acc, j) => acc + (j.speed_bps || 0), 0)
  const pct = total > 0 ? Math.min(100, Math.round((completed / total) * 100)) : 0
  const isPaused = primary.status === 'paused'

  return (
    <div
      className="mx-6 mb-3 px-4 py-2.5 rounded-2xl border backdrop-blur-md flex items-center gap-4 animate-fade-up shrink-0"
      style={{
        backgroundColor: 'var(--bg-glass)',
        borderColor: 'var(--border-strong)',
        boxShadow: 'var(--shadow-md)',
      }}
    >
      <div
        className="w-8 h-8 rounded-xl flex items-center justify-center shrink-0"
        style={{ backgroundColor: 'var(--accent-soft)', color: 'var(--accent)' }}
      >
        <Activity className="w-4 h-4" />
      </div>

      <div className="min-w-0 flex-1">
        <div className="flex items-center justify-between gap-2 text-xs mb-1">
          <div className="flex items-center gap-2 min-w-0">
            <span className="font-semibold truncate">{primary.title}</span>
            {primary.current_file && (
              <span className="truncate hidden sm:inline" style={{ color: 'var(--text-muted)' }}>
                · {primary.current_file}
              </span>
            )}
          </div>
          <div className="flex items-center gap-3 shrink-0 tabular-nums font-medium">
            {primary.current_total > 0 && (
              <span style={{ color: 'var(--text-muted)' }}>
                {formatBytes(primary.current_written)} / {formatBytes(primary.current_total)}
              </span>
            )}
            <span style={{ color: 'var(--accent)' }}>{formatSpeed(totalSpeed)}</span>
            {primary.eta_seconds != null && (
              <span style={{ color: 'var(--text-muted)' }}>ETA {formatEta(primary.eta_seconds)}</span>
            )}
            <span>
              {completed}/{total || '?'} ({pct}%)
            </span>
          </div>
        </div>
        <div
          className="h-1.5 rounded-full overflow-hidden"
          style={{ backgroundColor: 'var(--bg-muted)' }}
        >
          <div
            className="h-full rounded-full transition-all duration-200"
            style={{
              width: `${Math.max(4, pct)}%`,
              background: isPaused
                ? 'var(--warning)'
                : 'linear-gradient(90deg, var(--accent) 0%, #0ea5e9 100%)',
            }}
          />
        </div>
      </div>

      <div className="flex items-center gap-1.5 shrink-0">
        {isPaused ? (
          <button
            onClick={() => api.resumeTask(primary.job_id)}
            title="继续"
            className="p-1.5 rounded-lg hover:bg-[var(--bg-muted)] cursor-pointer"
            style={{ color: 'var(--accent)' }}
          >
            <Play className="w-4 h-4" />
          </button>
        ) : (
          <button
            onClick={() => api.pauseTask(primary.job_id)}
            title="暂停"
            className="p-1.5 rounded-lg hover:bg-[var(--bg-muted)] cursor-pointer"
            style={{ color: 'var(--text-secondary)' }}
          >
            <Pause className="w-4 h-4" />
          </button>
        )}
        <button
          onClick={() => api.cancelTask(primary.job_id)}
          title="终止"
          className="p-1.5 rounded-lg hover:bg-[var(--danger-soft)] cursor-pointer"
          style={{ color: 'var(--danger)' }}
        >
          <Square className="w-4 h-4" />
        </button>
        <button
          onClick={onOpenTasks}
          className="flex items-center gap-1 text-xs font-medium px-2.5 py-1.5 rounded-lg hover:bg-[var(--bg-muted)] cursor-pointer"
          style={{ color: 'var(--accent)' }}
        >
          <span>详情</span>
          <ArrowRight className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  )
}
