import { useState } from 'react'

import { logout, removeApiKey } from '../lib/api'
import type { Account, Usage } from '../lib/types'

interface Props {
  account: Account
  usage: Usage | null
  onChanged: (account: Account) => void
}

export function AccountBar({ account, usage, onChanged }: Props) {
  const [open, setOpen] = useState(false)

  const nearLimit =
    usage !== null && usage.analysis_limit > 0 && usage.analyses >= usage.analysis_limit * 0.8

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2 rounded-full border border-stone-200 py-1 pl-1 pr-3 text-xs transition hover:bg-stone-100 dark:border-stone-700 dark:hover:bg-stone-800"
      >
        {account.picture ? (
          <img src={account.picture} alt="" className="h-6 w-6 rounded-full" />
        ) : (
          <span className="flex h-6 w-6 items-center justify-center rounded-full bg-indigo-100 text-[10px] font-medium text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300">
            {account.name.slice(0, 1) || account.email.slice(0, 1)}
          </span>
        )}
        <span className="max-w-[9rem] truncate">{account.name || account.email}</span>
        {usage && (
          <span className={nearLimit ? 'text-amber-600 dark:text-amber-400' : 'text-stone-400'}>
            {usage.analyses}/{usage.analysis_limit}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 z-10 mt-2 w-72 rounded-xl border border-stone-200 bg-white p-4 shadow-lg dark:border-stone-700 dark:bg-stone-900">
          <p className="truncate text-sm font-medium">{account.name}</p>
          <p className="truncate text-xs text-stone-400">{account.email}</p>

          <dl className="mt-3 flex flex-col gap-1.5 border-t border-stone-100 pt-3 text-xs dark:border-stone-800">
            <div className="flex justify-between">
              <dt className="text-stone-400">API 키</dt>
              <dd className="font-mono">{account.api_key_hint || '없음'}</dd>
            </div>
            {usage && (
              <>
                <div className="flex justify-between">
                  <dt className="text-stone-400">오늘 분석</dt>
                  <dd>
                    {usage.analyses} / {usage.analysis_limit}
                  </dd>
                </div>
                <div className="flex justify-between">
                  <dt className="text-stone-400">오늘 작문 연습</dt>
                  <dd>
                    {usage.practices} / {usage.practice_limit}
                  </dd>
                </div>
              </>
            )}
          </dl>

          <p className="mt-3 text-[11px] leading-relaxed text-stone-400">
            이 한도는 이 서비스가 두는 안전장치입니다. 실제 호출은 회원님 Gemini 한도에서
            차감됩니다.
          </p>

          <div className="mt-3 flex gap-2 border-t border-stone-100 pt-3 dark:border-stone-800">
            <button
              type="button"
              onClick={async () => onChanged(await removeApiKey())}
              className="flex-1 rounded-lg border border-stone-200 py-1.5 text-xs transition hover:bg-stone-100 dark:border-stone-700 dark:hover:bg-stone-800"
            >
              키 삭제
            </button>
            <button
              type="button"
              onClick={async () => {
                await logout()
                window.location.reload()
              }}
              className="flex-1 rounded-lg border border-stone-200 py-1.5 text-xs transition hover:bg-stone-100 dark:border-stone-700 dark:hover:bg-stone-800"
            >
              로그아웃
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
