import React, { useEffect, useMemo, useRef, useState } from 'react'
import { Check, Copy, Search, Trash2, X } from 'lucide-react'
import type { LogEntry } from '../types/api'

interface LogDrawerProps {
  open: boolean
  logs: LogEntry[]
  onClose: () => void
  onClear: () => void
}

export const LogDrawer: React.FC<LogDrawerProps> = ({ open, logs, onClose, onClear }) => {
  const [levelFilter, setLevelFilter] = useState<'ALL' | 'INFO' | 'WARNING' | 'ERROR'>('ALL')
  const [query, setQuery] = useState('')
  const [autoScroll, setAutoScroll] = useState(true)
  const [copied, setCopied] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    return logs.filter((entry) => {
      if (levelFilter !== 'ALL') {
        if (levelFilter === 'WARNING' && entry.level !== 'WARNING') return false
        if (levelFilter === 'ERROR' && entry.level !== 'ERROR' && entry.level !== 'CRITICAL') return false
        if (levelFilter === 'INFO' && entry.level !== 'INFO') return false
      }
      if (!q) return true
      return (
        entry.message.toLowerCase().includes(q) ||
        entry.logger.toLowerCase().includes(q)
      )
    })
  }, [logs, levelFilter, query])

  useEffect(() => {
    if (open && autoScroll) {
      bottomRef.current?.scrollIntoView({ behavior: 'auto' })
    }
  }, [filtered.length, open, autoScroll])

  if (!open) return null

  const copyAll = async () => {
    const text = filtered.map((l) => `[${l.ts}] [${l.level}] [${l.logger}] ${l.message}`).join('\n')
    await navigator.clipboard?.writeText(text)
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1500)
  }

  return (
    <aside
      className="w-[380px] shrink-0 border-l flex flex-col h-full animate-fade-up"
      style={{
        backgroundColor: 'var(--bg-sidebar)',
        borderColor: 'var(--border-subtle)',
      }}
    >
      <div
        className="px-4 h-14 flex items-center justify-between border-b shrink-0"
        style={{ borderColor: 'var(--border-subtle)' }}
      >
        <div className="flex items-center gap-2">
          <span className="font-semibold text-sm">运行日志</span>
          <span
            className="tabular-nums text-[11px] px-2 py-0.5 rounded-full font-medium"
            style={{ backgroundColor: 'var(--bg-muted)', color: 'var(--text-muted)' }}
          >
            {filtered.length}
          </span>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={copyAll}
            title="复制日志"
            className="p-1.5 rounded-lg hover:bg-[var(--bg-muted)] cursor-pointer"
            style={{ color: copied ? 'var(--success)' : 'var(--text-muted)' }}
          >
            {copied ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
          </button>
          <button
            onClick={onClear}
            title="清空日志"
            className="p-1.5 rounded-lg hover:bg-[var(--bg-muted)] cursor-pointer"
            style={{ color: 'var(--text-muted)' }}
          >
            <Trash2 className="w-4 h-4" />
          </button>
          <button
            onClick={onClose}
            title="收起"
            className="p-1.5 rounded-lg hover:bg-[var(--bg-muted)] cursor-pointer"
            style={{ color: 'var(--text-muted)' }}
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="p-2.5 border-b space-y-2 shrink-0" style={{ borderColor: 'var(--border-subtle)' }}>
        <div className="relative">
          <Search className="w-3.5 h-3.5 absolute left-2.5 top-2.5" style={{ color: 'var(--text-muted)' }} />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="搜索日志关键字或模块…"
            className="w-full pl-8 pr-3 py-1.5 text-xs rounded-lg border outline-none focus:border-[var(--accent)]"
            style={{
              backgroundColor: 'var(--bg-app)',
              borderColor: 'var(--border-subtle)',
              color: 'var(--text-primary)',
            }}
          />
        </div>
        <div className="flex items-center justify-between gap-1">
          <div className="flex gap-1">
            {(['ALL', 'INFO', 'WARNING', 'ERROR'] as const).map((lvl) => (
              <button
                key={lvl}
                onClick={() => setLevelFilter(lvl)}
                className="px-2 py-1 rounded-md text-[11px] font-medium cursor-pointer transition-colors"
                style={{
                  backgroundColor: levelFilter === lvl ? 'var(--accent-soft)' : 'transparent',
                  color: levelFilter === lvl ? 'var(--accent)' : 'var(--text-muted)',
                }}
              >
                {lvl === 'ALL' ? '全部' : lvl === 'WARNING' ? '警告' : lvl === 'ERROR' ? '错误' : '信息'}
              </button>
            ))}
          </div>
          <label className="flex items-center gap-1.5 text-[11px] cursor-pointer" style={{ color: 'var(--text-muted)' }}>
            <input
              type="checkbox"
              checked={autoScroll}
              onChange={(e) => setAutoScroll(e.target.checked)}
              className="accent-[var(--accent)]"
            />
            自动滚动
          </label>
        </div>
      </div>

      {/* Log lines */}
      <div className="flex-1 overflow-y-auto p-2.5 font-mono text-[11.5px] leading-relaxed space-y-1">
        {filtered.length === 0 ? (
          <div className="text-center py-12 text-xs" style={{ color: 'var(--text-muted)' }}>
            暂无匹配的日志输出
          </div>
        ) : (
          filtered.map((entry, idx) => {
            const levelColor =
              entry.level === 'ERROR' || entry.level === 'CRITICAL'
                ? 'var(--danger)'
                : entry.level === 'WARNING'
                  ? 'var(--warning)'
                  : 'var(--text-muted)'
            return (
              <div
                key={idx}
                className="px-2 py-1 rounded-md hover:bg-[var(--bg-muted)] break-all"
              >
                <span className="tabular-nums mr-1.5" style={{ color: 'var(--text-muted)' }}>
                  {entry.ts}
                </span>
                <span className="font-semibold mr-1.5" style={{ color: levelColor }}>
                  [{entry.logger}]
                </span>
                <span style={{ color: 'var(--text-primary)' }}>{entry.message}</span>
              </div>
            )
          })
        )}
        <div ref={bottomRef} />
      </div>
    </aside>
  )
}
