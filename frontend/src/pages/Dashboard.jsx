import React, { useEffect, useState, useCallback } from 'react';
import AlertFeed from '../components/AlertFeed';
import TriagePanel from '../components/TriagePanel';
import { fetchAlerts, runTriage, resolveAlerts, seedData, simulateAlert, ageAlerts } from '../lib/api';
import { Database, Brain, Plus, Clock, ChevronDown } from 'lucide-react';
import { toast, Toaster } from 'sonner';
import { useNavigate } from 'react-router-dom';

export default function Dashboard() {
  const [alerts, setAlerts] = useState([]);
  const [selected, setSelected] = useState(new Set());
  const [severityFilter, setSeverityFilter] = useState(new Set());
  const [triageResult, setTriageResult] = useState(null);
  const [triaging, setTriaging] = useState(false);
  const [demoOpen, setDemoOpen] = useState(false);
  const nav = useNavigate();

  const load = useCallback(async () => {
    try { setAlerts(await fetchAlerts('active')); } catch (e) {}
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 6000);
    return () => clearInterval(t);
  }, [load]);

  const toggleSelected = (id) => setSelected(prev => {
    const next = new Set(prev);
    next.has(id) ? next.delete(id) : next.add(id);
    return next;
  });

  const toggleFilter = (sev) => setSeverityFilter(prev => {
    const next = new Set(prev);
    next.has(sev) ? next.delete(sev) : next.add(sev);
    return next;
  });

  const handleTriage = async () => {
    if (selected.size === 0) return toast.error('Select at least one alert');
    setTriaging(true);
    setTriageResult(null);
    try {
      const r = await runTriage([...selected]);
      setTriageResult(r);
      toast.success(`Triage complete · ${r.priority}`, {
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

  const handleSeed = async () => { await seedData(); toast.success('Sample data loaded'); setSelected(new Set()); setTriageResult(null); load(); setDemoOpen(false); };
  const handleSimulate = async () => { await simulateAlert(); toast.success('Alert simulated'); load(); setDemoOpen(false); };
  const handleAge = async () => { const r = await ageAlerts(); toast.success(`Aged ${r.aged} alerts`); load(); setDemoOpen(false); };

  return (
    <div className="h-[calc(100vh-4rem)] flex flex-col">
      <Toaster theme="dark" position="bottom-right" />
      {/* Top bar */}
      <div className="px-8 py-6 flex items-center justify-between gap-4 flex-wrap">
        <div>
          <div className="text-xs text-neutral-500 mb-1">Mission Control</div>
          <h2 className="font-display text-3xl font-black tracking-tight">Live Alert Triage</h2>
        </div>
        <div className="flex items-center gap-2">
          {/* Demo menu */}
          <div className="relative">
            <button onClick={() => setDemoOpen(o => !o)}
                    className="flex items-center gap-2 px-3.5 py-2 rounded-md border border-[#1f1f1f] hover:border-[#2a2a2a] text-sm text-neutral-300 transition-colors">
              <Database size={14} strokeWidth={1.75} /> Demo <ChevronDown size={13} />
            </button>
            {demoOpen && (
              <>
                <div className="fixed inset-0 z-10" onClick={() => setDemoOpen(false)} />
                <div className="absolute right-0 top-full mt-1.5 w-56 z-20 rounded-lg border border-[#1f1f1f] bg-[#0d0d0d] shadow-2xl py-1">
                  <button data-testid="seed-btn" onClick={handleSeed} className="w-full px-3 py-2 text-left text-sm hover:bg-[#161616] flex items-center gap-2 text-neutral-300">
                    <Database size={13} strokeWidth={1.75} /> Seed sample data
                  </button>
                  <button data-testid="simulate-btn" onClick={handleSimulate} className="w-full px-3 py-2 text-left text-sm hover:bg-[#161616] flex items-center gap-2 text-neutral-300">
                    <Plus size={13} strokeWidth={1.75} /> Simulate one alert
                  </button>
                  <button data-testid="age-alerts-btn" onClick={handleAge} className="w-full px-3 py-2 text-left text-sm hover:bg-[#161616] flex items-center gap-2 text-neutral-300">
                    <Clock size={13} strokeWidth={1.75} /> Age alerts (test SLA)
                  </button>
                </div>
              </>
            )}
          </div>
          <button
            data-testid="run-triage-btn"
            onClick={handleTriage}
            disabled={selected.size === 0 || triaging}
            className="flex items-center gap-2 px-4 py-2 rounded-md bg-[#D4AF37] text-black font-semibold text-sm disabled:opacity-30 disabled:cursor-not-allowed hover:bg-[#e6c14d] hover-lift transition-colors">
            <Brain size={15} strokeWidth={2} /> Run AI Triage {selected.size > 0 && <span className="px-1.5 py-0.5 rounded bg-black/20 text-xs">{selected.size}</span>}
          </button>
        </div>
      </div>

      {/* Split */}
      <div className="flex-1 grid grid-cols-1 lg:grid-cols-12 min-h-0 gap-0 px-8 pb-6">
        <section className="lg:col-span-7 flex flex-col min-h-0 rounded-l-xl border border-[#1f1f1f] bg-[#0a0a0a]" data-testid="alert-feed-section">
          <div className="px-6 py-4 border-b border-[#1f1f1f] flex items-center justify-between">
            <div>
              <h3 className="font-display font-bold text-base tracking-tight text-white">Incoming Signals</h3>
              <div className="text-xs text-neutral-500 mt-0.5">{alerts.length} active alerts</div>
            </div>
            <div className="flex items-center gap-1.5 text-xs text-neutral-500">
              <span className="w-1.5 h-1.5 rounded-full bg-[#30D158] live-dot" />
              Live · refreshes every 6s
            </div>
          </div>
          <AlertFeed alerts={alerts} selected={selected} onToggle={toggleSelected} severityFilter={severityFilter} onFilterChange={toggleFilter} />
        </section>
        <section className="lg:col-span-5 flex flex-col min-h-0 rounded-r-xl border border-l-0 border-[#1f1f1f] bg-[#080808]" data-testid="triage-panel-section">
          <TriagePanel result={triageResult} loading={triaging} onResolve={handleResolve} />
        </section>
      </div>
    </div>
  );
}
