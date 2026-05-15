import React, { useEffect, useState } from 'react';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from './ui/sheet';
import { Badge } from './ui/badge';
import {
  fetchSonarIssue,
  claimSonarIssue,
  assignSonarIssue,
  updateSonarIssueStatus,
  listUsers,
  fetchSonarIssueComments,
  addSonarIssueComment,
} from '../lib/api';
import { useAuth } from '../lib/auth';
import {
  Code2, Bug, Shield, Sparkles, AlertTriangle, FileCode, Wand2,
  Hand, UserPlus, RefreshCw, CheckCircle2, Brain, MessageSquarePlus, Send,
} from 'lucide-react';
import { toast } from 'sonner';
import IssueAIChat from './IssueAIChat';
import FixPreviewModal from './FixPreviewModal';
import { severityBucket, BUCKET_BADGE_CLASS, BUCKET_LABEL } from '../lib/severity';

// Status flow now includes WONT_FIX so triagers can close non-actionable issues.
const STATUS_OPTIONS = ['OPEN', 'CLAIMED', 'IN_PROGRESS', 'FIXED', 'WONT_FIX'];

const TYPE_COLORS = {
  BUG: 'bg-red-500/10 text-red-400 border-red-500/30',
  VULNERABILITY: 'bg-orange-500/10 text-orange-400 border-orange-500/30',
  CODE_SMELL: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30',
  SECURITY_HOTSPOT: 'bg-blue-500/10 text-blue-400 border-blue-500/30',
};

const SEVERITY_COLORS = {
  BLOCKER: 'bg-red-600/20 text-red-300 border-red-600/40',
  CRITICAL: 'bg-orange-600/20 text-orange-300 border-orange-600/40',
  MAJOR: 'bg-yellow-600/20 text-yellow-300 border-yellow-600/40',
  MINOR: 'bg-blue-600/20 text-blue-300 border-blue-600/40',
  INFO: 'bg-neutral-600/20 text-neutral-300 border-neutral-600/40',
};

const STATUS_COLORS = {
  OPEN: 'bg-neutral-500/10 text-neutral-300 border-neutral-500/30',
  CLAIMED: 'bg-blue-500/10 text-blue-300 border-blue-500/30',
  IN_PROGRESS: 'bg-[#D4AF37]/15 text-[#D4AF37] border-[#D4AF37]/40',
  FIXED: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30',
  WONT_FIX: 'bg-slate-500/15 text-slate-300 border-slate-500/40',
};

const TYPE_ICONS = {
  BUG: Bug,
  VULNERABILITY: Shield,
  CODE_SMELL: Sparkles,
  SECURITY_HOTSPOT: AlertTriangle,
};

function Section({ title, icon: Icon, children }) {
  return (
    <section className="rounded-lg border border-[#1f1f1f] bg-[#0a0a0a] p-4">
      <div className="flex items-center gap-2 mb-3">
        {Icon && <Icon size={14} className="text-neutral-500" />}
        <h4 className="text-xs font-semibold uppercase tracking-wider text-neutral-400">{title}</h4>
      </div>
      {children}
    </section>
  );
}

function MetaRow({ label, children }) {
  return (
    <div className="flex items-start gap-3 py-2 border-b border-[#161616] last:border-b-0">
      <div className="w-28 shrink-0 text-xs text-neutral-500 pt-0.5">{label}</div>
      <div className="text-sm text-neutral-100 min-w-0 flex-1">{children}</div>
    </div>
  );
}

