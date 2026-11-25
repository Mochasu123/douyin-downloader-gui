import React from 'react'
import { AlertTriangle, CheckCircle2, Info, X, XCircle } from 'lucide-react'
import type { ToastMessage } from '../types/api'

interface ToastContainerProps {
  toasts: ToastMessage[]
  onDismiss: (id: string) => void
}

export const ToastContainer: React.FC<ToastContainerProps> = ({ toasts, onDismiss }) => {
  if (toasts.length === 0) return null

  return (
    <div className="fixed bottom-5 right-5 z-50 flex flex-col gap-2.5 max-w-sm w-full pointer-events-none">
      {toasts.map((toast) => {
        const Icon =
          toast.kind === 'success'
            ? CheckCircle2
            : toast.kind === 'error'
              ? XCircle
              : toast.kind === 'warning'
                ? AlertTriangle
                : Info
        const color =
          toast.kind === 'success'
            ? 'var(--success)'
            : toast.kind === 'error'
              ? 'var(--danger)'
              : toast.kind === 'warning'
                ? 'var(--warning)'
                : 'var(--accent)'

        return (
          <div
            key={toast.id}
            className="pointer-events-auto flex items-start gap-3 p-3.5 rounded-2xl border backdrop-blur-md animate-fade-up"
            style={{
              backgroundColor: 'var(--bg-glass)',
              borderColor: 'var(--border-strong)',
              boxShadow: 'var(--shadow-lg)',
            }}
          >
            <Icon className="w-5 h-5 shrink-0 mt-0.5" style={{ color }} />
            <div className="min-w-0 flex-1">
              <div className="text-[13px] font-semibold leading-snug">{toast.title}</div>
              {toast.detail && (
                <div className="text-xs mt-0.5 break-words" style={{ color: 'var(--text-muted)' }}>
                  {toast.detail}
                </div>
              )}
              {toast.actionLabel && toast.onAction && (
                <button
                  onClick={() => {
                    toast.onAction?.()
                    onDismiss(toast.id)
                  }}
                  className="mt-2 text-xs font-semibold px-2.5 py-1 rounded-lg cursor-pointer"
                  style={{ backgroundColor: 'var(--accent-soft)', color: 'var(--accent)' }}
                >
                  {toast.actionLabel}
                </button>
              )}
            </div>
            <button
              onClick={() => onDismiss(toast.id)}
              className="p-1 rounded-lg hover:bg-[var(--bg-muted)] cursor-pointer shrink-0"
              style={{ color: 'var(--text-muted)' }}
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        )
      })}
    </div>
  )
}
