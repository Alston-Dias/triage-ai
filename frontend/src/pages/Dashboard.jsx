import React, { useEffect, useState, useCallback } from 'react';
import AlertFeed from '../components/AlertFeed';
import TriagePanel from '../components/TriagePanel';
import { fetchAlerts, runTriage, resolveAlerts, seedData, simulateAlert, ageAlerts } from '../lib/api';
import { Database, Zap as Lightning, Brain, Plus, Clock } from 'lucide-react';
import { toast, Toaster } from 'sonner';
import { useNavigate } from 'react-router-dom';

export default function Dashboard() {
  const [alerts, setAlerts] = useState([]);
  const [selected, setSelected] = useState(new Set());
  const [severityFilter, setSeverityFilter] = useState(new Set());
  const [triageResult, setTriageResult] = useState(null);
  const [triaging, setTriaging] = useState(false);
  const nav = useNavigate();

  const load = useCallback(async () => {
    try {
      const data = await fetchAlerts('active');
      setAlerts(data);
    } catch (e) { /* silent */ }
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 6000);
    return () => clearInterval(t);
  }, [load]);

  const toggleSelected = (id) => {
    setSelected(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const toggleFilter = (sev) => {
    setSeverityFilter(prev => {
      const next = new Set(prev);
      next.has(sev) ? next.delete(sev) : next.add(sev);
      return next;
    });
  };

  const handleTriage = async () => {
    if (selected.size === 0) { toast.error('Select at least one alert'); return; }
    setTriaging(true);
    setTriageResult(null);
    try {
      const r = await runTriage([...selected]);
      setTriageResult(r);
      toast.success(`Triage complete · ${r.priority} · click "View Incident" to track`, {
        action: { label: 'View Incident', onClick: () => nav(`/incidents/${r.incident_id}`) },
        duration: 8000,
      });
    } catch (e) {
      toast.error('Triage failed: ' + (e?.response?.data?.detail || e.message));
    } finally { setTriaging(false); }
  };

  const handleResolve = async () => {
    if (!triageResult) return;
    try {
      await resolveAlerts(triageResult.alert_ids);
      toast.success(`${triageResult.alert_ids.length} alerts resolved`);
      setTriageResult(null);
      setSelected(new Set());
      load();
    } catch (e) { toast.error('Resolve failed'); }
  };

  const handleSeed = async () => {
    await seedData();
    toast.success('Sample data loaded');
    setSelected(new Set());
    setTriageResult(null);
    load();
  };
  const handleSimulate = async () => { await simulateAlert(); toast.success('Alert simulated'); load(); };
  const handleAge = async () => {
    const r = await ageAlerts();
    toast.success(`Aged ${r.aged} alerts to 6 days old · banner will show shortly`);
    load();
  };

  return (
    <div className="h-[calc(100vh-3.5rem)] flex flex-col">
      <Toaster theme="dark" position="bottom-right" />
      <div className="border-b border-[#1f1f1f] px-6 py-4 flex items-center justify-between gap-4 flex-wrap">
        <div>
          <div className="text-[10px] tracking-[0.3em] text-neutral-500 uppercase">Mission Control</div>
          <h1 className="font-display text-3xl font-black tracking-tighter mt-1">LIVE ALERT TRIAGE</h1>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <button data-testid="seed-btn" onClick={handleSeed} className="flex items-center gap-2 px-3 py-2 border border-[#262626] hover:border-[#404040] text-[11px] tracking-[0.2em] uppercase text-neutral-300 transition-colors">
            <Database size={13} /> Seed Demo
          </button>
          <button data-testid="age-alerts-btn" onClick={handleAge} className="flex items-center gap-2 px-3 py-2 border border-[#262626] hover:border-[#404040] text-[11px] tracking-[0.2em] uppercase text-neutral-300 transition-colors">
            <Clock size={13} /> Age Alerts (Demo SLA)
          </button>
          <button data-testid="simulate-btn" onClick={handleSimulate} className="flex items-center gap-2 px-3 py-2 border border-[#262626] hover:border-[#404040] text-[11px] tracking-[0.2em] uppercase text-neutral-300 transition-colors">
            <Plus size={13} /> Simulate Alert
          </button>
          <button
            data-testid="run-triage-btn"
            onClick={handleTriage}
            disabled={selected.size === 0 || triaging}
            className="flex items-center gap-2 px-4 py-2 bg-[#D4AF37] text-black font-bold text-[11px] tracking-[0.2em] uppercase disabled:opacity-30 disabled:cursor-not-allowed hover:bg-[#e6c14d] transition-colors">
            <Brain size={13} /> Run AI Triage{selected.size > 0 ? ` (${selected.size})` : ''}
          </button>
        </div>
      </div>

      <div className="flex-1 grid grid-cols-1 lg:grid-cols-12 min-h-0">
        <section className="lg:col-span-7 border-r border-[#1f1f1f] flex flex-col min-h-0" data-testid="alert-feed-section">
          <div className="px-4 py-3 border-b border-[#1f1f1f] flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Lightning size={14} fill="#FF9F0A" color="#FF9F0A" />
              <span className="text-[11px] tracking-[0.25em] uppercase text-neutral-300">Incoming Signals</span>
              <span className="text-[10px] text-neutral-500 ml-2">{alerts.length} active</span>
            </div>
            <div className="flex items-center gap-2 text-[10px] text-neutral-500 tracking-widest uppercase">
              <span className="w-1.5 h-1.5 rounded-full bg-[#30D158] live-dot" />
              LIVE · 6s
            </div>
          </div>
          <AlertFeed alerts={alerts} selected={selected} onToggle={toggleSelected} severityFilter={severityFilter} onFilterChange={toggleFilter} />
        </section>
        <section className="lg:col-span-5 flex flex-col min-h-0 bg-[#080808]" data-testid="triage-panel-section">
          <TriagePanel result={triageResult} loading={triaging} onResolve={handleResolve} />
        </section>
      </div>
    </div>
  );
}
