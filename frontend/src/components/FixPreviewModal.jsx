import React, { useState, useEffect, useMemo } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from './ui/dialog';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { Loader2, Copy, Check, Wand2, ShieldAlert, ShieldCheck } from 'lucide-react';
import { generateSonarFix } from '../lib/api';
import { toast } from 'sonner';

/**
 * FixPreviewModal — opens from the IssueDetailSheet's "Generate AI Fix" button.
 *
 * On open, calls POST /api/sonarqube/issues/{key}/generate-fix and renders:
 *   • a unified-diff viewer (line-by-line, red/green)
 *   • the natural-language explanation
 *   • a confidence pill + safe-to-apply badge
 *   • Copy patch + Apply CTAs (Apply currently logs + copies; ready for git)
 *
 * Designed to be drop-in for a real LLM-backed implementation later — only the
 * `generateSonarFix` call changes; the UI contract stays.
 */
export default function FixPreviewModal({ open, onOpenChange, issue }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    if (!open || !issue?.key) return undefined;

    setLoading(true);
    setError(null);
    setData(null);
    setCopied(false);

    generateSonarFix(issue.key)
      .then((res) => {
        if (!cancelled) setData(res);
      })
      .catch((err) => {
        if (!cancelled) {
          const detail = err?.response?.data?.detail;
          setError(detail || 'Failed to generate fix proposal.');
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [open, issue?.key]);

  /**
   * Split the unified diff into renderable rows with a per-line "kind"
   * (header / hunk / add / remove / context) so we can colour them.
   */
  const rows = useMemo(() => {
    if (!data?.unified_diff) return [];
    return data.unified_diff.split('\n').map((line, idx) => {
      let kind = 'context';
      if (line.startsWith('---') || line.startsWith('+++')) kind = 'header';
      else if (line.startsWith('@@')) kind = 'hunk';
      else if (line.startsWith('+')) kind = 'add';
      else if (line.startsWith('-')) kind = 'remove';
      return { idx, line, kind };
    });
  }, [data]);

  const confidencePct = data ? Math.round((data.confidence || 0) * 100) : 0;
  const confidenceTone =
    confidencePct >= 80 ? 'emerald'
    : confidencePct >= 60 ? 'amber'
    : 'rose';

  const handleCopy = async () => {
    if (!data?.unified_diff) return;
    try {
      await navigator.clipboard.writeText(data.unified_diff);
      setCopied(true);
      toast.success('Patch copied to clipboard');
      setTimeout(() => setCopied(false), 1800);
    } catch {
      toast.error('Clipboard write failed');
    }
  };

  const handleApply = async () => {
    // Phase 1: copy to clipboard + log so users can verify the contract.
    // Phase 2 (future Emergent prompt): POST to a new /apply-fix endpoint that
    // writes a branch + opens a PR via the existing CICD integration layer.
    await handleCopy();
    // eslint-disable-next-line no-console
    console.info('[FixPreview] would apply patch for', issue?.key, '\n', data?.unified_diff);
    toast.message('Apply Fix (mock)', {
      description:
        'Patch copied. Wiring this to git/PR creation is the next step — see lib/api.js for the contract.',
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="sm:max-w-3xl max-h-[85vh] overflow-hidden flex flex-col p-0"
        data-testid="fix-preview-modal"
      >
        <DialogHeader className="px-6 pt-6 pb-3 border-b">
          <DialogTitle className="flex items-center gap-2">
            <Wand2 className="h-4 w-4 text-amber-500" />
            AI Fix Preview
            {data && (
              <Badge
                variant="outline"
                className="ml-2 capitalize"
                title={`Source: ${data.source}`}
              >
                {data.source}
              </Badge>
            )}
          </DialogTitle>
          {issue && (
            <p className="text-xs text-slate-500 mt-1">
              <code className="font-mono">{issue.rule || '—'}</code>
              {issue.component && (
                <>
                  {' · '}
                  <code className="font-mono">{issue.component}{issue.line ? `:${issue.line}` : ''}</code>
                </>
              )}
            </p>
          )}
        </DialogHeader>

        <div className="px-6 py-4 overflow-y-auto flex-1 space-y-4">
          {loading && (
            <div className="flex items-center gap-2 text-sm text-slate-500 py-10 justify-center">
              <Loader2 className="h-4 w-4 animate-spin" /> Generating fix proposal…
            </div>
          )}

          {error && (
            <div className="rounded-md border border-red-200 bg-red-50 text-red-700 text-sm px-3 py-2">
              {error}
            </div>
          )}

          {data && (
            <>
              <div className="flex flex-wrap items-center gap-2">
                <span
                  className={[
                    'inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-medium',
                    confidenceTone === 'emerald' && 'border-emerald-200 bg-emerald-50 text-emerald-700',
                    confidenceTone === 'amber' && 'border-amber-200 bg-amber-50 text-amber-800',
                    confidenceTone === 'rose' && 'border-rose-200 bg-rose-50 text-rose-700',
                  ].filter(Boolean).join(' ')}
                  data-testid="fix-confidence"
                >
                  Confidence: {confidencePct}%
                </span>
                <span
                  className={[
                    'inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-medium',
                    data.safe_to_apply
                      ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                      : 'border-amber-200 bg-amber-50 text-amber-800',
                  ].join(' ')}
                  data-testid="fix-safety"
                >
                  {data.safe_to_apply ? (
                    <ShieldCheck className="h-3.5 w-3.5" />
                  ) : (
                    <ShieldAlert className="h-3.5 w-3.5" />
                  )}
                  {data.safe_to_apply ? 'Safe to apply' : 'Review before apply'}
                </span>
                {data.language && (
                  <Badge variant="outline" className="capitalize">
                    {data.language}
                  </Badge>
                )}
              </div>

              {/* Diff viewer */}
              <div
                className="rounded-md border bg-slate-950 text-slate-100 overflow-x-auto"
                data-testid="fix-diff-viewer"
              >
                <pre className="text-xs font-mono leading-5 p-0 m-0">
                  {rows.map(({ idx, line, kind }) => (
                    <div
                      key={idx}
                      className={[
                        'px-3 whitespace-pre',
                        kind === 'header' && 'text-slate-400',
                        kind === 'hunk' && 'text-cyan-300 bg-slate-900',
                        kind === 'add' && 'bg-emerald-950/60 text-emerald-300',
                        kind === 'remove' && 'bg-rose-950/60 text-rose-300',
                        kind === 'context' && 'text-slate-300',
                      ].filter(Boolean).join(' ')}
                    >
                      {line || '\u00A0'}
                    </div>
                  ))}
                </pre>
              </div>

              {/* Explanation */}
              <div
                className="rounded-md border bg-white text-sm text-slate-700 whitespace-pre-wrap leading-relaxed px-3 py-2"
                data-testid="fix-explanation"
              >
                {data.explanation}
              </div>
            </>
          )}
        </div>

        <DialogFooter className="px-6 py-3 border-t flex flex-row items-center justify-between gap-2">
          <p className="text-[11px] text-slate-400">
            Apply currently copies the patch. Wiring to a real PR is the next step.
          </p>
          <div className="flex items-center gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={handleCopy}
              disabled={!data || loading}
              data-testid="fix-copy-button"
            >
              {copied ? <Check className="h-3.5 w-3.5 mr-1" /> : <Copy className="h-3.5 w-3.5 mr-1" />}
              {copied ? 'Copied' : 'Copy patch'}
            </Button>
            <Button
              type="button"
              size="sm"
              onClick={handleApply}
              disabled={!data || loading}
              data-testid="fix-apply-button"
              className="bg-amber-500 hover:bg-amber-600 text-white"
            >
              Apply Fix
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
