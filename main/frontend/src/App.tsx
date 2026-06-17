import { useState, useEffect } from 'react';
import { healthAPI, organizationAPI, queueAPI } from './services/api';
import HomeView from './pages/HomeView';
import UserPortal from './pages/UserPortal';
import AdminLogin from './pages/AdminLogin';
import AdminDashboard from './pages/AdminDashboard';
import DisplayBoard from './pages/DisplayBoard';
import { Zap, RefreshCw, AlertTriangle } from 'lucide-react';

export type AppView = 'home' | 'user' | 'admin-login' | 'admin' | 'display';

export default function App() {
  const [view, setView] = useState<AppView>(() => {
    const params = new URLSearchParams(window.location.search);
    const v = params.get('view') as AppView;
    return v || 'home';
  });
  const [isHealthy, setIsHealthy] = useState(false);
  const [loading, setLoading]     = useState(true);
  const [queueId, setQueueId]     = useState<string | null>(() =>
    localStorage.getItem('palo_queue_id')
  );
  const [orgId, setOrgId] = useState<string | null>(() =>
    localStorage.getItem('palo_org_id')
  );

  useEffect(() => {
    const init = async () => {
      try {
        await healthAPI.check();
        setIsHealthy(true);

        let savedOrgId   = localStorage.getItem('palo_org_id');
        let savedQueueId = localStorage.getItem('palo_queue_id');

        try {
          const orgsRes = await organizationAPI.listAll();
          if (!orgsRes.data || orgsRes.data.length === 0) throw new Error('No organizations');

          const orgExists = savedOrgId && orgsRes.data.some((o: any) => o.id === savedOrgId);
          if (!orgExists) {
            savedOrgId = orgsRes.data[0].id;
            localStorage.setItem('palo_org_id', savedOrgId!);
            savedQueueId = null;
            localStorage.removeItem('palo_queue_id');
            localStorage.removeItem('palo_active_token_id');
          }

          if (!savedQueueId) {
            const qRes = await queueAPI.list(savedOrgId!);
            const queues = qRes.data;
            if (queues && queues.length > 0) {
              savedQueueId = queues[0].id;
              localStorage.setItem('palo_queue_id', savedQueueId!);
            } else {
              savedQueueId = null;
            }
          }
        } catch {
          savedQueueId = null;
        }

        if (savedOrgId)   setOrgId(savedOrgId);
        if (savedQueueId) setQueueId(savedQueueId);
      } catch {
        setIsHealthy(false);
      } finally {
        setLoading(false);
      }
    };
    init();
  }, []);

  const handleAdminLogout = () => {
    sessionStorage.removeItem('palo_admin');
    setView('home');
  };

  const handleAdminLoginSuccess = () => {
    sessionStorage.setItem('palo_admin', '1');
    setView('admin');
  };

  const handleQueueChange = (newQueueId: string) => {
    localStorage.setItem('palo_queue_id', newQueueId);
    setQueueId(newQueueId);
  };

  const handleReset = () => {
    localStorage.clear();
    sessionStorage.clear();
    setQueueId(null);
    setView('home');
    window.location.reload();
  };

  /* ── Loading Screen ────────────────────────────────────────────────── */
  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-[#0a0f1e]">
        <div className="text-center">
          <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-blue-500 to-violet-600 flex items-center justify-center mx-auto mb-5 shadow-xl shadow-blue-500/25">
            <Zap size={24} className="text-white" fill="white" />
          </div>
          <div className="w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin mx-auto mb-4" />
          <p className="text-slate-500 text-sm font-medium">Starting Pālo…</p>
        </div>
      </div>
    );
  }

  /* ── Backend Offline ───────────────────────────────────────────────── */
  if (!isHealthy) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-[#0a0f1e] p-6">
        <div className="w-full max-w-sm bg-[#111827] border border-red-500/20 rounded-2xl p-8 text-center shadow-2xl">
          <div className="w-14 h-14 rounded-2xl bg-red-500/10 border border-red-500/20 flex items-center justify-center mx-auto mb-5">
            <AlertTriangle size={24} className="text-red-400" />
          </div>
          <h2 className="text-xl font-bold text-white mb-2">Backend Offline</h2>
          <p className="text-slate-400 text-sm mb-6 leading-relaxed">
            Cannot reach the server at <code className="text-slate-300 text-xs">localhost:8000</code>. Please make sure the backend is running.
          </p>
          <button
            onClick={() => window.location.reload()}
            className="w-full btn-primary h-12 text-sm"
          >
            <RefreshCw size={16} /> Try Again
          </button>
        </div>
      </div>
    );
  }

  /* ── No Queue ──────────────────────────────────────────────────────── */
  if (!queueId) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-[#0a0f1e] p-6">
        <div className="w-full max-w-sm bg-[#111827] border border-amber-500/20 rounded-2xl p-8 text-center shadow-2xl">
          <div className="w-14 h-14 rounded-2xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center mx-auto mb-5">
            <AlertTriangle size={24} className="text-amber-400" />
          </div>
          <h2 className="text-xl font-bold text-white mb-2">No Queue Found</h2>
          <p className="text-slate-400 text-sm mb-6 leading-relaxed">
            The backend hasn't created any queues yet. Make sure the backend has fully started.
          </p>
          <button
            onClick={() => window.location.reload()}
            className="w-full btn-primary h-12 text-sm"
          >
            <RefreshCw size={16} /> Retry
          </button>
        </div>
      </div>
    );
  }

  const renderContent = () => {
    switch (view) {
      case 'home':
        return <HomeView orgId={orgId!} setView={setView} onReset={handleReset} onSelectQueue={handleQueueChange} />;
      case 'user':
        return <UserPortal orgId={orgId!} defaultQueueId={queueId!} onBack={() => setView('home')} />;
      case 'admin-login':
        return <AdminLogin onSuccess={handleAdminLoginSuccess} onBack={() => setView('home')} />;
      case 'admin':
        return <AdminDashboard queueId={queueId!} orgId={orgId!} onLogout={handleAdminLogout} onQueueChange={handleQueueChange} />;
      case 'display':
        return <DisplayBoard queueId={queueId!} onBack={() => setView('home')} />;
      default:
        return <HomeView orgId={orgId!} setView={setView} onReset={handleReset} onSelectQueue={handleQueueChange} />;
    }
  };

  return (
    <div className="relative min-h-screen bg-[#0a0f1e]">
      <div className="relative z-10 min-h-screen">
        {renderContent()}
      </div>
    </div>
  );
}
