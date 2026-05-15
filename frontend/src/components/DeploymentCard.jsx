import React, { useState } from 'react';
import {
  Rocket, GitPullRequest, ExternalLink, Copy, ChevronDown, ChevronRight,
  Clock, FileCode, Undo2,
} from 'lucide-react';
import { toast } from 'sonner';

const CONF_STYLE = {
  high:   { color: '#30D158', bg: 'rgba(48,209,88,0.10)',  border: 'rgba(48,209,88,0.40)' },
  medium: { color: '#FF9F0A', bg: 'rgba(255,159,10,0.10)', border: 'rgba(255,159,10,0.40)' },
  low:    { color: '#FF3B30', bg: 'rgba(255,59,48,0.10)',  border: 'rgba(255,59,48,0.40)' },
};

function ConfidenceBadge({ label, score }) {
  const s = CONF_STYLE[label] || CONF_STYLE.low;
  return (
    <span
      data-testid={`confidence-badge-${label}`}
      className="text-[11px] uppercase tracking-wider font-bold px-2 py-1 rounded-md"
      style={{ color: s.color, background: s.bg, border: `1px solid ${s.border}` }}
    >
      {label} confidence · {Math.round(score * 100)}%
    </span>
  );
}

function Avatar({ url, name }) {
  if (url) {
    return (
      <img src={url} alt={name} className="w-6 h-6 rounded-full border border-[#262626]"
           onError={(e) => { e.target.style.display = 'none'; }} />
    );
  }
  const initials = (name || '?').split(' ').map(p => p[0]).join('').slice(0, 2).toUpperCase();
  return (
    <span className="w-6 h-6 rounded-full bg-[#D4AF37]/20 border border-[#D4AF37]/30 text-[10px] font-bold text-[#D4AF37] flex items-center justify-center">
      {initials}
    </span>
  );
}

