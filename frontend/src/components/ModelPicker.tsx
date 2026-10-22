import { useState } from 'react'

import { ApiError, chooseModel, removeApiKey, saveApiKey } from '../lib/api'
import type { AccountSettings, AppConfig } from '../lib/types'

/**
 * 어느 제공자·모델로 일할지 고르고, 제공자별 키를 넣고 지운다.
 *
 * **두 모드가 같은 화면을 쓴다.** 로컬도 cloud LLM 을 고를 수 있으므로(09 §3.2)
 * 이 화면을 cloud 전용으로 두면 로컬에서 고를 길이 없다.
 *
 * **목록을 여기 적지 않는다.** `/api/config` 가 모드에 맞는 것만 내려주고, 그것을
 * 그대로 그린다 — 적어 두면 모드가 바뀔 때 어긋난다.
 */
export function ModelPicker({
  config,
  settings,
  onChanged,
}: {
  config: AppConfig
  settings: AccountSettings
  onChanged: (next: AccountSettings) => void
}) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [typedKey, setTypedKey] = useState('')

  const chosen = config.providers.find((p) => p.id === settings.active_provider)

  async function run(work: () => Promise<AccountSettings>) {
    setBusy(true)
    setError(null)
    try {
      onChanged(await work())
      setTypedKey('')
    } catch (e) {
      setError(e instanceof ApiError ? e.message : '바꾸지 못했습니다.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <h3 className="text-xs font-medium uppercase tracking-wide text-stone-400">모델</h3>
        {!settings.ready && (
          // 고른 제공자의 키가 없으면 분석이 시작되지 않는다. 미리 말해 준다.
          <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[11px] text-amber-700 dark:bg-amber-950 dark:text-amber-300">
            키 필요
          </span>
        )}
      </div>

      <ul className="flex flex-col gap-1">
        {config.providers.map((provider) => {
          const active = provider.id === settings.active_provider
          const held = settings.keys[provider.id]
          return (
            <li key={provider.id}>
              <button
                type="button"
                disabled={busy}
                onClick={() => void run(() => chooseModel(provider.id))}
                aria-pressed={active}
                className={`flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-xs transition disabled:opacity-50 ${
                  active
                    ? 'bg-indigo-50 text-indigo-700 dark:bg-indigo-950/60 dark:text-indigo-300'
                    : 'text-stone-500 hover:bg-stone-100 dark:hover:bg-stone-800'
                }`}
              >
                <span className="min-w-0 flex-1 truncate">{provider.label}</span>
                {held && <span className="font-mono text-[11px] text-stone-400">{held}</span>}
                {provider.needs_key && !held && (
                  <span className="text-[11px] text-amber-600 dark:text-amber-400">키 없음</span>
                )}
              </button>
            </li>
          )
        })}
      </ul>

      {chosen && chosen.models.length > 1 && (
        <label className="flex items-center gap-2 text-xs text-stone-500">
          <span className="shrink-0">모델</span>
          <select
            value={settings.active_model}
            disabled={busy}
            onChange={(e) => void run(() => chooseModel(chosen.id, e.target.value))}
            className="min-w-0 flex-1 rounded-lg border border-stone-200 bg-white px-2 py-1 dark:border-stone-700 dark:bg-stone-950"
          >
            {chosen.models.map((model) => (
              <option key={model} value={model}>
                {model}
              </option>
            ))}
          </select>
        </label>
      )}

      {chosen?.needs_key && (
        <div className="flex flex-col gap-2 border-t border-stone-100 pt-3 dark:border-stone-800">
          {settings.keys[chosen.id] ? (
            <div className="flex items-center gap-2 text-xs">
              <span className="min-w-0 flex-1 truncate text-stone-400">
                {chosen.label} 키 {settings.keys[chosen.id]}
              </span>
              <button
                type="button"
                disabled={busy}
                onClick={() => void run(() => removeApiKey(chosen.id))}
                className="shrink-0 rounded-lg border border-stone-200 px-2 py-1 transition hover:bg-stone-100 disabled:opacity-50 dark:border-stone-700 dark:hover:bg-stone-800"
              >
                키 삭제
              </button>
            </div>
          ) : (
            <>
              <input
                type="password"
                value={typedKey}
                onChange={(e) => setTypedKey(e.target.value)}
                placeholder={`${chosen.label} API 키`}
                autoComplete="off"
                spellCheck={false}
                className="w-full rounded-lg border border-stone-200 bg-white px-2 py-1.5 font-mono text-xs outline-none focus:border-indigo-400 dark:border-stone-700 dark:bg-stone-950"
              />
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  disabled={busy || typedKey.trim().length < 10}
                  onClick={() => void run(() => saveApiKey(typedKey.trim(), chosen.id))}
                  className="rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-indigo-500 disabled:bg-stone-300 dark:disabled:bg-stone-700"
                >
                  {busy ? '확인 중…' : '키 저장'}
                </button>
                {chosen.key_url && (
                  <a
                    href={chosen.key_url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-xs text-stone-400 underline hover:text-stone-600 dark:hover:text-stone-300"
                  >
                    키 발급
                  </a>
                )}
              </div>
            </>
          )}
        </div>
      )}

      {error && <p className="text-xs text-red-500">{error}</p>}
    </div>
  )
}
