import React, { useEffect, useState } from 'react';
import { fetchSources, addSource, deleteSource, toggleSource } from '../lib/api';
import { CloudUpload as CloudArrowUp, Bell, Brain, Shield, CheckCircle, Plus, Trash2, Power } from 'lucide-react';
import { toast, Toaster } from 'sonner';

const TYPES = ['cloudwatch', 'datadog', 'pagerduty', 'grafana', 'prometheus', 'custom'];

export default function Settings() {
  const [sources, setSources] = useState([]);
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState({ name: '', type: 'cloudwatch', webhook_url: '', api_key: '' });

  const load = () => fetchSources().then(setSources);
  useEffect(() => { load(); }, []);

  const submit = async (e) => {
    e.preventDefault();
    if (!form.name.trim()) return toast.error('Name required');
    await addSource(form);
    toast.success('Source added');
    setForm({ name: '', type: 'cloudwatch', webhook_url: '', api_key: '' });
    setShowAdd(false);
    load();
  };
  const remove = async (id) => { await deleteSource(id); toast.success('Removed'); load(); };
  const toggle = async (id) => { await toggleSource(id); load(); };

  return (
    <div className="p-6 max-w-4xl">
      <Toaster theme="dark" position="bottom-right" />
      <div className="text-[10px] tracking-[0.3em] text-neutral-500 uppercase">Configuration</div>
      <h1 className="font-display text-3xl font-black tracking-tighter mt-1 mb-6">SYSTEM SETTINGS</h1>

      <Section title="Alert Sources" icon={CloudArrowUp}
               action={
                 <button data-testid="add-source-btn" onClick={()=>setShowAdd(s=>!s)} className="flex items-center gap-1.5 px-2.5 py-1.5 border border-[#262626] hover:border-[#D4AF37] text-[10px] tracking-[0.18em] uppercase">
                   <Plus size={11} /> Add Source
                 </button>
               }>
        {showAdd && (
          <form onSubmit={submit} className="mb-4 grid grid-cols-1 md:grid-cols-2 gap-3 border border-[#262626] p-3 bg-[#0a0a0a]" data-testid="add-source-form">
            <Input label="Name" value={form.name} onChange={v=>setForm(f=>({...f, name: v}))} placeholder="Datadog Production" testid="src-name" />
            <div>
              <label className="text-[10px] tracking-[0.2em] uppercase text-neutral-500">Type</label>
              <select data-testid="src-type" value={form.type} onChange={e=>setForm(f=>({...f, type: e.target.value}))}
                      className="mt-1 w-full bg-[#0a0a0a] border border-[#262626] focus:border-[#D4AF37] text-white text-xs px-3 py-2 outline-none font-mono">
                {TYPES.map(t => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
            <Input label="Webhook URL" value={form.webhook_url} onChange={v=>setForm(f=>({...f, webhook_url: v}))} placeholder="https://..." testid="src-webhook" />
            <Input label="API Key (optional)" value={form.api_key} onChange={v=>setForm(f=>({...f, api_key: v}))} placeholder="••••••••" testid="src-apikey" />
            <div className="md:col-span-2 flex justify-end gap-2">
              <button type="button" onClick={()=>setShowAdd(false)} className="px-3 py-2 border border-[#262626] text-[10px] tracking-[0.18em] uppercase text-neutral-400">Cancel</button>
              <button type="submit" data-testid="src-submit" className="px-3 py-2 bg-[#D4AF37] text-black font-bold text-[10px] tracking-[0.18em] uppercase">Save Source</button>
            </div>
          </form>
        )}

        {sources.map(s => (
          <div key={s.id} data-testid={`source-row-${s.id}`} className="flex items-center justify-between border-b border-[#161616] py-3 last:border-b-0">
            <div className="min-w-0">
              <div className="text-sm text-neutral-100">{s.name}</div>
              <div className="text-[10px] text-neutral-500 mt-0.5 font-mono">type: {s.type}{s.webhook_url ? ` · ${s.webhook_url.slice(0,40)}${s.webhook_url.length>40?'…':''}` : ''}</div>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <span className="flex items-center gap-1.5 text-[10px] tracking-widest uppercase" style={{color: s.enabled ? '#30D158' : '#71717A'}}>
                {s.enabled && <CheckCircle size={11} fill="currentColor" />}
                {s.enabled ? 'Connected' : 'Disabled'}
              </span>
              <button onClick={()=>toggle(s.id)} title="Toggle" className="p-1.5 border border-[#262626] hover:border-[#404040]" data-testid={`toggle-source-${s.id}`}>
                <Power size={11} />
              </button>
              <button onClick={()=>remove(s.id)} title="Delete" className="p-1.5 border border-[#262626] hover:border-[#FF3B30] hover:text-[#FF3B30]" data-testid={`delete-source-${s.id}`}>
                <Trash2 size={11} />
              </button>
            </div>
          </div>
        ))}
      </Section>

      <Section title="AI Engine" icon={Brain}>
        <Row label="Triage Model" value="claude-sonnet-4-5-20250929" />
        <Row label="Chat Model" value="claude-sonnet-4-5-20250929" />
        <Row label="Provider" value="Anthropic via Emergent Universal Key" />
      </Section>

      <Section title="Notifications" icon={Bell}>
        <Row label="Unattended Alert SLA" value="5 days" />
        <Row label="In-App Toasts" value="Enabled" />
        <Row label="Slack" value="Not configured" muted />
      </Section>

      <Section title="Security" icon={Shield}>
        <Row label="Auth" value="JWT Bearer · 24h" />
        <Row label="SSO" value="Disabled · roadmap" muted />
      </Section>
    </div>
  );
}

function Section({ title, icon: Icon, action, children }) {
  return (
    <section className="border border-[#1f1f1f] mb-4">
      <div className="px-4 py-3 border-b border-[#1f1f1f] flex items-center gap-2">
        <Icon size={14} color="#D4AF37" />
        <h2 className="text-[11px] tracking-[0.25em] uppercase text-neutral-300 font-display font-bold">{title}</h2>
        <div className="ml-auto">{action}</div>
      </div>
      <div className="px-4 py-2">{children}</div>
    </section>
  );
}
function Row({ label, value, muted }) {
  return (
    <div className="flex items-center justify-between border-b border-[#161616] py-2.5 last:border-b-0">
      <div className="text-[11px] tracking-[0.18em] uppercase text-neutral-500">{label}</div>
      <div className={`text-xs font-mono ${muted ? 'text-neutral-500' : 'text-neutral-100'}`}>{value}</div>
    </div>
  );
}
function Input({ label, value, onChange, placeholder, testid }) {
  return (
    <div>
      <label className="text-[10px] tracking-[0.2em] uppercase text-neutral-500">{label}</label>
      <input data-testid={testid} value={value} onChange={e=>onChange(e.target.value)} placeholder={placeholder}
             className="mt-1 w-full bg-[#0a0a0a] border border-[#262626] focus:border-[#D4AF37] text-white text-xs px-3 py-2 outline-none font-mono" />
    </div>
  );
}
