import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import type { AccountSettings } from '../lib/types'

const chooseModel = vi.fn<(p: string, m?: string) => Promise<AccountSettings>>()
const saveApiKey = vi.fn<(k: string, p?: string) => Promise<AccountSettings>>()
const removeApiKey = vi.fn<(p?: string) => Promise<AccountSettings>>()

vi.mock('../lib/api', () => ({
  chooseModel: (p: string, m?: string) => chooseModel(p, m),
  saveApiKey: (k: string, p?: string) => saveApiKey(k, p),
  removeApiKey: (p?: string) => removeApiKey(p),
  getAccount: vi.fn(),
  // DataMenu 안의 DataPanel 이 쓴다. 가짜가 좁으면 "모듈에 없다" 로 터진다.
  getMyDataCounts: vi.fn(async () => ({
    analyses: 0,
    practices: 0,
    vocabulary: 0,
    usage_counters: 0,
  })),
  purgeMyData: vi.fn(),
  leaveService: vi.fn(),
  ApiError: class ApiError extends Error {
    constructor(
      readonly code: string,
      message: string,
    ) {
      super(message)
    }
  },
}))

const { ModelPicker } = await import('../components/ModelPicker')
const { DataMenu } = await import('../components/DataMenu')
const { appConfig, accountSettings } = await import('./fixtures')

const LOCAL = appConfig({
  mode: 'local',
  requires_login: false,
  default_provider: 'llama',
  providers: [
    { id: 'llama', label: 'llama-server (내 PC)', models: ['local-model'], needs_key: false, key_url: '' },
    {
      id: 'gemini',
      label: 'Google Gemini',
      models: ['gemini-3.5-flash-lite'],
      needs_key: true,
      key_url: 'https://aistudio.google.com/apikey',
    },
  ],
})

beforeEach(() => {
  chooseModel.mockReset()
  saveApiKey.mockReset()
  removeApiKey.mockReset()
  chooseModel.mockResolvedValue(accountSettings())
  saveApiKey.mockResolvedValue(accountSettings())
  removeApiKey.mockResolvedValue(accountSettings())
})

describe('고를 수 있는 것만 그린다', () => {
  test('서버가 준 목록을 그대로 그린다', () => {
    // **프론트가 목록을 들고 있지 않다.** 적어 두면 모드가 바뀔 때 어긋난다.
    render(
      <ModelPicker config={LOCAL} settings={accountSettings({ active_provider: 'llama' })} onChanged={() => {}} />,
    )

    expect(screen.getByText('llama-server (내 PC)')).toBeTruthy()
    expect(screen.getByText('Google Gemini')).toBeTruthy()
  })

  test('지금 고른 것이 눌린 상태로 보인다', () => {
    render(
      <ModelPicker config={LOCAL} settings={accountSettings({ active_provider: 'llama' })} onChanged={() => {}} />,
    )

    const llama = screen.getByText('llama-server (내 PC)').closest('button')
    expect(llama?.getAttribute('aria-pressed')).toBe('true')
  })

  test('누르면 그 제공자로 저장한다 — 전역 설정이다', async () => {
    render(
      <ModelPicker config={LOCAL} settings={accountSettings({ active_provider: 'llama' })} onChanged={() => {}} />,
    )

    fireEvent.click(screen.getByText('Google Gemini'))

    await waitFor(() => expect(chooseModel).toHaveBeenCalledWith('gemini', undefined))
  })
})

describe('키', () => {
  const gemini = accountSettings({ active_provider: 'gemini', ready: false })

  test('키가 없는 제공자는 없다고 말한다', () => {
    render(<ModelPicker config={LOCAL} settings={gemini} onChanged={() => {}} />)

    expect(screen.getByText('키 없음')).toBeTruthy()
    // 고른 제공자의 키가 없으면 분석이 시작되지 않는다. 미리 말해 준다.
    expect(screen.getByText('키 필요')).toBeTruthy()
  })

  test('키를 넣으면 그 제공자로 저장한다', async () => {
    render(<ModelPicker config={LOCAL} settings={gemini} onChanged={() => {}} />)

    fireEvent.change(screen.getByPlaceholderText('Google Gemini API 키'), {
      target: { value: 'AIzaSyREALKEY1234' },
    })
    fireEvent.click(screen.getByText('키 저장'))

    await waitFor(() => expect(saveApiKey).toHaveBeenCalledWith('AIzaSyREALKEY1234', 'gemini'))
  })

  test('짧은 키는 저장 버튼이 눌리지 않는다', () => {
    render(<ModelPicker config={LOCAL} settings={gemini} onChanged={() => {}} />)

    fireEvent.change(screen.getByPlaceholderText('Google Gemini API 키'), {
      target: { value: 'short' },
    })

    expect(screen.getByText('키 저장').closest('button')?.disabled).toBe(true)
  })

  test('키가 있으면 끝 네 자리만 보이고 지울 수 있다', async () => {
    const held = accountSettings({ active_provider: 'gemini', keys: { gemini: '••••1234' }, ready: true })
    render(<ModelPicker config={LOCAL} settings={held} onChanged={() => {}} />)

    // 평문은 서버에서 나오지 않는다. 화면도 끝자리만 안다.
    // 제공자 줄과 키 줄 양쪽에 나오므로 개수를 묻지 않는다.
    expect(screen.getAllByText(/••••1234/).length).toBeGreaterThan(0)
    expect(screen.queryByPlaceholderText(/API 키/)).toBeNull()

    fireEvent.click(screen.getByText('키 삭제'))
    await waitFor(() => expect(removeApiKey).toHaveBeenCalledWith('gemini'))
  })

  test('키가 필요 없는 제공자에는 키 칸이 없다', () => {
    render(
      <ModelPicker config={LOCAL} settings={accountSettings({ active_provider: 'llama', ready: true })} onChanged={() => {}} />,
    )

    expect(screen.queryByPlaceholderText(/API 키/)).toBeNull()
    expect(screen.queryByText('키 필요')).toBeNull()
  })
})

test('로컬 설정 메뉴에도 모델 선택이 있다', () => {
  /**
   * **이것이 이 작업의 핵심이다.** 전에는 이 화면이 cloud 쪽(`AccountBar`)에만 있어서
   * **로컬에서는 제공자를 고를 길이 없었다** — 요청의 절반이 동작하지 않았다.
   */
  render(
    <DataMenu
      config={LOCAL}
      settings={accountSettings({ active_provider: 'llama', ready: true })}
      onSettingsChanged={() => {}}
    />,
  )

  fireEvent.click(screen.getByText('설정'))

  expect(screen.getByText('Google Gemini')).toBeTruthy()
})
