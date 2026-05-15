import React, { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import {
  fetchIncident, listUsers, pickupIncident,
  addCollaborator, postUpdate, resolveIncident,
  fetchIncidentDeployments,
} from '../lib/api';
import { PriorityBadge, StatusPill, SeverityBadge, SourceBadge } from '../components/Badges';
import IncidentChat from '../components/IncidentChat';
import DeploymentCard from '../components/DeploymentCard';
import { useAuth } from '../lib/auth';
import { ArrowLeft, UserPlus, CheckCircle, Hand, Send } from 'lucide-react';
import { relTime } from '../lib/format';
import { toast, Toaster } from 'sonner';

export default function IncidentDetail() {
  const { id } = useParams();
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const [users, setUsers] = useState([]);
  const [deployments, setDeployments] = useState([]);
  const [showAddCollab, setShowAddCollab] = useState(false);
  const [updateText, setUpdateText] = useState('');

  const load = () => fetchIncident(id).then(setData);
  useEffect(() => {
    load();
    listUsers().then(setUsers);
    fetchIncidentDeployments(id).then(r => setDeployments(r.deployments || [])).catch(() => {});
  }, [id]);

  if (!data) return <div className="px-8 py-12 text-sm text-neutral-500">Loading incident…</div>;

  const { incident, triage, alerts } = data;
  const isAssignee = incident.assignee === user?.email;
  const isCollab = incident.collaborators?.includes(user?.email) || isAssignee || incident.created_by === user?.email;
  const resolved = incident.status === 'resolved';
  const canPickup = !incident.assignee && !resolved;

  const onPickup = async () => { await pickupIncident(id); toast.success('Incident picked up'); load(); };
  const onResolve = async () => { await resolveIncident(id); toast.success('Incident resolved'); load(); };
  const onAddCollab = async (email) => { await addCollaborator(id, email); toast.success(`Added ${email}`); setShowAddCollab(false); load(); };
  const onPostUpdate = async (e) => {
    e.preventDefault();
    if (!updateText.trim()) return;
    await postUpdate(id, updateText.trim());
    setUpdateText('');
    load();
  };

  const userByEmail = (em) => users.find(u => u.email === em);

  return (
    <div className="px-8 py-6">
      <Toaster theme="dark" position="bottom-right" />
      <Link to="/incidents" className="inline-flex items-center gap-1.5 text-sm text-neutral-500 hover:text-white transition-colors" data-testid="back-to-incidents">
        <ArrowLeft size={14} /> Back to Incidents
      </Link>

      {/* Header card */}
      <div className="mt-4 rounded-xl border border-[#1f1f1f] bg-[#0d0d0d] p-6">
        <div className="flex items-start gap-3 flex-wrap">
          <PriorityBadge priority={incident.priority} />
          <StatusPill status={incident.status} />
          <span className="text-xs font-mono text-neutral-500">{incident.id}</span>
          <span className="text-xs text-neutral-500">· {relTime(incident.created_at)}</span>
          <div className="ml-auto flex items-center gap-2 flex-wrap">
            {canPickup && (
              <button data-testid="pickup-btn" onClick={onPickup} className="flex items-center gap-1.5 px-3.5 py-2 rounded-md bg-[#D4AF37] text-black font-semibold text-sm hover:bg-[#e6c14d] hover-lift">
                <Hand size={14} strokeWidth={2} /> Pick Up
              </button>
            )}
            {isCollab && !resolved && (
              <button data-testid="add-collab-btn" onClick={()=>setShowAddCollab(s=>!s)} className="flex items-center gap-1.5 px-3.5 py-2 rounded-md border border-[#262626] hover:border-[#404040] text-sm text-neutral-300 transition-colors">
                <UserPlus size={14} strokeWidth={1.75} /> Add Collaborator
              </button>
            )}
            {(isAssignee || user?.role === 'admin') && !resolved && (
              <button data-testid="resolve-incident-btn" onClick={onResolve} className="flex items-center gap-1.5 px-3.5 py-2 rounded-md bg-[#30D158] text-black font-semibold text-sm hover:bg-[#3ce369] hover-lift">
                <CheckCircle size={14} strokeWidth={2} /> Mark Resolved
              </button>
            )}
          </div>
        </div>
        <h2 className="mt-4 text-lg text-neutral-100 font-medium leading-snug">{incident.title}</h2>

        <div className="mt-5 grid grid-cols-2 md:grid-cols-4 gap-4">
          <Field label="Assignee" value={incident.assignee ? (userByEmail(incident.assignee)?.name || incident.assignee) : 'Unassigned'} />
          <Field label="Created by" value={userByEmail(incident.created_by)?.name || incident.created_by || '—'} />
          <Field label="Blast radius" value={incident.blast_radius || '—'} />
          <Field label="Affected services" value={(incident.affected_services || []).join(', ') || '—'} />
        </div>

        {incident.collaborators?.length > 0 && (
          <div className="mt-4 flex items-center gap-2 flex-wrap pt-4 border-t border-[#1f1f1f]">
            <span className="text-xs text-neutral-500">Collaborators</span>
            {incident.collaborators.map(em => (
              <span key={em} className="text-xs px-2 py-0.5 rounded-md bg-[#161616] border border-[#262626] text-neutral-300">
                {userByEmail(em)?.name || em}
              </span>
            ))}
          </div>
        )}

        {showAddCollab && (
          <div className="mt-4 pt-4 border-t border-[#1f1f1f] flex flex-wrap gap-2" data-testid="collab-picker">
            {users.filter(u => u.email !== incident.assignee && !incident.collaborators?.includes(u.email))
              .map(u => (
                <button key={u.email} onClick={()=>onAddCollab(u.email)}
                        data-testid={`add-collab-${u.email.split('@')[0]}`}
                        className="text-xs px-3 py-1.5 rounded-md border border-[#262626] hover:border-[#D4AF37]/40 hover:bg-[#D4AF37]/[0.05] text-neutral-400 hover:text-white transition-colors">
                  + {u.name}
                </button>
            ))}
          </div>
        )}
      </div>

      {/* Body grid */}
      <div className="mt-4 grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Left: triage + alerts + updates */}
        <div className="lg:col-span-2 space-y-4">
          {deployments.length > 0 && (
            <section className="rounded-xl border border-[#1f1f1f] bg-[#0d0d0d] p-6" data-testid="incident-deployment-section">
              <h3 className="text-base font-display font-bold text-white tracking-tight mb-4 flex items-center gap-2">
                Deployment Correlation
                <span className="text-xs font-normal text-neutral-500">· {deployments.length} match{deployments.length === 1 ? '' : 'es'}</span>
              </h3>
              <DeploymentCard deployment={deployments[0]} />
              {deployments.length > 1 && (
                <details className="mt-2">
                  <summary className="text-xs text-neutral-500 cursor-pointer hover:text-neutral-300">
                    Show {deployments.length - 1} additional correlated deployment{deployments.length - 1 === 1 ? '' : 's'}
                  </summary>
                  <div className="mt-3 space-y-2">
                    {deployments.slice(1).map(d => <DeploymentCard key={d.id} deployment={d} />)}
                  </div>
                </details>
              )}
            </section>
          )}

          {triage && (
            <Section title="AI Triage Summary">
              <p className="text-sm text-neutral-300 leading-relaxed">{triage.summary}</p>
              <div className="mt-4 grid grid-cols-3 gap-2.5">
                <Stat label="Priority" value={triage.priority} />
                <Stat label="ETA" value={`${triage.mttr_estimate_minutes}m`} />
                <Stat label="Hypotheses" value={triage.root_causes?.length || 0} />
              </div>
              {triage.root_causes?.length > 0 && (
                <div className="mt-5 pt-5 border-t border-[#1f1f1f]">
                  <div className="text-xs text-neutral-500 mb-2">Top root cause</div>
                  <div className="text-sm text-white font-medium">#{triage.root_causes[0].rank} · {triage.root_causes[0].hypothesis}</div>
                  <p className="text-xs text-neutral-400 mt-1 leading-relaxed">{triage.root_causes[0].reasoning}</p>
                </div>
              )}
            </Section>
          )}

          <Section title={`Linked alerts · ${alerts.length}`}>
            <div className="space-y-2">
              {alerts.map(a => (
                <div key={a.id} className="flex items-center gap-2.5 py-2 flex-wrap border-b border-[#161616] last:border-b-0">
                  <SeverityBadge severity={a.severity} />
                  <SourceBadge source={a.source} />
                  <span className="text-xs font-mono text-neutral-500">{a.id}</span>
                  <span className="text-sm text-neutral-200 truncate flex-1">{a.title}</span>
                  <span className="text-xs text-neutral-500">{a.service} · {a.region}</span>
                </div>
              ))}
            </div>
          </Section>

          <Section title="Activity Log">
            {!resolved && isCollab && (
              <form onSubmit={onPostUpdate} className="flex items-center gap-2 mb-4" data-testid="post-update-form">
                <input
                  data-testid="update-input"
                  value={updateText} onChange={e=>setUpdateText(e.target.value)}
                  placeholder="Post an update…"
                  className="flex-1 bg-[#0a0a0a] border border-[#262626] rounded-md focus:border-[#D4AF37] outline-none px-3 py-2 text-sm text-white" />
                <button type="submit" data-testid="post-update-btn" className="px-3.5 py-2 rounded-md bg-white text-black font-semibold text-sm flex items-center gap-1.5 disabled:opacity-30" disabled={!updateText.trim()}>
                  <Send size={13} strokeWidth={2} /> Post
                </button>
              </form>
            )}
            <div className="border-l-2 border-[#262626] ml-1.5 pl-5 space-y-4">
              <TimelineItem label="Created" value={`by ${userByEmail(incident.created_by)?.name || incident.created_by || 'system'}`} time={incident.created_at} />
              {(incident.updates || []).map((u, i) => (
                <TimelineItem key={i} label={u.user_name || u.user_email} value={u.text} time={u.timestamp} />
              ))}
              {incident.resolved_at && <TimelineItem label="Resolved" value="" time={incident.resolved_at} accent="#30D158" />}
            </div>
          </Section>
        </div>

        {/* Right: chat */}
        <div className="lg:col-span-1 lg:sticky lg:top-4 lg:self-start">
          <IncidentChat incidentId={id} locked={resolved} />
        </div>
      </div>
    </div>
  );
}

function Section({ title, children }) {
  return (
    <section className="rounded-xl border border-[#1f1f1f] bg-[#0d0d0d] p-6">
      <h3 className="text-base font-display font-bold text-white tracking-tight mb-4">{title}</h3>
      {children}
    </section>
  );
}
function Field({ label, value }) {
  return (
    <div>
      <div className="text-xs text-neutral-500 mb-1">{label}</div>
      <div className="text-sm text-neutral-100 font-medium truncate">{value}</div>
    </div>
  );
}
function Stat({ label, value }) {
  return (
    <div className="rounded-lg border border-[#262626] bg-[#0a0a0a] p-3 text-center">
      <div className="text-xs text-neutral-500">{label}</div>
      <div className="font-display font-black text-2xl text-[#D4AF37] mt-1">{value}</div>
    </div>
  );
}
function TimelineItem({ label, value, time, accent = '#D4AF37' }) {
  return (
    <div className="relative">
      <span className="absolute -left-[26px] top-1.5 w-2 h-2 rounded-full" style={{ background: accent, boxShadow: `0 0 0 3px #0d0d0d` }} />
      <div className="flex items-center gap-2">
        <div className="text-xs font-medium text-neutral-300">{label}</div>
        <div className="text-xs text-neutral-600 ml-auto">{relTime(time)}</div>
      </div>
      {value && <div className="text-sm text-neutral-200 mt-1 leading-relaxed">{value}</div>}
    </div>
  );
}
