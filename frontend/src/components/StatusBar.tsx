import type { LlmHealth } from '../lib/types'

export function StatusBar({ health }: { health: LlmHealth | null }) {
  if (!health) {
    return <span className="text-xs text-stone-400">상태 확인 중…</span>
  }

  if (!health.reachable) {
    return (
      <span className="flex items-center gap-1.5 text-xs text-red-500" title={health.detail ?? ''}>
        <span className="h-2 w-2 rounded-full bg-red-500" />
        LLM 연결 안 됨 ({health.base_url})
      </span>
    )
  }

  return (
    <span className="flex items-center gap-1.5 text-xs text-emerald-600 dark:text-emerald-400">
      <span className="h-2 w-2 rounded-full bg-emerald-500" />
      {health.models[0] ?? '연결됨'}
    </span>
  )
}
