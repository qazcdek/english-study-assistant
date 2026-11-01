import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { useState } from 'react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import type { Account, AccountSettings, AppConfig } from '../lib/types'

/**
 * **관문.** 틀리면 사용자가 갇히는 판단이라, 검사가 **실제 `Gate` 를** 띄운다.
 *
 * 가짜 서버는 백엔드와 **같은 규칙**을 쓴다 — `ready` 는 "지금 고른 제공자의 키가
 * 있나" 다. 규칙을 다르게 적으면 통과해도 아무것도 증명하지 못한다.
 */
const server = { active_provider: 'openai', keys: {} as Record<string, string> }

function settingsOf(): AccountSettings {
  return {
    active_provider: server.active_provider,
    active_model: server.active_provider === 'openai' ? 'gpt-5' : 'gemini-3.5-flash-lite',
    keys: { ...server.keys },
    ready: Boolean(server.keys[server.active_provider]),
  }
}

const chooseModel = vi.fn(async (provider: string, _model?: string) => {
  server.active_provider = provider
  return settingsOf()
})
const saveApiKey = vi.fn(async (key: string, provider?: string) => {
  server.keys[provider || server.active_provider] = `••••${key.slice(-4)}`
  return settingsOf()
})
const logout = vi.fn(async () => ({ ok: true }))
const onSkipKey = vi.fn()

vi.mock('../lib/api', () => ({
  chooseModel: (p: string, m?: string) => chooseModel(p, m),
  saveApiKey: (k: string, p?: string) => saveApiKey(k, p),
  removeApiKey: vi.fn(async () => settingsOf()),
  giveConsent: vi.fn(),
  logout: () => logout(),
  loginUrl: (next: string) => `/api/auth/google/start?next=${encodeURIComponent(next)}`,
  ApiError: class ApiError extends Error {
    constructor(
      readonly code: string,
      message: string,
    ) {
      super(message)
    }
  },
}))

const { Gate } = await import('../components/Gate')
const { stageFor } = await import('../lib/useSession')
const { appConfig, account } = await import('./fixtures')

const CONFIG = appConfig({
  providers: [
    {
      id: 'gemini',
      label: 'Google Gemini',
      models: ['gemini-3.5-flash-lite'],
      needs_key: true,
      key_url: 'https://aistudio.google.com/apikey',
    },
    {
      id: 'openai',
      label: 'OpenAI ChatGPT',
      models: ['gpt-5'],
      needs_key: true,
      key_url: 'https://platform.openai.com/api-keys',
    },
  ],
})

/**
 * 관문을 **실제 조립 그대로** 세운다 — `stageFor` 가 단계를 정하고 `Gate` 가 그린다.
 * 단계를 화면에 적어 열렸는지 확인한다.
 */
function Harness({
  acct,
  config = CONFIG,
  withSettings = true,
  error = null,
}: {
  acct: Account
  config?: AppConfig | null
  withSettings?: boolean
  error?: string | null
}) {
  const [settings, setSettings] = useState<AccountSettings | null>(
    withSettings ? settingsOf() : null,
  )
  const stage = stageFor(config, acct, settings)
  const session = {
    stage,
    config,
    account: acct,
    usage: null,
    settings,
    error,
    setAccount: () => {},
    setSettings,
    refreshUsage: async () => {},
  }
  return (
    <>
      <p data-testid="stage">{stage}</p>
      {stage !== 'ready' && stage !== 'local' && (
        <Gate
          session={session}
          next="/"
          onOpenTerms={() => {}}
          onOpenPrivacy={() => {}}
          onSkipKey={onSkipKey}
        />
      )}
    </>
  )
}

beforeEach(() => {
  server.active_provider = 'openai'
  server.keys = { gemini: '••••0000' }
  chooseModel.mockClear()
  logout.mockClear()
  onSkipKey.mockClear()
})

describe('키 등록 화면에 갇힌 계정 (H-037)', () => {
  // 로그인 때는 Gemini 키가 있었다 — `account` 는 그 자리에서 낡은다.
  const stuck = account({ has_api_key: true })

  test('들어오면 관문에 선다', () => {
    render(<Harness acct={stuck} />)

    expect(screen.getByTestId('stage').textContent).toBe('api-key')
  })

  test('가진 키의 제공자로 되돌리면 **그 자리에서 열린다**', async () => {
    render(<Harness acct={stuck} />)

    fireEvent.click(screen.getByRole('button', { name: /Google Gemini/ }))

    await waitFor(() => expect(screen.getByTestId('stage').textContent).toBe('ready'))
  })

  test('키 없이 본 화면으로 갈 수도 있다 — 기록과 나의 표현은 키가 필요 없다 (H-041)', () => {
    render(<Harness acct={stuck} />)

    fireEvent.click(screen.getByRole('button', { name: /메인 화면으로/ }))

    expect(onSkipKey).toHaveBeenCalled()
  })

  test('키가 아무 제공자에도 없으면, 넣어서 열 수도 있다', async () => {
    server.keys = {}
    render(<Harness acct={stuck} />)

    fireEvent.change(screen.getByPlaceholderText(/OpenAI ChatGPT/), {
      target: { value: 'sk-test-0123456789' },
    })
    fireEvent.click(screen.getByRole('button', { name: '키 저장' }))

    await waitFor(() => expect(screen.getByTestId('stage').textContent).toBe('ready'))
  })
})

describe('관문은 빈 화면이 되지 않는다 (H-039)', () => {
  test('설정을 못 읽었으면 흰 화면이 아니라 나갈 문을 준다', () => {
    render(
      <Harness
        acct={account({ has_api_key: false })}
        withSettings={false}
        error="설정을 가져오지 못했습니다."
      />,
    )

    // 단계는 관문인데 그릴 것이 없다. **그래도 아무것도 안 그리면 갇힌다.**
    expect(screen.getByTestId('stage').textContent).toBe('api-key')
    expect(screen.getByRole('button', { name: '다시 불러오기' })).toBeTruthy()
    expect(screen.getByRole('button', { name: '로그아웃' })).toBeTruthy()
    expect(screen.getByText(/설정을 가져오지 못했습니다/)).toBeTruthy()
  })

  test('로그아웃은 실제로 서버를 부른다', async () => {
    render(<Harness acct={account({ has_api_key: false })} withSettings={false} />)

    fireEvent.click(screen.getByRole('button', { name: '로그아웃' }))

    await waitFor(() => expect(logout).toHaveBeenCalled())
  })

  test('로그인 화면은 보던 주소를 들고 간다', () => {
    render(<Harness acct={null as unknown as Account} withSettings={false} />)

    expect(screen.getByTestId('stage').textContent).toBe('login')
    expect(screen.getByRole('link').getAttribute('href')).toContain('next=%2F')
  })
})
