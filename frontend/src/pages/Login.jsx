import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { login as apiLogin } from '../lib/api';
import { useAuth } from '../lib/auth';
import { useTheme } from '../lib/theme';
import { Zap, ArrowRight, Sun, Moon, ShieldCheck, Activity, Sparkles } from 'lucide-react';

const DEMO_USERS = [
  { email: 'admin@triage.ai',  password: 'admin123',  label: 'Admin' },
  { email: 'sre1@triage.ai',   password: 'sre123',    label: 'On-call · Alex' },
  { email: 'sre2@triage.ai',   password: 'sre123',    label: 'On-call · Maya' },
  { email: 'viewer@triage.ai', password: 'viewer123', label: 'Viewer' },
];

export default function Login() {
  const [email, setEmail] = useState('sre1@triage.ai');
  const [password, setPassword] = useState('sre123');
  const [err, setErr] = useState('');
  const [loading, setLoading] = useState(false);
  const nav = useNavigate();
  const { setUser } = useAuth();
  const { theme, toggle } = useTheme();

  const submit = async (e) => {
    e?.preventDefault?.();
    setLoading(true); setErr('');
    try {
      const res = await apiLogin(email.trim(), password);
      localStorage.setItem('triage_token', res.access_token);
      localStorage.setItem('triage_user', JSON.stringify(res.user));
      setUser(res.user);
      nav('/');
    } catch (e2) {
      setErr(e2?.response?.data?.detail || 'Login failed');
    } finally { setLoading(false); }
  };

  const quick = (u) => { setEmail(u.email); setPassword(u.password); };

  return (
    <div className="min-h-screen flex items-center justify-center p-6 relative overflow-hidden">
      {/* Aurora blobs */}
      <div className="pointer-events-none absolute inset-0 -z-10">
        <div className="aurora-blob absolute -top-40 -left-20 w-[600px] h-[600px] rounded-full bg-[#D4AF37]/20" />
        <div className="aurora-blob absolute top-1/2 -right-32 w-[520px] h-[520px] rounded-full bg-[#0A84FF]/20" style={{ animationDelay: '4s' }} />
        <div className="aurora-blob absolute -bottom-40 left-1/3 w-[480px] h-[480px] rounded-full bg-[#30D158]/14" style={{ animationDelay: '8s' }} />
      </div>

      {/* Theme toggle floating */}
      <button
        data-testid="theme-toggle"
        onClick={toggle}
        title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
        className="absolute top-6 right-6 z-20 w-9 h-9 rounded-md border border-white/10 bg-white/5 backdrop-blur hover:border-[#D4AF37]/40 hover:bg-[#D4AF37]/[0.08] text-neutral-300 hover:text-[#D4AF37] transition-all flex items-center justify-center"
      >
        {theme === 'dark' ? <Sun size={15} /> : <Moon size={15} />}
      </button>

      <div className="w-full max-w-5xl grid grid-cols-1 lg:grid-cols-2 rounded-2xl overflow-hidden glass-strong animate-slide-up">
        {/* Left brand */}
        <div className="p-12 border-b lg:border-b-0 lg:border-r border-white/[0.06] flex flex-col justify-between relative overflow-hidden">
          <div className="absolute inset-0 -z-10 bg-gradient-to-br from-[#D4AF37]/[0.06] via-transparent to-[#0A84FF]/[0.04]" />
          <div>
            <div className="flex items-center gap-3">
              <div className="relative w-11 h-11 rounded-xl bg-gradient-to-br from-[#D4AF37]/30 via-[#D4AF37]/10 to-transparent border border-[#D4AF37]/30 flex items-center justify-center shadow-[0_8px_24px_-12px_rgba(212,175,55,0.6)]">
                <Zap size={20} fill="#D4AF37" color="#D4AF37" />
              </div>
              <div className="font-display font-black text-2xl tracking-tight">Triage<span className="text-[#D4AF37]">AI</span></div>
            </div>

            <div className="mt-14">
              <div className="text-[11px] text-neutral-400 mb-3 tracking-[0.18em] uppercase flex items-center gap-2">
                <Sparkles size={12} className="text-[#D4AF37]" /> AI-powered incident triage
              </div>
              <h1 className="font-display text-5xl font-black tracking-tight leading-[1.05]">
                Correlate.<br />Analyze.<br /><span className="bg-gradient-to-r from-[#D4AF37] via-[#E6C14D] to-[#D4AF37] bg-clip-text text-transparent">Resolve.</span>
              </h1>
              <p className="text-sm text-neutral-400 mt-6 leading-relaxed max-w-md">
                Sign in to your operator console — correlate alerts, run AI-powered triage with Claude Sonnet 4.5, and ship remediation playbooks straight to your team.
              </p>

              <div className="mt-10 grid grid-cols-1 gap-3 max-w-sm">
                <FeatureRow icon={ShieldCheck} title="Encrypted at rest" caption="Fernet-derived tokens · role-based access" />
                <FeatureRow icon={Activity} title="Real-time signals" caption="60s correlation · WebSocket-streamed predictions" />
              </div>
            </div>
          </div>
          <div className="text-[10px] text-neutral-600 mt-12 font-mono tracking-wider uppercase">v0.4.0 · Claude Sonnet 4.5</div>
        </div>

        {/* Right form */}
        <div className="p-12 relative">
          <div className="text-[11px] text-neutral-400 mb-2 tracking-[0.18em] uppercase">Authentication</div>
          <h2 className="font-display text-2xl font-black tracking-tight mb-1">Sign in</h2>
          <p className="text-xs text-neutral-500 mb-8">Use your operator credentials or a demo account below.</p>

          <form onSubmit={submit} className="space-y-5">
            <div>
              <label className="text-[11px] text-neutral-400 mb-1.5 block tracking-wide uppercase">Email</label>
              <input
                data-testid="login-email"
                type="email" value={email} onChange={e=>setEmail(e.target.value)}
                className="focus-ring w-full bg-white/[0.02] border border-white/10 rounded-lg text-white text-sm px-3.5 py-3 outline-none transition-colors" />
            </div>
            <div>
              <label className="text-[11px] text-neutral-400 mb-1.5 block tracking-wide uppercase">Password</label>
              <input
                data-testid="login-password"
                type="password" value={password} onChange={e=>setPassword(e.target.value)}
                className="focus-ring w-full bg-white/[0.02] border border-white/10 rounded-lg text-white text-sm px-3.5 py-3 outline-none transition-colors" />
            </div>
            {err && (
              <div className="text-xs text-[#FF3B30] flex items-center gap-2 px-3 py-2 rounded-md border border-[#FF3B30]/30 bg-[#FF3B30]/[0.06]" data-testid="login-error">
                {err}
              </div>
            )}
            <button
              type="submit" disabled={loading}
              data-testid="login-submit"
              className="group w-full flex items-center justify-center gap-2 bg-[#D4AF37] text-black font-semibold text-sm py-3 rounded-lg hover:bg-[#e6c14d] disabled:opacity-50 hover-lift transition-all shadow-[0_10px_24px_-12px_rgba(212,175,55,0.6)]">
              {loading ? 'Authenticating…' : <>Sign In <ArrowRight size={15} className="group-hover:translate-x-0.5 transition-transform" /></>}
            </button>
          </form>

          <div className="mt-8">
            <div className="text-[11px] text-neutral-400 mb-3 tracking-[0.18em] uppercase">Quick access · demo accounts</div>
            <div className="grid grid-cols-2 gap-2">
              {DEMO_USERS.map(u => (
                <button
                  key={u.email} type="button" onClick={()=>quick(u)}
                  data-testid={`demo-user-${u.email.split('@')[0]}`}
                  className="text-left text-xs px-3 py-2.5 rounded-lg border border-white/10 hover:border-[#D4AF37]/40 hover:bg-[#D4AF37]/[0.06] text-neutral-300 transition-all">
                  <div className="font-mono text-[11px]">{u.email}</div>
                  <div className="text-[10px] text-neutral-500 mt-0.5">{u.label}</div>
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function FeatureRow({ icon: Icon, title, caption }) {
  return (
    <div className="flex items-start gap-3 text-left">
      <div className="w-8 h-8 rounded-lg bg-white/[0.04] border border-white/10 flex items-center justify-center text-[#D4AF37] shrink-0">
        <Icon size={14} />
      </div>
      <div>
        <div className="text-sm text-neutral-200 font-medium">{title}</div>
        <div className="text-[11px] text-neutral-500">{caption}</div>
      </div>
    </div>
  );
}
