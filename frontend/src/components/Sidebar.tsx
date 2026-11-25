import React from 'react'
import {
  Activity,
  CheckCircle2,
  FolderClock,
  Link2,
  MessageSquareText,
  Monitor,
  Moon,
  PanelLeftClose,
  PanelLeftOpen,
  Settings,
  Sun,
  Terminal,
  UserCheck,
  Users,
} from 'lucide-react'
import type { AuthStatus, PageKey, ThemeMode } from '../types/api'
import { proxyImageUrl } from '../lib/format'

interface SidebarProps {
  activePage: PageKey
  onSelectPage: (page: PageKey) => void
  collapsed: boolean
  onToggleCollapse: () => void
  auth: AuthStatus | null
  activeTaskCount: number
  logCount: number
  errorLogCount: number
  logOpen: boolean
  onToggleLogs: () => void
  theme: ThemeMode
  onCycleTheme: () => void
}

const NAV_ITEMS: { key: PageKey; label: string; icon: React.ComponentType<{ className?: string }> }[] = [
  { key: 'download', label: '链接下载', icon: Link2 },
  { key: 'creator', label: '博主主页', icon: Users },
  { key: 'comments', label: '评论与图库', icon: MessageSquareText },
  { key: 'tasks', label: '任务中心', icon: Activity },
  { key: 'history', label: '下载记录', icon: FolderClock },
  { key: 'settings', label: '设置中心', icon: Settings },
]

