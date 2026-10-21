import type { Overview } from '../lib/types'

/** 값이 비면 줄 자체를 그리지 않는다. 옛 기록에는 없는 칸이 있다. */
function Row({ label, value }: { label: string; value: string }) {
  if (!value.trim()) return null
  return (
    <div className="flex items-baseline gap-3 py-1.5 text-sm">
      <span className="w-20 shrink-0 text-stone-400">{label}</span>
      <span className="font-medium">{value}</span>
    </div>
  )
}

export function OverviewCard({ overview }: { overview: Overview }) {
  return (
    <div>
      <div className="divide-y divide-stone-100 dark:divide-stone-800/60">
        <Row label="분야" value={overview.domain} />
        <Row label="톤" value={overview.tone} />
        <Row label="격식 수준" value={overview.formality} />
        <Row label="문체" value={overview.style} />
      </div>

      {overview.key_expressions.length > 0 && (
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <span className="text-xs text-stone-400">꼭 챙길 표현</span>
          {overview.key_expressions.map((e) => (
            <span
              key={e}
              className="rounded-lg bg-amber-100 px-2 py-0.5 font-mono text-xs font-medium text-amber-800 dark:bg-amber-950 dark:text-amber-300"
            >
              {e}
            </span>
          ))}
        </div>
      )}

      <p className="mt-4 rounded-xl bg-stone-50 p-3 text-sm leading-relaxed text-stone-600 dark:bg-stone-950 dark:text-stone-300">
        {overview.comment}
      </p>
    </div>
  )
}
