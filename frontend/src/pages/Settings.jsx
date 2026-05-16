import React, { useEffect, useState } from 'react';
import { fetchSources, addSource, deleteSource, toggleSource, api } from '../lib/api';
import { CloudUpload, Brain, Shield, CheckCircle, Plus, Trash2, Power, Copy, Eye, EyeOff, PlayCircle, Webhook, ChevronDown, ChevronRight } from 'lucide-react';
import { toast, Toaster } from 'sonner';
import { relTime } from '../lib/format';
import NotificationsSettings from '../components/NotificationsSettings';
import CICDToolsSettings from '../components/CICDToolsSettings';
import { useActiveModel } from '../hooks/useActiveModel';

const TYPES = ['cloudwatch', 'datadog', 'pagerduty', 'grafana', 'prometheus', 'custom'];
const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;

export default function Settings() {
  const { model, provider } = useActiveModel();
  const [sources, setSources] = useState([]);
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState({ name: '', type: 'cloudwatch', webhook_url: '', api_key: '' });
  const [revealed, setRevealed] = useState({});
  const [expanded, setExpanded] = useState({});
  const [testing, setTesting] = useState({});

  const load = () => fetchSources().then(setSources);
  useEffect(() => { load(); }, []);

  const submit = async (e) => {
    e.preventDefault();
    if (!form.name.trim()) return toast.error('Name required');
    const created = await addSource(form);
    toast.success('Source added');
    setForm({ name: '', type: 'cloudwatch', webhook_url: '', api_key: '' });
    setShowAdd(false);
    setExpanded(s => ({ ...s, [created.id]: true }));
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
      toast.success(`Test sent · ${r.ingested} alert${r.ingested>1?'s':''} ingested`);
      load();
    } catch (e) {
      toast.error('Test failed: ' + (e?.response?.data?.detail || e.message));
    } finally { setTesting(t => ({ ...t, [id]: false })); }
  };

  return (
    <div className="px-8 py-6 max-w-5xl">
      <Toaster theme="dark" position="bottom-right" />
      <div className="mb-6">
        <div className="text-xs text-neutral-500 mb-1">Configuration</div>
        <h2 className="font-display text-3xl font-black tracking-tight">System Settings</h2>
      </div>

      <Section title="Alert Sources & Webhooks" icon={CloudUpload}
               description="Each source has a unique webhook URL. Point your monitoring tools at it to ingest alerts."
               action={
                 <button data-testid="add-source-btn" onClick={()=>setShowAdd(s=>!s)} className="flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-[#262626] hover:border-[#D4AF37]/40 text-sm text-neutral-300 transition-colors">
                   <Plus size={13} /> Add Source
                 </button>
               }>
        {showAdd && (
          <form onSubmit={submit} className="mb-4 rounded-lg border border-[#262626] bg-[#0a0a0a] p-4 grid grid-cols-1 md:grid-cols-2 gap-3" data-testid="add-source-form">
            <Input label="Name" value={form.name} onChange={v=>setForm(f=>({...f, name: v}))} placeholder="Datadog Production" testid="src-name" />
            <div>
              <label className="text-xs text-neutral-400 mb-1.5 block">Type</label>
              <select data-testid="src-type" value={form.type} onChange={e=>setForm(f=>({...f, type: e.target.value}))}
                      className="w-full bg-[#0a0a0a] border border-[#262626] rounded-md focus:border-[#D4AF37] text-white text-sm px-3 py-2 outline-none">
                {TYPES.map(t => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
            <Input label="API key (optional)" value={form.api_key} onChange={v=>setForm(f=>({...f, api_key: v}))} placeholder="••••••" testid="src-apikey" />
            <Input label="Outbound webhook URL (optional)" value={form.webhook_url} onChange={v=>setForm(f=>({...f, webhook_url: v}))} placeholder="https://…" testid="src-webhook" />
            <div className="md:col-span-2 flex justify-end gap-2 pt-1">
              <button type="button" onClick={()=>setShowAdd(false)} className="px-3.5 py-2 rounded-md border border-[#262626] text-sm text-neutral-400 hover:text-white">Cancel</button>
              <button type="submit" data-testid="src-submit" className="px-3.5 py-2 rounded-md bg-[#D4AF37] text-black font-semibold text-sm hover:bg-[#e6c14d]">Save Source</button>
            </div>
          </form>
        )}

        <div className="space-y-2">
          {sources.map(s => {
            const isOpen = !!expanded[s.id];
            const isRevealed = !!revealed[s.id];
            const tokenDisplay = isRevealed ? s.ingest_token : (s.ingest_token || '').replace(/./g, '•');
            const ingestUrl = `${BACKEND_URL}/api/sources/${s.id}/ingest?token=${s.ingest_token}`;
            const maskedUrl = `${BACKEND_URL}/api/sources/${s.id}/ingest?token=${tokenDisplay}`;
            return (
              <div key={s.id} data-testid={`source-row-${s.id}`} className="rounded-lg border border-[#1f1f1f] bg-[#0a0a0a]">
                <button onClick={() => setExpanded(x => ({...x, [s.id]: !isOpen}))}
                        className="w-full p-4 flex items-center gap-3 text-left hover:bg-[#101010] transition-colors rounded-t-lg">
                  {isOpen ? <ChevronDown size={15} className="text-neutral-500 shrink-0" /> : <ChevronRight size={15} className="text-neutral-500 shrink-0" />}
                  <div className="w-8 h-8 rounded-md bg-[#D4AF37]/10 border border-[#D4AF37]/20 flex items-center justify-center shrink-0">
                    <Webhook size={14} strokeWidth={1.75} color="#D4AF37" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-sm font-medium text-neutral-100">{s.name}</span>
                      <span className="text-xs px-2 py-0.5 rounded bg-[#161616] text-neutral-400">{s.type}</span>
                    </div>
                    <div className="text-xs text-neutral-500 mt-1">
                      {s.ingest_count || 0} ingested {s.last_ingested_at && <> · last {relTime(s.last_ingested_at)}</>}
                    </div>
                  </div>
                  <span className="flex items-center gap-1.5 text-xs font-medium shrink-0" style={{color: s.enabled ? '#30D158' : '#71717A'}}>
                    <span className="w-1.5 h-1.5 rounded-full" style={{background: s.enabled ? '#30D158' : '#71717A'}} />
                    {s.enabled ? 'Active' : 'Disabled'}
                  </span>
                </button>

                {isOpen && (
                  <div className="border-t border-[#1f1f1f] p-4 space-y-3">
                    <div>
                      <div className="text-xs text-neutral-500 mb-1.5">Webhook URL</div>
                      <div className="flex items-center gap-2">
                        <div className="flex-1 bg-black/40 border border-[#1f1f1f] rounded-md px-3 py-2 overflow-x-auto">
                          <code className="text-xs font-mono text-[#D4AF37] whitespace-nowrap" data-testid={`webhook-url-${s.id}`}>{maskedUrl}</code>
                        </div>
                        <button onClick={()=>setRevealed(r=>({...r, [s.id]: !isRevealed}))} title={isRevealed?'Hide':'Reveal'}
                                data-testid={`reveal-token-${s.id}`}
                                className="p-2 rounded-md border border-[#262626] hover:border-[#404040] text-neutral-400">
                          {isRevealed ? <EyeOff size={13} /> : <Eye size={13} />}
                        </button>
                        <button onClick={()=>copy(ingestUrl, 'Webhook URL')} title="Copy URL"
                                data-testid={`copy-url-${s.id}`}
                                className="p-2 rounded-md border border-[#262626] hover:border-[#D4AF37]/40 text-neutral-400 hover:text-[#D4AF37]">
                          <Copy size={13} />
                        </button>
                      </div>
                      <div className="text-xs text-neutral-500 mt-2">
                        POST JSON as <code className="text-neutral-300">{s.type}</code> · or use <code className="text-neutral-300">X-Ingest-Token</code> header
                      </div>
                    </div>

                    <div className="flex items-center gap-2 pt-2 border-t border-[#1f1f1f]">
                      <button onClick={()=>runTest(s.id)} disabled={testing[s.id] || !s.enabled} data-testid={`test-source-${s.id}`}
                              className="flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-[#262626] hover:border-[#D4AF37]/40 text-sm text-neutral-300 disabled:opacity-30">
                        <PlayCircle size={13} /> Send test
                      </button>
                      <button onClick={()=>toggle(s.id)} data-testid={`toggle-source-${s.id}`}
                              className="flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-[#262626] hover:border-[#404040] text-sm text-neutral-300">
                        <Power size={13} /> {s.enabled ? 'Disable' : 'Enable'}
                      </button>
                      <button onClick={()=>remove(s.id)} data-testid={`delete-source-${s.id}`}
                              className="ml-auto flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-[#262626] hover:border-[#FF3B30]/40 hover:text-[#FF3B30] text-sm text-neutral-300">
                        <Trash2 size={13} /> Delete
                      </button>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </Section>

      <Section title="AI Engine" icon={Brain}>
        <Row label="Triage model" value={model} />
        <Row label="Chat model"   value={model} />
        <Row label="Provider"     value={provider === 'emergent' ? 'Anthropic via Emergent Universal Key' : 'OpenAI-compatible LLM gateway'} />
      </Section>

      <NotificationsSettings />

      <CICDToolsSettings />

      <Section title="Security" icon={Shield}>
        <Row label="Authentication" value="JWT Bearer · 24h" />
        <Row label="Webhook auth"   value="Per-source token in ?token= or X-Ingest-Token" />
      </Section>
    </div>
  );
}

function Section({ title, icon: Icon, action, description, children }) {
  return (
    <section className="rounded-xl border border-[#1f1f1f] bg-[#0d0d0d] mb-4">
      <div className="px-6 py-4 border-b border-[#1f1f1f] flex items-center gap-3">
        {Icon && <Icon size={16} strokeWidth={1.75} color="#D4AF37" />}
        <div className="flex-1">
          <h3 className="font-display font-bold text-base tracking-tight text-white">{title}</h3>
          {description && <div className="text-xs text-neutral-500 mt-0.5">{description}</div>}
        </div>
        {action}
      </div>
      <div className="px-6 py-4">{children}</div>
    </section>
  );
}
function Row({ label, value, muted }) {
  return (
    <div className="flex items-center justify-between py-2.5 border-b border-[#161616] last:border-b-0">
      <div className="text-sm text-neutral-400">{label}</div>
      <div className={`text-sm font-mono ${muted ? 'text-neutral-500' : 'text-neutral-100'}`}>{value}</div>
    </div>
  );
}
function Input({ label, value, onChange, placeholder, testid }) {
  return (
    <div>
      <label className="text-xs text-neutral-400 mb-1.5 block">{label}</label>
      <input data-testid={testid} value={value} onChange={e=>onChange(e.target.value)} placeholder={placeholder}
             className="w-full bg-[#0a0a0a] border border-[#262626] rounded-md focus:border-[#D4AF37] text-white text-sm px-3 py-2 outline-none" />
    </div>
  );
}
