import React, { useEffect, useState } from 'react';
import { api } from '../lib/api';
import { useAuth } from '../lib/auth';
import { Plus, Trash2, Power, PlayCircle, MessageSquare, Hash, Mail, Webhook as WebhookIcon, Bell, X, CheckCircle, AlertCircle } from 'lucide-react';
import { toast } from 'sonner';
import { relTime } from '../lib/format';

const CHANNEL_META = {
  slack:   { label: 'Slack',           icon: MessageSquare, fields: [{key:'webhook_url', label:'Slack Webhook URL', placeholder:'https://hooks.slack.com/services/...'}] },
  teams:   { label: 'Microsoft Teams', icon: Hash,          fields: [{key:'webhook_url', label:'Teams Webhook URL', placeholder:'https://outlook.office.com/webhook/...'}] },
  discord: { label: 'Discord',         icon: Hash,          fields: [{key:'webhook_url', label:'Discord Webhook URL', placeholder:'https://discord.com/api/webhooks/...'}] },
  webhook: { label: 'Generic Webhook', icon: WebhookIcon,   fields: [{key:'webhook_url', label:'POST URL',           placeholder:'https://...'}] },
  email:   { label: 'Email (Resend)',  icon: Mail,          fields: [
    {key:'api_key', label:'Resend API Key', placeholder:'re_xxxxxxxx'},
    {key:'from_email', label:'From Email', placeholder:'alerts@yourdomain.com'},
    {key:'to_email', label:'To Email', placeholder:'oncall@yourcompany.com'},
  ]},
};

const TRIGGERS = [
  { key: 'incident_created', label: 'New P1/P2 incident' },
  { key: 'sla_breach',       label: 'SLA breach (>5d)' },
  { key: 'incident_resolved', label: 'Incident resolved' },
];

