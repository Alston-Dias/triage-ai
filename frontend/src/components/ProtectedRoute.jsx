import React from 'react';
import { Navigate } from 'react-router-dom';
import { useAuth } from '../lib/auth';

export default function ProtectedRoute({ children }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="min-h-screen bg-[#0A0A0A] flex items-center justify-center text-xs tracking-widest text-neutral-500 uppercase">// Authenticating...</div>;
  if (!user) return <Navigate to="/login" replace />;
  return children;
}
