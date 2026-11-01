import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import type { AccountSettings } from '../lib/types'

const chooseModel = vi.fn<(p: string, m?: string) => Promise<AccountSettings>>()
const saveApiKey = vi.fn<(k: string, p?: string) => Promise<AccountSettings>>()

vi.mock('../lib/api', () => ({
  chooseModel: (p: string, m?: string) => chooseModel(p, m),
  saveApiKey: (k: string, p?: string) => saveApiKey(k, p),
  removeApiKey: vi.fn(),
  ApiError: class ApiError extends Error {
    constructor(
      readonly code: string,
      message: string,
    ) {
      super(message)
    }
  },
}))

const { ApiKeyPanel } = await import('../components/ApiKeyPanel')
const { appConfig, accountSettings } = await import('./fixtures')

const GEMINI = {
  id: 'gemini',
  label: 'Google Gemini',
  models: ['gemini-3.5-flash-lite'],
  needs_key: true,
  key_url: 'https://aistudio.google.com/apikey',
}
const OPENAI = {
  id: 'openai',
  label: 'OpenAI ChatGPT',
  models: ['gpt-5'],
  needs_key: true,
  key_url: 'https://platform.openai.com/api-keys',
}
const CONFIG = appConfig({ providers: [GEMINI, OPENAI] })

beforeEach(() => {
  chooseModel.mockReset()
  saveApiKey.mockReset()
  chooseModel.mockResolvedValue(accountSettings())
  saveApiKey.mockResolvedValue(accountSettings())
})

function show(settings: AccountSettings) {
  render(<ApiKeyPanel config={CONFIG} settings={settings} onSettingsChanged={() => {}} />)
}

describe('키 등록 화면은 **지금 고른 제공자**를 따른다 (H-037)', () => {
  test('OpenAI 를 골랐으면 OpenAI 키를 요구한다 — Gemini 가 아니다', () => {
    show(accountSettings({ active_provider: 'openai', active_model: 'gpt-5' }))

    expect(screen.getByRole('heading', { level: 2 }).textContent).toContain('OpenAI ChatGPT')
    expect(screen.getByRole('link', { name: /키 발급/ }).getAttribute('href')).toBe(
      OPENAI.key_url,
    )
    // 엉뚱한 제공자의 발급 주소를 보여주면 **그 키를 받아 저장하게 된다.**
    expect(document.body.innerHTML).not.toContain('aistudio.google.com')
  })

  test('Gemini 를 골랐으면 Gemini 를 요구한다', () => {
    show(accountSettings())

    expect(screen.getByRole('heading', { level: 2 }).textContent).toContain('Google Gemini')
  })

  test('제공자를 되돌릴 길이 있다 — 여기서 빠져나올 수 있어야 한다', async () => {
    show(accountSettings({ active_provider: 'openai', active_model: 'gpt-5' }))

    fireEvent.click(screen.getByRole('button', { name: /Google Gemini/ }))

    await waitFor(() => expect(chooseModel).toHaveBeenCalledWith('gemini', undefined))
  })

  test('키는 고른 제공자 자리로 저장된다', async () => {
    show(accountSettings({ active_provider: 'openai', active_model: 'gpt-5' }))

    fireEvent.change(screen.getByPlaceholderText(/OpenAI ChatGPT/), {
      target: { value: 'sk-test-0123456789' },
    })
    fireEvent.click(screen.getByRole('button', { name: '키 저장' }))

    await waitFor(() => expect(saveApiKey).toHaveBeenCalledWith('sk-test-0123456789', 'openai'))
  })
})
