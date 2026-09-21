import { useEffect, useRef, useState } from 'react'

import { AccountBar } from './components/AccountBar'
import { ApiKeyPanel } from './components/ApiKeyPanel'
import { ConsentPanel } from './components/ConsentPanel'
import { HistoryList } from './components/HistoryList'
import { InputPanel } from './components/InputPanel'
import { LoginPanel } from './components/LoginPanel'
import { ResultView } from './components/ResultView'
import { StatusBar } from './components/StatusBar'
import { initialState, reduce, type AnalysisState } from './lib/analysis'
import {
  ApiError,
  analyzeStream,
  getHistoryDetail,
  giveConsent,
  health as fetchHealth,
  listHistory,
} from './lib/api'
import { addEntry, loadHistory, type HistoryEntry } from './lib/history'
import { useSession } from './lib/useSession'
import type { Level, LlmHealth } from './lib/types'

export default function App() {
  const session = useSession()
  const cloud = session.config?.requires_login ?? false

  const [text, setText] = useState('')
  const [level, setLevel] = useState<Level>('intermediate')
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)
  const [analysis, setAnalysis] = useState<AnalysisState | null>(null)
  const [history, setHistory] = useState<HistoryEntry[]>(() => loadHistory())
  const [activeId, setActiveId] = useState<string | null>(null)
  const [llmHealth, setLlmHealth] = useState<LlmHealth | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  const ready = session.stage === 'ready' || session.stage === 'local'

  useEffect(() => {
    if (!ready) return
    fetchHealth()
      .then((h) => setLlmHealth(h.llm))
      .catch(() => setLlmHealth({ reachable: false, base_url: '백엔드 미응답', models: [] }))
    return () => abortRef.current?.abort()
  }, [ready])

  // 웹 모드는 히스토리를 서버에서 가져와 기기 간 동기화한다.
  useEffect(() => {
    if (session.stage !== 'ready') return
    void listHistory()
      .then((rows) =>
        setHistory(
          rows.map((r) => ({
            id: String(r.id),
            text: r.source_text,
            createdAt: Date.parse(r.created_at) || Date.now(),
            state: null,
          })),
        ),
      )
      .catch(() => {})
  }, [session.stage])

  async function handleSubmit() {
    const trimmed = text.trim()
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller

    setRunning(true)
    setError(null)
    setActiveId(null)

    let state = initialState(trimmed)
    setAnalysis(state)

    try {
      await analyzeStream(
        trimmed,
        level,
        (event) => {
          state = reduce(state, event)
          setAnalysis(state)
        },
        controller.signal,
      )
      if (!controller.signal.aborted) {
        if (cloud) {
          void session.refreshUsage()
          void listHistory().then((rows) =>
            setHistory(
              rows.map((r) => ({
                id: String(r.id),
                text: r.source_text,
                createdAt: Date.parse(r.created_at) || Date.now(),
                state: null,
              })),
            ),
          )
        } else {
          const next = addEntry(history, state)
          setHistory(next)
          setActiveId(next[0]?.id ?? null)
        }
      }
    } catch (e) {
      setError(e instanceof ApiError ? e : new ApiError('unknown', '알 수 없는 오류입니다.'))
      setAnalysis(null)
    } finally {
      setRunning(false)
    }
  }

  async function handleSelectHistory(entry: HistoryEntry) {
    abortRef.current?.abort()
    setRunning(false)
    setText(entry.text)
    setActiveId(entry.id)
    setError(null)

    if (entry.state) {
      setAnalysis(entry.state)
      return
    }
    // 서버 히스토리는 목록에 본문이 없다. 고를 때 가져온다.
    try {
      const detail = await getHistoryDetail(Number(entry.id))
      setAnalysis({
        result: detail.result,
        markdown: detail.markdown,
        fullMarkdown: detail.markdown.full,
        status: {
          translation: { state: 'done' },
          expressions: { state: 'done' },
          structures: { state: 'done' },
          overview: { state: 'done' },
        },
      })
    } catch {
      setError(new ApiError('unknown', '기록을 불러오지 못했습니다.'))
    }
  }

  // ------------------------------------------------------------ 로그인 전 화면

  if (session.stage === 'loading') {
    return <p className="p-10 text-center text-sm text-stone-400">불러오는 중…</p>
  }

  if (session.stage !== 'ready' && session.stage !== 'local') {
    return (
      <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
        {session.stage === 'login' && <LoginPanel error={session.error} />}
        {session.stage === 'consent' && session.config && (
          <ConsentPanel
            config={session.config}
            onAgree={async () => session.setAccount(await giveConsent())}
          />
        )}
        {session.stage === 'api-key' && session.config && (
          <ApiKeyPanel config={session.config} onSaved={session.setAccount} />
        )}
      </div>
    )
  }

  // ------------------------------------------------------------ 본 화면

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6 px-4 py-8 sm:px-6">
      <header className="flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-semibold tracking-tight">English Study Assistant</h1>
        <p className="hidden text-sm text-stone-400 sm:block">
          영어 문장을 번역 · 표현 · 구조 · 총평으로 정리합니다
        </p>
        <div className="ml-auto flex items-center gap-3">
          {!cloud && <StatusBar health={llmHealth} />}
          {cloud && session.account && (
            <AccountBar
              account={session.account}
              usage={session.usage}
              onChanged={session.setAccount}
            />
          )}
        </div>
      </header>

      <div className="grid gap-6 lg:grid-cols-[1fr_200px]">
        <main className="flex flex-col gap-4">
          <InputPanel
            text={text}
            level={level}
            loading={running}
            onTextChange={setText}
            onLevelChange={setLevel}
            onSubmit={handleSubmit}
          />

          {error && (
            <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/40 dark:text-red-300">
              <p className="font-medium">{error.message}</p>
              {error.detail && (
                <p className="mt-1 font-mono text-xs opacity-70">{error.detail.slice(0, 300)}</p>
              )}
              {error.code === 'llm_unavailable' && !cloud && (
                <p className="mt-2 font-mono text-xs opacity-70">
                  llama-server -m model.gguf -c 8192 --host 127.0.0.1 --port 8080
                </p>
              )}
            </div>
          )}

          {analysis && <ResultView state={analysis} level={level} />}

          {!analysis && !error && (
            <div className="rounded-2xl border border-dashed border-stone-300 p-10 text-center text-sm text-stone-400 dark:border-stone-700">
              분석할 영어 문장을 위에 붙여넣고 <b>분석하기</b>를 눌러 주세요.
            </div>
          )}
        </main>

        <aside className="order-first lg:order-none">
          <h2 className="mb-2 px-2 text-xs font-medium uppercase tracking-wide text-stone-400">
            최근 분석
          </h2>
          <HistoryList entries={history} activeId={activeId} onSelect={handleSelectHistory} />
        </aside>
      </div>
    </div>
  )
}
