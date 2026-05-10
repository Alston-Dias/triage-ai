import React, { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import {
  fetchIncident, fetchChat, listUsers, pickupIncident,
  addCollaborator, postUpdate, resolveIncident
} from '../lib/api';
import { PriorityBadge, StatusPill, SeverityBadge, SourceBadge } from '../components/Badges';
import IncidentChat from '../components/IncidentChat';
import { useAuth } from '../lib/auth';
import { ArrowLeft, UserPlus, CheckCircle, Hand, Send } from 'lucide-react';
import { relTime } from '../lib/format';
import { toast, Toaster } from 'sonner';

export default function IncidentDetail() {
  const { id } = useParams();
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const [users, setUsers] = useState([]);
  const [showAddCollab, setShowAddCollab] = useState(false);
  const [updateText, setUpdateText] = useState('');

  const load = () => fetchIncident(id).then(setData);
  useEffect(() => { load(); listUsers().then(setUsers); }, [id]);

  if (!data) return <div className="p-8 text-xs tracking-widest uppercase text-neutral-500">// Loading incident...</div>;

  const { incident, triage, alerts } = data;
  const isAssignee = incident.assignee === user?.email;
  const isCollab = incident.collaborators?.includes(user?.email) || isAssignee || incident.created_by === user?.email;
  const resolved = incident.status === 'resolved';
  const canPickup = !incident.assignee && !resolved;

  const onPickup = async () => {
    await pickupIncident(id);
    toast.success('Incident picked up');
    load();
  };
  const onResolve = async () => {
    await resolveIncident(id);
    toast.success('Incident resolved');
    load();
  };
  const onAddCollab = async (email) => {
    await addCollaborator(id, email);
    toast.success(`Added ${email}`);
    setShowAddCollab(false);
    load();
  };
  const onPostUpdate = async (e) => {
    e.preventDefault();
    if (!updateText.trim()) return;
    await postUpdate(id, updateText.trim());
    setUpdateText('');
    load();
  };

  const userByEmail = (em) => users.find(u => u.email === em);

  return (
    <div className="p-6">
      <Toaster theme="dark" position="bottom-right" />
      <Link to="/incidents" className="inline-flex items-center gap-1.5 text-[10px] tracking-[0.2em] uppercase text-neutral-500 hover:text-white" data-testid="back-to-incidents">
        <ArrowLeft size={12} /> Back to Incidents
      </Link>

      {/* Header */}
      <div className="mt-3 border border-[#1f1f1f] bg-[#0d0d0d] p-5">
        <div className="flex items-start gap-3 flex-wrap">
          <PriorityBadge priority={incident.priority} />
          <StatusPill status={incident.status} />
          <span className="text-[10px] font-mono text-neutral-500">{incident.id}</span>
          <span className="text-[10px] text-neutral-500 tracking-wider">{relTime(incident.created_at)}</span>
          <div className="ml-auto flex items-center gap-2">
            {canPickup && (
              <button data-testid="pickup-btn" onClick={onPickup} className="flex items-center gap-1.5 px-3 py-2 bg-[#D4AF37] text-black font-bold text-[10px] tracking-[0.18em] uppercase hover:bg-[#e6c14d]">
                <Hand size={12} /> Pick Up
              </button>
            )}
            {isCollab && !resolved && (
              <button data-testid="add-collab-btn" onClick={()=>setShowAddCollab(s=>!s)} className="flex items-center gap-1.5 px-3 py-2 border border-[#262626] hover:border-[#404040] text-[10px] tracking-[0.18em] uppercase">
                <UserPlus size={12} /> Add Collaborator
              </button>
            )}
            {(isAssignee || user?.role === 'admin') && !resolved && (
              <button data-testid="resolve-incident-btn" onClick={onResolve} className="flex items-center gap-1.5 px-3 py-2 bg-[#30D158] text-black font-bold text-[10px] tracking-[0.18em] uppercase hover:bg-[#3ce369]">
                <CheckCircle size={12} /> Mark Resolved
              </button>
            )}
          </div>
        </div>
        <div className="text-sm text-neutral-100 mt-3">{incident.title}</div>
        <div className="mt-3 grid grid-cols-2 md:grid-cols-4 gap-4 text-[10px]">
          <Field label="Assignee" value={incident.assignee ? (userByEmail(incident.assignee)?.name || incident.assignee) : '— Unassigned —'} />
          <Field label="Created By" value={userByEmail(incident.created_by)?.name || incident.created_by || '—'} />
          <Field label="Blast Radius" value={incident.blast_radius || '—'} />
          <Field label="Affected" value={(incident.affected_services || []).join(', ') || '—'} />
        </div>
        {incident.collaborators?.length > 0 && (
          <div className="mt-3 flex items-center gap-2 flex-wrap">
            <span className="text-[10px] tracking-[0.2em] uppercase text-neutral-500">Collaborators</span>
            {incident.collaborators.map(em => (
              <span key={em} className="text-[10px] px-2 py-0.5 border border-[#262626] text-neutral-300 font-mono">
                {userByEmail(em)?.name || em}
              </span>
            ))}
          </div>
        )}

        {showAddCollab && (
          <div className="mt-4 border-t border-[#1f1f1f] pt-3 flex flex-wrap gap-2" data-testid="collab-picker">
            {users.filter(u => u.email !== incident.assignee && !incident.collaborators?.includes(u.email))
              .map(u => (
                <button key={u.email} onClick={()=>onAddCollab(u.email)}
                        data-testid={`add-collab-${u.email.split('@')[0]}`}
                        className="text-[10px] px-2.5 py-1.5 border border-[#262626] hover:border-[#D4AF37] hover:text-white text-neutral-400 transition-colors">
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
          {/* Triage summary */}
          {triage && (
            <Section title="AI Triage Summary">
              <div className="text-xs text-neutral-300 leading-relaxed">{triage.summary}</div>
              <div className="mt-3 grid grid-cols-3 gap-3">
                <Stat label="Priority" value={triage.priority} />
                <Stat label="ETA" value={`${triage.mttr_estimate_minutes}m`} />
                <Stat label="Hypotheses" value={triage.root_causes?.length || 0} />
              </div>
              {triage.root_causes?.length > 0 && (
                <div className="mt-4">
                  <div className="text-[10px] tracking-[0.25em] uppercase text-neutral-500 mb-2">Top Root Cause</div>
                  <div className="text-sm text-white">#{triage.root_causes[0].rank} · {triage.root_causes[0].hypothesis}</div>
                  <div className="text-[11px] text-neutral-400 mt-1">{triage.root_causes[0].reasoning}</div>
                </div>
              )}
            </Section>
          )}

          {/* Alerts */}
          <Section title={`Linked Alerts (${alerts.length})`}>
            <div className="space-y-1">
              {alerts.map(a => (
                <div key={a.id} className="flex items-center gap-2 py-1.5 border-b border-[#161616] last:border-b-0">
                  <SeverityBadge severity={a.severity} />
                  <SourceBadge source={a.source} />
                  <span className="text-[10px] font-mono text-neutral-500">{a.id}</span>
                  <span className="text-xs text-neutral-300 truncate flex-1">{a.title}</span>
                  <span className="text-[10px] text-neutral-500">{a.service} · {a.region}</span>
                </div>
              ))}
            </div>
          </Section>

          {/* Updates / activity */}
          <Section title="Activity Log">
            {!resolved && isCollab && (
              <form onSubmit={onPostUpdate} className="flex items-center gap-2 mb-3" data-testid="post-update-form">
                <input
                  data-testid="update-input"
                  value={updateText} onChange={e=>setUpdateText(e.target.value)}
                  placeholder="Post an update..."
                  className="flex-1 bg-[#0a0a0a] border border-[#262626] focus:border-[#D4AF37] outline-none px-3 py-2 text-xs font-mono text-white" />
                <button type="submit" data-testid="post-update-btn" className="px-3 py-2 bg-white text-black font-bold text-[10px] tracking-[0.18em] uppercase flex items-center gap-1.5 disabled:opacity-30" disabled={!updateText.trim()}>
                  <Send size={11} /> Post
                </button>
              </form>
            )}
            <div className="border-l border-[#262626] ml-1 pl-4 space-y-3">
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
    <section className="border border-[#1f1f1f] bg-[#0d0d0d]">
      <div className="px-4 py-3 border-b border-[#1f1f1f]">
        <h3 className="text-[10px] tracking-[0.25em] uppercase text-neutral-300 font-display font-bold">{title}</h3>
      </div>
      <div className="p-4">{children}</div>
    </section>
  );
}
function Field({ label, value }) {
  return (
    <div>
      <div className="text-[9px] tracking-[0.25em] uppercase text-neutral-500">{label}</div>
      <div className="text-xs text-neutral-100 mt-0.5 font-mono truncate">{value}</div>
    </div>
  );
}
function Stat({ label, value }) {
  return (
    <div className="border border-[#262626] p-2 text-center">
      <div className="text-[9px] tracking-[0.2em] uppercase text-neutral-500">{label}</div>
      <div className="font-display font-black text-xl text-[#D4AF37] mt-1">{value}</div>
    </div>
  );
}
function TimelineItem({ label, value, time, accent = '#D4AF37' }) {
  return (
    <div className="relative">
      <span className="absolute -left-[20px] top-1.5 w-1.5 h-1.5" style={{ background: accent }} />
      <div className="flex items-center gap-2">
        <div className="text-[10px] tracking-[0.18em] uppercase text-neutral-400">{label}</div>
        <div className="text-[10px] text-neutral-600 ml-auto">{relTime(time)}</div>
      </div>
      {value && <div className="text-xs text-neutral-200 mt-1">{value}</div>}
    </div>
  );
}
