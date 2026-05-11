import React, { useEffect, useState } from 'react';
import { fetchSources, addSource, deleteSource, toggleSource, api } from '../lib/api';
import { CloudUpload as CloudArrowUp, Bell, Brain, Shield, CheckCircle, Plus, Trash2, Power, Copy, Eye, EyeOff, PlayCircle, Webhook } from 'lucide-react';
import { toast, Toaster } from 'sonner';
import { relTime } from '../lib/format';
import NotificationsSettings from '../components/NotificationsSettings';

const TYPES = ['cloudwatch', 'datadog', 'pagerduty', 'grafana', 'prometheus', 'custom'];
const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;

export default function Settings() {
  const [sources, setSources] = useState([]);
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState({ name: '', type: 'cloudwatch', webhook_url: '', api_key: '' });
  const [revealed, setRevealed] = useState({}); // { src_id: bool }
  const [testing, setTesting] = useState({});

  const load = () => fetchSources().then(setSources);
  useEffect(() => { load(); }, []);

  const submit = async (e) => {
    e.preventDefault();
    if (!form.name.trim()) return toast.error('Name required');
    const created = await addSource(form);
    toast.success('Source added · webhook URL ready');
    setForm({ name: '', type: 'cloudwatch', webhook_url: '', api_key: '' });
    setShowAdd(false);
    setRevealed(r => ({ ...r, [created.id]: true })); // auto-reveal new
    load();
  };
  const remove = async (id) => { await deleteSource(id); toast.success('Removed'); load(); };
  const toggle = async (id) => { await toggleSource(id); load(); };

  const copy = (text, label) => {
    navigator.clipboard.writeText(text).then(() => toast.success(`${label} copied`));
  };

  const runTest = async (id) => {
    setTesting(t => ({ ...t, [id]: true }));
    try {
      const r = await api.post(`/sources/${id}/test`).then(x => x.data);
      toast.success(`Test successful · ingested ${r.ingested} alert${r.ingested>1?'s':''}`);
      load();
    } catch (e) {
      toast.error('Test failed: ' + (e?.response?.data?.detail || e.message));
    } finally {
      setTesting(t => ({ ...t, [id]: false }));
    }
  };

  return (
    <div className="p-6 max-w-5xl">
      <Toaster theme="dark" position="bottom-right" />
      <div className="text-[10px] tracking-[0.3em] text-neutral-500 uppercase">Configuration</div>
      <h1 className="font-display text-3xl font-black tracking-tighter mt-1 mb-6">SYSTEM SETTINGS</h1>

      <Section title="Alert Sources & Webhooks" icon={CloudArrowUp}
               action={
                 <button data-testid="add-source-btn" onClick={()=>setShowAdd(s=>!s)} className="flex items-center gap-1.5 px-2.5 py-1.5 border border-[#262626] hover:border-[#D4AF37] text-[10px] tracking-[0.18em] uppercase">
                   <Plus size={11} /> Add Source
                 </button>
               }>
        <div className="text-[11px] text-neutral-500 mb-3">
          Each source exposes a unique webhook URL. Configure your monitoring tool (CloudWatch SNS, Datadog, PagerDuty, Grafana, Prometheus Alertmanager) to POST alerts to that URL — TriageAI will normalize and ingest them.
        </div>

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
            <Input label="API Key (optional)" value={form.api_key} onChange={v=>setForm(f=>({...f, api_key: v}))} placeholder="••••••••" testid="src-apikey" />
            <Input label="Outbound Webhook URL (optional)" value={form.webhook_url} onChange={v=>setForm(f=>({...f, webhook_url: v}))} placeholder="https://..." testid="src-webhook" />
            <div className="md:col-span-2 flex justify-end gap-2">
              <button type="button" onClick={()=>setShowAdd(false)} className="px-3 py-2 border border-[#262626] text-[10px] tracking-[0.18em] uppercase text-neutral-400">Cancel</button>
              <button type="submit" data-testid="src-submit" className="px-3 py-2 bg-[#D4AF37] text-black font-bold text-[10px] tracking-[0.18em] uppercase">Save Source</button>
            </div>
          </form>
        )}

        <div className="space-y-2">
          {sources.map(s => {
            const isRevealed = !!revealed[s.id];
            const tokenDisplay = isRevealed ? s.ingest_token : (s.ingest_token || '').replace(/./g, '•');
            const ingestUrl = `${BACKEND_URL}/api/sources/${s.id}/ingest?token=${s.ingest_token}`;
            const maskedUrl = `${BACKEND_URL}/api/sources/${s.id}/ingest?token=${tokenDisplay}`;
            return (
              <div key={s.id} data-testid={`source-row-${s.id}`} className="border border-[#1f1f1f] bg-[#0d0d0d] p-3">
                <div className="flex items-center gap-3 flex-wrap">
                  <Webhook size={13} color="#D4AF37" />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-sm text-neutral-100">{s.name}</span>
                      <span className="text-[9px] tracking-[0.2em] uppercase px-1.5 py-0.5 border border-[#262626] text-neutral-400">{s.type}</span>
                    </div>
                    <div className="text-[10px] text-neutral-500 mt-0.5 font-mono">
                      {s.id} · {s.ingest_count || 0} ingested
                      {s.last_ingested_at && <> · last {relTime(s.last_ingested_at)}</>}
                    </div>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <span className="flex items-center gap-1.5 text-[10px] tracking-widest uppercase" style={{color: s.enabled ? '#30D158' : '#71717A'}}>
                      {s.enabled && <CheckCircle size={11} fill="currentColor" />}
                      {s.enabled ? 'Active' : 'Disabled'}
                    </span>
                    <button onClick={()=>runTest(s.id)} disabled={testing[s.id] || !s.enabled} title="Send test payload"
                            data-testid={`test-source-${s.id}`}
                            className="p-1.5 border border-[#262626] hover:border-[#D4AF37] hover:text-[#D4AF37] disabled:opacity-30">
                      <PlayCircle size={11} />
                    </button>
                    <button onClick={()=>toggle(s.id)} title="Toggle" className="p-1.5 border border-[#262626] hover:border-[#404040]" data-testid={`toggle-source-${s.id}`}>
                      <Power size={11} />
                    </button>
                    <button onClick={()=>remove(s.id)} title="Delete" className="p-1.5 border border-[#262626] hover:border-[#FF3B30] hover:text-[#FF3B30]" data-testid={`delete-source-${s.id}`}>
                      <Trash2 size={11} />
                    </button>
                  </div>
                </div>

                <div className="mt-3 border-t border-[#1f1f1f] pt-3 grid grid-cols-1 md:grid-cols-[1fr_auto] gap-2 items-center">
                  <div className="flex items-center gap-2 bg-black border border-[#1f1f1f] px-3 py-2 overflow-x-auto">
                    <span className="text-[9px] tracking-[0.2em] uppercase text-neutral-500 shrink-0">URL</span>
                    <code className="text-[10px] font-mono text-[#D4AF37] whitespace-nowrap" data-testid={`webhook-url-${s.id}`}>{maskedUrl}</code>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <button onClick={()=>setRevealed(r=>({...r, [s.id]: !isRevealed}))} title={isRevealed?'Hide':'Reveal'}
                            data-testid={`reveal-token-${s.id}`}
                            className="p-1.5 border border-[#262626] hover:border-[#404040] text-neutral-400">
                      {isRevealed ? <EyeOff size={11} /> : <Eye size={11} />}
                    </button>
                    <button onClick={()=>copy(ingestUrl, 'Webhook URL')} title="Copy URL"
                            data-testid={`copy-url-${s.id}`}
                            className="p-1.5 border border-[#262626] hover:border-[#D4AF37] text-neutral-400 hover:text-[#D4AF37]">
                      <Copy size={11} />
                    </button>
                  </div>
                </div>

                <div className="mt-2 text-[10px] text-neutral-500 font-mono">
                  → POST JSON payload as <span className="text-neutral-300">{s.type}</span> sends an alert. Click <PlayCircle size={10} className="inline" /> to fire a sample.
                </div>
              </div>
            );
          })}
        </div>
      </Section>

      <Section title="AI Engine" icon={Brain}>
        <Row label="Triage Model" value="claude-sonnet-4-5-20250929" />
        <Row label="Chat Model" value="claude-sonnet-4-5-20250929" />
        <Row label="Provider" value="Anthropic via Emergent Universal Key" />
      </Section>

      <NotificationsSettings />

      <Section title="Security" icon={Shield}>
        <Row label="Auth" value="JWT Bearer · 24h" />
        <Row label="Webhook Auth" value="Per-source token in ?token=... or X-Ingest-Token header" />
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
      <div className="p-4">{children}</div>
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
