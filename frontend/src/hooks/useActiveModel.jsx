/**
 * useActiveModel — small hook + context that resolves the currently active
 * LLM (model name + provider) by calling GET /api/system/llm once on app
 * mount. Replaces the old hardcoded "claude-sonnet-4.5" strings scattered
 * across panels.
 *
 * Usage:
 *   <ActiveModelProvider>...</ActiveModelProvider>   // wrap App once
 *   const { model, provider } = useActiveModel();    // anywhere below
 */
import React, { createContext, useContext, useEffect, useState } from 'react';
import { fetchSystemLLM } from '@/lib/api';

const DEFAULTS = { model: 'gpt-5.2-CIO', provider: 'gateway', loading: true };

const ActiveModelContext = createContext(DEFAULTS);

export function ActiveModelProvider({ children }) {
  const [state, setState] = useState(DEFAULTS);

  useEffect(() => {
    let alive = true;
    fetchSystemLLM()
      .then((data) => {
        if (!alive) return;
        setState({
          model: data?.model || DEFAULTS.model,
          provider: data?.provider || DEFAULTS.provider,
          loading: false,
        });
      })
      .catch(() => {
        if (!alive) return;
        setState((s) => ({ ...s, loading: false }));
      });
    return () => { alive = false; };
  }, []);

  return (
    <ActiveModelContext.Provider value={state}>
      {children}
    </ActiveModelContext.Provider>
  );
}

export function useActiveModel() {
  return useContext(ActiveModelContext);
}
