import React from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { Activity, Radio, LineChart as ChartLine, Settings as Gear, Zap as Lightning, LogOut, Sun, Moon, TrendingUp, Code2 } from 'lucide-react';
import { useAuth } from '../lib/auth';
import { useTheme } from '../lib/theme';
import UnattendedBanner from './UnattendedBanner';

const NAV = [
  { to: '/', label: 'Live Triage', icon: Radio, testid: 'nav-triage' },
  { to: '/incidents', label: 'Incidents', icon: Activity, testid: 'nav-incidents' },
  { to: '/predictive', label: 'Predictive', icon: TrendingUp, testid: 'nav-predictive' },
  { to: '/analytics', label: 'Analytics', icon: ChartLine, testid: 'nav-analytics' },
  { to: '/code-quality', label: 'Code Quality', icon: Code2, testid: 'nav-code-quality' },
  { to: '/settings', label: 'Settings', icon: Gear, testid: 'nav-settings' },
];

export default function Layout({ children }) {
  const loc = useLocation();
  const { user, logout } = useAuth();
  const { theme, toggle } = useTheme();
  const section = NAV.find(n => loc.pathname === n.to || (n.to !== '/' && loc.pathname.startsWith(n.to)))?.label || 'Live Triage';

  const initials = user ? user.name.split(' ').map(p => p[0]).slice(0,2).join('').toUpperCase() : '';

  return (
    <div className="h-screen overflow-hidden text-white flex">
      {/* Sidebar */}
      <aside className="w-64 border-r border-[#1f1f1f] bg-[#0A0A0A]/60 backdrop-blur-xl flex flex-col relative z-10 h-full overflow-y-auto">
        {/* Brand */}
        <div className="px-6 py-6 flex items-center gap-3">
          <div className="relative w-10 h-10 rounded-xl flex items-center justify-center
                          bg-gradient-to-br from-[#D4AF37]/30 via-[#D4AF37]/10 to-transparent
                          border border-[#D4AF37]/30 shadow-[0_8px_24px_-12px_rgba(212,175,55,0.6)]">
            <Lightning size={18} fill="#D4AF37" color="#D4AF37" />
            <span className="absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 rounded-full bg-[#30D158] ring-2 ring-[#0A0A0A] live-dot" />
          </div>
          <div>
            <div className="font-display font-black text-xl tracking-tight leading-none">
              Triage<span className="text-[#D4AF37]">AI</span>
            </div>
            <div className="text-[10px] text-neutral-500 tracking-[0.18em] mt-1 uppercase">SRE Console</div>
          </div>
        </div>

        {/* Section label */}
        <div className="px-6 mt-2 mb-1 text-[10px] tracking-[0.18em] uppercase text-neutral-600">Operations</div>

        <nav className="flex flex-col px-3 gap-0.5">
          {NAV.map(n => {
            const Icon = n.icon;
            const isActive = n.to === '/' ? loc.pathname === '/' : loc.pathname === n.to || loc.pathname.startsWith(n.to + '/');
            return (
              <NavLink
                to={n.to}
                key={n.to}
                data-testid={n.testid}
                end={n.to === '/'}
                className={`group relative flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-all duration-200 ${
                  isActive
                    ? 'bg-gradient-to-r from-[#D4AF37]/[0.12] via-[#D4AF37]/[0.04] to-transparent text-white border border-[#D4AF37]/20'
                    : 'text-neutral-400 hover:text-white hover:bg-white/[0.03] border border-transparent'
                }`}
              >
                <span className={`absolute left-0 top-1.5 bottom-1.5 w-[3px] rounded-r-full bg-[#D4AF37] transition-all duration-300 ${isActive ? 'opacity-100 scale-y-100' : 'opacity-0 scale-y-50'}`} />
                <Icon
                  size={17}
                  strokeWidth={1.75}
                  className={isActive ? 'text-[#D4AF37]' : 'text-neutral-500 group-hover:text-neutral-300 transition-colors'}
                />
                <span className="font-medium">{n.label}</span>
              </NavLink>
            );
          })}
        </nav>

        {/* Footer / user */}
        <div className="mt-auto p-4">
          {user && (
            <div className="rounded-xl border border-[#1f1f1f] bg-gradient-to-b from-white/[0.025] to-transparent p-3 mb-3" data-testid="user-card">
              <div className="flex items-center gap-3">
                <div className="relative w-9 h-9 rounded-full flex items-center justify-center
                                bg-gradient-to-br from-[#D4AF37]/25 to-[#D4AF37]/5 border border-[#D4AF37]/30
                                text-[#D4AF37] font-semibold text-sm">
                  {initials}
                  <span className="absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 rounded-full bg-[#30D158] ring-2 ring-[#0d0d0d]" />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="text-sm text-white truncate font-medium">{user.name}</div>
                  <div className="text-[11px] text-neutral-500 truncate uppercase tracking-wide">{user.role}</div>
                </div>
              </div>
            </div>
          )}
          <button
            data-testid="logout-btn"
            onClick={logout}
            className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-lg border border-[#1f1f1f] hover:border-[#FF3B30]/40 hover:bg-[#FF3B30]/[0.06] hover:text-[#FF3B30] text-xs text-neutral-400 transition-all">
            <LogOut size={13} /> Sign Out
          </button>
        </div>
      </aside>

      {/* Main */}
      <main className="flex-1 flex flex-col min-w-0 relative">
        <header className="h-16 border-b border-[#1f1f1f] px-8 flex items-center justify-between bg-[#0A0A0A]/60 backdrop-blur-xl sticky top-0 z-20">
          <div className="flex items-center gap-3">
            <h1 className="font-display font-bold text-xl tracking-tight">{section}</h1>
            <span className="text-neutral-700">/</span>
            <span className="text-[11px] text-neutral-500 font-mono">
              {new Date().toUTCString().slice(5, 22)} <span className="text-neutral-600">UTC</span>
            </span>
          </div>
          <div className="flex items-center gap-2">
            <ThemeToggle theme={theme} onToggle={toggle} />
            <div className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md border border-[#1f1f1f] bg-white/[0.02] text-[11px] text-neutral-300">
              <span className="w-1.5 h-1.5 rounded-full bg-[#30D158] live-dot inline-block" />
              <span>Online</span>
            </div>
          </div>
        </header>
        <UnattendedBanner />
        <div className="flex-1 min-h-0 overflow-auto">{children}</div>
      </main>
    </div>
  );
}

/** Animated theme toggle with rotating sun/moon */
function ThemeToggle({ theme, onToggle }) {
  const isDark = theme === 'dark';
  return (
    <button
      data-testid="theme-toggle"
      onClick={onToggle}
      title={`Switch to ${isDark ? 'light' : 'dark'} theme`}
      className="relative w-9 h-9 rounded-md border border-[#1f1f1f] bg-white/[0.02] hover:border-[#D4AF37]/40 hover:bg-[#D4AF37]/[0.06] text-neutral-300 hover:text-[#D4AF37] transition-all overflow-hidden"
    >
      <span className={`absolute inset-0 flex items-center justify-center transition-all duration-300 ${isDark ? 'opacity-100 rotate-0' : 'opacity-0 -rotate-90'}`}>
        <Sun size={15} />
      </span>
      <span className={`absolute inset-0 flex items-center justify-center transition-all duration-300 ${!isDark ? 'opacity-100 rotate-0' : 'opacity-0 rotate-90'}`}>
        <Moon size={15} />
      </span>
    </button>
  );
}