export default function NotificationsSettings() {
  const { user } = useAuth();
  const [channels, setChannels] = useState([]);
  const [logs, setLogs] = useState([]);
  const [showAdd, setShowAdd] = useState(false);
  const [editing, setEditing] = useState(null); // channel.id or null
  const [form, setForm] = useState({ name: '', type: 'slack', config: {}, triggers: ['incident_created', 'sla_breach', 'incident_resolved'], enabled: true });
  const [testing, setTesting] = useState({});

  const isAdmin = user?.role === 'admin';

  const load = () => {
    api.get('/notifications/channels').then(r => setChannels(r.data));
    api.get('/notifications/log').then(r => setLogs(r.data || []));
  };
  useEffect(() => { load(); }, []);

  const startAdd = () => {
    setEditing(null);
    setForm({ name: '', type: 'slack', config: {}, triggers: ['incident_created', 'sla_breach', 'incident_resolved'], enabled: true });
    setShowAdd(true);
  };
  const startEdit = (ch) => {
    setEditing(ch.id);
    setForm({ name: ch.name, type: ch.type, config: ch.config || {}, triggers: ch.triggers || [], enabled: ch.enabled });
    setShowAdd(true);
  };

  const submit = async (e) => {
    e.preventDefault();
    if (!form.name.trim()) return toast.error('Name required');
    try {
      if (editing) {
        await api.patch(`/notifications/channels/${editing}`, form);
        toast.success('Channel updated');
      } else {
        await api.post('/notifications/channels', form);
        toast.success('Channel added');
      }
      setShowAdd(false);
      setEditing(null);
      load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Save failed');
    }
  };

  const remove = async (id) => {
    if (!window.confirm('Delete this channel?')) return;
    await api.delete(`/notifications/channels/${id}`);
    toast.success('Channel deleted');
    load();
  };

  const toggle = async (ch) => {
    await api.patch(`/notifications/channels/${ch.id}`, { ...ch, enabled: !ch.enabled });
    load();
  };

  const test = async (id) => {
    setTesting(t => ({ ...t, [id]: true }));
    try {
      const r = await api.post(`/notifications/channels/${id}/test`);
      if (r.data.status === 'ok') toast.success('Test sent successfully');
      else toast.error(`Test failed: ${r.data.status}`);
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Test failed');
    } finally {
      setTesting(t => ({ ...t, [id]: false }));
    }
  };

  const toggleTrigger = (key) => {
    setForm(f => ({ ...f, triggers: f.triggers.includes(key) ? f.triggers.filter(t=>t!==key) : [...f.triggers, key] }));
  };

  const meta = CHANNEL_META[form.type];

  return (
    <section className="rounded-xl border border-[#1f1f1f] bg-[#0d0d0d] mb-4" data-testid="notifications-section">
      <div className="px-6 py-4 border-b border-[#1f1f1f] flex items-center gap-3">
        <Bell size={16} strokeWidth={1.75} color="#D4AF37" />
        <div className="flex-1">
          <h3 className="font-display font-bold text-base tracking-tight text-white">Notification Channels</h3>
          <div className="text-xs text-neutral-500 mt-0.5">
            {isAdmin ? 'Send notifications to Slack, Teams, Discord, webhooks, or email' : 'Read-only · admin only'}
          </div>
        </div>
        {isAdmin && (
          <button data-testid="add-channel-btn" onClick={startAdd} className="flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-[#262626] hover:border-[#D4AF37]/40 text-sm text-neutral-300 transition-colors">
            <Plus size={13} /> Add Channel
          </button>
        )}
      </div>

      <div className="px-6 py-4">
        <div className="text-sm text-neutral-400 mb-4">
          Configure Slack, Teams, Discord, custom webhooks, or email to receive automatic notifications on incident triggers.
        </div>

        {showAdd && isAdmin && (
          <form onSubmit={submit} className="mb-4 border border-[#262626] p-3 bg-[#0a0a0a] space-y-3" data-testid="channel-form">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <Input label="Name" value={form.name} onChange={v=>setForm(f=>({...f, name:v}))} placeholder="On-call Slack" testid="channel-name" />
              <div>
                <label className="text-[10px] tracking-[0.2em] uppercase text-neutral-500">Channel Type</label>
                <select data-testid="channel-type" value={form.type}
                  onChange={e=>setForm(f=>({...f, type: e.target.value, config: {}}))}
                  className="mt-1 w-full bg-[#0a0a0a] border border-[#262626] focus:border-[#D4AF37] text-white text-xs px-3 py-2 outline-none font-mono">
                  {Object.entries(CHANNEL_META).map(([k,m])=>(<option key={k} value={k}>{m.label}</option>))}
                </select>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {meta.fields.map(f => (
                <Input key={f.key} label={f.label} placeholder={f.placeholder}
                  value={form.config[f.key] || ''}
                  onChange={v=>setForm(p=>({...p, config: {...p.config, [f.key]: v}}))}
                  testid={`channel-${f.key}`} />
              ))}
            </div>

            <div>
              <div className="text-[10px] tracking-[0.2em] uppercase text-neutral-500 mb-1.5">Triggers</div>
              <div className="flex flex-wrap gap-2">
                {TRIGGERS.map(t => {
                  const on = form.triggers.includes(t.key);
                  return (
                    <button type="button" key={t.key} onClick={()=>toggleTrigger(t.key)}
                      data-testid={`trigger-${t.key}`}
                      className={`px-3 py-1.5 text-[10px] tracking-[0.18em] uppercase border transition-colors ${on ? 'bg-[#D4AF37]/10 border-[#D4AF37] text-[#D4AF37]' : 'border-[#262626] text-neutral-400 hover:border-[#404040]'}`}>
                      {on ? '✓ ' : ''}{t.label}
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="flex justify-end gap-2">
              <button type="button" onClick={()=>{setShowAdd(false); setEditing(null);}} className="px-3 py-2 border border-[#262626] text-[10px] tracking-[0.18em] uppercase text-neutral-400">Cancel</button>
              <button type="submit" data-testid="channel-submit" className="px-3 py-2 bg-[#D4AF37] text-black font-bold text-[10px] tracking-[0.18em] uppercase">{editing?'Update':'Save'} Channel</button>
            </div>
          </form>
        )}

        <div className="space-y-2">
          {channels.length === 0 && (
            <div className="text-center py-8 text-xs text-neutral-500 tracking-wider uppercase">// No channels configured</div>
          )}
          {channels.map(ch => {
            const cMeta = CHANNEL_META[ch.type] || CHANNEL_META.webhook;
            const Icon = cMeta.icon;
            const statusOk = ch.last_status === 'ok';
            const statusErr = ch.last_status && ch.last_status.startsWith('error');
            return (
              <div key={ch.id} data-testid={`channel-row-${ch.id}`} className="border border-[#1f1f1f] bg-[#0d0d0d] p-3">
                <div className="flex items-center gap-3 flex-wrap">
                  <Icon size={14} color="#D4AF37" />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-sm text-neutral-100">{ch.name}</span>
                      <span className="text-[9px] tracking-[0.2em] uppercase px-1.5 py-0.5 border border-[#262626] text-neutral-400">{cMeta.label}</span>
                      {(ch.triggers || []).map(t => (
                        <span key={t} className="text-[9px] tracking-wider px-1.5 py-0.5 bg-[#161616] text-neutral-400 font-mono">{t}</span>
                      ))}
                    </div>
                    <div className="text-[10px] text-neutral-500 mt-0.5 font-mono">
                      {ch.id}{ch.last_used_at && <> · last sent {relTime(ch.last_used_at)}</>}
                      {statusOk && <span className="ml-2 text-[#30D158]">· <CheckCircle size={9} className="inline" /> OK</span>}
                      {statusErr && <span className="ml-2 text-[#FF3B30]" title={ch.last_status}>· <AlertCircle size={9} className="inline" /> {ch.last_status.slice(0,40)}</span>}
                    </div>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <span className="flex items-center gap-1.5 text-[10px] tracking-widest uppercase" style={{color: ch.enabled ? '#30D158' : '#71717A'}}>
                      {ch.enabled && <CheckCircle size={11} fill="currentColor" />}
                      {ch.enabled ? 'Active' : 'Disabled'}
                    </span>
                    {isAdmin && (
                      <>
                        <button onClick={()=>test(ch.id)} disabled={testing[ch.id] || !ch.enabled} title="Send test" data-testid={`test-channel-${ch.id}`}
                                className="p-1.5 border border-[#262626] hover:border-[#D4AF37] hover:text-[#D4AF37] disabled:opacity-30">
                          <PlayCircle size={11} />
                        </button>
                        <button onClick={()=>startEdit(ch)} title="Edit" data-testid={`edit-channel-${ch.id}`}
                                className="p-1.5 border border-[#262626] hover:border-[#404040] text-[10px] tracking-widest px-2">
                          EDIT
                        </button>
                        <button onClick={()=>toggle(ch)} title="Toggle" data-testid={`toggle-channel-${ch.id}`}
                                className="p-1.5 border border-[#262626] hover:border-[#404040]">
                          <Power size={11} />
                        </button>
                        <button onClick={()=>remove(ch.id)} title="Delete" data-testid={`delete-channel-${ch.id}`}
                                className="p-1.5 border border-[#262626] hover:border-[#FF3B30] hover:text-[#FF3B30]">
                          <Trash2 size={11} />
                        </button>
                      </>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        {logs.length > 0 && (
          <details className="mt-6" data-testid="notification-log-details">
            <summary className="text-[10px] tracking-[0.25em] uppercase text-neutral-500 cursor-pointer hover:text-neutral-300">
              Recent Notification Log ({logs.length})
            </summary>
            <div className="mt-2 border border-[#1f1f1f] divide-y divide-[#161616]">
              {logs.slice(0,15).map(l => (
                <div key={l.id} className="px-3 py-2 text-[11px] flex items-center gap-2">
                  <span className="text-[9px] tracking-wider px-1.5 py-0.5 border border-[#262626] uppercase text-neutral-400">{l.event}</span>
                  <span className="text-neutral-300 truncate flex-1">{l.subject}</span>
                  <span className="text-[10px]" style={{color: l.status === 'ok' ? '#30D158' : (l.status === 'pending' ? '#D4AF37' : '#FF3B30')}}>{l.status}</span>
                  <span className="text-[10px] text-neutral-500">{relTime(l.timestamp)}</span>
                </div>
              ))}
            </div>
          </details>
        )}
      </div>
    </section>
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
