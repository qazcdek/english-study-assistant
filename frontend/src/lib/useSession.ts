import { useCallback, useEffect, useState } from 'react'

import { ApiError, getAccount, getConfig, getSettings, getUsage } from './api'
import type { Account, AccountSettings, AppConfig, Usage } from './types'

export type SessionStage =
  | 'loading'
  | 'local' // 로컬 모드 — 로그인 없이 바로 쓴다
  | 'login' // 로그인 필요
  | 'consent' // 로그인했지만 이용 동의 전
  | 'api-key' // 동의했지만 키 미등록
  | 'ready'

export interface Session {
  stage: SessionStage
  config: AppConfig | null
  account: Account | null
  usage: Usage | null
  /** 지금 무엇으로 일하나. **두 모드 모두 있다** — 로컬도 제공자를 고른다. */
  settings: AccountSettings | null
  error: string | null
  setAccount: (account: Account) => void
  setSettings: (settings: AccountSettings) => void
  refreshUsage: () => Promise<void>
}

/**
 * 어느 화면을 보여줄지. **검사가 직접 부를 수 있게 내놓는다** — 관문 판단은
 * 네트워크 없이 따질 수 있는 순수한 것이고, 틀리면 사용자가 갇힌다.
 */
export function stageFor(
  config: AppConfig | null,
  account: Account | null,
  settings: AccountSettings | null,
): SessionStage {
  if (!config) return 'loading'
  if (!config.requires_login) return 'local'
  if (!account) return 'login'
  if (!account.has_consented) return 'consent'
  // **키 보유는 "지금 고른 제공자" 에 달렸다** (M12-T2). 제공자를 바꾸면 로그인 때
  // 받은 `account` 는 그 자리에서 낡는다 — 설정이 이 사실의 주인이고, `account` 의
  // 같은 칸은 설정을 아직 못 읽었을 때의 첫 값일 뿐이다.
  //
  // 둘을 각자 믿으면 **제공자를 되돌려도 관문이 열리지 않는다.** 실제로 그랬다 —
  // 키 없는 제공자를 고른 회원이 키 등록 화면에 갇혔다 (H-037).
  if (!(settings ? settings.ready : account.has_api_key)) return 'api-key'
  return 'ready'
}

export function useSession(): Session {
  const [config, setConfig] = useState<AppConfig | null>(null)
  const [account, setAccountState] = useState<Account | null>(null)
  const [usage, setUsage] = useState<Usage | null>(null)
  const [settings, setSettings] = useState<AccountSettings | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loaded, setLoaded] = useState(false)

  const refreshUsage = useCallback(async () => {
    try {
      setUsage(await getUsage())
    } catch {
      // 사용량은 부가 정보다. 실패해도 앱은 돌아간다.
    }
  }, [])

  const setAccount = useCallback(
    (next: Account) => {
      setAccountState(next)
      if (next.has_api_key) void refreshUsage()
    },
    [refreshUsage],
  )

  useEffect(() => {
    // OAuth 콜백이 실패를 쿼리로 돌려준다.
    const params = new URLSearchParams(window.location.search)
    const loginError = params.get('login_error')
    if (loginError) {
      setError(loginError)
      window.history.replaceState({}, '', window.location.pathname)
    }

    void (async () => {
      try {
        const cfg = await getConfig()
        setConfig(cfg)
        if (!cfg.requires_login) {
          // 로컬은 로그인이 없으니 바로 읽는다.
          try {
            setSettings(await getSettings())
          } catch {
            // 설정을 못 읽어도 분석은 돌아간다. 선택 UI 만 안 나온다.
          }
        }
        if (cfg.requires_login) {
          try {
            const me = await getAccount()
            setAccountState(me)
            if (me.has_api_key) void refreshUsage()
            try {
              setSettings(await getSettings())
            } catch (e) {
              // **부가 정보가 아니다.** 관문은 "지금 고른 제공자의 키가 있나" 로
              // 열리고 닫히므로, 이것이 없으면 관문이 그릴 것을 못 받는다.
              // 삼키면 흰 화면이 된다 — 화면에는 나갈 문이 없다 (H-039).
              setError(
                e instanceof ApiError ? e.message : '설정을 가져오지 못했습니다.',
              )
            }
          } catch (e) {
            // 401 은 그냥 비로그인 상태다.
            if (!(e instanceof ApiError) || e.code !== 'auth_required') {
              setError(e instanceof ApiError ? e.message : '계정 정보를 가져오지 못했습니다.')
            }
          }
        }
      } catch (e) {
        setError(e instanceof ApiError ? e.message : '서버 설정을 가져오지 못했습니다.')
      } finally {
        setLoaded(true)
      }
    })()
  }, [refreshUsage])

  return {
    stage: loaded ? stageFor(config, account, settings) : 'loading',
    config,
    account,
    usage,
    settings,
    error,
    setAccount,
    setSettings,
    refreshUsage,
  }
}
