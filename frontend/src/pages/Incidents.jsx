import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { fetchIncidents } from '../lib/api';
import { PriorityBadge, StatusPill } from '../components/Badges';
import { relTime } from '../lib/format';
import { useAuth } from '../lib/auth';
import { Inbox, Star } from 'lucide-react';

const TABS = [
  { key: 'mine', label: 'My Incidents' },
  { key: 'others', label: 'Other Incidents' },
  { key: 'all', label: 'All' },
];

export default function Incidents() {
  const { user } = useAuth();
  const [tab, setTab] = useState('mine');
  const [incidents, setIncidents] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    const scope = tab === 'all' ? null : tab;
    fetchIncidents(scope).then(d => { setIncidents(d); setLoading(false); });
  }, [tab]);

  return (
    <div className="px-8 py-6 max-w-[1400px]">
      <div className="mb-6">
        <div className="text-xs text-neutral-500 mb-1">Operations Log</div>
        <h2 className="font-display text-3xl font-black tracking-tight">Incident Register</h2>
      </div>

      <div className="flex items-center gap-1 mb-4">
        {TABS.map(t => (
          <button
            key={t.key}
            data-testid={`incidents-tab-${t.key}`}
            onClick={() => setTab(t.key)}
            className={`px-4 py-2 text-sm rounded-md font-medium transition-colors ${tab === t.key ? 'bg-[#D4AF37]/10 text-[#D4AF37] border border-[#D4AF37]/30' : 'text-neutral-400 hover:text-white hover:bg-[#121212] border border-transparent'}`}>
            {t.label}
          </button>
        ))}
      </div>

      <div className="rounded-xl border border-[#1f1f1f] overflow-hidden bg-[#0a0a0a]">
        <div className="grid grid-cols-12 px-5 py-3 border-b border-[#1f1f1f] text-xs text-neutral-500 bg-[#0d0d0d]">
          <div className="col-span-1">Priority</div>
          <div className="col-span-5">Title</div>
          <div className="col-span-2">Status</div>
          <div className="col-span-2">Assignee</div>
          <div className="col-span-1">Updates</div>
          <div className="col-span-1 text-right">Created</div>
        </div>
        {loading && (
          <div className="px-5 py-12 text-center text-sm text-neutral-500">Loading…</div>
        )}
        {!loading && incidents.length === 0 && (
          <div className="px-5 py-16 text-center text-neutral-500">
            <Inbox size={32} strokeWidth={1.5} className="mx-auto mb-3 opacity-40" />
            <div className="text-sm">No incidents in this view</div>
            <div className="text-xs text-neutral-600 mt-1">{tab === 'mine' ? "Pick one up from 'Other Incidents'" : 'Run a triage to create one'}</div>
          </div>
        )}
        {incidents.map(inc => (
          <Link
            to={`/incidents/${inc.id}`}
            key={inc.id}
            data-testid={`incident-row-${inc.id}`}
            className="grid grid-cols-12 items-center px-5 py-4 border-b border-[#161616] last:border-b-0 hover:bg-[#101010] transition-colors">
            <div className="col-span-1"><PriorityBadge priority={inc.priority} /></div>
            <div className="col-span-5 text-sm text-neutral-100 truncate pr-3 font-medium">{inc.title}</div>
            <div className="col-span-2"><StatusPill status={inc.status} /></div>
            <div className="col-span-2 text-xs text-neutral-300 truncate flex items-center gap-1.5">
              {inc.assignee ? (
                <>
                  <span className="truncate">{inc.assignee.split('@')[0]}</span>
                  {inc.assignee === user?.email && <Star size={11} fill="#D4AF37" color="#D4AF37" />}
                </>
              ) : <span className="text-neutral-600">Unassigned</span>}
            </div>
            <div className="col-span-1 text-xs text-neutral-500">{inc.updates?.length || 0}</div>
            <div className="col-span-1 text-xs text-neutral-500 text-right">{relTime(inc.created_at)}</div>
          </Link>
        ))}
      </div>
    </div>
  );
}
