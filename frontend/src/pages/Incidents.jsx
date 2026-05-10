import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { fetchIncidents } from '../lib/api';
import { PriorityBadge, StatusPill } from '../components/Badges';
import { relTime } from '../lib/format';
import { useAuth } from '../lib/auth';

const TABS = [
  { key: 'mine', label: 'My Incidents' },
  { key: 'others', label: 'Others' },
  { key: 'all', label: 'All' },
];

export default function Incidents() {
  const { user } = useAuth();
  const [tab, setTab] = useState('mine');
  const [incidents, setIncidents] = useState([]);

  useEffect(() => {
    const scope = tab === 'all' ? null : tab;
    fetchIncidents(scope).then(setIncidents);
  }, [tab]);

  return (
    <div className="p-6 max-w-[1400px]">
      <div className="text-[10px] tracking-[0.3em] text-neutral-500 uppercase">Operations Log</div>
      <h1 className="font-display text-3xl font-black tracking-tighter mt-1 mb-4">INCIDENT REGISTER</h1>

      <div className="flex items-center gap-1 border-b border-[#1f1f1f] mb-0">
        {TABS.map(t => (
          <button
            key={t.key}
            data-testid={`incidents-tab-${t.key}`}
            onClick={() => setTab(t.key)}
            className={`px-4 py-2.5 text-[11px] tracking-[0.2em] uppercase border-b-2 -mb-[1px] transition-colors ${tab === t.key ? 'border-[#D4AF37] text-white' : 'border-transparent text-neutral-500 hover:text-neutral-300'}`}>
            {t.label}
          </button>
        ))}
      </div>

      <div className="border border-[#1f1f1f] border-t-0">
        <div className="grid grid-cols-12 px-4 py-2.5 border-b border-[#1f1f1f] text-[10px] tracking-[0.2em] uppercase text-neutral-500 bg-[#0d0d0d]">
          <div className="col-span-1">Pri</div>
          <div className="col-span-4">Title</div>
          <div className="col-span-2">Status</div>
          <div className="col-span-2">Assignee</div>
          <div className="col-span-1">Updates</div>
          <div className="col-span-2 text-right">Created</div>
        </div>
        {incidents.length === 0 && (
          <div className="px-4 py-12 text-center text-xs text-neutral-500 tracking-wider uppercase">
            // No incidents in this view
          </div>
        )}
        {incidents.map(inc => (
          <Link
            to={`/incidents/${inc.id}`}
            key={inc.id}
            data-testid={`incident-row-${inc.id}`}
            className="grid grid-cols-12 px-4 py-3 border-b border-[#161616] hover:bg-[#101010] last:border-b-0">
            <div className="col-span-1"><PriorityBadge priority={inc.priority} /></div>
            <div className="col-span-4 text-sm text-neutral-100 truncate pr-2">{inc.title}</div>
            <div className="col-span-2"><StatusPill status={inc.status} /></div>
            <div className="col-span-2 text-[11px] text-neutral-400 truncate">
              {inc.assignee || <span className="text-neutral-600">— unassigned —</span>}
              {inc.assignee === user?.email && <span className="ml-1 text-[#D4AF37]">★</span>}
            </div>
            <div className="col-span-1 text-[10px] text-neutral-500">{inc.updates?.length || 0}</div>
            <div className="col-span-2 text-[10px] text-neutral-500 text-right">{relTime(inc.created_at)}</div>
          </Link>
        ))}
      </div>
    </div>
  );
}
