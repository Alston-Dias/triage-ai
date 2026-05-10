import React from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { Activity, Radio, LineChart as ChartLine, Settings as Gear, Zap as Lightning, LogOut } from 'lucide-react';
import { useAuth } from '../lib/auth';
import UnattendedBanner from './UnattendedBanner';

const NAV = [
  { to: '/', label: 'Live Triage', icon: Radio, testid: 'nav-triage' },
  { to: '/incidents', label: 'Incidents', icon: Activity, testid: 'nav-incidents' },
  { to: '/analytics', label: 'Analytics', icon: ChartLine, testid: 'nav-analytics' },
  { to: '/settings', label: 'Settings', icon: Gear, testid: 'nav-settings' },
];

export default function Layout({ children }) {
  const loc = useLocation();
  const { user, logout } = useAuth();
  const section = NAV.find(n => loc.pathname === n.to || (n.to !== '/' && loc.pathname.startsWith(n.to)))?.label || 'Live Triage';

  return (
    <div className="min-h-screen bg-[#0A0A0A] text-white flex">
      <aside className="w-60 border-r border-[#1f1f1f] bg-[#0A0A0A] flex flex-col">
        <div className="px-5 py-5 border-b border-[#1f1f1f] flex items-center gap-2">
          <Lightning size={22} fill="#D4AF37" color="#D4AF37" />
          <div className="font-display font-black text-xl tracking-tighter">TRIAGE<span className="text-[#D4AF37]">AI</span></div>
        </div>
        <div className="px-3 py-2 text-[10px] tracking-[0.2em] text-neutral-500 uppercase mt-2">Operator Console</div>
        <nav className="flex flex-col px-2 gap-0.5">
          {NAV.map(n => {
            const Icon = n.icon;
            return (
              <NavLink to={n.to} key={n.to} data-testid={n.testid} end={n.to === '/'}
                className={({isActive}) => `flex items-center gap-3 px-3 py-2.5 text-sm transition-colors ${isActive ? 'bg-[#161616] text-white border-l-2 border-[#D4AF37]' : 'text-neutral-400 hover:bg-[#121212] hover:text-white border-l-2 border-transparent'}`}>
                <Icon size={16} />
                <span className="tracking-wide uppercase text-[11px]">{n.label}</span>
              </NavLink>
            );
          })}
        </nav>

        {/* User card */}
        <div className="mt-auto p-3 border-t border-[#1f1f1f]">
          {user && (
            <div className="border border-[#262626] bg-[#0d0d0d] p-2.5 mb-2" data-testid="user-card">
              <div className="text-[10px] tracking-[0.18em] uppercase text-[#D4AF37]">{user.role}</div>
              <div className="text-xs text-white truncate mt-0.5">{user.name}</div>
              <div className="text-[10px] text-neutral-500 truncate font-mono">{user.email}</div>
            </div>
          )}
          <button data-testid="logout-btn" onClick={logout} className="w-full flex items-center justify-center gap-2 px-2 py-2 border border-[#262626] hover:border-[#FF3B30] hover:text-[#FF3B30] text-[10px] tracking-[0.18em] uppercase text-neutral-400">
            <LogOut size={11} /> Sign Out
          </button>
          <div className="mt-2 flex items-center gap-2 text-[10px] text-neutral-500">
            <span className="w-1.5 h-1.5 rounded-full bg-[#30D158] live-dot inline-block" />
            <span className="uppercase tracking-widest">SYSTEM ONLINE</span>
          </div>
        </div>
      </aside>

      <main className="flex-1 flex flex-col min-w-0">
        <header className="h-14 border-b border-[#1f1f1f] px-6 flex items-center justify-between bg-[#0A0A0A]/95 backdrop-blur sticky top-0 z-20">
          <div className="flex items-center gap-3">
            <div className="text-[10px] tracking-[0.25em] text-neutral-500 uppercase">// {section}</div>
            <div className="text-xs text-neutral-700">·</div>
            <div className="text-[11px] text-neutral-400 tracking-wide">{new Date().toUTCString().slice(5,22)} UTC</div>
          </div>
          <div className="flex items-center gap-2 text-[10px] tracking-widest uppercase text-neutral-500">
            <span className="px-2 py-1 border border-[#262626]">claude-sonnet-4.5</span>
            {user && <span className="px-2 py-1 border border-[#262626] text-neutral-300">{user.name.split(' ')[0]}</span>}
          </div>
        </header>
        <UnattendedBanner />
        <div className="flex-1 overflow-auto">{children}</div>
      </main>
    </div>
  );
}
