import React, { createContext, useContext, useEffect, useState } from 'react';
import { me as fetchMe } from './api';

const AuthContext = createContext({ user: null, loading: true, setUser: () => {}, logout: () => {} });

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem('triage_token');
    const cached = localStorage.getItem('triage_user');
    if (!token) { setLoading(false); return; }
    if (cached) { try { setUser(JSON.parse(cached)); } catch (_) {} }
    fetchMe()
      .then(u => { setUser(u); localStorage.setItem('triage_user', JSON.stringify(u)); })
      .catch(() => { localStorage.removeItem('triage_token'); localStorage.removeItem('triage_user'); setUser(null); })
      .finally(() => setLoading(false));
  }, []);

  const logout = () => {
    localStorage.removeItem('triage_token');
    localStorage.removeItem('triage_user');
    setUser(null);
    window.location.href = '/login';
  };

  return <AuthContext.Provider value={{ user, loading, setUser, logout }}>{children}</AuthContext.Provider>;
}

export const useAuth = () => useContext(AuthContext);
