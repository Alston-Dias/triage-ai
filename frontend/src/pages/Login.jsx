import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { login as apiLogin } from '../lib/api';
import { useAuth } from '../lib/auth';
import { Zap, ArrowRight } from 'lucide-react';

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
    <div className="min-h-screen bg-[#0A0A0A] flex items-center justify-center p-6">
      <div className="w-full max-w-5xl grid grid-cols-1 lg:grid-cols-2 rounded-2xl overflow-hidden border border-[#1f1f1f] bg-[#0d0d0d] shadow-2xl">
        {/* Left brand */}
        <div className="p-12 border-b lg:border-b-0 lg:border-r border-[#1f1f1f] flex flex-col justify-between bg-gradient-to-br from-[#D4AF37]/[0.04] via-transparent to-transparent">
          <div>
            <div className="flex items-center gap-2.5">
              <div className="w-10 h-10 rounded-lg bg-[#D4AF37]/10 border border-[#D4AF37]/30 flex items-center justify-center">
                <Zap size={20} fill="#D4AF37" color="#D4AF37" />
              </div>
              <div className="font-display font-black text-2xl tracking-tight">Triage<span className="text-[#D4AF37]">AI</span></div>
            </div>
            <div className="mt-16">
              <div className="text-xs text-neutral-500 mb-3">AI-powered incident triage</div>
              <h1 className="font-display text-5xl font-black tracking-tight leading-[1.05]">
                Correlate.<br />Analyze.<br /><span className="text-[#D4AF37]">Resolve.</span>
              </h1>
              <p className="text-sm text-neutral-400 mt-6 leading-relaxed max-w-md">
                Sign in to your operator console — correlate alerts, run AI-powered triage with Claude Sonnet 4.5, and ship remediation playbooks straight to your team.
              </p>
            </div>
          </div>
          <div className="text-xs text-neutral-600 mt-12">v0.4.0 · Claude Sonnet 4.5</div>
        </div>

        {/* Right form */}
        <div className="p-12">
          <div className="text-xs text-neutral-500 mb-2">Authentication</div>
          <h2 className="font-display text-2xl font-black tracking-tight mb-8">Sign in</h2>

          <form onSubmit={submit} className="space-y-5">
            <div>
              <label className="text-xs text-neutral-400 mb-1.5 block">Email</label>
              <input
                data-testid="login-email"
                type="email" value={email} onChange={e=>setEmail(e.target.value)}
                className="w-full bg-[#0a0a0a] border border-[#262626] rounded-lg focus:border-[#D4AF37] text-white text-sm px-3.5 py-3 outline-none transition-colors" />
            </div>
            <div>
              <label className="text-xs text-neutral-400 mb-1.5 block">Password</label>
              <input
                data-testid="login-password"
                type="password" value={password} onChange={e=>setPassword(e.target.value)}
                className="w-full bg-[#0a0a0a] border border-[#262626] rounded-lg focus:border-[#D4AF37] text-white text-sm px-3.5 py-3 outline-none transition-colors" />
            </div>
            {err && <div className="text-xs text-[#FF3B30]" data-testid="login-error">{err}</div>}
            <button
              type="submit" disabled={loading}
              data-testid="login-submit"
              className="w-full flex items-center justify-center gap-2 bg-[#D4AF37] text-black font-semibold text-sm py-3 rounded-lg hover:bg-[#e6c14d] disabled:opacity-50 hover-lift transition-colors">
              {loading ? 'Authenticating…' : <>Sign In <ArrowRight size={15} /></>}
            </button>
          </form>

          <div className="mt-8">
            <div className="text-xs text-neutral-500 mb-3">Quick access · demo accounts</div>
            <div className="grid grid-cols-2 gap-2">
              {DEMO_USERS.map(u => (
                <button
                  key={u.email} type="button" onClick={()=>quick(u)}
                  data-testid={`demo-user-${u.email.split('@')[0]}`}
                  className="text-left text-xs px-3 py-2.5 rounded-lg border border-[#262626] hover:border-[#D4AF37]/40 hover:bg-[#D4AF37]/[0.04] text-neutral-300 transition-colors">
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
