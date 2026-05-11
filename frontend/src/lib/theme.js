import React, { createContext, useContext, useEffect, useState } from 'react';

const ThemeContext = createContext({ theme: 'dark', toggle: () => {} });

export function ThemeProvider({ children }) {
  const [theme, setTheme] = useState(() => localStorage.getItem('triage_theme') || 'dark');

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('triage_theme', theme);
  }, [theme]);

  const toggle = () => setTheme(t => t === 'dark' ? 'light' : 'dark');
  return <ThemeContext.Provider value={{ theme, toggle }}>{children}</ThemeContext.Provider>;
}
export const useTheme = () => useContext(ThemeContext);
