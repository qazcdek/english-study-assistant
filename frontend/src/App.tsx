import { useCallback, useEffect, useRef, useState } from 'react'

import { AccountBar } from './components/AccountBar'
import { ApiKeyPanel } from './components/ApiKeyPanel'
import { ConsentPanel } from './components/ConsentPanel'
import { DataMenu } from './components/DataMenu'
import { HistoryList } from './components/HistoryList'
import { InputPanel } from './components/InputPanel'
import { LoginPanel } from './components/LoginPanel'
import { MyExpressions } from './components/MyExpressions'
import { ResultView } from './components/ResultView'
import { StatusBar } from './components/StatusBar'
import { MIN_CHARS } from './components/InputPanel'
import { Toast } from './components/Toast'
import { initialState, reduce, type AnalysisState } from './lib/analysis'
import {
  ApiError,
  analyzeStream,
  deleteHistory,
  getHistoryDetail,
  giveConsent,
  health as fetchHealth,
  listHistory,
} from './lib/api'
import type { HistoryEntry } from './lib/history'
import { useSession } from './lib/useSession'
import { useVocabulary } from './lib/useVocabulary'
import type { Level, LlmHealth } from './lib/types'

export default function App() {
  const session = useSession()
  const cloud = session.config?.requires_login ?? false

  const [text, setText] = useState('')
  const [level, setLevel] = useState<Level>('intermediate')
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)
  const [analysis, setAnalysis] = useState<AnalysisState | null>(null)
  const [history, setHistory] = useState<HistoryEntry[]>([])
  const [activeId, setActiveId] = useState<string | null>(null)
  const [llmHealth, setLlmHealth] = useState<LlmHealth | null>(null)
  // 분석 화면과 나의 표현 중 어느 쪽을 보고 있나. 주소를 쓰지 않는 한 화면 앱이다.
  const [view, setView] = useState<'analyze' | 'mine'>('analyze')
  const abortRef = useRef<AbortController | null>(null)
  // 같은 문구를 연달아 띄워도 다시 나타나야 해서, 띄운 시각을 key 로 쓴다.
  const [toast, setToast] = useState<{ message: string; at: number } | null>(null)

  const ready = session.stage === 'ready' || session.stage === 'local'
  // 나의 표현은 두 화면이 함께 본다 — 분석 화면의 별과 목록이 어긋나지 않게 한 곳에서 든다.
  const vocab = useVocabulary(ready)

  useEffect(() => {
    if (!ready) return
    fetchHealth()
      .then((h) => setLlmHealth(h.llm))
      .catch(() => setLlmHealth({ reachable: false, base_url: '백엔드 미응답', models: [] }))
    return () => abortRef.current?.abort()
  }, [ready])

  // 웹 모드는 히스토리를 서버에서 가져와 기기 간 동기화한다.
  const reloadServerHistory = useCallback(async () => {
    try {
      const rows = await listHistory()
      setHistory(
        rows.map((r) => ({
          id: String(r.id),
          text: r.source_text,
          createdAt: Date.parse(r.created_at) || Date.now(),
          state: null,
          level: r.level,
        })),
      )
    } catch {
      // 목록 갱신 실패로 분석 자체를 막을 필요는 없다.
    }
  }, [])

  useEffect(() => {
    // 두 모드 모두 기록은 서버에 있다. cloud 는 로그인·키 등록까지 끝나야 읽을 수 있다.
    if (session.stage !== 'ready' && session.stage !== 'local') return
    void reloadServerHistory()
  }, [session.stage, reloadServerHistory])

  async function handleSubmit() {
    const trimmed = text.trim()
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller

    setRunning(true)
    setError(null)
    setActiveId(null)
    // 나의 표현을 보던 중에 분석을 시작하면 결과가 안 보인다.
    setView('analyze')

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
        if (cloud) void session.refreshUsage()
        await reloadServerHistory()
      }
    } catch (e) {
      setError(e instanceof ApiError ? e : new ApiError('unknown', '알 수 없는 오류입니다.'))
      setAnalysis(null)
    } finally {
      setRunning(false)
    }
  }

  async function handleDeleteHistory(entry: HistoryEntry) {
    try {
      await deleteHistory(Number(entry.id))
    } catch (e) {
      setError(e instanceof ApiError ? e : new ApiError('unknown', '삭제하지 못했습니다.'))
      return
    }
    await reloadServerHistory()
    // 보고 있던 항목을 지웠다면 결과 화면도 비운다.
    if (entry.id === activeId) {
      setActiveId(null)
      setAnalysis(null)
    }
  }

  async function handleSelectHistory(entry: HistoryEntry) {
    abortRef.current?.abort()
    setRunning(false)
    setText(entry.text)
    setActiveId(entry.id)
    setError(null)
    setView('analyze')

    // 목록에는 본문이 없다. 고를 때 가져온다.
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
      <Toast key={toast?.at} message={toast?.message ?? null} />
      <header className="flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-semibold tracking-tight">English Study Assistant</h1>
        <p className="hidden text-sm text-stone-400 sm:block">
          영어 문장을 번역 · 표현 · 구조 · 총평으로 정리합니다
        </p>
        <div className="ml-auto flex items-center gap-3">
          <nav className="flex items-center gap-1 rounded-lg bg-stone-100 p-0.5 text-xs dark:bg-stone-800">
            {(
              [
                ['analyze', '분석'],
                ['mine', '나의 표현'],
              ] as const
            ).map(([key, label]) => (
              <button
                key={key}
                type="button"
                onClick={() => setView(key)}
                aria-current={view === key}
                className={`rounded-md px-2.5 py-1 transition ${
                  view === key
                    ? 'bg-white font-medium text-stone-900 shadow-sm dark:bg-stone-950 dark:text-stone-100'
                    : 'text-stone-500 hover:text-stone-700 dark:hover:text-stone-300'
                }`}
              >
                {label}
                {key === 'mine' && vocab.items.length > 0 && (
                  <span className="ml-1 text-stone-400">{vocab.items.length}</span>
                )}
              </button>
            ))}
          </nav>
          {!cloud && <StatusBar health={llmHealth} />}
          {!cloud && ready && <DataMenu />}
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
          {view === 'mine' ? (
            <MyExpressions vocab={vocab} />
          ) : (
            <>
          <InputPanel
            text={text}
            level={level}
            loading={running}
            onTextChange={setText}
            maxChars={session.config?.max_input_chars}
            onLevelChange={setLevel}
            onSubmit={handleSubmit}
            onTooShort={() => setToast({ message: `${MIN_CHARS}자 이상 입력해 주세요`, at: Date.now() })}
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

          {analysis && <ResultView state={analysis} level={level} vocab={vocab} />}

          {!analysis && !error && (
            <div className="rounded-2xl border border-dashed border-stone-300 p-10 text-center text-sm text-stone-400 dark:border-stone-700">
              분석할 영어 문장을 위에 붙여넣고 <b>분석하기</b>를 눌러 주세요.
            </div>
          )}
            </>
          )}
        </main>

        <aside className="order-first lg:order-none">
          <h2 className="mb-2 px-2 text-xs font-medium uppercase tracking-wide text-stone-400">
            최근 분석
          </h2>
          <HistoryList
            entries={history}
            activeId={activeId}
            onSelect={handleSelectHistory}
            onDelete={handleDeleteHistory}
          />
        </aside>
      </div>
    </div>
  )
}
