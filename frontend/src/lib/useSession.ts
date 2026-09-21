import { useCallback, useEffect, useState } from 'react'

import { ApiError, getAccount, getConfig, getUsage } from './api'
import type { Account, AppConfig, Usage } from './types'

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
  error: string | null
  setAccount: (account: Account) => void
  refreshUsage: () => Promise<void>
}

function stageFor(config: AppConfig | null, account: Account | null): SessionStage {
  if (!config) return 'loading'
  if (!config.requires_login) return 'local'
  if (!account) return 'login'
  if (!account.has_consented) return 'consent'
  if (!account.has_api_key) return 'api-key'
  return 'ready'
}

export function useSession(): Session {
  const [config, setConfig] = useState<AppConfig | null>(null)
  const [account, setAccountState] = useState<Account | null>(null)
  const [usage, setUsage] = useState<Usage | null>(null)
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
        if (cfg.requires_login) {
          try {
            const me = await getAccount()
            setAccountState(me)
            if (me.has_api_key) void refreshUsage()
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
    stage: loaded ? stageFor(config, account) : 'loading',
    config,
    account,
    usage,
    error,
    setAccount,
    refreshUsage,
  }
}
