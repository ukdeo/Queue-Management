import { useState, useEffect, useRef } from 'react';
import { tokenAPI, queueAPI } from '../services/api';
import TokenBadge from '../components/TokenBadge';
import {
  ArrowLeft, Clock, Hash, Users, AlertCircle,
  ArrowRight, Brain, ShieldAlert, CheckCircle, User, Phone, ChevronDown,
  Calendar, Bell, Search, Smartphone,
  Zap, ArrowUpCircle
} from 'lucide-react';

interface UserPortalProps {
  orgId: string;
  defaultQueueId: string;
  onBack: () => void;
}

// Helper: get today's date in YYYY-MM-DD in Nepal Time (NPT = UTC+5:45)
const todayStr = () => {
  const d = new Date(new Date().toLocaleString('en-US', { timeZone: 'Asia/Kathmandu' }));
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
};

// Format YYYY-MM-DD to "Mon, Jun 11"
const formatDate = (iso: string) => {
  const d = new Date(iso + 'T00:00:00');
  return d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
};

export default function UserPortal({ orgId, defaultQueueId, onBack }: UserPortalProps) {
  const [name, setName]   = useState('');
  const [phone, setPhone] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError]    = useState('');
  const [token, setToken]    = useState<any>(null);
  const [showInsights, setShowInsights] = useState(false);
  const [cancelLoading, setCancelLoading] = useState(false);
  const [serviceDate, setServiceDate] = useState<string>(todayStr());
  const [queuePosition, setQueuePosition] = useState<number | null>(null);
  const [totalWaiting, setTotalWaiting]   = useState<number>(0);
  const [mlPrediction, setMlPrediction]   = useState<{ estimated_wait_minutes: number; source: string; current_waiting: number; is_ml_trained: boolean } | null>(null);
  const [queues, setQueues] = useState<any[]>([]);
  const [selectedQueueId, setSelectedQueueId] = useState<string>(defaultQueueId);
  const [userPriority, setUserPriority] = useState<number>(0);

  // Retrieve-ticket state
  const [showLookup, setShowLookup]     = useState(false);
  const [lookupPhone, setLookupPhone]   = useState('');
  const [lookupPin, setLookupPin]       = useState('');
  const [lookupLoading, setLookupLoading] = useState(false);
  const [lookupError, setLookupError]   = useState('');

  const notified1MinRef  = useRef(false);
  const notifiedCalledRef = useRef(false);

  // Fetch available queues
  useEffect(() => {
    const fetchQueues = async () => {
      try {
        const idToUse = orgId || localStorage.getItem('palo_org_id');
        if (!idToUse) return;
        const res = await queueAPI.list(idToUse, serviceDate);
        const activeQueues = res.data.filter((q: any) => q.active === 1);
        setQueues(activeQueues);
        if (activeQueues.length > 0 && (!selectedQueueId || !activeQueues.find((q: any) => q.id === selectedQueueId))) {
          setSelectedQueueId(activeQueues[0].id);
        }
      } catch {}
    };
    fetchQueues();
  }, [orgId, selectedQueueId, serviceDate]);

  // Restore an active token session
  useEffect(() => {
    const activeTokenId = localStorage.getItem('palo_active_token_id');
    if (activeTokenId) {
      tokenAPI.get(activeTokenId).then(res => {
        const t = res.data;
        if (t.state === 'waiting' || t.state === 'called' || t.state === 'serving') {
          setToken(t);
        } else {
          localStorage.removeItem('palo_active_token_id');
        }
      }).catch(() => localStorage.removeItem('palo_active_token_id'));
    }
  }, []);

  // Request browser notifications
  useEffect(() => {
    if ('Notification' in window && Notification.permission === 'default') {
      Notification.requestPermission();
    }
  }, []);

  // Live wait prediction (join form)
  useEffect(() => {
    if (token || !selectedQueueId) return;
    const fetchPrediction = async () => {
      try {
        const res = await queueAPI.predict(selectedQueueId);
        setMlPrediction(res.data);
      } catch {}
    };
    fetchPrediction();
    const interval = setInterval(fetchPrediction, 10000);
    return () => clearInterval(interval);
  }, [selectedQueueId, token]);

  // Live ticket refresh
  useEffect(() => {
    if (!token) return;
    const refresh = async () => {
      try {
        const [tRes, qRes, listRes] = await Promise.all([
          tokenAPI.get(token.id),
          queueAPI.getStats(selectedQueueId, serviceDate),
          tokenAPI.list(selectedQueueId, serviceDate),
        ]);
        setToken(tRes.data);
        setTotalWaiting(qRes.data.total_waiting);
        const waiting = listRes.data.tokens.filter((t: any) => t.state === 'waiting' || t.state === 'called' || t.state === 'serving');
        const pos = waiting.findIndex((t: any) => t.id === token.id);
        setQueuePosition(pos >= 0 ? pos + 1 : null);

        if ('Notification' in window && Notification.permission === 'granted') {
          if (tRes.data.state === 'called' && !notifiedCalledRef.current) {
            new Notification("It's your turn!", { body: 'Please proceed to the counter now.', requireInteraction: true });
            notifiedCalledRef.current = true;
          } else if (tRes.data.state === 'waiting' && tRes.data.estimated_wait_minutes < 1.0 && !notified1MinRef.current) {
            new Notification('Almost there!', { body: 'Less than a minute. Get ready!' });
            notified1MinRef.current = true;
          }
        }
      } catch {}
    };
    refresh();
    const t = setInterval(refresh, 5000);
    return () => clearInterval(t);
  }, [token?.id, selectedQueueId, serviceDate]);

  const handleLookup = async (e: React.FormEvent) => {
    e.preventDefault();
    setLookupLoading(true);
    setLookupError('');
    try {
      const res = await tokenAPI.lookup(lookupPhone.trim(), lookupPin.trim());
      const { token_id, secret_token } = res.data;
      // Restore session on this device
      localStorage.setItem(`token_secret_${token_id}`, secret_token);
      localStorage.setItem('palo_active_token_id', token_id);
      // Fetch and display full ticket
      const tRes = await tokenAPI.get(token_id);
      setToken(tRes.data);
      setShowLookup(false);
    } catch (err: any) {
      setLookupError(
        err.response?.data?.detail ||
        'Could not find a matching active ticket. Please check your phone number and PIN.'
      );
    } finally {
      setLookupLoading(false);
    }
  };

  const handleJoin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedQueueId) return;
    setLoading(true); setError('');
    try {
      const res = await tokenAPI.create(selectedQueueId, {
        name: name.trim() || undefined,
        phone: phone || undefined,
        service_date: serviceDate,
        priority_level: userPriority,
      });
      const newToken = res.data;
      if (newToken.secret_token) {
        localStorage.setItem(`token_secret_${newToken.id}`, newToken.secret_token);
      }
      localStorage.setItem('palo_active_token_id', newToken.id);
      setToken(newToken);
    } catch (err: any) {
      const msg = err.response?.data?.detail || 'Something went wrong. Please try again.';
      if (err.response?.status === 403 && msg.includes('paused')) {
        setError("Joining Paused: The administration has temporarily stopped issuing new tokens for this queue. Please try again later.");
      } else if (msg.includes('INVALID')) {
        setError('INVALID: Daily token limit reached. Please try again tomorrow.');
      } else {
        setError(msg);
      }
    } finally {
      setLoading(false);
    }
  };

  const isServing   = token?.state === 'serving' || token?.state === 'called';
  const isCompleted = token?.state === 'completed';
  const isCancelled = token?.state === 'cancelled';

  const handleExit = () => {
    if (isCompleted || isCancelled) {
      localStorage.removeItem('palo_active_token_id');
      setToken(null);
    }
    onBack();
  };

  const handleCancel = async () => {
    if (!token) return;
    if (!confirm('Cancel your queue ticket? This cannot be undone.')) return;
    setCancelLoading(true);
    try {
      const res = await tokenAPI.updateState(token.id, 'cancelled');
      setToken(res.data);
      localStorage.removeItem('palo_active_token_id');
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Failed to cancel ticket.');
    } finally {
      setCancelLoading(false);
    }
  };

  const handleConfirm = async () => {
    if (!token) return;
    try {
      const res = await tokenAPI.confirm(token.id);
      setToken(res.data);
    } catch (err: any) {
      alert(err.response?.data?.detail || 'Failed to confirm attendance.');
    }
  };

  /* ── TICKET TRACKING VIEW ─────────────────────────────────────────── */
  if (token) {
    // Parse service_date from token for display
    const tokenDate = token.service_date
      ? new Date(token.service_date).toLocaleDateString('en-US', { timeZone: 'Asia/Kathmandu', weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' })
      : '';

    return (
      <div className="min-h-screen text-slate-100 flex flex-col items-center justify-center p-5 relative overflow-hidden">
        <div className="fixed inset-0 -z-10 bg-[#0a0f1e]">
          <div className="absolute top-0 left-1/4 w-[500px] h-[350px] bg-blue-600/5 rounded-full blur-[100px]" />
          <div className="absolute bottom-0 right-1/4 w-[400px] h-[300px] bg-violet-600/5 rounded-full blur-[100px]" />
        </div>

        {/* Back button */}
        <button
          onClick={handleExit}
          className="absolute top-6 left-6 flex items-center gap-2 text-slate-400 hover:text-white transition-colors bg-white/[0.04] hover:bg-white/[0.07] px-4 py-2 rounded-xl border border-white/[0.07] text-sm font-medium"
        >
          <ArrowLeft size={16} /> {isCompleted || isCancelled ? 'Go Home' : 'Exit'}
        </button>

        <div className="relative z-10 w-full max-w-md animate-slide-up pt-16">
          {/* Header */}
          <div className="text-center mb-8">
            <h1 className="text-3xl font-bold text-white mb-1">Your Ticket</h1>
            <p className="text-slate-500 text-sm">Live status update</p>
          </div>

          {/* Main Ticket Card */}
          <div className={`rounded-2xl border p-8 mb-5 relative overflow-hidden ${
            isServing
              ? 'bg-emerald-500/5 border-emerald-500/25 shadow-lg shadow-emerald-500/10'
              : isCompleted || isCancelled
              ? 'bg-white/[0.02] border-white/[0.07]'
              : 'bg-white/[0.03] border-white/[0.08]'
          }`}>
            {!isCompleted && !isCancelled && (
              <div className="absolute inset-0 shimmer pointer-events-none opacity-30" />
            )}

            <div className="relative z-10 text-center">
              {/* Status Badge */}
              <div className={`inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-semibold mb-6 border ${
                isServing    ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/25' :
                isCompleted  ? 'bg-slate-500/10 text-slate-400 border-slate-500/25' :
                isCancelled  ? 'bg-red-500/10 text-red-400 border-red-500/25' :
                               'bg-blue-500/10 text-blue-400 border-blue-500/25'
              }`}>
                {isServing   && <><span className="w-2 h-2 bg-emerald-400 rounded-full animate-pulse" /> It's Your Turn!</>}
                {isCompleted && <><CheckCircle size={13} /> Service Completed</>}
                {isCancelled && 'Ticket Cancelled'}
                {!isServing && !isCompleted && !isCancelled && <><span className="w-2 h-2 bg-blue-400 rounded-full animate-pulse" /> Waiting in Queue</>}
              </div>

              {/* Token Number */}
              <div className="mb-5">
                <p className="text-xs text-slate-500 font-medium uppercase tracking-widest mb-3">Token Number</p>
                <div className="scale-110 origin-center inline-block">
                  <TokenBadge
                    number={token.number}
                    status={token.state === 'called' ? 'called' : token.state as any}
                    priority={token.priority_level}
                    size="lg"
                  />
                </div>
              </div>

              {/* Progress bar */}
              {!isCompleted && !isServing && !isCancelled && (
                <div className="h-1 w-24 bg-white/[0.05] rounded-full mx-auto overflow-hidden">
                  <div className="h-full bg-blue-500/50 w-1/3 shimmer" />
                </div>
              )}

              {/* Serving message */}
              {isServing && (
                <div className="mt-4 py-3 px-5 bg-emerald-500/10 border border-emerald-500/20 rounded-xl">
                  <p className="text-emerald-400 font-semibold text-sm">Please proceed to the counter now</p>
                </div>
              )}
            </div>
          </div>

          {/* Booking Details */}
          <div className="grid grid-cols-2 gap-3 mb-5">
            <div className="rounded-xl p-4 bg-white/[0.03] border border-white/[0.06] text-center">
              <div className="flex justify-center mb-2"><Calendar size={14} className="text-blue-400" /></div>
              <p className="text-xs text-slate-500 mt-0.5">Service Date</p>
              <p className="text-sm font-bold text-white mt-1 leading-tight">{tokenDate}</p>
            </div>
            {token.estimated_reporting_time && (
              <div className="rounded-xl p-4 bg-white/[0.03] border border-white/[0.06] text-center">
                <div className="flex justify-center mb-2"><Clock size={14} className="text-amber-400" /></div>
                <p className="text-xs text-slate-500 mt-0.5">Reported Time</p>
                <p className="text-xl font-bold text-amber-300 mt-1">{token.estimated_reporting_time}</p>
              </div>
            )}
          </div>

          {/* Verification PIN */}
          <div className="rounded-2xl p-6 mb-5 border border-white/[0.07] bg-white/[0.02] text-center">
            <p className="text-xs text-slate-500 font-medium uppercase tracking-widest mb-2">Verification Code</p>
            <p className="text-4xl font-bold text-white tracking-[0.2em] mb-1">{token.verification_pin}</p>
            <p className="text-xs text-slate-600">Show this code to the counter staff</p>
          </div>

          {/* Live Stats */}
          {!isCompleted && !isCancelled && (
            <div className="grid grid-cols-3 gap-3 mb-5">
              {[
                { icon: <Hash size={14} className="text-blue-400" />, value: queuePosition ?? '—', label: 'Your Position' },
                { icon: <Clock size={14} className="text-amber-400" />, value: (token.estimated_wait_minutes !== null && token.estimated_wait_minutes !== undefined) ? `${Math.round(token.estimated_wait_minutes)}m` : '0m', label: 'Est. Wait' },
                { icon: <Users size={14} className="text-purple-400" />, value: totalWaiting, label: 'In Queue' },
              ].map(stat => (
                <div key={stat.label} className="rounded-xl p-4 text-center bg-white/[0.03] border border-white/[0.06]">
                  <div className="flex justify-center mb-2">{stat.icon}</div>
                  <p className="text-xl font-bold text-white">{stat.value}</p>
                  <p className="text-xs text-slate-500 mt-0.5">{stat.label}</p>
                </div>
              ))}
            </div>
          )}

          {/* Insights Toggle */}
          {!isCompleted && !isCancelled && (
            <div className="mb-4">
              <button
                onClick={() => setShowInsights(!showInsights)}
                className="w-full flex items-center justify-between px-4 py-3 rounded-xl bg-white/[0.03] border border-white/[0.06] hover:bg-white/[0.05] transition-all text-sm text-slate-400 hover:text-slate-200"
              >
                <span className="font-medium">Ticket Details</span>
                <ChevronDown size={16} className={`transition-transform duration-300 ${showInsights ? 'rotate-180' : ''}`} />
              </button>

              {showInsights && (
                <div className="mt-2 p-5 rounded-xl bg-white/[0.02] border border-white/[0.06] space-y-4 animate-slide-up">
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <p className="text-xs text-slate-500 font-medium mb-1">Registered at</p>
                      <p className="text-sm font-semibold text-slate-200">
                        {new Date(token.joined_at).toLocaleTimeString('en-US', { timeZone: 'Asia/Kathmandu', hour: '2-digit', minute: '2-digit', hour12: true })}
                      </p>
                    </div>
                    {token.name && (
                      <div>
                        <p className="text-xs text-slate-500 font-medium mb-1">Name</p>
                        <p className="text-sm font-semibold text-slate-200">{token.name}</p>
                      </div>
                    )}
                    {token.phone && (
                      <div>
                        <p className="text-xs text-slate-500 font-medium mb-1">Phone</p>
                        <p className="text-sm font-semibold text-slate-200">{token.phone}</p>
                      </div>
                    )}
                    <div>
                      <p className="text-xs text-slate-500 font-medium mb-1">Status</p>
                      <p className="text-sm font-semibold text-slate-200 capitalize">{token.state}</p>
                    </div>
                  </div>

                  <div className="pt-3 border-t border-white/[0.05]">
                    <button
                      onClick={handleCancel}
                      disabled={cancelLoading}
                      className="w-full py-3 rounded-xl font-semibold text-sm bg-red-500/8 text-red-400 hover:bg-red-500 hover:text-white border border-red-500/20 transition-all flex justify-center items-center gap-2"
                    >
                      {cancelLoading
                        ? <><span className="w-4 h-4 border-2 border-red-400/30 border-t-red-400 rounded-full animate-spin" /> Cancelling...</>
                        : 'Cancel My Ticket'
                      }
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Return Home Button */}
          {(isCompleted || isCancelled) && (
            <button
              onClick={handleExit}
              className="w-full mt-2 py-3.5 rounded-xl font-semibold text-sm bg-gradient-to-r from-blue-600 to-violet-600 text-white hover:opacity-90 transition-opacity shadow-lg shadow-blue-500/20"
            >
              Return to Home
            </button>
          )}

          {/* Live sync indicator */}
          <div className="mt-8 flex items-center justify-center gap-2 opacity-40">
            <span className="live-dot" style={{ width: 6, height: 6 }} />
            <span className="text-slate-400 text-xs font-medium">Updating live</span>
          </div>
        </div>
      </div>
    );
  }

  /* ── JOIN FORM VIEW ────────────────────────────────────────────────── */
  return (
    <div className="min-h-screen text-slate-100 flex flex-col items-center justify-center p-5 relative overflow-hidden">
      <div className="fixed inset-0 -z-10 bg-[#0a0f1e]">
        <div className="absolute top-0 left-1/4 w-[500px] h-[350px] bg-blue-600/5 rounded-full blur-[100px]" />
        <div className="absolute bottom-0 right-1/4 w-[400px] h-[300px] bg-violet-600/5 rounded-full blur-[100px]" />
      </div>

      {/* Back */}
      <button
        onClick={onBack}
        className="absolute top-6 left-6 flex items-center gap-2 text-slate-400 hover:text-white transition-colors bg-white/[0.04] hover:bg-white/[0.07] px-4 py-2 rounded-xl border border-white/[0.07] text-sm font-medium"
      >
        <ArrowLeft size={16} /> Home
      </button>

      <div className="relative z-10 w-full max-w-md animate-slide-up">
        {/* Header */}
        <div className="text-center mb-10">
          <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-blue-500/20 to-violet-500/20 border border-blue-500/20 flex items-center justify-center mx-auto mb-5">
            <Users size={28} className="text-blue-400" />
          </div>
          <h1 className="text-3xl font-bold text-white mb-2">Join the Queue</h1>
          <p className="text-slate-400 text-sm">Fill in your details to get your token</p>
        </div>

        {/* Error */}
        {error && (
          <div className="flex items-start gap-3 bg-red-900/15 border border-red-500/20 p-4 rounded-xl text-red-300 text-sm mb-6 animate-slide-up">
            <AlertCircle size={18} className="shrink-0 text-red-400 mt-0.5" />
            <p>{error}</p>
          </div>
        )}



        {/* Live wait preview / Paused notice */}
        {mlPrediction && (
          <div className={`flex items-center justify-between px-5 py-4 rounded-2xl mb-6 border ${
            queues.find(q => q.id === selectedQueueId)?.is_accepting_tokens === 0
              ? 'bg-red-500/10 border-red-500/20 text-red-400'
              : 'bg-blue-500/5 border-blue-500/10 text-blue-400'
          }`}>
            <div className="flex items-center gap-2 text-sm">
              {queues.find(q => q.id === selectedQueueId)?.is_accepting_tokens === 0 
                ? <><ShieldAlert size={16} /><span className="font-bold">Joining is Paused</span></>
                : <><Brain size={16} /><span className="font-medium">Current estimated wait</span></>
              }
            </div>
            <span className="font-bold text-sm">
              {queues.find(q => q.id === selectedQueueId)?.is_accepting_tokens === 0
                ? 'Check back later'
                : mlPrediction.current_waiting === 0
                  ? 'No wait!'
                  : `~${Math.round(mlPrediction.estimated_wait_minutes)} min`
              }
            </span>
          </div>
        )}

        <form onSubmit={handleJoin} className="space-y-6" noValidate>
          {/* Department Selection */}
          {queues.length > 0 && (
            <div>
              <label className="label">Select Department <span className="text-red-400">*</span></label>
              <div className="grid grid-cols-1 gap-2.5 mt-1">
                {queues.map(q => {
                  const isPaused = q.is_accepting_tokens === 0;
                  const isSelected = selectedQueueId === q.id;
                  return (
                    <button
                      key={q.id}
                      type="button"
                      disabled={isPaused}
                      onClick={() => !isPaused && setSelectedQueueId(q.id)}
                      className={`w-full text-left px-4 py-3.5 rounded-xl border transition-all flex items-center gap-4 ${
                        isPaused
                          ? 'border-white/[0.05] bg-white/[0.01] opacity-50 cursor-not-allowed'
                          : isSelected
                          ? 'border-blue-500/40 bg-blue-500/10 ring-1 ring-blue-500/20'
                          : 'border-white/[0.08] bg-white/[0.03] hover:border-white/[0.15] hover:bg-white/[0.05] cursor-pointer'
                      }`}
                    >
                      <div className={`w-4 h-4 rounded-full border-2 flex items-center justify-center shrink-0 transition-all ${
                        isSelected ? 'border-blue-400 bg-blue-400' : 'border-slate-600'
                      }`}>
                        {isSelected && <div className="w-1.5 h-1.5 rounded-full bg-white" />}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <p className="text-sm font-semibold text-white truncate">{q.name}</p>
                          {isPaused && (
                            <span className="shrink-0 text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded bg-red-500/15 text-red-400 border border-red-500/20">Paused</span>
                          )}
                        </div>
                        {q.description && (
                          <p className="text-xs text-slate-500 mt-0.5 truncate">{q.description}</p>
                        )}
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {/* User-Nominated Priority */}
          <div>
            <label className="label">Triage / Priority <span className="text-slate-500">(Optional)</span></label>
            <div className="grid grid-cols-3 gap-2 mt-1">
              {[
                { label: 'Normal', value: 0, icon: <Clock size={14} />, color: 'text-blue-400' },
                { label: 'Urgent', value: 100, icon: <ArrowUpCircle size={14} />, color: 'text-amber-400' },
                { label: 'Critical', value: 1000, icon: <Zap size={14} />, color: 'text-red-500' },
              ].map(p => (
                <button
                  key={p.value}
                  type="button"
                  onClick={() => setUserPriority(p.value)}
                  className={`flex flex-col items-center justify-center p-3 rounded-xl border transition-all ${
                    userPriority === p.value
                      ? 'bg-white/[0.08] border-white/20 ring-1 ring-white/10'
                      : 'bg-white/[0.03] border-white/5 hover:bg-white/[0.05]'
                  }`}
                >
                  <div className={`mb-1 ${p.color}`}>{p.icon}</div>
                  <span className="text-[10px] font-bold uppercase tracking-wider">{p.label}</span>
                </button>
              ))}
            </div>
          </div>

          {/* Date Picker */}
          <div>
            <label className="label" htmlFor="input-date">
              Booking Date <span className="text-red-400">*</span>
            </label>
            <div className="relative">
              <Calendar size={16} className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-500 pointer-events-none" />
              <input
                id="input-date"
                type="date"
                required
                value={serviceDate}
                min={todayStr()}
                onChange={e => setServiceDate(e.target.value)}
                className="input-field pl-11"
                style={{ colorScheme: 'dark' }}
              />
            </div>
            {serviceDate && (
              <p className="text-xs text-blue-400 mt-1.5 ml-1 font-medium">
                📅 {formatDate(serviceDate)}
              </p>
            )}
          </div>

          {/* Name */}
          <div>
            <label className="label" htmlFor="input-name">
              Your Name <span className="text-red-400">*</span>
            </label>
            <div className="relative">
              <User size={16} className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-500" />
              <input
                id="input-name"
                type="text"
                required
                value={name}
                onChange={e => setName(e.target.value)}
                placeholder="e.g., Ram Prasad Sharma"
                className="input-field pl-11"
                autoComplete="name"
              />
            </div>
          </div>

          {/* Phone */}
          <div>
            <label className="label" htmlFor="input-phone">
              Phone Number <span className="text-red-400">*</span>
            </label>
            <div className="relative">
              <Phone size={16} className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-500" />
              <input
                id="input-phone"
                type="tel"
                required
                value={phone}
                onChange={e => setPhone(e.target.value)}
                placeholder="+977 98XXXXXXXX"
                className="input-field pl-11"
                autoComplete="tel"
              />
            </div>
            <p className="text-xs mt-1.5 ml-1">
              {phone.replace(/\D/g, '').length >= 7
                ? <span className="text-emerald-500">✓ We'll notify you when your turn is near.</span>
                : <span className="text-slate-600">We'll notify you when your turn is near.</span>}
            </p>
          </div>

          {/* Submit */}
          <button
            type="submit"
            id="btn-get-ticket"
            disabled={
              loading || 
              !name.trim() || 
              name.trim().length < 2 || 
              phone.replace(/\D/g, '').length < 7 || 
              !serviceDate ||
              !selectedQueueId ||
              queues.find(q => q.id === selectedQueueId)?.is_accepting_tokens === 0
            }
            className={`w-full btn-premium mt-2 h-14 text-base rounded-2xl shadow-xl transition-all ${
              queues.find(q => q.id === selectedQueueId)?.is_accepting_tokens === 0
                ? 'grayscale opacity-50 cursor-not-allowed shadow-none border-white/5'
                : 'shadow-blue-500/20'
            }`}
          >
            {loading ? (
              <><span className="w-5 h-5 border-2 border-white/25 border-t-white rounded-full animate-spin" /> Getting your ticket...</>
            ) : queues.find(q => q.id === selectedQueueId)?.is_accepting_tokens === 0 ? (
              <span className="flex items-center gap-2 opacity-60">Joining Paused <ShieldAlert size={18} /></span>
            ) : (
              <><span className="flex items-center gap-2">Get My Ticket <ArrowRight size={18} /></span></>
            )}
          </button>
        </form>

        {/* ── Retrieve my ticket ─────────────────────────────────────── */}
        <div className="mt-6">
          <button
            type="button"
            onClick={() => { setShowLookup(!showLookup); setLookupError(''); }}
            className="w-full flex items-center justify-between px-4 py-3 rounded-xl bg-white/[0.03] border border-white/[0.06] hover:bg-white/[0.05] transition-all text-sm text-slate-400 hover:text-slate-200"
          >
            <span className="flex items-center gap-2 font-medium">
              <Smartphone size={15} className="text-violet-400" />
              Already have a ticket? Retrieve it on this device
            </span>
            <ChevronDown size={16} className={`transition-transform duration-300 ${showLookup ? 'rotate-180' : ''}`} />
          </button>

          {showLookup && (
            <form
              onSubmit={handleLookup}
              className="mt-2 p-5 rounded-xl bg-white/[0.02] border border-white/[0.06] space-y-4 animate-slide-up"
            >
              <p className="text-xs text-slate-500 leading-relaxed">
                Enter the <span className="text-slate-300 font-semibold">phone number</span> and
                the <span className="text-slate-300 font-semibold">4-digit verification PIN</span> shown
                on your original ticket to restore your session here.
              </p>

              {lookupError && (
                <div className="flex items-start gap-3 bg-red-900/15 border border-red-500/20 p-3 rounded-xl text-red-300 text-xs">
                  <AlertCircle size={15} className="shrink-0 text-red-400 mt-0.5" />
                  <p>{lookupError}</p>
                </div>
              )}

              <div>
                <label className="label" htmlFor="lookup-phone">Registered Phone Number</label>
                <div className="relative">
                  <Phone size={15} className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-500" />
                  <input
                    id="lookup-phone"
                    type="tel"
                    required
                    value={lookupPhone}
                    onChange={e => setLookupPhone(e.target.value)}
                    placeholder="+977 98XXXXXXXX"
                    className="input-field pl-11"
                    autoComplete="tel"
                  />
                </div>
              </div>

              <div>
                <label className="label" htmlFor="lookup-pin">4-Digit Verification PIN</label>
                <div className="relative">
                  <Search size={15} className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-500" />
                  <input
                    id="lookup-pin"
                    type="text"
                    inputMode="numeric"
                    maxLength={4}
                    pattern="[0-9]{4}"
                    required
                    value={lookupPin}
                    onChange={e => setLookupPin(e.target.value.replace(/\D/g, ''))}
                    placeholder="e.g. 4829"
                    className="input-field pl-11 tracking-[0.3em] font-bold"
                  />
                </div>
              </div>

              <button
                type="submit"
                disabled={lookupLoading || lookupPhone.replace(/\D/g, '').length < 7 || lookupPin.length < 4}
                className="w-full py-3 rounded-xl font-semibold text-sm bg-gradient-to-r from-violet-600 to-blue-600 text-white hover:opacity-90 disabled:opacity-40 transition-all flex justify-center items-center gap-2"
              >
                {lookupLoading
                  ? <><span className="w-4 h-4 border-2 border-white/25 border-t-white rounded-full animate-spin" /> Searching...
                  </>
                  : <><Search size={15} /> Find My Ticket</>
                }
              </button>
            </form>
          )}
        </div>

        {/* Security note */}
        <div className="mt-8 flex items-center justify-center gap-2 opacity-50">
          <span className="live-dot" style={{ width: 6, height: 6 }} />
          <span className="text-xs text-slate-400 font-medium">Secure &amp; private</span>
        </div>
      </div>
    </div>
  );
}
