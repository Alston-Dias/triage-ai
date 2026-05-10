import React, { useEffect, useState } from 'react';
import { fetchIncidents, fetchIncident } from '../lib/api';
import { PriorityBadge, StatusPill } from '../components/Badges';
import { relTime } from '../lib/format';
import { Activity } from 'lucide-react';

export default function Incidents() {
  const [incidents, setIncidents] = useState([]);
  const [selected, setSelected] = useState(null);

  useEffect(() => { fetchIncidents().then(setIncidents); }, []);

  const open = async (id) => {
    const d = await fetchIncident(id);
    setSelected(d);
  };

  return (
    <div className="p-6 max-w-[1400px]">
      <div className="text-[10px] tracking-[0.3em] text-neutral-500 uppercase">Operations Log</div>
      <h1 className="font-display text-3xl font-black tracking-tighter mt-1 mb-6">INCIDENT REGISTER</h1>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-0 border border-[#1f1f1f]">
        <div className="lg:col-span-2 border-r border-[#1f1f1f]">
          <div className="grid grid-cols-12 px-4 py-2.5 border-b border-[#1f1f1f] text-[10px] tracking-[0.2em] uppercase text-neutral-500">
            <div className="col-span-1">Pri</div>
            <div className="col-span-5">Title</div>
            <div className="col-span-2">Status</div>
            <div className="col-span-2">Services</div>
            <div className="col-span-2 text-right">Created</div>
          </div>
          {incidents.length === 0 && (
            <div className="px-4 py-12 text-center text-xs text-neutral-500 tracking-wider uppercase">No incidents yet · Run a triage first</div>
          )}
          {incidents.map(inc => (
            <div
              key={inc.id}
              data-testid={`incident-row-${inc.id}`}
              onClick={() => open(inc.id)}
              className={`grid grid-cols-12 px-4 py-3 border-b border-[#161616] cursor-pointer hover:bg-[#101010] ${selected?.incident?.id === inc.id ? 'bg-[#141414]' : ''}`}>
              <div className="col-span-1"><PriorityBadge priority={inc.priority} /></div>
              <div className="col-span-5 text-sm text-neutral-100 truncate pr-2">{inc.title}</div>
              <div className="col-span-2"><StatusPill status={inc.status} /></div>
              <div className="col-span-2 text-[10px] text-neutral-400 truncate">{(inc.affected_services||[]).slice(0,2).join(' · ')}</div>
              <div className="col-span-2 text-[10px] text-neutral-500 text-right">{relTime(inc.created_at)}</div>
            </div>
          ))}
        </div>

        <aside className="bg-[#0a0a0a] p-4 min-h-[300px]" data-testid="incident-detail">
          {!selected && (
            <div className="text-center text-xs text-neutral-500 tracking-wider uppercase mt-12">
              <Activity size={24} className="mx-auto mb-3 opacity-50" />
              Select an incident
            </div>
          )}
          {selected && (
            <div>
              <div className="flex items-center gap-2 mb-2">
                <PriorityBadge priority={selected.incident.priority} />
                <StatusPill status={selected.incident.status} />
              </div>
              <div className="text-[10px] text-neutral-500 tracking-widest font-mono">{selected.incident.id}</div>
              <div className="text-sm text-neutral-100 mt-2">{selected.incident.title}</div>
              <div className="mt-4 text-[10px] tracking-[0.2em] uppercase text-neutral-500">Timeline</div>
              <div className="border-l border-[#262626] ml-1 mt-2 pl-4 space-y-3">
                <TimelineItem label="Created" value={relTime(selected.incident.created_at)} />
                {selected.triage && <TimelineItem label="AI Triage" value={`${selected.triage.root_causes?.length || 0} hypotheses · ETA ${selected.triage.mttr_estimate_minutes}m`} />}
                {selected.incident.resolved_at && <TimelineItem label="Resolved" value={relTime(selected.incident.resolved_at)} />}
              </div>
              <div className="mt-4 text-[10px] tracking-[0.2em] uppercase text-neutral-500">Alerts ({selected.alerts.length})</div>
              <div className="mt-2 space-y-1">
                {selected.alerts.map(a => (
                  <div key={a.id} className="text-[11px] text-neutral-300 truncate">
                    <span className="text-neutral-500 font-mono">{a.id}</span> · {a.title}
                  </div>
                ))}
              </div>
              {selected.triage?.summary && (
                <>
                  <div className="mt-4 text-[10px] tracking-[0.2em] uppercase text-neutral-500">AI Summary</div>
                  <div className="mt-1 text-xs text-neutral-300 leading-relaxed">{selected.triage.summary}</div>
                </>
              )}
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}

function TimelineItem({ label, value }) {
  return (
    <div className="relative">
      <span className="absolute -left-[20px] top-1.5 w-1.5 h-1.5 bg-[#D4AF37]" />
      <div className="text-[10px] tracking-[0.2em] uppercase text-neutral-500">{label}</div>
      <div className="text-xs text-neutral-200">{value}</div>
    </div>
  );
}
