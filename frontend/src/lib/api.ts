import type {
  HealthResponse,
  Level,
  PracticeRequest,
  PracticeResponse,
  StreamEvent,
} from './types'

const BASE = import.meta.env.VITE_API_BASE ?? ''

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
    })
  } catch {
    throw new ApiError('network', '백엔드 서버에 연결할 수 없습니다.')
  }

  if (!response.ok) throw await parseError(response)
  return response.json()
}

export async function health(): Promise<HealthResponse> {
  const response = await fetch(`${BASE}/api/health`)
  if (!response.ok) throw await parseError(response)
  return response.json()
}
