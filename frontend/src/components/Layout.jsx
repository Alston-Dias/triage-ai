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
    <div className="min-h-screen bg-[#0A0A0A] text-white flex">
      {/* Sidebar */}
      <aside className="w-64 border-r border-[#1f1f1f] bg-[#0A0A0A] flex flex-col">
        <div className="px-6 py-6 flex items-center gap-2.5">
          <div className="w-9 h-9 rounded-lg bg-[#D4AF37]/10 border border-[#D4AF37]/30 flex items-center justify-center">
            <Lightning size={18} fill="#D4AF37" color="#D4AF37" />
          </div>
          <div>
            <div className="font-display font-black text-xl tracking-tight leading-none">Triage<span className="text-[#D4AF37]">AI</span></div>
            <div className="text-[10px] text-neutral-500 tracking-wider mt-0.5">Incident Operations</div>
          </div>
        </div>

        <nav className="flex flex-col px-3 gap-1 mt-2">
          {NAV.map(n => {
            const Icon = n.icon;
            return (
              <NavLink to={n.to} key={n.to} data-testid={n.testid} end={n.to === '/'}
                className={({isActive}) => `flex items-center gap-3 px-3 py-2.5 rounded-md text-sm transition-all ${isActive ? 'bg-[#161616] text-white' : 'text-neutral-400 hover:bg-[#121212] hover:text-white'}`}>
                <Icon size={17} strokeWidth={1.75} />
                <span className="font-medium">{n.label}</span>
              </NavLink>
            );
          })}
        </nav>

        <div className="mt-auto p-4">
          {user && (
            <div className="rounded-lg border border-[#1f1f1f] bg-[#0d0d0d] p-3 mb-3" data-testid="user-card">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-full bg-[#D4AF37]/10 border border-[#D4AF37]/30 flex items-center justify-center text-[#D4AF37] font-semibold text-sm">
                  {initials}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="text-sm text-white truncate font-medium">{user.name}</div>
                  <div className="text-[11px] text-neutral-500 truncate">{user.role}</div>
                </div>
              </div>
            </div>
          )}
          <button data-testid="logout-btn" onClick={logout} className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-md border border-[#1f1f1f] hover:border-[#FF3B30]/40 hover:text-[#FF3B30] text-xs text-neutral-400 transition-colors">
            <LogOut size={13} /> Sign Out
          </button>
        </div>
      </aside>

      {/* Main */}
      <main className="flex-1 flex flex-col min-w-0">
        <header className="h-16 border-b border-[#1f1f1f] px-8 flex items-center justify-between bg-[#0A0A0A]/90 backdrop-blur sticky top-0 z-20">
          <div className="flex items-center gap-3">
            <h1 className="font-display font-bold text-xl tracking-tight">{section}</h1>
            <span className="text-neutral-700">/</span>
            <span className="text-xs text-neutral-500">{new Date().toUTCString().slice(5, 22)} UTC</span>
          </div>
          <div className="flex items-center gap-2">
            <button
              data-testid="theme-toggle"
              onClick={toggle}
              title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
              className="p-2 rounded-md border border-[#1f1f1f] hover:border-[#D4AF37]/40 hover:text-[#D4AF37] transition-colors">
              {theme === 'dark' ? <Sun size={15} /> : <Moon size={15} />}
            </button>
            <div className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md border border-[#1f1f1f] text-[11px] text-neutral-400">
              <span className="w-1.5 h-1.5 rounded-full bg-[#30D158] live-dot inline-block" />
              <span>Online</span>
            </div>
          </div>
        </header>
        <UnattendedBanner />
        <div className="flex-1 overflow-auto">{children}</div>
      </main>
    </div>
  );
}
