import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

/**
 * MarkdownMessage
 * ---------------
 * Renders markdown text for chat-style surfaces (AI responses, user input)
 * with styling tuned for our dark, gold-accent theme.
 *
 * - Supports GitHub-Flavoured Markdown (tables, strikethrough, autolinks,
 *   task lists) via remark-gfm.
 * - Renders inline + fenced code with monospace + subtle bg contrast.
 * - All external links open in a new tab.
 * - Compact spacing so messages don't feel airy inside chat bubbles.
 * - Falls back gracefully if `text` is empty / non-string.
 */
export default function MarkdownMessage({ text, className = '' }) {
  const safe = typeof text === 'string' ? text : String(text ?? '');

  return (
    <div className={`md-msg ${className}`.trim()}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          // Open links in a new tab + safe rel
          a: ({ node, ...props }) => (
            <a
              {...props}
              target="_blank"
              rel="noopener noreferrer"
              className="text-[#D4AF37] underline underline-offset-2 hover:text-[#E5C158]"
            />
          ),
          // Inline + fenced code styling. react-markdown v9 no longer
          // passes `inline` — we detect a fenced block by the parent being
          // a <pre>; otherwise treat as inline.
          code: ({ node, className: cls, children, ...props }) => {
            const isFenced = node?.position?.start?.line !== node?.position?.end?.line
              || /language-/.test(cls || '');
            if (isFenced) {
              return (
                <code
                  {...props}
                  className={`block whitespace-pre-wrap break-words font-mono text-[12px] ${cls || ''}`.trim()}
                >
                  {children}
                </code>
              );
            }
            return (
              <code
                {...props}
                className="px-1 py-0.5 rounded bg-black/40 border border-white/10 font-mono text-[12px]"
              >
                {children}
              </code>
            );
          },
          pre: ({ node, children, ...props }) => (
            <pre
              {...props}
              className="my-2 p-3 rounded-md bg-black/50 border border-white/10 overflow-x-auto"
            >
              {children}
            </pre>
          ),
          p: ({ node, ...props }) => (
            <p {...props} className="my-1.5 first:mt-0 last:mb-0 whitespace-pre-wrap" />
          ),
          ul: ({ node, ...props }) => (
            <ul {...props} className="my-1.5 ml-5 list-disc space-y-0.5" />
          ),
          ol: ({ node, ...props }) => (
            <ol {...props} className="my-1.5 ml-5 list-decimal space-y-0.5" />
          ),
          li: ({ node, ...props }) => <li {...props} className="leading-snug" />,
          h1: ({ node, ...props }) => (
            <h1 {...props} className="mt-2 mb-1 text-base font-semibold text-white" />
          ),
          h2: ({ node, ...props }) => (
            <h2 {...props} className="mt-2 mb-1 text-sm font-semibold text-white" />
          ),
          h3: ({ node, ...props }) => (
            <h3 {...props} className="mt-1.5 mb-0.5 text-sm font-semibold text-neutral-100" />
          ),
          blockquote: ({ node, ...props }) => (
            <blockquote
              {...props}
              className="my-2 pl-3 border-l-2 border-[#D4AF37]/40 text-neutral-300 italic"
            />
          ),
          hr: () => <hr className="my-2 border-white/10" />,
          table: ({ node, ...props }) => (
            <div className="my-2 overflow-x-auto">
              <table {...props} className="text-xs border-collapse" />
            </div>
          ),
          th: ({ node, ...props }) => (
            <th
              {...props}
              className="border border-white/10 px-2 py-1 text-left font-semibold bg-white/5"
            />
          ),
          td: ({ node, ...props }) => (
            <td {...props} className="border border-white/10 px-2 py-1 align-top" />
          ),
          strong: ({ node, ...props }) => (
            <strong {...props} className="font-semibold text-white" />
          ),
          em: ({ node, ...props }) => <em {...props} className="italic" />,
        }}
      >
        {safe}
      </ReactMarkdown>
    </div>
  );
}
