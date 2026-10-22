import { useState } from 'react'

import { ApiError, countDuplicates, tidyHistory } from '../lib/api'
import { ConfirmDialog } from './ConfirmDialog'

/**
 * 같은 문단의 분석 기록에서 **최신 하나만** 남긴다.
 *
 * **묻기 전에 몇 건인지 센다.** 지울 것이 없으면 묻지 않고 그대로 알려 준다 —
 * 물을 일이 없는데 물으면 다음에 진짜 물을 때 안 읽는다 (나의 표현 제외와 같은 규칙).
 *
 * 되돌릴 수 없는 일이라 확인은 여기서 받는다. API 는 묻지 않는다.
 */
export const TIDY_WARNING =
  '같은 영어 문단을 여러 번 분석한 경우, 중복된 내용의 분석 기록은 최신 기록만 남습니다. 정리하시겠습니까?'

export function TidyButton({ onTidied }: { onTidied: (removed: number) => void }) {
  const [asking, setAsking] = useState(false)
  const [busy, setBusy] = useState(false)

  async function ask() {
    if (busy) return
    setBusy(true)
    try {
      const { removed } = await countDuplicates()
      if (removed === 0) {
        onTidied(0)
        return
      }
      setAsking(true)
    } catch (e) {
      onTidied(e instanceof ApiError ? -1 : -1)
    } finally {
      setBusy(false)
    }
  }

  async function confirm() {
    setAsking(false)
    setBusy(true)
    try {
      const { removed } = await tidyHistory()
      onTidied(removed)
    } catch {
      onTidied(-1)
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <ConfirmDialog
        message={asking ? TIDY_WARNING : null}
        onCancel={() => setAsking(false)}
        onConfirm={() => void confirm()}
      />
      <button
        type="button"
        onClick={() => void ask()}
        disabled={busy}
        className="rounded-md px-1.5 py-0.5 text-[11px] text-stone-400 transition hover:bg-stone-100 hover:text-stone-600 disabled:opacity-50 dark:hover:bg-stone-800 dark:hover:text-stone-300"
      >
        기록 정리
      </button>
    </>
  )
}
