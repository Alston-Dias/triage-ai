import React, { useEffect, useRef, useState } from 'react';
import { fetchSonarIssueChat, sendSonarIssueChat } from '../lib/api';
import { Brain, Send, BookOpen, Wand2, Shuffle, FlaskConical, GitPullRequest } from 'lucide-react';

// 5 canonical quick actions for the enhanced Sonar Copilot.
// `intent` matches the backend SONAR_AI_INTENTS list; backend keeps the old
// codes (explain/suggest_fix/refactor/best_practices) accepted for back-compat.
const QUICK_INTENTS = [
  { id: 'explain_rule',    label: 'Explain Rule',     icon: BookOpen,        prompt: 'Explain the SonarQube rule behind this issue.' },
  { id: 'generate_fix',    label: 'Generate Fix',     icon: Wand2,           prompt: 'Generate a fix for this issue.' },
  { id: 'alternative_fix', label: 'Alternative Fix',  icon: Shuffle,         prompt: 'Suggest an alternative approach to fix this.' },
  { id: 'write_test',      label: 'Write Test',       icon: FlaskConical,    prompt: 'Write a regression test for this fix.' },
  { id: 'pr_description',  label: 'PR Description',   icon: GitPullRequest,  prompt: 'Draft a PR description for the fix.' },
];

export default function IssueAIChat({ issueKey }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const scrollerRef = useRef(null);

  useEffect(() => {
    if (!issueKey) return;
    setLoaded(false);
    fetchSonarIssueChat(issueKey)
      .then((d) => setMessages(d.messages || []))
      .catch(() => setMessages([]))
      .finally(() => setLoaded(true));
  }, [issueKey]);

  useEffect(() => {
    if (scrollerRef.current) scrollerRef.current.scrollTop = scrollerRef.current.scrollHeight;
  }, [messages, sending]);

  const send = async (text, intent) => {
    const t = (text || '').trim();
    if (!t || sending) return;
    setInput('');
    setMessages((prev) => [
      ...prev,
      { role: 'user', text: t, timestamp: new Date().toISOString() },
    ]);
    setSending(true);
    try {
      const r = await sendSonarIssueChat(issueKey, t, intent);
      setMessages((prev) => [...prev, r.assistant_message]);
    } catch {
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', text: '_(AI assistant unavailable — please retry)_', timestamp: new Date().toISOString() },
      ]);
    } finally {
      setSending(false);
    }
  };

  const submit = (e) => {
    e?.preventDefault?.();
    send(input);
  };

  return (
    <div
      className="flex flex-col rounded-lg border border-[#1f1f1f] bg-[#0a0a0a] overflow-hidden"
      data-testid="issue-ai-chat"
    >
      {/* Header */}
      <div className="px-4 py-3 border-b border-[#1f1f1f] flex items-center gap-2.5">
        <div className="w-7 h-7 rounded-md bg-[#D4AF37]/10 border border-[#D4AF37]/30 flex items-center justify-center">
          <Brain size={14} strokeWidth={1.75} color="#D4AF37" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-sm font-semibold text-white">AI Remediation Copilot</div>
          <div className="text-[11px] text-neutral-500">
            {loaded ? `${messages.length} messages` : 'loading…'} · mocked responses
          </div>
        </div>
      </div>

      {/* Quick intent chips */}
      <div className="px-3 py-2.5 border-b border-[#1f1f1f] flex flex-wrap gap-1.5" data-testid="issue-ai-quick-intents">
        {QUICK_INTENTS.map(({ id, label, icon: Icon, prompt }) => (
          <button
            key={id}
            type="button"
            data-testid={`issue-ai-intent-${id}`}
            disabled={sending}
            onClick={() => send(prompt, id)}
            className="inline-flex items-center gap-1.5 text-[11px] font-medium px-2.5 py-1 rounded-md border border-[#262626] hover:border-[#D4AF37]/40 hover:bg-[#D4AF37]/[0.05] text-neutral-300 hover:text-white disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            <Icon size={11} strokeWidth={1.75} />
            {label}
          </button>
        ))}
      </div>

      {/* Messages */}
      <div
        ref={scrollerRef}
        className="overflow-y-auto p-3 space-y-2.5 min-h-[180px] max-h-[360px]"
        data-testid="issue-ai-chat-messages"
      >
        {loaded && messages.length === 0 && (
          <div className="text-center text-xs text-neutral-500 py-8">
            <div className="text-neutral-400">Ask the AI about this issue</div>
            <div className="text-[11px] text-neutral-600 mt-1">Use a chip above or type a question.</div>
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div
              className={`max-w-[88%] text-xs leading-relaxed px-3 py-2 rounded-lg ${
                m.role === 'user'
                  ? 'bg-[#D4AF37]/10 border border-[#D4AF37]/30 text-neutral-100'
                  : 'bg-[#121212] border border-[#262626] text-neutral-200'
              }`}
              data-testid={`issue-ai-msg-${m.role}`}
            >
              <div className="text-[10px] text-neutral-500 mb-1 font-medium flex items-center gap-1.5">
                <span>{m.role === 'user' ? 'You' : 'AI Copilot'}</span>
                {m.intent && m.role === 'assistant' && (
                  <span className="px-1.5 py-0.5 rounded bg-[#D4AF37]/10 border border-[#D4AF37]/20 text-[#D4AF37] text-[9px] uppercase tracking-wider">
                    {m.intent.replace('_', ' ')}
                  </span>
                )}
              </div>
              <div className="whitespace-pre-wrap">{m.text}</div>
            </div>
          </div>
        ))}
        {sending && (
          <div className="flex justify-start">
            <div className="bg-[#121212] border border-[#262626] rounded-lg px-3 py-2">
              <div className="flex gap-1" data-testid="issue-ai-typing">
                {[0, 1, 2].map((i) => (
                  <span
                    key={i}
                    className="w-1.5 h-1.5 rounded-full bg-[#D4AF37]"
                    style={{ animation: `pulse-dot 1s ease-in-out ${i * 0.15}s infinite` }}
                  />
                ))}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Input */}
      <form onSubmit={submit} className="border-t border-[#1f1f1f] p-2.5 flex items-center gap-2">
        <input
          data-testid="issue-ai-chat-input"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask about this issue…"
          disabled={sending}
          className="flex-1 bg-[#0a0a0a] border border-[#262626] rounded-md focus:border-[#D4AF37] outline-none px-3 py-1.5 text-xs text-white disabled:opacity-50"
        />
        <button
          data-testid="issue-ai-chat-send"
          type="submit"
          disabled={sending || !input.trim()}
          className="bg-[#D4AF37] text-black font-semibold px-3 py-1.5 rounded-md disabled:opacity-30 disabled:cursor-not-allowed hover:bg-[#e6c14d] flex items-center gap-1.5 text-xs"
        >
          <Send size={12} strokeWidth={2} />
        </button>
      </form>
    </div>
  );
}
