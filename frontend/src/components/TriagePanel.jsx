import React from 'react';
import { PriorityBadge } from './Badges';
import DeploymentCard from './DeploymentCard';
import { useActiveModel } from '@/hooks/useActiveModel';
import { Brain, ShieldAlert, Wrench, Terminal, CheckCircle, Filter, Sparkles, Clock } from 'lucide-react';

const CONF_COLOR = { high: '#30D158', medium: '#D4AF37', low: '#71717A' };

export default function TriagePanel({ result, loading, onResolve }) {
  const { model } = useActiveModel();
  if (loading) {
    return (
      <div className="flex flex-col h-full">
        <PanelHeader status="analyzing" model={model} />
        <div className="flex-1 flex items-center justify-center px-8">
          <div className="text-center max-w-sm">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-[#D4AF37]/10 border border-[#D4AF37]/30 text-[11px] text-[#D4AF37] font-medium mb-4">
              <span className="w-1.5 h-1.5 rounded-full bg-[#D4AF37] live-dot" /> {model}
            </div>
            <h3 className="font-display text-2xl font-black tracking-tight">Correlating signals</h3>
            <p className="text-sm text-neutral-400 mt-2 leading-relaxed">
              Deduplicating, clustering by service, and generating root cause hypotheses
            </p>
            <div className="mt-8 flex justify-center gap-1">
              {[0,1,2,3,4].map(i => <span key={i} className="w-1 h-3 bg-[#D4AF37]/50 rounded-full" style={{animation: `pulse-dot 1s ease-in-out ${i*0.12}s infinite`}}/>)}
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (!result) {
    return (
      <div className="flex flex-col h-full">
        <PanelHeader status="idle" model={model} />
        <div className="flex-1 flex items-center justify-center text-center px-10">
          <div className="max-w-xs">
            <div className="w-14 h-14 mx-auto rounded-full bg-[#D4AF37]/10 border border-[#D4AF37]/20 flex items-center justify-center mb-4">
              <Sparkles size={24} strokeWidth={1.5} color="#D4AF37" />
            </div>
            <h3 className="font-display text-xl font-black tracking-tight">Ready to triage</h3>
            <p className="text-sm text-neutral-400 mt-2 leading-relaxed">
              Select one or more alerts and run AI triage. The engine will correlate them and produce a remediation playbook.
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full" data-testid="triage-result-panel">
      <PanelHeader status="complete" model={model} />

      <div className="flex-1 overflow-auto p-6 space-y-6">
        {/* F-01: Deployment card at the very top */}
        {result.deployments && result.deployments.length > 0 && (
          <div data-testid="deployment-card-wrapper">
            <DeploymentCard deployment={result.deployments[0]} />
            {result.deployments.length > 1 && (
              <div className="text-[11px] text-neutral-500 -mt-2 mb-2">
                + {result.deployments.length - 1} additional correlated deployment{result.deployments.length - 1 === 1 ? '' : 's'} (lower confidence)
              </div>
            )}
          </div>
        )}

        {/* Header card */}
        <div className="rounded-lg border border-[#D4AF37]/20 bg-gradient-to-br from-[#D4AF37]/[0.04] to-transparent p-5">
          <div className="flex items-start gap-3 flex-wrap">
            <PriorityBadge priority={result.priority} />
            <span className="text-xs px-2.5 py-1 rounded-md bg-[#161616] text-neutral-300 border border-[#262626]">{result.blast_radius}</span>
            <div className="ml-auto flex items-center gap-1.5 text-xs text-neutral-400">
              <Clock size={13} strokeWidth={1.75} /> ETA {result.mttr_estimate_minutes}m
            </div>
          </div>
          <p className="mt-4 text-sm text-neutral-200 leading-relaxed">{result.summary}</p>
          <div className="mt-4 flex flex-wrap gap-1.5">
            {result.affected_services.map(s => (
              <span key={s} className="text-xs px-2 py-0.5 rounded-md bg-[#161616] border border-[#2a2a2a] text-neutral-300 font-mono">{s}</span>
            ))}
          </div>
        </div>

        {/* Noise filter */}
        {result.noise_alert_ids?.length > 0 && (
          <Section title="Noise filter" icon={Filter} count={result.noise_alert_ids.length}>
            <div className="text-xs text-neutral-400 mb-2">Likely false-positives</div>
            <div className="flex flex-wrap gap-1.5">
              {result.noise_alert_ids.map(id => (
                <span key={id} className="text-xs px-2 py-1 rounded-md bg-[#0A84FF]/10 border border-[#0A84FF]/30 text-[#0A84FF] font-mono">{id}</span>
              ))}
            </div>
          </Section>
        )}

        {/* Root causes */}
        <Section title="Root cause hypotheses" icon={ShieldAlert} count={result.root_causes.length}>
          <div className="space-y-3">
            {result.root_causes.map((rc, idx) => (
              <div key={idx} data-testid={`root-cause-${rc.rank}`} className="rounded-lg border border-[#1f1f1f] bg-[#0d0d0d] p-4">
                <div className="flex items-center gap-2.5 flex-wrap">
                  <span className="inline-flex items-center justify-center w-6 h-6 rounded-md bg-[#D4AF37]/10 text-[#D4AF37] text-xs font-bold font-mono">{rc.rank}</span>
                  <span className="text-sm font-semibold text-white flex-1 min-w-0">{rc.hypothesis}</span>
                  <span className="text-[11px] px-2 py-0.5 rounded-md font-medium" style={{color: CONF_COLOR[rc.confidence] || '#71717A', background: `${CONF_COLOR[rc.confidence] || '#71717A'}15`, border: `1px solid ${CONF_COLOR[rc.confidence] || '#71717A'}40`}}>
                    {rc.confidence} confidence
                  </span>
                </div>
                <p className="mt-2.5 text-xs text-neutral-400 leading-relaxed">{rc.reasoning}</p>
                {rc.supporting_alert_ids?.length > 0 && (
                  <div className="mt-2.5 flex flex-wrap gap-1">
                    {rc.supporting_alert_ids.map(id => (
                      <span key={id} className="text-[10px] px-1.5 py-0.5 rounded border border-[#2a2a2a] text-neutral-500 font-mono">{id}</span>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </Section>

        {/* Remediation */}
        <Section title="Remediation playbook" icon={Wrench} count={result.remediation.length}>
          <div className="space-y-3">
            {result.remediation.map((s, i) => (
              <div key={i} data-testid={`remediation-step-${i}`} className="rounded-lg border border-[#1f1f1f] bg-[#0d0d0d] p-4">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-[11px] px-2 py-0.5 rounded-md font-medium" style={{color: phaseColor(s.phase), background: `${phaseColor(s.phase)}15`, border: `1px solid ${phaseColor(s.phase)}40`}}>
                    {s.phase}
                  </span>
                  <span className="text-xs text-neutral-500">Step {i+1}</span>
                </div>
                <div className="mt-2.5 text-sm text-neutral-100 leading-relaxed">{s.action}</div>
                {s.cli_command && (
                  <div className="mt-3 flex items-start gap-2 rounded-md bg-black/40 border border-[#1f1f1f] px-3 py-2 font-mono text-[12px] text-[#D4AF37] overflow-x-auto">
                    <Terminal size={13} strokeWidth={1.75} className="mt-0.5 shrink-0 text-neutral-500" />
                    <code className="whitespace-pre">{s.cli_command}</code>
                  </div>
                )}
              </div>
            ))}
          </div>
        </Section>
      </div>

      <div className="border-t border-[#1f1f1f] p-4">
        <button
          data-testid="resolve-incident-btn"
          onClick={onResolve}
          className="w-full flex items-center justify-center gap-2 bg-white text-black font-semibold text-sm py-3 rounded-lg hover:bg-neutral-200 hover-lift transition-colors">
          <CheckCircle size={16} strokeWidth={2} /> Resolve selected alerts
        </button>
      </div>
    </div>
  );
}

function PanelHeader({ status, model }) {
  const map = {
    idle:     { label: 'Idle', color: '#71717A' },
    analyzing:{ label: 'Analyzing…', color: '#D4AF37' },
    complete: { label: 'Complete', color: '#30D158' },
  };
  const m = map[status];
  return (
    <div className="px-6 py-4 border-b border-[#1f1f1f] flex items-center gap-2.5">
      <div className="w-8 h-8 rounded-md bg-[#D4AF37]/10 border border-[#D4AF37]/30 flex items-center justify-center">
        <Brain size={15} strokeWidth={1.75} color="#D4AF37" />
      </div>
      <div className="flex-1">
        <div className="text-sm font-semibold text-white">AI Triage Engine</div>
        <div className="text-[11px] text-neutral-500 font-mono" data-testid="triage-active-model">{model || 'AI gateway'}</div>
      </div>
      <span className="text-[11px] font-medium flex items-center gap-1.5" style={{ color: m.color }}>
        <span className="w-1.5 h-1.5 rounded-full" style={{ background: m.color }} />{m.label}
      </span>
    </div>
  );
}

function Section({ title, icon: Icon, count, children }) {
  return (
    <div>
      <div className="flex items-center gap-2 mb-3">
        <Icon size={14} strokeWidth={1.75} className="text-neutral-400" />
        <h3 className="text-sm font-semibold text-white">{title}</h3>
        {count !== undefined && <span className="text-xs text-neutral-500">· {count}</span>}
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