export default function IssueDetailSheet({ issueKey, open, onOpenChange, onChanged }) {
  const { user } = useAuth();
  const [issue, setIssue] = useState(null);
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(false);
  const [showAssignPicker, setShowAssignPicker] = useState(false);
  const [busyAction, setBusyAction] = useState(null);
  const [showAIChat, setShowAIChat] = useState(false);
  // F-02 additions
  const [comments, setComments] = useState([]);
  const [newComment, setNewComment] = useState('');
  const [commentBusy, setCommentBusy] = useState(false);
  const [fixOpen, setFixOpen] = useState(false);

  useEffect(() => {
    if (!open || !issueKey) return;
    setLoading(true);
    setShowAssignPicker(false);
    setShowAIChat(false);
    setFixOpen(false);
    setComments([]);
    setNewComment('');
    Promise.all([
      fetchSonarIssue(issueKey),
      listUsers().catch(() => []),
      fetchSonarIssueComments(issueKey).catch(() => ({ comments: [] })),
    ])
      .then(([data, u, c]) => {
        setIssue(data);
        setUsers(u);
        setComments(c?.comments || []);
      })
      .catch(() => toast.error('Failed to load issue detail'))
      .finally(() => setLoading(false));
  }, [open, issueKey]);

  const userByEmail = (em) => users.find((u) => u.email === em);
  const assigneeName = issue?.assignee ? (userByEmail(issue.assignee)?.name || issue.assignee) : null;
  const isAssignee = issue?.assignee === user?.email;

  const applyResult = (updated, successMsg) => {
    setIssue(updated);
    toast.success(successMsg);
    if (onChanged) onChanged(updated);
  };

  const handleClaim = async () => {
    try {
      setBusyAction('claim');
      const updated = await claimSonarIssue(issueKey);
      applyResult(updated, 'Issue claimed');
    } catch (e) {
      toast.error('Failed to claim issue');
    } finally {
      setBusyAction(null);
    }
  };

  const handleAssign = async (email) => {
    try {
      setBusyAction(`assign:${email}`);
      const updated = await assignSonarIssue(issueKey, email);
      setShowAssignPicker(false);
      applyResult(updated, `Assigned to ${userByEmail(email)?.name || email}`);
    } catch (e) {
      toast.error('Failed to assign issue');
    } finally {
      setBusyAction(null);
    }
  };

  const handleStatus = async (status) => {
    if (status === issue?.status) return;
    try {
      setBusyAction(`status:${status}`);
      const updated = await updateSonarIssueStatus(issueKey, status);
      applyResult(updated, `Status updated → ${status.replace('_', ' ')}`);
    } catch (e) {
      toast.error('Failed to update status');
    } finally {
      setBusyAction(null);
    }
  };

  const handleAddComment = async () => {
    const t = newComment.trim();
    if (!t || commentBusy) return;
    try {
      setCommentBusy(true);
      const created = await addSonarIssueComment(issueKey, t);
      setComments((prev) => [...prev, created]);
      setNewComment('');
    } catch (e) {
      toast.error('Failed to add comment');
    } finally {
      setCommentBusy(false);
    }
  };

  const TypeIcon = issue ? TYPE_ICONS[issue.type] || Code2 : Code2;

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        className="bg-[#0d0d0d] border-l border-[#1f1f1f] text-white w-full sm:max-w-xl overflow-y-auto p-0"
        data-testid="issue-detail-sheet"
      >
        <SheetHeader className="px-6 pt-6 pb-4 border-b border-[#1f1f1f]">
          <div className="flex items-center gap-2 flex-wrap">
            {issue && (
              <Badge className={`${TYPE_COLORS[issue.type] || TYPE_COLORS.CODE_SMELL} border text-[10px] font-semibold px-2 py-0.5`}>
                <TypeIcon size={11} className="inline mr-1" />
                {issue.type.replace('_', ' ')}
              </Badge>
            )}
            {issue && (
              <Badge className={`${SEVERITY_COLORS[issue.severity] || SEVERITY_COLORS.INFO} border text-[10px] font-semibold px-2 py-0.5`}>
                {issue.severity}
              </Badge>
            )}
            {issue && (() => {
              const b = severityBucket(issue.severity);
              return (
                <Badge
                  className={`${BUCKET_BADGE_CLASS[b]} border text-[10px] font-semibold px-2 py-0.5`}
                  data-testid="issue-bucket-badge"
                  title={`Simplified bucket — ${BUCKET_LABEL[b]}`}
                >
                  {BUCKET_LABEL[b]}
                </Badge>
              );
            })()}
            {issue && (
              <Badge
                className={`${STATUS_COLORS[issue.status] || STATUS_COLORS.OPEN} border text-[10px] font-bold px-2 py-0.5`}
                data-testid="issue-status-badge"
              >
                {issue.status?.replace('_', ' ')}
              </Badge>
            )}
            <span className="ml-auto text-[10px] font-mono text-neutral-600">{issueKey}</span>
          </div>
          <SheetTitle className="text-lg font-display font-bold text-white mt-3 leading-snug">
            {issue?.title || (loading ? 'Loading…' : 'Issue')}
          </SheetTitle>
        </SheetHeader>

        {loading && !issue && (
          <div className="px-6 py-10 text-sm text-neutral-500">Loading issue detail…</div>
        )}

        {issue && (
          <div className="px-6 py-5 space-y-4">
            {/* Action toolbar */}
            <div className="flex items-center gap-2 flex-wrap" data-testid="issue-actions">
              <button
                data-testid="issue-claim-btn"
                onClick={handleClaim}
                disabled={busyAction === 'claim' || isAssignee}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-[#D4AF37] text-black font-semibold text-xs hover:bg-[#e6c14d] disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                <Hand size={12} strokeWidth={2.25} /> {isAssignee ? 'You own this' : 'Claim'}
              </button>
              <button
                data-testid="issue-assign-toggle"
                onClick={() => setShowAssignPicker((s) => !s)}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-[#262626] hover:border-[#404040] text-xs text-neutral-300 transition-colors"
              >
                <UserPlus size={12} strokeWidth={1.75} /> Assign…
              </button>
              <div className="ml-auto flex items-center gap-1" data-testid="issue-status-picker">
                {STATUS_OPTIONS.map((s) => {
                  const active = issue.status === s;
                  return (
                    <button
                      key={s}
                      data-testid={`issue-status-${s.toLowerCase()}`}
                      onClick={() => handleStatus(s)}
                      disabled={busyAction === `status:${s}` || active}
                      className={`text-[10px] font-semibold px-2 py-1 rounded-md border transition-colors ${
                        active
                          ? 'bg-[#D4AF37]/15 text-[#D4AF37] border-[#D4AF37]/40 cursor-default'
                          : 'border-[#262626] text-neutral-400 hover:border-[#D4AF37]/40 hover:text-white'
                      }`}
                    >
                      {s.replace('_', ' ')}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Assign picker */}
            {showAssignPicker && (
              <div className="flex flex-wrap gap-2 p-3 rounded-md border border-[#1f1f1f] bg-[#0a0a0a]" data-testid="issue-assign-picker">
                {users.length === 0 && (
                  <span className="text-xs text-neutral-500">No users available</span>
                )}
                {users.map((u) => (
                  <button
                    key={u.email}
                    data-testid={`issue-assign-${u.email.split('@')[0]}`}
                    onClick={() => handleAssign(u.email)}
                    disabled={busyAction === `assign:${u.email}` || issue.assignee === u.email}
                    className="text-xs px-3 py-1.5 rounded-md border border-[#262626] hover:border-[#D4AF37]/40 hover:bg-[#D4AF37]/[0.05] text-neutral-300 hover:text-white disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                  >
                    + {u.name}
                  </button>
                ))}
              </div>
            )}

            {/* Meta block */}
            <Section title="Details" icon={Code2}>
              <MetaRow label="Assignee">
                {issue.assignee ? (
                  <span className="inline-flex items-center gap-1.5">
                    <CheckCircle2 size={12} className="text-emerald-400" />
                    <span data-testid="issue-assignee-value">{assigneeName}</span>
                    <span className="text-neutral-500">· {issue.assignee}</span>
                  </span>
                ) : (
                  <span className="text-neutral-500" data-testid="issue-assignee-value">Unassigned</span>
                )}
              </MetaRow>
              <MetaRow label="File">
                <span className="font-mono text-xs text-neutral-200 break-all">{issue.component}</span>
                {issue.line && <span className="text-neutral-500 ml-2">: line {issue.line}</span>}
              </MetaRow>
              <MetaRow label="Rule">
                <span className="text-neutral-200">{issue.rule || '—'}</span>
              </MetaRow>
              <MetaRow label="Effort">{issue.effort || '—'}</MetaRow>
              <MetaRow label="Tags">
                {issue.tags?.length ? (
                  <div className="flex flex-wrap gap-1">
                    {issue.tags.map((t) => (
                      <span key={t} className="text-[10px] px-1.5 py-0.5 rounded bg-[#161616] border border-[#262626] text-neutral-400">
                        {t}
                      </span>
                    ))}
                  </div>
                ) : '—'}
              </MetaRow>
            </Section>

            {/* Description */}
            <Section title="Description" icon={FileCode}>
              <p className="text-sm text-neutral-200 leading-relaxed whitespace-pre-line" data-testid="issue-description">
                {issue.description || issue.message}
              </p>
            </Section>

            {/* Suggested fix */}
            <Section title="Suggested fix" icon={Wand2}>
              <pre
                data-testid="issue-suggested-fix"
                className="text-xs text-neutral-200 leading-relaxed bg-[#050505] border border-[#1f1f1f] rounded-md p-3 overflow-x-auto whitespace-pre-wrap"
              >
                {issue.suggestedFix || 'No fix suggestion available.'}
              </pre>
            </Section>

            {/* AI Remediation Copilot */}
            <div>
              <div className="flex gap-2 mb-0">
                <button
                  type="button"
                  data-testid="issue-ai-toggle"
                  onClick={() => setShowAIChat((s) => !s)}
                  aria-expanded={showAIChat}
                  className="flex-1 inline-flex items-center justify-between gap-2 px-4 py-2.5 rounded-md border border-[#D4AF37]/30 bg-[#D4AF37]/[0.06] hover:bg-[#D4AF37]/[0.12] text-[#D4AF37] text-xs font-semibold transition-colors"
                >
                  <span className="inline-flex items-center gap-2">
                    <Brain size={14} strokeWidth={1.75} />
                    AI Remediation Copilot
                  </span>
                  <span className="text-[10px] font-normal text-neutral-400">
                    {showAIChat ? 'Hide' : 'Open'}
                  </span>
                </button>
                <button
                  type="button"
                  data-testid="issue-generate-fix-btn"
                  onClick={() => setFixOpen(true)}
                  className="inline-flex items-center gap-1.5 px-3 py-2.5 rounded-md border border-amber-400/40 bg-amber-400/10 hover:bg-amber-400/20 text-amber-300 text-xs font-semibold transition-colors"
                  title="Generate an AI fix proposal with diff preview"
                >
                  <Wand2 size={14} strokeWidth={1.75} />
                  Generate AI Fix
                </button>
              </div>
              {showAIChat && (
                <div className="mt-3" data-testid="issue-ai-chat-wrap">
                  <IssueAIChat issueKey={issueKey} />
                </div>
              )}
            </div>

            {/* Comments thread */}
            <Section title={`Comments (${comments.length})`} icon={MessageSquarePlus}>
              <div className="space-y-2.5" data-testid="issue-comments">
                {comments.length === 0 && (
                  <p className="text-xs text-neutral-500">
                    No comments yet — add one below to start the thread.
                  </p>
                )}
                {comments.map((c) => (
                  <div
                    key={c.id}
                    className="rounded-md border border-[#1f1f1f] bg-[#050505] px-3 py-2"
                    data-testid="issue-comment-item"
                  >
                    <div className="flex items-center justify-between gap-2 mb-1">
                      <span className="text-[11px] font-semibold text-neutral-200">
                        {c.author_name || c.author_email}
                      </span>
                      <span className="text-[10px] text-neutral-600">
                        {c.created_at ? new Date(c.created_at).toLocaleString() : ''}
                      </span>
                    </div>
                    <p className="text-xs text-neutral-300 whitespace-pre-wrap">{c.text}</p>
                  </div>
                ))}
                <div className="flex items-center gap-2 pt-1">
                  <input
                    data-testid="issue-comment-input"
                    value={newComment}
                    onChange={(e) => setNewComment(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && !e.shiftKey) {
                        e.preventDefault();
                        handleAddComment();
                      }
                    }}
                    placeholder="Add a comment…"
                    disabled={commentBusy}
                    className="flex-1 bg-[#050505] border border-[#262626] rounded-md focus:border-[#D4AF37] outline-none px-3 py-1.5 text-xs text-white disabled:opacity-50"
                  />
                  <button
                    type="button"
                    data-testid="issue-comment-send"
                    onClick={handleAddComment}
                    disabled={commentBusy || !newComment.trim()}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-[#D4AF37] text-black font-semibold text-xs hover:bg-[#e6c14d] disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                  >
                    <Send size={12} strokeWidth={2} />
                    Post
                  </button>
                </div>
              </div>
            </Section>

            {loading && (
              <div className="flex items-center gap-2 text-xs text-neutral-500">
                <RefreshCw size={12} className="animate-spin" /> Refreshing…
              </div>
            )}
          </div>
        )}
      </SheetContent>
      <FixPreviewModal open={fixOpen} onOpenChange={setFixOpen} issue={issue} />
    </Sheet>
  );
}
