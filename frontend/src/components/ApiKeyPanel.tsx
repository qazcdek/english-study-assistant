import type { AccountSettings, AppConfig } from '../lib/types'
import { ModelPicker } from './ModelPicker'

interface Props {
  config: AppConfig
  settings: AccountSettings
  onSettingsChanged: (next: AccountSettings) => void
  /** 키 없이 본 화면으로 간다. 저장된 기록과 나의 표현은 키가 없어도 읽는다. */
  onSkip: () => void
}

/**
 * 관문의 마지막 칸 — **지금 고른 제공자의 키가 없으면** 여기서 멈춘다.
 *
 * **키 입력을 여기서 또 그리지 않는다.** 제공자 선택·키 입력·키 삭제는
 * `ModelPicker` 하나가 든다 (두 모드가 같은 화면을 쓰는 이유는 거기 적혀 있다).
 *
 * 전에는 이 화면이 자기 입력칸을 들고 **제목·발급 링크를 Gemini 로 고정**한 채
 * 제공자를 안 붙여 저장했다. 그래서 OpenAI 를 고른 회원에게 Gemini 키를 요구하고
 * **그 키를 OpenAI 키 자리에** 넣었다. 게다가 제공자를 되돌릴 길이 없어
 * 여기서 빠져나올 수 없었다 (H-037).
 */
export function ApiKeyPanel({ config, settings, onSettingsChanged, onSkip }: Props) {
  const chosen = config.providers.find((p) => p.id === settings.active_provider)

  return (
    <div className="mx-auto max-w-2xl rounded-2xl border border-stone-200 bg-white p-6 shadow-sm dark:border-stone-800 dark:bg-stone-900">
      <h2 className="text-lg font-semibold tracking-tight">
        {chosen ? `${chosen.label} API 키 등록` : 'API 키 등록'}
      </h2>
      <p className="mt-2 text-sm leading-relaxed text-stone-500 dark:text-stone-400">
        분석은 회원님이 등록하신 키로, 회원님의 사용 한도 안에서 이루어집니다. 무료 등급으로도
        쓸 수 있습니다.
      </p>

      <ol className="mt-4 flex flex-col gap-1.5 text-sm text-stone-600 dark:text-stone-300">
        <li>1. 아래 {chosen?.key_url ? <b>키 발급</b> : <b>제공자</b>} 에서 키를 만듭니다</li>
        <li>2. 만들어진 키를 복사합니다</li>
        <li>3. 아래 칸에 붙여넣고 저장합니다</li>
      </ol>

      <div className="mt-5 rounded-xl border border-stone-200 p-4 dark:border-stone-800">
        <ModelPicker config={config} settings={settings} onChanged={onSettingsChanged} />
      </div>

      {/* **여기서 나갈 길이 있어야 한다.** 분석은 키가 있어야 하지만, 저장된 기록과
          나의 표현을 읽는 데에는 키가 필요 없다 — 그것들까지 막을 이유가 없다 (H-041). */}
      <button
        type="button"
        onClick={onSkip}
        className="mt-4 w-full rounded-xl border border-stone-200 py-2 text-sm text-stone-500 transition hover:bg-stone-100 dark:border-stone-700 dark:hover:bg-stone-800"
      >
        나중에 하고 메인 화면으로
      </button>

      <p className="mt-3 text-xs leading-relaxed text-stone-400">
        <b>다른 제공자를 쓰실 수 있습니다</b> — 위 목록에서 바꾸면 그 제공자의 키를 넣는
        화면이 됩니다. 키는 저장 전에 짧은 요청 한 번으로 실제로 동작하는지 확인하며,
        암호화해 보관하고 다시 화면에 표시하지 않습니다.
      </p>
      <p className="mt-2 text-xs leading-relaxed text-stone-400">
        키 없이 들어가면 <b>이전 기록과 나의 표현은 그대로 보이고</b>, 새 분석만
        시작되지 않습니다.
      </p>
    </div>
  )
}
