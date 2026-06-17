import { ReactNode } from 'react';

interface StatsCardProps {
  label: string;
  value: string | number;
  colour?: string;
  icon: ReactNode;
  subtitle?: string;
}

export default function StatsCard({ label, value, icon, subtitle }: StatsCardProps) {
  return (
    <div className="rounded-2xl p-5 bg-white/[0.03] border border-white/[0.07] hover:border-white/[0.12] transition-all duration-200 group">
      <div className="flex items-center justify-between mb-4">
        <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">{label}</p>
        <div className="w-8 h-8 rounded-xl bg-white/[0.05] border border-white/[0.07] flex items-center justify-center group-hover:bg-blue-500/10 group-hover:border-blue-500/20 transition-all">
          {icon}
        </div>
      </div>
      <p className="text-3xl font-bold text-white tracking-tight leading-none">{value}</p>
      {subtitle && <p className="text-xs text-slate-500 font-medium mt-1.5">{subtitle}</p>}
    </div>
  );
}
