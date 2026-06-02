const toneMap = {
  low: "border-emerald-500/40 bg-emerald-500/10 text-emerald-200",
  medium: "border-amber-500/40 bg-amber-500/10 text-amber-200",
  high: "border-orange-500/40 bg-orange-500/10 text-orange-200",
  critical: "border-red-500/40 bg-red-500/10 text-red-200",
  neutral: "border-slate-500/40 bg-slate-500/10 text-slate-200"
};

export function StatusPill({
  label,
  tone = "neutral"
}: {
  label: string;
  tone?: keyof typeof toneMap;
}) {
  return (
    <span className={`inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-medium ${toneMap[tone]}`}>
      {label}
    </span>
  );
}

