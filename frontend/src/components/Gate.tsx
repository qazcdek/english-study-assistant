import { giveConsent, logout } from '../lib/api'
import type { Session } from '../lib/useSession'
import { ApiKeyPanel } from './ApiKeyPanel'
import { ConsentPanel } from './ConsentPanel'
import { LoginPanel } from './LoginPanel'

interface Props {
  session: Session
  /** 로그인 뒤 돌아갈 주소. 보던 화면으로 돌려보낸다. */
  next: string
  onOpenTerms: () => void
  onOpenPrivacy: () => void
  /** 키 단계만 넘길 수 있다. 로그인과 동의는 넘길 수 없다 — 신원과 법적 근거다. */
  onSkipKey: () => void
}

/**
 * 로그인 · 동의 · 키 등록 — 본 화면 앞에 서는 관문.
 *
 * **`App.tsx` 안에 있었는데 꺼냈다.** 관문은 틀리면 사용자가 **갇히는** 판단인데,
 * 화면 전체를 띄워야만 물을 수 있어서 검사가 닿지 않았다. 그래서 이 파일은
 * 분기만 들고, `tests/gate.test.tsx` 가 **실제로 이것을** 띄워 본다.
 *
 * **관문은 절대 빈 화면이 되지 않는다.** 전에는 `stage === 'api-key'` 인데
 * 설정을 못 읽었으면(`settings === null`) 아무것도 안 그렸다 — 흰 화면이고,
 * 화면에는 나갈 문이 없다. 무료 플랜의 콜드 스타트에서 실제로 날 수 있다
 * (`M3-T3`). 무엇이 없는지 말하고 **다시 시도와 로그아웃**을 준다 (H-039).
 */
export function Gate({ session, next, onOpenTerms, onOpenPrivacy, onSkipKey }: Props) {
  const { stage, config, settings } = session

  if (stage === 'login') return <LoginPanel error={session.error} next={next} />

  if (stage === 'consent' && config) {
    return (
      <ConsentPanel
        config={config}
        onAgree={async () => session.setAccount(await giveConsent())}
        onOpenTerms={onOpenTerms}
        onOpenPrivacy={onOpenPrivacy}
      />
    )
  }

  if (stage === 'api-key' && config && settings) {
    return (
      <ApiKeyPanel
        config={config}
        settings={settings}
        onSettingsChanged={session.setSettings}
        onSkip={onSkipKey}
      />
    )
  }

  return <Stalled error={session.error} />
}

/** 관문이 그릴 것을 못 받았을 때. **빈 화면 대신 나갈 문을 준다.** */
function Stalled({ error }: { error: string | null }) {
  return (
    <div className="mx-auto max-w-md rounded-2xl border border-stone-200 bg-white p-6 text-center shadow-sm dark:border-stone-800 dark:bg-stone-900">
      <h2 className="text-lg font-semibold tracking-tight">준비하지 못했습니다</h2>
      <p className="mt-2 text-sm leading-relaxed text-stone-500 dark:text-stone-400">
        어느 제공자로 일할지 서버에서 읽어오지 못했습니다. 한동안 쓰지 않은 뒤 첫 요청은
        깨어나는 데 1분까지 걸릴 수 있습니다.
      </p>
      {error && (
        <p className="mt-3 rounded-lg bg-red-50 p-2 font-mono text-xs text-red-600 dark:bg-red-950/40 dark:text-red-400">
          {error}
        </p>
      )}
      <div className="mt-5 flex flex-col gap-2">
        <button
          type="button"
          onClick={() => window.location.reload()}
          className="w-full rounded-xl bg-indigo-600 py-2.5 text-sm font-medium text-white transition hover:bg-indigo-500"
        >
          다시 불러오기
        </button>
        {/* **로그아웃도 길이다.** 세션 쪽이 문제라면 다시 들어오는 것이 가장 빠르다. */}
        <button
          type="button"
          onClick={async () => {
            try {
              await logout()
            } finally {
              window.location.assign('/')
            }
          }}
          className="w-full rounded-xl border border-stone-200 py-2 text-sm text-stone-500 transition hover:bg-stone-100 dark:border-stone-700 dark:hover:bg-stone-800"
        >
          로그아웃
        </button>
      </div>
    </div>
  )
}
