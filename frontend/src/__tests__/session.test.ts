import { describe, expect, test } from 'vitest'

import { stageFor } from '../lib/useSession'
import { account, accountSettings, appConfig } from './fixtures'

const CLOUD = appConfig()
const LOCAL = appConfig({ mode: 'local', requires_login: false })

describe('관문은 어느 화면을 보여줄지 정한다', () => {
  test('설정을 못 읽기 전에는 로그인 때 받은 값으로 판단한다', () => {
    expect(stageFor(null, null, null)).toBe('loading')
    expect(stageFor(LOCAL, null, null)).toBe('local')
    expect(stageFor(CLOUD, null, null)).toBe('login')
    expect(stageFor(CLOUD, account({ has_consented: false }), null)).toBe('consent')
    expect(stageFor(CLOUD, account({ has_api_key: false }), null)).toBe('api-key')
    expect(stageFor(CLOUD, account({ has_api_key: true }), null)).toBe('ready')
  })

  test('키 보유는 **지금 고른 제공자**에 달렸다 — 설정이 그 사실의 주인이다', () => {
    // 로그인 때는 Gemini 키가 있었다. 그 뒤 OpenAI 로 바꿨으면 키는 없는 것이다.
    const switched = accountSettings({ active_provider: 'openai', ready: false })

    expect(stageFor(CLOUD, account({ has_api_key: true }), switched)).toBe('api-key')
  })

  test('제공자를 되돌리면 그 자리에서 관문이 열린다 — 갇히지 않는다 (H-037)', () => {
    const back = accountSettings({ active_provider: 'gemini', keys: { gemini: '••••0000' }, ready: true })

    expect(stageFor(CLOUD, account({ has_api_key: false }), back)).toBe('ready')
  })
})
