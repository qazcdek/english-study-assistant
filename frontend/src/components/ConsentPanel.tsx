import { useState } from 'react'

import type { AppConfig } from '../lib/types'

interface Props {
  config: AppConfig
  onAgree: () => Promise<void>
}

/**
 * 가입 후 첫 관문.
 *
 * 이 서비스는 회원이 등록한 Gemini API 키로, 회원 본인의 사용 한도 안에서 호출한다.
 * 비용과 한도가 이용자에게 귀속되므로 동의 없이는 진행하지 않는다.
 */
export function ConsentPanel({ config, onAgree }: Props) {
  const [checked, setChecked] = useState(false)
  const [busy, setBusy] = useState(false)

  return (
    <div className="mx-auto max-w-2xl rounded-2xl border border-stone-200 bg-white p-6 shadow-sm dark:border-stone-800 dark:bg-stone-900">
      <h2 className="text-lg font-semibold tracking-tight">이용 방식 안내</h2>
      <p className="mt-2 text-sm text-stone-500 dark:text-stone-400">
        시작하기 전에 아래 내용을 확인해 주세요.
      </p>

      <ul className="mt-5 flex flex-col gap-3 text-sm leading-relaxed">
        <li className="flex gap-3">
          <span className="text-indigo-500">1</span>
          <span>
            분석과 채점은 <b>회원님이 직접 등록한 Google Gemini API 키</b>로 호출됩니다. 서버가
            대신 비용을 내지 않습니다.
          </span>
        </li>
        <li className="flex gap-3">
          <span className="text-indigo-500">2</span>
          <span>
            따라서 <b>회원님 Google 계정의 사용 한도(무료 등급 포함)가 소모</b>됩니다. 한도를
            넘으면 Google이 요청을 거부하며, 이 서비스가 대신 처리해 드릴 수 없습니다.
          </span>
        </li>
        <li className="flex gap-3">
          <span className="text-indigo-500">3</span>
          <span>
            사용 모델은 <code className="font-mono text-xs">{config.model}</code> 입니다. 분석 한
            번에 LLM 호출이 <b>4회</b> 일어납니다(번역·표현·구조·총평).
          </span>
        </li>
        <li className="flex gap-3">
          <span className="text-indigo-500">4</span>
          <span>
            입력하신 영어 원문은 Google에 전송됩니다. Gemini 무료 등급은 Google의 서비스 개선에
            데이터가 쓰일 수 있으니, <b>민감한 내용은 넣지 마세요.</b>
          </span>
        </li>
        <li className="flex gap-3">
          <span className="text-indigo-500">5</span>
          <span>
            등록한 키는 암호화해 보관하며 화면에는 끝 네 자리만 보입니다. 언제든 삭제할 수
            있습니다.
          </span>
        </li>
      </ul>

      <label className="mt-6 flex cursor-pointer items-start gap-2.5 rounded-xl bg-stone-50 p-3 text-sm dark:bg-stone-950">
        <input
          type="checkbox"
          checked={checked}
          onChange={(e) => setChecked(e.target.checked)}
          className="mt-0.5 accent-indigo-600"
        />
        <span>
          위 내용을 이해했고, <b>내 API 키와 내 사용 한도로 호출되는 것에 동의</b>합니다.
        </span>
      </label>

      <button
        type="button"
        disabled={!checked || busy}
        onClick={async () => {
          setBusy(true)
          try {
            await onAgree()
          } finally {
            setBusy(false)
          }
        }}
        className="mt-4 w-full rounded-xl bg-indigo-600 py-2.5 text-sm font-medium text-white transition hover:bg-indigo-500 disabled:bg-stone-300 dark:disabled:bg-stone-700"
      >
        {busy ? '처리 중…' : '동의하고 계속'}
      </button>
    </div>
  )
}
