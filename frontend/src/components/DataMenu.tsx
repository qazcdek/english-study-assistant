import { useState } from 'react'

import { DataPanel } from './DataPanel'

/**
 * 로컬 모드의 데이터 칸 입구.
 *
 * cloud 는 같은 내용을 `AccountBar` 안에 둔다 — 계정이 있으니 계정 메뉴에 있는 게 맞다.
 * 로컬에는 계정 메뉴가 없어서 머리말에 따로 둔다.
 */
export function DataMenu() {
  const [open, setOpen] = useState(false)

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="rounded-full border border-stone-200 px-3 py-1 text-xs transition hover:bg-stone-100 dark:border-stone-700 dark:hover:bg-stone-800"
      >
        내 데이터
      </button>

      {open && (
        <div className="absolute right-0 z-10 mt-2 w-[min(16rem,calc(100vw-2rem))] rounded-xl border border-stone-200 bg-white p-4 shadow-lg dark:border-stone-700 dark:bg-stone-900">
          <DataPanel cloud={false} />
        </div>
      )}
    </div>
  )
}
