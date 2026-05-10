import React, { useEffect, useRef, useState } from 'react';
import { fetchChat, sendChat } from '../lib/api';
import { Brain, Send } from 'lucide-react';

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
    <div className="flex flex-col h-full border border-[#1f1f1f] bg-[#0a0a0a]" data-testid="incident-chat">
      <div className="px-4 py-3 border-b border-[#1f1f1f] flex items-center gap-2">
        <Brain size={14} color="#D4AF37" />
        <span className="text-[11px] tracking-[0.25em] uppercase text-neutral-300">AI Copilot</span>
        <span className="ml-auto text-[10px] text-neutral-500 tracking-widest uppercase">{messages.length} msgs</span>
      </div>

      <div ref={scrollerRef} className="flex-1 overflow-auto p-4 space-y-3 min-h-[300px]">
        {messages.length === 0 && (
          <div className="text-center text-[11px] text-neutral-500 tracking-wider uppercase py-12">
            Ask the AI about this incident.<br />
            <span className="text-neutral-700">e.g. "What should I check first?"</span>
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[85%] text-xs leading-relaxed px-3 py-2 ${
              m.role === 'user'
                ? 'bg-[#D4AF37]/10 border border-[#D4AF37]/30 text-neutral-100'
                : 'bg-[#121212] border border-[#262626] text-neutral-200'
            }`}>
              <div className="text-[9px] tracking-[0.2em] uppercase mb-1 opacity-60">
                {m.role === 'user' ? 'You' : 'TriageAI'}
              </div>
              <div className="whitespace-pre-wrap font-mono">{m.text}</div>
            </div>
          </div>
        ))}
        {sending && (
          <div className="flex justify-start">
            <div className="bg-[#121212] border border-[#262626] px-3 py-2">
              <div className="flex gap-1">
                {[0,1,2].map(i => <span key={i} className="w-1 h-1 bg-[#D4AF37]" style={{animation:`pulse-dot 1s ease-in-out ${i*0.15}s infinite`}}/>)}
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
          placeholder={locked ? 'Chat locked · incident resolved' : 'Ask about this incident...'}
          disabled={locked || sending}
          className="flex-1 bg-[#0a0a0a] border border-[#262626] focus:border-[#D4AF37] outline-none px-3 py-2 text-xs font-mono text-white disabled:opacity-50"
        />
        <button
          data-testid="chat-send"
          type="submit"
          disabled={locked || sending || !input.trim()}
          className="bg-[#D4AF37] text-black font-bold px-3 py-2 disabled:opacity-30 disabled:cursor-not-allowed hover:bg-[#e6c14d] transition-colors flex items-center gap-1.5 text-[10px] tracking-[0.18em] uppercase">
          <Send size={12} /> Send
        </button>
      </form>
    </div>
  );
}