export const Sidebar: React.FC<SidebarProps> = ({
  activePage,
  onSelectPage,
  collapsed,
  onToggleCollapse,
  auth,
  activeTaskCount,
  errorLogCount,
  logOpen,
  onToggleLogs,
  theme,
  onCycleTheme,
}) => {
  const ThemeIcon = theme === 'dark' ? Moon : theme === 'light' ? Sun : Monitor
  const themeLabel = theme === 'dark' ? '深色模式' : theme === 'light' ? '浅色模式' : '跟随系统'

  return (
    <aside
      className={`flex flex-col shrink-0 border-r transition-all duration-200 select-none ${
        collapsed ? 'w-[72px]' : 'w-[228px]'
      }`}
      style={{
        backgroundColor: 'var(--bg-sidebar)',
        borderColor: 'var(--border-subtle)',
      }}
    >
      {/* Brand header */}
      <div className="flex items-center justify-between px-4 h-16 border-b" style={{ borderColor: 'var(--border-subtle)' }}>
        <div className="flex items-center gap-2.5 overflow-hidden">
          <div
            className="w-9 h-9 rounded-xl flex items-center justify-center shrink-0 text-white font-bold text-sm shadow-sm"
            style={{
              background: 'linear-gradient(135deg, #2563eb 0%, #0ea5e9 100%)',
            }}
          >
            抖
          </div>
          {!collapsed && (
            <div className="min-w-0">
              <div className="font-semibold text-[15px] tracking-tight truncate">抖音下载器</div>
              <div className="text-[11px] truncate" style={{ color: 'var(--text-muted)' }}>
                Douyin Studio v2.1
              </div>
            </div>
          )}
        </div>
        <button
          onClick={onToggleCollapse}
          title={collapsed ? '展开侧边栏' : '收起侧边栏'}
          className="p-1.5 rounded-lg transition-colors hover:bg-[var(--bg-muted)] cursor-pointer"
          style={{ color: 'var(--text-muted)' }}
        >
          {collapsed ? <PanelLeftOpen className="w-4 h-4" /> : <PanelLeftClose className="w-4 h-4" />}
        </button>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-2.5 py-3 space-y-1 overflow-y-auto">
        {NAV_ITEMS.map(({ key, label, icon: Icon }) => {
          const active = activePage === key
          return (
            <button
              key={key}
              onClick={() => onSelectPage(key)}
              title={collapsed ? label : undefined}
              className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-[13.5px] font-medium transition-all cursor-pointer relative ${
                active
                  ? 'shadow-xs'
                  : 'hover:bg-[var(--bg-muted)]'
              }`}
              style={{
                backgroundColor: active ? 'var(--accent-soft)' : 'transparent',
                color: active ? 'var(--accent)' : 'var(--text-secondary)',
              }}
            >
              <Icon className="w-[18px] h-[18px] shrink-0" />
              {!collapsed && <span className="truncate flex-1 text-left">{label}</span>}
              {key === 'tasks' && activeTaskCount > 0 && (
                <span
                  className={`tabular-nums text-[11px] font-semibold px-1.5 py-0.5 rounded-full text-white ${
                    collapsed ? 'absolute top-1.5 right-1.5 px-1 text-[10px]' : ''
                  }`}
                  style={{ backgroundColor: 'var(--accent)' }}
                >
                  {activeTaskCount}
                </span>
              )}
            </button>
          )
        })}
      </nav>

      {/* Bottom controls + Account pill */}
      <div className="p-2.5 space-y-2 border-t" style={{ borderColor: 'var(--border-subtle)' }}>
        <div className={`flex ${collapsed ? 'flex-col gap-1.5' : 'gap-1.5'}`}>
          <button
            onClick={onCycleTheme}
            title={`主题：${themeLabel}`}
            className="flex-1 flex items-center justify-center gap-1.5 py-2 px-2.5 rounded-xl text-xs font-medium transition-colors hover:bg-[var(--bg-muted)] cursor-pointer"
            style={{ color: 'var(--text-secondary)', backgroundColor: 'var(--bg-app)' }}
          >
            <ThemeIcon className="w-3.5 h-3.5 shrink-0" />
            {!collapsed && <span className="truncate">{themeLabel}</span>}
          </button>

          <button
            onClick={onToggleLogs}
            title="运行日志"
            className="flex-1 flex items-center justify-center gap-1.5 py-2 px-2.5 rounded-xl text-xs font-medium transition-colors cursor-pointer relative"
            style={{
              color: logOpen ? 'var(--accent)' : 'var(--text-secondary)',
              backgroundColor: logOpen ? 'var(--accent-soft)' : 'var(--bg-app)',
            }}
          >
            <Terminal className="w-3.5 h-3.5 shrink-0" />
            {!collapsed && <span>日志</span>}
            {errorLogCount > 0 && (
              <span
                className="w-2 h-2 rounded-full"
                style={{ backgroundColor: 'var(--danger)' }}
              />
            )}
          </button>
        </div>

        {/* Account status */}
        <button
          onClick={() => onSelectPage('settings')}
          title={auth?.user?.nickname || (auth?.has_cookie ? 'Cookie 已配置' : '点击配置账号登录')}
          className="w-full flex items-center gap-2.5 p-2 rounded-xl border transition-colors hover:bg-[var(--bg-muted)] cursor-pointer text-left"
          style={{
            borderColor: 'var(--border-subtle)',
            backgroundColor: 'var(--bg-app)',
          }}
        >
          {auth?.user?.avatar_url ? (
            <img
              src={proxyImageUrl(auth.user.avatar_url)}
              alt=""
              className="w-8 h-8 rounded-full object-cover shrink-0 border"
              style={{ borderColor: 'var(--border-subtle)' }}
            />
          ) : (
            <div
              className="w-8 h-8 rounded-full flex items-center justify-center shrink-0"
              style={{
                backgroundColor: auth?.has_cookie ? 'var(--success-soft)' : 'var(--warning-soft)',
                color: auth?.has_cookie ? 'var(--success)' : 'var(--warning)',
              }}
            >
              <UserCheck className="w-4 h-4" />
            </div>
          )}

          {!collapsed && (
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-1">
                <span className="text-xs font-semibold truncate">
                  {auth?.user?.nickname || (auth?.has_cookie ? 'Cookie 已配置' : '未登录账号')}
                </span>
                {auth?.logged_in && (
                  <CheckCircle2 className="w-3.5 h-3.5 shrink-0" style={{ color: 'var(--success)' }} />
                )}
              </div>
              <div className="text-[11px] truncate" style={{ color: 'var(--text-muted)' }}>
                {auth?.has_cookie
                  ? `${auth.cookie_count} 项凭据 · 点击管理`
                  : '点击一键登录或配置'}
              </div>
            </div>
          )}
        </button>
      </div>
    </aside>
  )
}
