import React from 'react';
import { PriorityBadge } from './Badges';
import { Brain, ShieldAlert as ShieldWarning, Wrench, Terminal, CheckCircle, Filter as Funnel, Sparkles as Sparkle, Clock } from 'lucide-react';

const CONF_COLOR = { high: '#30D158', medium: '#D4AF37', low: '#71717A' };

export default function TriagePanel({ result, loading, onResolve }) {
  if (loading) {
    return (
      <div className="flex flex-col h-full scanlines">
        <div className="border-b border-[#1f1f1f] px-5 py-4 flex items-center gap-2">
          <Brain size={18} color="#D4AF37" />
          <span className="text-[11px] tracking-[0.25em] uppercase text-neutral-300">AI Triage Engine</span>
          <span className="ml-auto text-[10px] text-[#D4AF37] tracking-widest cursor-blink">ANALYZING</span>
        </div>
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center max-w-sm">
            <div className="text-[10px] tracking-[0.3em] text-[#D4AF37] uppercase mb-2">claude-sonnet-4.5</div>
            <div className="font-display text-2xl font-black tracking-tighter">CORRELATING SIGNALS</div>
            <div className="text-xs text-neutral-500 mt-3 leading-relaxed">
              Deduplicating · Clustering by service · Temporal proximity · Generating root cause hypotheses
            </div>
            <div className="mt-6 flex justify-center gap-1">
              {[0,1,2,3,4].map(i => <span key={i} className="w-1 h-3 bg-[#D4AF37]/50" style={{animation: `pulse-dot 1s ease-in-out ${i*0.12}s infinite`}}/>)}
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (!result) {
    return (
      <div className="flex flex-col h-full scanlines">
        <div className="border-b border-[#1f1f1f] px-5 py-4 flex items-center gap-2">
          <Brain size={18} color="#D4AF37" />
          <span className="text-[11px] tracking-[0.25em] uppercase text-neutral-300">AI Triage Engine</span>
          <span className="ml-auto text-[10px] text-neutral-600 tracking-widest">IDLE</span>
        </div>
        <div className="flex-1 flex items-center justify-center text-center px-8">
          <div>
            <Sparkle size={28} color="#D4AF37" className="mx-auto mb-3" />
            <div className="font-display text-xl font-black tracking-tighter">AWAITING SIGNAL</div>
            <div className="text-xs text-neutral-500 mt-2 max-w-xs">
              Select alerts from the feed and run triage. The engine will correlate them, filter noise, and generate a remediation playbook.
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full scanlines" data-testid="triage-result-panel">
      <div className="border-b border-[#1f1f1f] px-5 py-4 flex items-center gap-2">
        <Brain size={18} color="#D4AF37" />
        <span className="text-[11px] tracking-[0.25em] uppercase text-neutral-300">AI Triage Result</span>
        <span className="ml-auto text-[10px] text-[#30D158] tracking-widest">COMPLETE</span>
      </div>

      <div className="flex-1 overflow-auto p-5 space-y-6">
        {/* Header */}
        <div className="border border-[#262626] bg-[#0e0e0e] p-4">
          <div className="flex items-start gap-3 flex-wrap">
            <PriorityBadge priority={result.priority} />
            <div className="text-[10px] tracking-[0.2em] uppercase text-neutral-500">{result.blast_radius}</div>
            <div className="ml-auto flex items-center gap-1 text-[10px] tracking-widest text-neutral-400 uppercase">
              <Clock size={11} /> ETA {result.mttr_estimate_minutes}m
            </div>
          </div>
          <div className="mt-3 text-sm text-neutral-200 leading-relaxed">{result.summary}</div>
          <div className="mt-3 flex flex-wrap gap-1.5">
            {result.affected_services.map(s => (
              <span key={s} className="text-[10px] tracking-wider px-2 py-0.5 bg-[#161616] border border-[#2a2a2a] text-neutral-300">{s}</span>
            ))}
          </div>
        </div>

        {/* Noise filter */}
        {result.noise_alert_ids?.length > 0 && (
          <Section title="Noise Filter" icon={Funnel} accent="#0A84FF">
            <div className="text-xs text-neutral-400 mb-2">{result.noise_alert_ids.length} alert(s) flagged as likely false-positives:</div>
            <div className="flex flex-wrap gap-1.5">
              {result.noise_alert_ids.map(id => (
                <span key={id} className="text-[10px] px-2 py-0.5 bg-[#0A84FF]/10 border border-[#0A84FF]/30 text-[#0A84FF] font-mono">{id}</span>
              ))}
            </div>
          </Section>
        )}

        {/* Root causes */}
        <Section title="Root Cause Hypotheses" icon={ShieldWarning} accent="#D4AF37">
          <div className="space-y-2">
            {result.root_causes.map((rc, idx) => (
              <div key={idx} data-testid={`root-cause-${rc.rank}`} className="border border-[#262626] bg-[#0d0d0d] p-3">
                <div className="flex items-center gap-2">
                  <span className="text-[11px] font-mono font-bold text-[#D4AF37]">#{rc.rank}</span>
                  <span className="text-sm font-medium text-white flex-1">{rc.hypothesis}</span>
                  <span className="text-[10px] tracking-[0.18em] uppercase font-mono" style={{color: CONF_COLOR[rc.confidence] || '#71717A'}}>
                    {rc.confidence} CONF
                  </span>
                </div>
                <div className="mt-2 text-xs text-neutral-400 leading-relaxed">{rc.reasoning}</div>
                {rc.supporting_alert_ids?.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1">
                    {rc.supporting_alert_ids.map(id => (
                      <span key={id} className="text-[9px] px-1.5 py-0.5 border border-[#2a2a2a] text-neutral-500 font-mono">{id}</span>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </Section>

        {/* Remediation */}
        <Section title="Remediation Playbook" icon={Wrench} accent="#30D158">
          <div className="space-y-2">
            {result.remediation.map((s, i) => (
              <div key={i} data-testid={`remediation-step-${i}`} className="border border-[#262626] bg-[#0d0d0d] p-3">
                <div className="flex items-center gap-2 text-[10px] tracking-[0.2em] uppercase">
                  <span className="px-1.5 py-0.5 border border-[#2a2a2a]" style={{color: phaseColor(s.phase)}}>{s.phase}</span>
                  <span className="text-neutral-500">STEP {i+1}</span>
                </div>
                <div className="mt-2 text-sm text-neutral-100">{s.action}</div>
                {s.cli_command && (
                  <div className="mt-2 flex items-start gap-2 bg-black border border-[#1f1f1f] p-2 font-mono text-[11px] text-[#D4AF37] overflow-x-auto">
                    <Terminal size={12} className="mt-0.5 shrink-0" />
                    <code className="whitespace-pre">{s.cli_command}</code>
                  </div>
                )}
              </div>
            ))}
          </div>
        </Section>
      </div>

      <div className="border-t border-[#1f1f1f] p-4 flex items-center gap-2">
        <button
          data-testid="resolve-incident-btn"
          onClick={onResolve}
          className="flex-1 flex items-center justify-center gap-2 bg-white text-black font-bold tracking-[0.18em] uppercase text-[11px] py-2.5 hover:bg-neutral-200 transition-colors">
          <CheckCircle size={14} /> Resolve Selected Alerts
        </button>
      </div>
    </div>
  );
}

function Section({ title, icon: Icon, accent, children }) {
  return (
    <div>
      <div className="flex items-center gap-2 mb-2">
        <Icon size={14} color={accent} />
        <h3 className="text-[10px] tracking-[0.25em] uppercase text-neutral-300 font-display font-bold">{title}</h3>
        <div className="flex-1 h-px bg-[#1f1f1f]" />
      </div>
      {children}
    </div>
  );
}

function phaseColor(p) {
  if (p === 'immediate') return '#FF3B30';
  if (p === 'short-term') return '#FF9F0A';
  return '#30D158';
}
