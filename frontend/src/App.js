import React from 'react';
import './App.css';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { AuthProvider } from './lib/auth';
import { ThemeProvider } from './lib/theme';
import ProtectedRoute from './components/ProtectedRoute';
import Layout from './components/Layout';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Incidents from './pages/Incidents';
import IncidentDetail from './pages/IncidentDetail';
import Analytics from './pages/Analytics';
import Settings from './pages/Settings';

function App() {
  return (
    <div className="App">
      <ThemeProvider>
        <AuthProvider>
          <BrowserRouter>
            <Routes>
              <Route path="/login" element={<Login />} />
              <Route path="/*" element={
                <ProtectedRoute>
                  <Layout>
                    <Routes>
                      <Route path="/" element={<Dashboard />} />
                      <Route path="/incidents" element={<Incidents />} />
                      <Route path="/incidents/:id" element={<IncidentDetail />} />
                      <Route path="/analytics" element={<Analytics />} />
                      <Route path="/settings" element={<Settings />} />
                    </Routes>
                  </Layout>
                </ProtectedRoute>
              } />
            </Routes>
          </BrowserRouter>
        </AuthProvider>
      </ThemeProvider>
    </div>
  );
}

export default App;
