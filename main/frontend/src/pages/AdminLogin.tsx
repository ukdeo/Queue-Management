import { useState, useEffect } from 'react';
import { adminAPI } from '../services/api';
import { ShieldAlert, ArrowLeft, Lock, Loader, ShieldCheck } from 'lucide-react';

interface AdminLoginProps {
  onSuccess: () => void;
  onBack: () => void;
}

export default function AdminLogin({ onSuccess, onBack }: AdminLoginProps) {
  const [pin, setPin]         = useState('');
  const [adminPin, setAdminPin] = useState<string | null>(null);
  const [error, setError]     = useState(false);
  const [shake, setShake]     = useState(false);
  const [loadingPin, setLoadingPin] = useState(true);

  useEffect(() => {
    adminAPI.getCredentials()
      .then(res => setAdminPin(res.data.pin))
      .catch(() => setAdminPin('1234'))
      .finally(() => setLoadingPin(false));
  }, []);

  const handleDigit = (d: string) => {
    if (pin.length >= 4 || !adminPin) return;
    const next = pin + d;
    setPin(next);
    setError(false);
    if (next.length === 4) {
      setTimeout(() => {
        if (next === adminPin) {
          onSuccess();
        } else {
          setError(true);
          setShake(true);
          setTimeout(() => { setShake(false); setPin(''); }, 600);
        }
      }, 150);
    }
  };

  const handleDelete = () => {
    if (pin.length === 0) return;
    setPin(prev => prev.slice(0, -1));
    setError(false);
  };

  const keys = ['1','2','3','4','5','6','7','8','9','','0','⌫'];

  return (
    <div className="min-h-screen flex flex-col items-center justify-center p-6 relative overflow-hidden">
      {/* Background */}
      <div className="fixed inset-0 -z-10 bg-[#0a0f1e]">
        <div className="absolute top-0 left-1/3 w-[500px] h-[350px] bg-blue-600/5 rounded-full blur-[100px]" />
        <div className="absolute bottom-0 right-1/3 w-[400px] h-[300px] bg-violet-600/5 rounded-full blur-[100px]" />
      </div>

      {/* Back button */}
      <button
        onClick={onBack}
        className="absolute top-6 left-6 flex items-center gap-2 text-slate-400 hover:text-white transition-colors bg-white/[0.04] hover:bg-white/[0.07] px-4 py-2 rounded-xl border border-white/[0.07] text-sm font-medium"
      >
        <ArrowLeft size={16} /> Home
      </button>

      <div className={`w-full max-w-sm animate-slide-up ${shake ? 'animate-shake' : ''}`}>
        {/* Header */}
        <div className="text-center mb-10">
          <div className={`w-20 h-20 rounded-2xl flex items-center justify-center mx-auto mb-6 border transition-all duration-500 ${
            error
              ? 'bg-red-500/10 border-red-500/25 shadow-lg shadow-red-500/10'
              : 'bg-white/[0.04] border-white/[0.08]'
          }`}>
            {loadingPin
              ? <Loader size={32} className="text-slate-500 animate-spin" />
              : error
                ? <ShieldAlert size={32} className="text-red-400" />
                : pin.length > 0
                  ? <Lock size={32} className="text-blue-400" />
                  : <ShieldCheck size={32} className="text-slate-400" />
            }
          </div>
          <h1 className="text-2xl font-bold text-white mb-1.5">Staff Access</h1>
          <p className="text-slate-500 text-sm">Enter your 4-digit PIN to continue</p>
        </div>

        {/* PIN Dots */}
        <div className="flex justify-center gap-5 mb-10">
          {[0,1,2,3].map(i => (
            <div
              key={i}
              className={`w-3.5 h-3.5 rounded-full transition-all duration-300 border-2 ${
                pin.length > i
                  ? error
                    ? 'bg-red-500 border-red-400 scale-110 shadow-md shadow-red-500/30'
                    : 'bg-blue-500 border-blue-400 scale-110 shadow-md shadow-blue-500/30'
                  : 'bg-transparent border-slate-700'
              }`}
            />
          ))}
        </div>

        {/* Numpad */}
        <div className="grid grid-cols-3 gap-3">
          {keys.map((key, i) => (
            <button
              key={i}
              id={key !== '' && key !== '⌫' ? `numpad-${key}` : key === '⌫' ? 'numpad-delete' : undefined}
              onClick={() => {
                if (key === '⌫') handleDelete();
                else if (key !== '') handleDigit(key);
              }}
              disabled={key === '' || loadingPin}
              className={`h-16 rounded-2xl text-xl font-bold transition-all duration-200 active:scale-95 ${
                key === ''
                  ? 'bg-transparent cursor-default pointer-events-none'
                  : key === '⌫'
                    ? 'bg-white/[0.03] hover:bg-white/[0.07] text-slate-400 border border-white/[0.06]'
                    : 'bg-white/[0.04] hover:bg-white/[0.08] text-white border border-white/[0.07] hover:border-blue-500/30'
              } disabled:opacity-30`}
            >
              {key}
            </button>
          ))}
        </div>

        {/* Error message */}
        {error && (
          <div className="mt-6 flex items-center justify-center gap-2 animate-slide-up">
            <span className="w-1.5 h-1.5 bg-red-500 rounded-full" />
            <p className="text-red-400 text-sm font-medium">Incorrect PIN. Try again.</p>
          </div>
        )}
      </div>
    </div>
  );
}
