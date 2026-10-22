import { useState } from 'react'

import type { AccountSettings, AppConfig } from '../lib/types'
import { DataPanel } from './DataPanel'
import { ModelPicker } from './ModelPicker'

/**
 * 로컬 모드의 설정 입구 — 모델 선택과 데이터 칸.
 *
 * cloud 는 같은 내용을 `AccountBar` 안에 둔다 — 계정이 있으니 계정 메뉴에 있는 게 맞다.
 * 로컬에는 계정 메뉴가 없어서 머리말에 따로 둔다.
 *
 * **모델 선택이 로컬에도 있어야 한다.** local 은 llama-server 와 cloud LLM 전부를
 * 고를 수 있다 (09 §3.2). 전에는 그 화면이 cloud 쪽에만 있어서 로컬에서는 고를 길이
 * 없었다 (M12-T4).
 */
export function DataMenu({
  config,
  settings,
  onSettingsChanged,
}: {
  config: AppConfig | null
  settings: AccountSettings | null
  onSettingsChanged: (settings: AccountSettings) => void
}) {
  const [open, setOpen] = useState(false)

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="rounded-full border border-stone-200 px-3 py-1 text-xs transition hover:bg-stone-100 dark:border-stone-700 dark:hover:bg-stone-800"
      >
        설정
      </button>

      {open && (
        <div className="absolute right-0 z-10 mt-2 w-[min(18rem,calc(100vw-2rem))] rounded-xl border border-stone-200 bg-white p-4 shadow-lg dark:border-stone-700 dark:bg-stone-900">
          {config && settings && (
            <div className="mb-3 border-b border-stone-100 pb-3 dark:border-stone-800">
              <ModelPicker
                config={config}
                settings={settings}
                onChanged={onSettingsChanged}
              />
            </div>
          )}
          <DataPanel cloud={false} />
        </div>
      )}
    </div>
  )
}
