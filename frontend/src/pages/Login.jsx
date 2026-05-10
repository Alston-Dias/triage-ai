import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { login as apiLogin } from '../lib/api';
import { useAuth } from '../lib/auth';
import { Zap, Lock, ArrowRight } from 'lucide-react';

const DEMO_USERS = [
  { email: 'admin@triage.ai', password: 'admin123', label: 'Admin' },
  { email: 'sre1@triage.ai', password: 'sre123', label: 'Alex Chen · On-Call' },
  { email: 'sre2@triage.ai', password: 'sre123', label: 'Maya Patel · On-Call' },
  { email: 'viewer@triage.ai', password: 'viewer123', label: 'Viewer' },
];

export default function Login() {
  const [email, setEmail] = useState('sre1@triage.ai');
  const [password, setPassword] = useState('sre123');
  const [err, setErr] = useState('');
  const [loading, setLoading] = useState(false);
  const nav = useNavigate();
  const { setUser } = useAuth();

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
    <div className="min-h-screen bg-[#0A0A0A] grid-bg flex items-center justify-center p-6">
      <div className="w-full max-w-4xl grid grid-cols-1 lg:grid-cols-2 border border-[#1f1f1f] bg-[#0d0d0d]">
        {/* Left brand */}
        <div className="p-10 border-b lg:border-b-0 lg:border-r border-[#1f1f1f] flex flex-col justify-between scanlines">
          <div>
            <div className="flex items-center gap-2">
              <Zap size={22} fill="#D4AF37" color="#D4AF37" />
              <div className="font-display font-black text-2xl tracking-tighter">TRIAGE<span className="text-[#D4AF37]">AI</span></div>
            </div>
            <div className="mt-12">
              <div className="text-[10px] tracking-[0.3em] uppercase text-neutral-500 mb-3">// Operator Console</div>
              <h1 className="font-display text-4xl font-black tracking-tighter leading-[1.05]">
                CORRELATE.<br />ANALYZE.<br /><span className="text-[#D4AF37]">RESOLVE.</span>
              </h1>
              <p className="text-xs text-neutral-400 mt-4 leading-relaxed max-w-sm">
                AI-powered incident triage for cloud operations. Sign in to access live alerts, AI hypotheses, and remediation playbooks.
              </p>
            </div>
          </div>
          <div className="text-[10px] text-neutral-600 tracking-widest mt-12">v0.2.0 · MVP · CLAUDE-SONNET-4.5</div>
        </div>
        {/* Right form */}
        <div className="p-10">
          <div className="text-[10px] tracking-[0.25em] uppercase text-neutral-500 mb-2">Authenticate</div>
          <h2 className="font-display text-2xl font-black tracking-tighter mb-6">SIGN IN</h2>
          <form onSubmit={submit} className="space-y-4">
            <div>
              <label className="text-[10px] tracking-[0.2em] uppercase text-neutral-500">Email</label>
              <input
                data-testid="login-email"
                type="email" value={email} onChange={e=>setEmail(e.target.value)}
                className="mt-1 w-full bg-[#0a0a0a] border border-[#262626] focus:border-[#D4AF37] text-white text-sm px-3 py-2.5 outline-none font-mono" />
            </div>
            <div>
              <label className="text-[10px] tracking-[0.2em] uppercase text-neutral-500">Password</label>
              <input
                data-testid="login-password"
                type="password" value={password} onChange={e=>setPassword(e.target.value)}
                className="mt-1 w-full bg-[#0a0a0a] border border-[#262626] focus:border-[#D4AF37] text-white text-sm px-3 py-2.5 outline-none font-mono" />
            </div>
            {err && <div className="text-[11px] text-[#FF3B30] tracking-wider" data-testid="login-error">{err}</div>}
            <button
              type="submit" disabled={loading}
              data-testid="login-submit"
              className="w-full flex items-center justify-center gap-2 bg-[#D4AF37] text-black font-bold tracking-[0.18em] uppercase text-[11px] py-3 hover:bg-[#e6c14d] disabled:opacity-50 transition-colors">
              {loading ? 'Authenticating...' : <>Sign In <ArrowRight size={14} /></>}
            </button>
          </form>

          <div className="mt-6">
            <div className="text-[10px] tracking-[0.25em] uppercase text-neutral-500 mb-2 flex items-center gap-2">
              <Lock size={11} /> Demo accounts
            </div>
            <div className="grid grid-cols-2 gap-2">
              {DEMO_USERS.map(u => (
                <button
                  key={u.email} type="button" onClick={()=>quick(u)}
                  data-testid={`demo-user-${u.email.split('@')[0]}`}
                  className="text-left text-[10px] px-2.5 py-2 border border-[#262626] hover:border-[#404040] text-neutral-400 hover:text-white transition-colors">
                  <div className="font-mono">{u.email}</div>
                  <div className="text-[9px] text-neutral-600 mt-0.5 tracking-widest uppercase">{u.label}</div>
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
