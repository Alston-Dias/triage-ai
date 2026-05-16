import React, { useEffect, useRef, useState } from 'react';
import { fetchChat, sendChat } from '../lib/api';
import { Brain, Send } from 'lucide-react';
import MarkdownMessage from './ui/MarkdownMessage';

export default function IncidentChat({ incidentId, locked }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const scrollerRef = useRef(null);

  useEffect(() => {
    if (!incidentId) return;
    fetchChat(incidentId).then(d => setMessages(d.messages || []));
  }, [incidentId]);

  useEffect(() => {
    if (scrollerRef.current) scrollerRef.current.scrollTop = scrollerRef.current.scrollHeight;
  }, [messages, sending]);

  const submit = async (e) => {
    e?.preventDefault?.();
    if (!input.trim() || sending || locked) return;
    const text = input.trim();
    setInput('');
    setMessages(prev => [...prev, { role: 'user', text, timestamp: new Date().toISOString() }]);
    setSending(true);
    try {
      const r = await sendChat(incidentId, text);
      setMessages(prev => [...prev, r.assistant_message]);
    } catch (err) {
      setMessages(prev => [...prev, { role: 'assistant', text: '_(error contacting AI)_', timestamp: new Date().toISOString() }]);
    } finally { setSending(false); }
  };

  return (
    <div className="flex flex-col h-full rounded-xl border border-[#1f1f1f] bg-[#0a0a0a] overflow-hidden" data-testid="incident-chat">
      <div className="px-4 py-3 border-b border-[#1f1f1f] flex items-center gap-2.5">
        <div className="w-7 h-7 rounded-md bg-[#D4AF37]/10 border border-[#D4AF37]/30 flex items-center justify-center">
          <Brain size={14} strokeWidth={1.75} color="#D4AF37" />
        </div>
        <div className="flex-1">
          <div className="text-sm font-semibold text-white">AI Copilot</div>
          <div className="text-[11px] text-neutral-500">{messages.length} messages</div>
        </div>
      </div>

      <div ref={scrollerRef} className="flex-1 overflow-auto p-4 space-y-3 min-h-[320px] max-h-[600px]">
        {messages.length === 0 && (
          <div className="text-center text-sm text-neutral-500 py-12">
            <div className="text-neutral-400">Ask the AI about this incident</div>
            <div className="text-xs text-neutral-600 mt-1">e.g. "What should I check first?"</div>
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[88%] text-sm leading-relaxed px-3.5 py-2.5 rounded-lg ${
              m.role === 'user'
                ? 'bg-[#D4AF37]/10 border border-[#D4AF37]/30 text-neutral-100'
                : 'bg-[#121212] border border-[#262626] text-neutral-200'
            }`}>
              <div className="text-[10px] text-neutral-500 mb-1 font-medium">
                {m.role === 'user' ? 'You' : 'TriageAI'}
              </div>
              <MarkdownMessage text={m.text} />
            </div>
          </div>
        ))}
        {sending && (
          <div className="flex justify-start">
            <div className="bg-[#121212] border border-[#262626] rounded-lg px-3 py-2.5">
              <div className="flex gap-1">
                {[0,1,2].map(i => <span key={i} className="w-1.5 h-1.5 rounded-full bg-[#D4AF37]" style={{animation: `pulse-dot 1s ease-in-out ${i*0.15}s infinite`}}/>)}
              </div>
            </div>
          </div>
        )}
      </div>

      <form onSubmit={submit} className="border-t border-[#1f1f1f] p-3 flex items-center gap-2">
        <input
          data-testid="chat-input"
          value={input}
          onChange={e=>setInput(e.target.value)}
          placeholder={locked ? 'Chat locked — incident resolved' : 'Ask about this incident…'}
          disabled={locked || sending}
          className="flex-1 bg-[#0a0a0a] border border-[#262626] rounded-md focus:border-[#D4AF37] outline-none px-3 py-2 text-sm text-white disabled:opacity-50"
        />
        <button
          data-testid="chat-send"
          type="submit"
          disabled={locked || sending || !input.trim()}
          className="bg-[#D4AF37] text-black font-semibold px-3.5 py-2 rounded-md disabled:opacity-30 disabled:cursor-not-allowed hover:bg-[#e6c14d] flex items-center gap-1.5 text-sm">
          <Send size={14} strokeWidth={2} />
        </button>
      </form>
    </div>
  );
}
