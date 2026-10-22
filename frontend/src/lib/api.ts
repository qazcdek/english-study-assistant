import type {
  Account,
  AccountSettings,
  AppConfig,
  DeletionSummary,
  HealthResponse,
  HistoryDetail,
  HistoryItem,
  Level,
  PracticeHistoryItem,
  PracticeRequest,
  PracticeResponse,
  StreamEvent,
  Usage,
  VocabularyItem,
  VocabularyRemoval,
} from './types'

const BASE = import.meta.env.VITE_API_BASE ?? ''

/** cloud 모드는 HttpOnly 세션 쿠키를 쓰므로 모든 요청에 자격 증명을 실어 보낸다. */
const CREDENTIALS: RequestCredentials = 'include'

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${BASE}${path}`, {
      credentials: CREDENTIALS,
      headers: init.body ? { 'Content-Type': 'application/json' } : undefined,
      ...init,
    })
  } catch {
    throw new ApiError('network', '서버에 연결할 수 없습니다.')
  }
  if (!response.ok) throw await parseError(response)
  return response.json() as Promise<T>
}

export class ApiError extends Error {
  constructor(
    readonly code: string,
    message: string,
    readonly detail?: string,
  ) {
    super(message)
  }
}

async function parseError(response: Response): Promise<ApiError> {
  try {
    const body = await response.json()
    if (body?.error) {
      return new ApiError(body.error.code, body.error.message, body.error.detail ?? undefined)
    }
    if (Array.isArray(body?.detail)) {
      // FastAPI 검증 오류
      return new ApiError('validation_error', body.detail[0]?.msg ?? '입력을 확인해 주세요.')
    }
  } catch {
    // 아래 기본 메시지로 떨어진다
  }
  return new ApiError('unknown', `요청이 실패했습니다 (HTTP ${response.status}).`)
}

/**
 * 파트가 완성되는 대로 SSE 이벤트를 흘려준다.
 *
 * EventSource 는 GET 만 지원하므로 fetch + ReadableStream 으로 직접 읽는다.
 */
export async function analyzeStream(
  text: string,
  level: Level,
  onEvent: (event: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  let response: Response
  try {
    response = await fetch(`${BASE}/api/analyze/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
      body: JSON.stringify({ text, level }),
      credentials: CREDENTIALS,
      signal,
    })
  } catch (e) {
    if ((e as Error)?.name === 'AbortError') return
    throw new ApiError('network', '백엔드 서버에 연결할 수 없습니다. 실행 중인지 확인해 주세요.')
  }

  if (!response.ok) throw await parseError(response)
  if (!response.body) throw new ApiError('unknown', '스트림 응답이 비어 있습니다.')

  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader()
  let buffer = ''

  try {
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += value

      // SSE 는 빈 줄로 이벤트를 구분한다. 마지막 조각은 다음 청크와 합쳐야 한다.
      let split: number
      while ((split = buffer.indexOf('\n\n')) !== -1) {
        const chunk = buffer.slice(0, split)
        buffer = buffer.slice(split + 2)
        for (const line of chunk.split('\n')) {
          if (!line.startsWith('data:')) continue
          try {
            onEvent(JSON.parse(line.slice(5).trim()) as StreamEvent)
          } catch {
            // 잘린 조각은 무시한다
          }
        }
      }
    }
  } finally {
    reader.cancel().catch(() => {})
  }
}

/** 예문을 가린 채 학습자가 쓴 문장을 채점한다. */
export async function gradePractice(request: PracticeRequest): Promise<PracticeResponse> {
  let response: Response
  try {
    response = await fetch(`${BASE}/api/practice`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
      credentials: CREDENTIALS,
    })
  } catch {
    throw new ApiError('network', '백엔드 서버에 연결할 수 없습니다.')
  }

  if (!response.ok) throw await parseError(response)
  return response.json()
}

export async function health(): Promise<HealthResponse> {
  return request<HealthResponse>('/api/health')
}

// --- 앱 설정 / 계정 ---

export const getConfig = () => request<AppConfig>('/api/config')
export const getAccount = () => request<Account>('/api/auth/me')
export const getUsage = () => request<Usage>('/api/usage')

export function loginUrl(next = '/'): string {
  return `${BASE}/api/auth/google/start?next=${encodeURIComponent(next)}`
}

export const logout = () => request<{ ok: boolean }>('/api/auth/logout', { method: 'POST' })

export const giveConsent = () =>
  request<Account>('/api/auth/consent', {
    method: 'POST',
    body: JSON.stringify({ agreed: true }),
  })

// --- 제공자·모델 선택과 키 (두 모드) ---
//
// **`/api/auth/*` 가 아니다.** 그 라우터는 cloud 전용이라 로컬에서는 404 였다 —
// 로컬에서도 cloud LLM 을 고를 수 있어야 하므로 두 모드가 쓰는 자리로 옮겼다 (M12-T4).

export const getSettings = () => request<AccountSettings>('/api/account/settings')

/** 쓸 제공자와 모델을 고른다. **저장하는 순간부터 모든 작업이 그것으로 간다.** */
export const chooseModel = (provider: string, model = '') =>
  request<AccountSettings>('/api/account/settings', {
    method: 'PUT',
    body: JSON.stringify({ provider, model }),
  })

export const saveApiKey = (apiKey: string, provider = '') =>
  request<AccountSettings>('/api/account/api-key', {
    method: 'PUT',
    body: JSON.stringify({ api_key: apiKey, provider }),
  })

export const removeApiKey = (provider = '') =>
  request<AccountSettings>(
    `/api/account/api-key${provider ? `?provider=${encodeURIComponent(provider)}` : ''}`,
    { method: 'DELETE' },
  )

// --- 저장 데이터 ---

export const listHistory = () => request<HistoryItem[]>('/api/history')
export const getHistoryDetail = (id: number) => request<HistoryDetail>(`/api/history/${id}`)
export const deleteHistory = (id: number) =>
  request<{ ok: boolean }>(`/api/history/${id}`, { method: 'DELETE' })

// --- 나의 표현 (서버에서는 vocabulary) ---

export const listVocabulary = () => request<VocabularyItem[]>('/api/vocabulary')

/** 제외. **그 표현의 직접 써본 기록도 함께 사라진다** — 확인은 화면이 먼저 받는다. */
export const deleteVocabulary = (id: number) =>
  request<VocabularyRemoval>(`/api/vocabulary/${id}`, { method: 'DELETE' })

export function addVocabulary(item: {
  expression: string
  type?: string
  meaning?: string
  example?: string
  example_ko?: string
  source_text?: string
}) {
  return request<VocabularyItem>('/api/vocabulary', {
    method: 'POST',
    body: JSON.stringify(item),
  })
}

/** 직접 써본 기록. `expression` 을 주면 그 표현 것만 가져온다. */
export function listPracticeHistory(expression?: string) {
  const query = expression ? `?expression=${encodeURIComponent(expression)}` : ''
  return request<PracticeHistoryItem[]>(`/api/practice/history${query}`)
}

// --- 데이터 삭제와 탈퇴 (03-api-spec.md) ---

/** 지우기 전에 무엇이 몇 건 사라지는지. */
export const getMyDataCounts = () => request<DeletionSummary>('/api/account/data')

/** 기록 전부 삭제. 계정은 남는다 — 두 모드 공통. */
export const purgeMyData = () =>
  request<DeletionSummary>('/api/account/data', { method: 'DELETE' })

/** 탈퇴. cloud 에만 있는 경로다 (09-mode-matrix.md §3.6). */
export const leaveService = () =>
  request<DeletionSummary>('/api/auth/account', { method: 'DELETE' })
