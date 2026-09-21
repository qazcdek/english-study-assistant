import { useState } from 'react'

import { ApiError, saveApiKey } from '../lib/api'
import type { Account, AppConfig } from '../lib/types'

interface Props {
  config: AppConfig
  onSaved: (account: Account) => void
}

export function ApiKeyPanel({ config, onSaved }: Props) {
  const [key, setKey] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function submit() {
    if (!key.trim() || busy) return
    setBusy(true)
    setError(null)
    try {
      onSaved(await saveApiKey(key.trim()))
    } catch (e) {
      setError(e instanceof ApiError ? e.message : '키를 저장하지 못했습니다.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="mx-auto max-w-2xl rounded-2xl border border-stone-200 bg-white p-6 shadow-sm dark:border-stone-800 dark:bg-stone-900">
      <h2 className="text-lg font-semibold tracking-tight">Gemini API 키 등록</h2>
      <p className="mt-2 text-sm leading-relaxed text-stone-500 dark:text-stone-400">
        Google AI Studio에서 키를 발급받아 붙여넣어 주세요. 무료 등급으로도 쓸 수 있습니다.
      </p>

      <ol className="mt-4 flex flex-col gap-1.5 text-sm text-stone-600 dark:text-stone-300">
        <li>
          1.{' '}
          <a
            href={config.api_key_issue_url}
            target="_blank"
            rel="noreferrer"
            className="text-indigo-600 underline underline-offset-2 dark:text-indigo-400"
          >
            aistudio.google.com/apikey
          </a>{' '}
          에서 <b>Create API key</b>
        </li>
        <li>2. 만들어진 키를 복사</li>
        <li>3. 아래에 붙여넣고 저장</li>
      </ol>

      <input
        type="password"
        value={key}
        onChange={(e) => setKey(e.target.value)}
        onKeyDown={(e) => e.key === 'Enter' && submit()}
        placeholder="AIza..."
        autoComplete="off"
        spellCheck={false}
        className="mt-5 w-full rounded-xl border border-stone-200 bg-stone-50 p-3 font-mono text-sm outline-none focus:border-indigo-400 focus:ring-2 focus:ring-indigo-200 dark:border-stone-700 dark:bg-stone-950 dark:focus:ring-indigo-900"
      />

      {error && <p className="mt-2 text-sm text-red-600 dark:text-red-400">{error}</p>}

      <button
        type="button"
        onClick={submit}
        disabled={!key.trim() || busy}
        className="mt-3 w-full rounded-xl bg-indigo-600 py-2.5 text-sm font-medium text-white transition hover:bg-indigo-500 disabled:bg-stone-300 dark:disabled:bg-stone-700"
      >
        {busy ? '키를 확인하는 중…' : '저장하고 시작'}
      </button>

      <p className="mt-3 text-xs leading-relaxed text-stone-400">
        저장 전에 짧은 요청 한 번으로 키가 실제로 동작하는지 확인합니다. 키는 암호화해 보관하며
        다시 화면에 표시되지 않습니다.
      </p>
    </div>
  )
}
