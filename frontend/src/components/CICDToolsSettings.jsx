import React, { useEffect, useState } from 'react';
import {
  fetchCICDTools, addCICDTool, updateCICDTool, deleteCICDTool,
  testCICDTool, syncAllCICD,
} from '../lib/api';
import {
  GitBranch, Plus, Trash2, Power, PlayCircle, RefreshCw, Edit3, X, CheckCircle, AlertCircle,
} from 'lucide-react';
import { toast } from 'sonner';
import { relTime } from '../lib/format';
import { useAuth } from '../lib/auth';

const TYPES = [
  { value: 'github',  label: 'GitHub Actions', help: 'base_url: https://api.github.com/repos/owner/repo · token: PAT with repo + actions:read' },
  { value: 'gitlab',  label: 'GitLab CI (stub)',   help: 'Coming soon' },
  { value: 'circle',  label: 'CircleCI (stub)',    help: 'Coming soon' },
  { value: 'argocd',  label: 'Argo CD (stub)',     help: 'Coming soon' },
  { value: 'mock',    label: 'Mock / Demo',        help: 'Generates synthetic deployments for testing the full flow without a real CI/CD' },
];

const EMPTY = { name: '', type: 'github', api_token: '', base_url: '', watch_services_csv: '', active: true };

export default function CICDToolsSettings() {
  const { user } = useAuth();
  const isAdmin = user?.role === 'admin';
  const [tools, setTools] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState(null); // id or null
  const [form, setForm] = useState(EMPTY);
  const [busy, setBusy] = useState({});

  const load = () => fetchCICDTools().then(setTools).catch(() => {});
  useEffect(() => { load(); }, []);

  const openNew = () => { setEditing(null); setForm(EMPTY); setShowForm(true); };
  const openEdit = (t) => {
    setEditing(t.id);
    setForm({
      name: t.name || '',
      type: t.type || 'github',
      api_token: '', // never pre-fill
      base_url: t.base_url || '',
      watch_services_csv: (t.watch_services || []).join(', '),
      active: !!t.active,
    });
    setShowForm(true);
  };
  const close = () => { setShowForm(false); setEditing(null); setForm(EMPTY); };

  const submit = async (e) => {
    e.preventDefault();
    if (!form.name.trim()) return toast.error('Name required');
    const payload = {
      name: form.name.trim(),
      type: form.type,
      api_token: form.api_token,
      base_url: form.base_url.trim(),
      watch_services: form.watch_services_csv.split(',').map(s => s.trim()).filter(Boolean),
      active: form.active,
    };
    try {
      if (editing) {
        await updateCICDTool(editing, payload);
        toast.success('Tool updated');
      } else {
        await addCICDTool(payload);
        toast.success('Tool added');
      }
      close();
      load();
    } catch (err) {
      toast.error('Save failed: ' + (err?.response?.data?.detail || err.message));
    }
  };

  const remove = async (id) => {
    if (!window.confirm('Delete this CI/CD tool?')) return;
    await deleteCICDTool(id); toast.success('Removed'); load();
  };

  const test = async (id) => {
    setBusy(b => ({ ...b, [id]: 'test' }));
    try {
      const r = await testCICDTool(id);
      if (r.ok) toast.success(`Test sync OK · ${r.ingested} deployment${r.ingested === 1 ? '' : 's'} ingested`);
      else toast.error('Test failed: ' + (r.error || 'unknown'));
      load();
    } catch (err) {
      toast.error('Test failed: ' + (err?.response?.data?.detail || err.message));
    } finally {
      setBusy(b => ({ ...b, [id]: null }));
    }
  };

  const toggleActive = async (t) => {
    await updateCICDTool(t.id, {
      name: t.name, type: t.type, api_token: '',
      base_url: t.base_url, watch_services: t.watch_services,
      active: !t.active,
    });
    load();
  };

  const syncAll = async () => {
    setBusy(b => ({ ...b, _all: true }));
    try {
      const r = await syncAllCICD();
      const total = (r.results || []).reduce((acc, x) => acc + (x.ingested || 0), 0);
      toast.success(`Synced ${r.synced} tool(s) · ${total} new deployment(s)`);
      load();
    } catch (err) {
      toast.error('Sync failed: ' + (err?.response?.data?.detail || err.message));
    } finally {
      setBusy(b => ({ ...b, _all: false }));
    }
  };

  return (
    <section className="rounded-xl border border-[#1f1f1f] bg-[#0d0d0d] mb-4">
      <div className="px-6 py-4 border-b border-[#1f1f1f] flex items-center gap-3">
        <GitBranch size={16} strokeWidth={1.75} color="#D4AF37" />
        <div className="flex-1">
          <h3 className="font-display font-bold text-base tracking-tight text-white">CI/CD Integrations</h3>
          <div className="text-xs text-neutral-500 mt-0.5">
            Connect your deployment platforms — TriageAI correlates recent deploys to incidents in real time.
          </div>
        </div>
        {isAdmin && (
          <>
            <button
              onClick={syncAll} disabled={busy._all || tools.length === 0}
              data-testid="cicd-sync-all-btn"
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-[#262626] hover:border-[#D4AF37]/40 text-sm text-neutral-300 disabled:opacity-30"
            >
              <RefreshCw size={13} className={busy._all ? 'animate-spin' : ''} /> Sync now
            </button>
            <button
              onClick={openNew}
              data-testid="cicd-add-btn"
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-[#262626] hover:border-[#D4AF37]/40 text-sm text-neutral-300"
            >
              <Plus size={13} /> Add Tool
            </button>
          </>
        )}
      </div>

      <div className="px-6 py-4">
        {showForm && (
          <form onSubmit={submit} className="mb-4 rounded-lg border border-[#262626] bg-[#0a0a0a] p-4 grid grid-cols-1 md:grid-cols-2 gap-3" data-testid="cicd-form">
            <div className="md:col-span-2 flex items-center">
              <div className="text-sm font-semibold text-neutral-200">{editing ? 'Edit tool' : 'New CI/CD tool'}</div>
              <button type="button" onClick={close} className="ml-auto text-neutral-500 hover:text-white"><X size={15} /></button>
            </div>
            <Input label="Name" value={form.name} onChange={v => setForm(f => ({ ...f, name: v }))} placeholder="Production GitHub Actions" testid="cicd-name" />
            <div>
              <label className="text-xs text-neutral-400 mb-1.5 block">Type</label>
              <select
                value={form.type}
                onChange={e => setForm(f => ({ ...f, type: e.target.value }))}
                data-testid="cicd-type"
                className="w-full bg-[#0a0a0a] border border-[#262626] rounded-md focus:border-[#D4AF37] text-white text-sm px-3 py-2 outline-none"
              >
                {TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
              </select>
              <div className="text-[11px] text-neutral-500 mt-1">{TYPES.find(t => t.value === form.type)?.help}</div>
            </div>
            <Input
              label="Base URL"
              value={form.base_url}
              onChange={v => setForm(f => ({ ...f, base_url: v }))}
              placeholder={form.type === 'github' ? 'https://api.github.com/repos/owner/repo' : 'https://...'}
              testid="cicd-baseurl"
            />
            <Input
              label={`API token${editing ? ' (leave empty to keep existing)' : ''}`}
              value={form.api_token}
              onChange={v => setForm(f => ({ ...f, api_token: v }))}
              placeholder={form.type === 'mock' ? 'not required for mock' : 'ghp_...'}
              testid="cicd-token"
              type="password"
            />
            <div className="md:col-span-2">
              <Input
                label="Watch services (comma-separated)"
                value={form.watch_services_csv}
                onChange={v => setForm(f => ({ ...f, watch_services_csv: v }))}
                placeholder="payments-api, auth-service, checkout-svc"
                testid="cicd-services"
              />
              <div className="text-[11px] text-neutral-500 mt-1">
                Service names that match incident <code className="text-neutral-300">affected_services</code>. Used for correlation matching.
              </div>
            </div>
            <label className="flex items-center gap-2 text-sm text-neutral-300 md:col-span-2">
              <input type="checkbox" checked={form.active} onChange={e => setForm(f => ({ ...f, active: e.target.checked }))} />
              Active (poll every 60s)
            </label>
            <div className="md:col-span-2 flex justify-end gap-2 pt-1">
              <button type="button" onClick={close} className="px-3.5 py-2 rounded-md border border-[#262626] text-sm text-neutral-400 hover:text-white">Cancel</button>
              <button type="submit" data-testid="cicd-submit" className="px-3.5 py-2 rounded-md bg-[#D4AF37] text-black font-semibold text-sm hover:bg-[#e6c14d]">
                {editing ? 'Save changes' : 'Add tool'}
              </button>
            </div>
          </form>
        )}

        {tools.length === 0 && !showForm && (
          <div className="text-sm text-neutral-500 py-6 text-center">
            No CI/CD tools registered yet. {isAdmin && <button onClick={openNew} className="text-[#D4AF37] hover:underline">Add the first one →</button>}
          </div>
        )}

        <div className="space-y-2">
          {tools.map(t => {
            const ok = t.last_sync_status === 'ok';
            const err = (t.last_sync_status || '').startsWith('error');
            return (
              <div key={t.id} data-testid={`cicd-row-${t.id}`} className="rounded-lg border border-[#1f1f1f] bg-[#0a0a0a] p-4">
                <div className="flex items-center gap-3 flex-wrap">
                  <div className="w-8 h-8 rounded-md bg-[#D4AF37]/10 border border-[#D4AF37]/20 flex items-center justify-center shrink-0">
                    <GitBranch size={14} strokeWidth={1.75} color="#D4AF37" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-sm font-medium text-neutral-100">{t.name}</span>
                      <span className="text-xs px-2 py-0.5 rounded bg-[#161616] text-neutral-400">{t.type}</span>
                      {!t.has_token && t.type !== 'mock' && (
                        <span className="text-xs px-2 py-0.5 rounded bg-[#FF9F0A]/10 text-[#FF9F0A] border border-[#FF9F0A]/30">no token</span>
                      )}
                    </div>
                    <div className="text-xs text-neutral-500 mt-1 flex items-center gap-2 flex-wrap">
                      {t.watch_services?.length ? (
                        <span>Watches: <code className="text-neutral-300">{t.watch_services.join(', ')}</code></span>
                      ) : <span className="text-neutral-600">no service filter</span>}
                      <span className="text-neutral-700">·</span>
                      <span>{t.sync_count || 0} syncs</span>
                      {t.last_sync_at && <><span className="text-neutral-700">·</span><span>last {relTime(t.last_sync_at)}</span></>}
                      {ok && <CheckCircle size={11} className="text-[#30D158]" />}
                      {err && <span title={t.last_sync_status} className="flex items-center gap-1 text-[#FF3B30]"><AlertCircle size={11} />{t.last_sync_status?.slice(0, 30)}</span>}
                    </div>
                  </div>
                  <span className="flex items-center gap-1.5 text-xs font-medium shrink-0" style={{ color: t.active ? '#30D158' : '#71717A' }}>
                    <span className="w-1.5 h-1.5 rounded-full" style={{ background: t.active ? '#30D158' : '#71717A' }} />
                    {t.active ? 'Active' : 'Disabled'}
                  </span>
                </div>

                {isAdmin && (
                  <div className="mt-3 flex items-center gap-2 flex-wrap pt-3 border-t border-[#161616]">
                    <button
                      onClick={() => test(t.id)} disabled={busy[t.id] === 'test' || !t.active}
                      data-testid={`cicd-test-${t.id}`}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-[#262626] hover:border-[#D4AF37]/40 text-sm text-neutral-300 disabled:opacity-30"
                    >
                      <PlayCircle size={13} /> {busy[t.id] === 'test' ? 'Syncing…' : 'Test sync'}
                    </button>
                    <button
                      onClick={() => openEdit(t)}
                      data-testid={`cicd-edit-${t.id}`}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-[#262626] hover:border-[#404040] text-sm text-neutral-300"
                    >
                      <Edit3 size={13} /> Edit
                    </button>
                    <button
                      onClick={() => toggleActive(t)}
                      data-testid={`cicd-toggle-${t.id}`}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-[#262626] hover:border-[#404040] text-sm text-neutral-300"
                    >
                      <Power size={13} /> {t.active ? 'Disable' : 'Enable'}
                    </button>
                    <button
                      onClick={() => remove(t.id)}
                      data-testid={`cicd-delete-${t.id}`}
                      className="ml-auto flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-[#262626] hover:border-[#FF3B30]/40 hover:text-[#FF3B30] text-sm text-neutral-300"
                    >
                      <Trash2 size={13} /> Delete
                    </button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}

function Input({ label, value, onChange, placeholder, testid, type = 'text' }) {
  return (
    <div>
      <label className="text-xs text-neutral-400 mb-1.5 block">{label}</label>
      <input
        type={type}
        data-testid={testid}
        value={value}
        onChange={e => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full bg-[#0a0a0a] border border-[#262626] rounded-md focus:border-[#D4AF37] text-white text-sm px-3 py-2 outline-none"
      />
    </div>
  );
}
