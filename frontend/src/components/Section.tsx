import type { ReactNode } from 'react'

import type { PartStatus } from '../lib/analysis'

function Skeleton() {
  return (
    <div className="flex animate-pulse flex-col gap-2" aria-hidden>
      <div className="h-3 w-full rounded bg-stone-100 dark:bg-stone-800" />
      <div className="h-3 w-[85%] rounded bg-stone-100 dark:bg-stone-800" />
      <div className="h-3 w-[60%] rounded bg-stone-100 dark:bg-stone-800" />
    </div>
  )
}

interface Props {
  title: string
  status: PartStatus
  badge?: ReactNode
  children: ReactNode
}

export function Section({ title, status, badge, children }: Props) {
  const waiting = status.state === 'pending' || status.state === 'running'

  return (
    <section
      className={`rounded-2xl border bg-white p-5 shadow-sm transition-opacity dark:bg-stone-900 ${
        status.state === 'error'
          ? 'border-red-200 dark:border-red-900/60'
          : 'border-stone-200 dark:border-stone-800'
      } ${status.state === 'pending' ? 'opacity-55' : ''}`}
    >
      <header className="mb-3 flex items-center gap-2">
        <h2 className="text-base font-semibold tracking-tight">{title}</h2>
        {status.state === 'done' && badge}

        {status.state === 'running' && (
          <span className="flex items-center gap-1.5 text-xs text-indigo-500">
            <span className="h-1.5 w-1.5 animate-ping rounded-full bg-indigo-500" />
            분석 중
          </span>
        )}
        {status.state === 'pending' && <span className="text-xs text-stone-400">대기</span>}

        {status.state === 'done' && status.elapsedMs !== undefined && (
          <span className="ml-auto text-xs text-stone-300 dark:text-stone-600">
            {(status.elapsedMs / 1000).toFixed(1)}초{status.retried && ' · 재시도'}
          </span>
        )}
      </header>

      {status.state === 'error' ? (
        <p className="text-sm text-red-600 dark:text-red-400">{status.error}</p>
      ) : waiting ? (
        <Skeleton />
      ) : (
        children
      )}
    </section>
  )
}
