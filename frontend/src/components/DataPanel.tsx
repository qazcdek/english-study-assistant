import { useEffect, useState } from 'react'

import { getMyDataCounts, leaveService, purgeMyData } from '../lib/api'
import type { DeletionSummary } from '../lib/types'

interface Props {
  /** cloud 에서만 탈퇴가 있다. 로컬에는 지울 계정이 없다. */
  cloud: boolean
}

const LABELS: [keyof DeletionSummary, string][] = [
  ['analyses', '분석 기록'],
  ['practices', '작문 연습'],
  ['vocabulary', '단어장'],
]

/**
 * 내 데이터를 세어 보고 지우는 칸.
 *
 * **되돌릴 수 없으므로 두 번 눌러야 실행된다.** API 는 확인을 받지 않으므로
 * 그 몫이 여기에 있다 (03-api-spec.md).
 */
export function DataPanel({ cloud }: Props) {
  const [counts, setCounts] = useState<DeletionSummary | null>(null)
  const [armed, setArmed] = useState<'purge' | 'leave' | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    getMyDataCounts()
      .then(setCounts)
      .catch(() => setCounts(null))
  }, [])

  const total = counts ? LABELS.reduce((sum, [key]) => sum + counts[key], 0) : 0

  async function run(action: () => Promise<unknown>) {
    setBusy(true)
    try {
      await action()
      window.location.reload()
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex flex-col gap-2 text-xs">
      <p className="font-medium">내 데이터</p>

      {counts && (
        <dl className="flex flex-col gap-1">
          {LABELS.map(([key, label]) => (
            <div key={key} className="flex justify-between">
              <dt className="text-stone-400">{label}</dt>
              <dd>{counts[key]}건</dd>
            </div>
          ))}
        </dl>
      )}

      <button
        type="button"
        disabled={busy || total === 0}
        onClick={() => (armed === 'purge' ? run(purgeMyData) : setArmed('purge'))}
        className="rounded-lg border border-stone-200 py-1.5 transition hover:bg-stone-100 disabled:opacity-40 dark:border-stone-700 dark:hover:bg-stone-800"
      >
        {total === 0
          ? '지울 기록이 없습니다'
          : armed === 'purge'
            ? `정말 지웁니다 — ${total}건 (되돌릴 수 없음)`
            : '기록 전부 삭제'}
      </button>

      {cloud && (
        <button
          type="button"
          disabled={busy}
          onClick={() => (armed === 'leave' ? run(leaveService) : setArmed('leave'))}
          className="rounded-lg border border-red-200 py-1.5 text-red-700 transition hover:bg-red-50 disabled:opacity-40 dark:border-red-900 dark:text-red-400 dark:hover:bg-red-950"
        >
          {armed === 'leave' ? '정말 탈퇴합니다 — 계정과 기록 전부 삭제' : '탈퇴'}
        </button>
      )}

      {armed && (
        <p className="text-[11px] leading-relaxed text-stone-400">
          한 번 더 누르면 실행됩니다. 되돌릴 수 없습니다.
          {armed === 'leave' && ' 등록한 Gemini 키도 함께 지워집니다.'}
        </p>
      )}
    </div>
  )
}