export default function DeploymentCard({ deployment }) {
  const [expanded, setExpanded] = useState(false);
  if (!deployment) return null;

  const {
    service, version, deployed_by = {}, minutes_before_incident,
    confidence, confidence_label, changed_files = [], diff_summary,
    pr_title, pr_url, ci_run_url, rollback_command,
  } = deployment;

  const accent = CONF_STYLE[confidence_label] || CONF_STYLE.low;
  const topFiles = changed_files.slice(0, 3);
  const remaining = changed_files.length - topFiles.length;

  const copyRollback = () => {
    if (!rollback_command) return;
    navigator.clipboard.writeText(rollback_command).then(
      () => toast.success('Rollback command copied to clipboard'),
      () => toast.error('Clipboard copy failed'),
    );
  };

  return (
    <div
      data-testid="deployment-card"
      className="rounded-lg border-2 p-4 mb-4"
      style={{
        background: `linear-gradient(135deg, ${accent.bg}, transparent 70%)`,
        borderColor: accent.border,
      }}
    >
      {/* Header row */}
      <div className="flex items-center gap-2 flex-wrap mb-3">
        <div
          className="w-7 h-7 rounded-md flex items-center justify-center shrink-0"
          style={{ background: accent.bg, border: `1px solid ${accent.border}` }}
        >
          <Rocket size={14} strokeWidth={2} color={accent.color} />
        </div>
        <span
          className="text-[10px] uppercase tracking-widest font-bold"
          style={{ color: accent.color }}
        >
          Deployment Detected
        </span>
        <span className="ml-auto">
          <ConfidenceBadge label={confidence_label} score={confidence} />
        </span>
      </div>

      {/* Service + version + deployer + time */}
      <div className="flex items-center gap-2 flex-wrap mb-2">
        <span className="font-mono text-sm font-bold text-white">{service}</span>
        {version && (
          <span className="font-mono text-xs px-1.5 py-0.5 rounded bg-[#161616] text-neutral-300 border border-[#262626]">
            {version}
          </span>
        )}
        <span className="text-xs text-neutral-400">deployed by</span>
        <Avatar url={deployed_by.avatar_url} name={deployed_by.name || deployed_by.handle} />
        <span className="text-xs text-neutral-200 font-medium" data-testid="deployment-deployer">
          {deployed_by.name || deployed_by.handle || 'unknown'}
          {deployed_by.handle && deployed_by.name && (
            <span className="text-neutral-500"> @{deployed_by.handle}</span>
          )}
        </span>
        <span className="text-xs text-neutral-500 ml-auto flex items-center gap-1">
          <Clock size={11} strokeWidth={1.75} />
          {minutes_before_incident} min before first alert
        </span>
      </div>

      {/* PR title */}
      {pr_title && (
        <div className="flex items-start gap-1.5 mb-3">
          <GitPullRequest size={13} strokeWidth={1.75} className="text-neutral-500 mt-0.5 shrink-0" />
          <span className="text-xs text-neutral-300 leading-snug line-clamp-2 flex-1">{pr_title}</span>
        </div>
      )}

      {/* Changed files (top 3, click to expand) */}
      {topFiles.length > 0 && (
        <div className="mb-3">
          <button
            onClick={() => setExpanded(e => !e)}
            data-testid="toggle-diff"
            className="flex items-center gap-1 text-[11px] text-neutral-500 hover:text-neutral-300 mb-1.5 transition-colors"
          >
            {expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
            <FileCode size={11} strokeWidth={1.75} />
            Changed files ({changed_files.length})
            {remaining > 0 && !expanded && <span className="text-neutral-600">· top 3 of {changed_files.length}</span>}
          </button>
          <div className="flex flex-wrap gap-1.5">
            {(expanded ? changed_files : topFiles).map((f, i) => (
              <code
                key={i}
                onClick={() => navigator.clipboard.writeText(f).then(() => toast.success('Path copied'))}
                className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-black/40 border border-[#262626] text-neutral-300 hover:border-[#D4AF37]/40 hover:text-white cursor-pointer transition-colors"
                title="Click to copy path"
              >
                {f}
              </code>
            ))}
          </div>
          {expanded && diff_summary && (
            <pre
              data-testid="deployment-diff"
              className="mt-2 rounded-md bg-black/60 border border-[#1f1f1f] p-2.5 text-[11px] font-mono text-neutral-300 leading-relaxed overflow-x-auto max-h-48"
            >{diff_summary}</pre>
          )}
        </div>
      )}

      {/* Actions */}
      <div className="flex items-center gap-2 flex-wrap pt-2.5 border-t border-white/5">
        {rollback_command && (
          <button
            onClick={copyRollback}
            data-testid="rollback-btn"
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-semibold transition-colors"
            style={{ background: accent.color, color: '#000' }}
            title={rollback_command}
          >
            <Undo2 size={13} strokeWidth={2.25} /> Rollback
            <span className="text-[10px] font-mono opacity-70 ml-1 hidden sm:inline">
              ⌘ copy
            </span>
          </button>
        )}
        {pr_url && (
          <a
            href={pr_url} target="_blank" rel="noopener noreferrer"
            data-testid="deployment-pr-link"
            className="flex items-center gap-1 px-2.5 py-1.5 rounded-md border border-[#262626] hover:border-[#404040] text-xs text-neutral-300 hover:text-white transition-colors"
          >
            <GitPullRequest size={12} strokeWidth={1.75} /> View PR
            <ExternalLink size={10} className="opacity-60" />
          </a>
        )}
        {ci_run_url && (
          <a
            href={ci_run_url} target="_blank" rel="noopener noreferrer"
            data-testid="deployment-ci-link"
            className="flex items-center gap-1 px-2.5 py-1.5 rounded-md border border-[#262626] hover:border-[#404040] text-xs text-neutral-300 hover:text-white transition-colors"
          >
            <Rocket size={12} strokeWidth={1.75} /> CI Run
            <ExternalLink size={10} className="opacity-60" />
          </a>
        )}
        {rollback_command && (
          <button
            onClick={copyRollback}
            className="ml-auto flex items-center gap-1 text-[11px] text-neutral-500 hover:text-neutral-200 transition-colors"
            title="Copy command"
          >
            <Copy size={11} />
            <code className="font-mono">{rollback_command}</code>
          </button>
        )}
      </div>
    </div>
  );
}
