export type Level = 'beginner' | 'intermediate' | 'advanced'

export type ExpressionType =
  | '고급 어휘'
  | '관용구'
  | 'Phrasal Verb'
  | '연어(Collocation)'
  | '문법 포인트'
  | '구어 표현'
  | '전문 용어'

export interface Expression {
  expression: string
  type: ExpressionType
  /** 한국어 대역어 한두 개 */
  meaning: string
  /** 어떤 상황에서 쓰는지·뉘앙스. 초급에서는 비어 있다. */
  nuance?: string
  example?: string | null
  /** example 의 한국어 뜻. 작문 연습의 제시문으로 쓴다. */
  example_ko?: string | null
}

export interface StructureNote {
  fragment: string
  /** 구조 이름 (표준 문법 용어) */
  name: string
  /** 이 문장에서 그 구조가 하는 일 */
  role: string
  /** 쉬운 말로 바꿔 쓴 등가 영어 표현. 없을 수 있다. */
  rewrite: string
  /** 한국어 화자가 놓치기 쉬운 지점. 없을 수 있다. */
  pitfall: string
}

export interface Overview {
  domain: string
  tone: string
  formality: '매우 격식' | '격식' | '중립' | '비격식' | '속어에 가까움'
  style: '문어체' | '구어체' | '혼합'
  key_expressions: string[]
  comment: string
}

export const PART_FIELDS = ['translation', 'expressions', 'structures', 'overview'] as const
export type PartField = (typeof PART_FIELDS)[number]

export const PART_TITLES: Record<PartField, string> = {
  translation: '자연스러운 번역',
  expressions: '표현 풀이',
  structures: '문장 구조',
  overview: '총평',
}

/** 파트별로 채워지므로 실패한 파트는 비어 있을 수 있다. */
export interface AnalysisResult {
  source_text: string
  translation: string
  expressions: Expression[]
  structures: StructureNote[]
  overview: Overview | null
}

export interface MarkdownSections {
  translation: string
  expressions: string
  structures: string
  overview: string
  full: string
}

export interface AnalyzeMeta {
  model: string
  elapsed_ms: number
  retried_parts: string[]
  failed_parts: string[]
}

export interface AnalyzeResponse {
  result: AnalysisResult
  markdown: MarkdownSections
  meta: AnalyzeMeta
}

// --- SSE 이벤트 ---

export interface PartEvent {
  type: 'part'
  field: PartField
  title: string
  index: number
  total: number
  data: Record<string, unknown>
  markdown: string
  elapsed_ms: number
  retried: boolean
}

export interface PartErrorEvent {
  type: 'part_error'
  field: PartField
  title: string
  index: number
  total: number
  code: string
  message: string
  detail?: string | null
}

export interface DoneEvent {
  type: 'done'
  result: AnalysisResult
  markdown: MarkdownSections
  meta: AnalyzeMeta
}

export interface StreamErrorEvent {
  type: 'error'
  code: string
  message: string
  detail?: string | null
}

export type StreamEvent = PartEvent | PartErrorEvent | DoneEvent | StreamErrorEvent

export interface LlmHealth {
  reachable: boolean
  base_url: string
  models: string[]
  detail?: string | null
}

export interface HealthResponse {
  status: 'ok'
  llm: LlmHealth
}

// --- 작문 연습 ---

export type Verdict = '정확함' | '통함' | '다시'

export interface PracticeRequest {
  expression: string
  meaning: string
  prompt_ko: string
  model_answer: string
  learner_answer: string
  level: Level
}

export interface PracticeResult {
  verdict: Verdict
  uses_target: boolean
  good_point: string
  target_note: string
  corrected: string
  other_notes: string[]
}

export interface PracticeResponse {
  result: PracticeResult
  model_answer: string
  meta: AnalyzeMeta
}

// --- 앱 설정 / 계정 (cloud 모드) ---

export interface AppConfig {
  mode: 'local' | 'cloud'
  requires_login: boolean
  model: string
  daily_analysis_limit: number
  daily_practice_limit: number
  api_key_issue_url: string
  max_input_chars: number
}

export interface Account {
  email: string
  name: string
  picture: string
  has_consented: boolean
  has_api_key: boolean
  api_key_hint: string
}

export interface Usage {
  day: string
  analyses: number
  practices: number
  analysis_limit: number
  practice_limit: number
}

export interface HistoryItem {
  id: number
  source_text: string
  level: Level
  created_at: string
  failed_parts: string[]
}

export interface HistoryDetail extends HistoryItem {
  result: AnalysisResult
  markdown: MarkdownSections
}

export interface VocabularyItem {
  id: number
  expression: string
  type: string
  meaning: string
  example: string
  example_ko: string
  source_text: string
  created_at: string
}
