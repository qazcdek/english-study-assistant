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
import { legalReady } from './legal/operator'
import { Privacy } from './legal/Privacy'
import { Terms } from './legal/Terms'
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
import { useIsWide } from './lib/useIsWide'
import { useSession } from './lib/useSession'
import { useVocabulary } from './lib/useVocabulary'
import type { Level, LlmHealth } from './lib/types'

/** 주소와 화면의 짝. 한 곳에만 둔다 — 흩어지면 주소와 화면이 어긋난다. */
const PATHS = {
  analyze: '/',
  mine: '/mine',
  terms: '/terms',
  privacy: '/privacy',
} as const

type View = keyof typeof PATHS

function viewOf(pathname: string): View {
  const found = (Object.keys(PATHS) as View[]).find((key) => PATHS[key] === pathname)
  return found ?? 'analyze'
}

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
  // 어느 화면을 보고 있나. 법적 문서 둘은 **주소로 들어올 수 있어야 한다** —
  // Google OAuth 심사가 개인정보처리방침 URL 을 요구한다. 라우터를 들이지 않고
  // SPA 폴백 + history API 로 해결한다 (07 §5.1 이 같은 오리진을 쓰는 덕이다).
  const [view, setView] = useState<View>(() => viewOf(window.location.pathname))
  const abortRef = useRef<AbortController | null>(null)
  // 같은 문구를 연달아 띄워도 다시 나타나야 해서, 띄운 시각을 key 로 쓴다.
  const [toast, setToast] = useState<{ message: string; at: number } | null>(null)
  // 좁은 화면에서 기록 목록을 펼쳤나. 기본은 접힘 — 본문 위를 막지 않는다.
  const [historyOpen, setHistoryOpen] = useState(false)

  const ready = session.stage === 'ready' || session.stage === 'local'

  const wide = useIsWide()

  /** 화면을 옮기고 주소도 맞춘다. 뒤로 가기가 동작해야 법적 문서를 링크할 수 있다. */
  const go = useCallback((next: View) => {
    setView(next)
    const path = PATHS[next]
    if (window.location.pathname !== path) window.history.pushState({}, '', path)
  }, [])

  useEffect(() => {
    const onPop = () => setView(viewOf(window.location.pathname))
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
  }, [])
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
    go('analyze')

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
    go('analyze')

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
    } catch (e) {
      // 서버가 무엇이 틀렸는지 말해 준다 — `not_found` 면 "찾을 수 없습니다" 다.
      // 전부 같은 문구로 덮으면 404 를 구별해 준 의미가 없어진다 (H-012).
      setError(e instanceof ApiError ? e : new ApiError('unknown', '기록을 불러오지 못했습니다.'))
      // 목록에만 남은 유령 항목을 고른 경우다. 목록을 다시 읽어 치운다.
      await reloadServerHistory()
      setActiveId(null)
    }
  }

  // ------------------------------------------------------------ 로그인 전 화면

  if (session.stage === 'loading') {
    return <p className="p-10 text-center text-sm text-stone-400">불러오는 중…</p>
  }

  if (view === 'terms' || view === 'privacy') {
    // **로그인 전에도 열려야 한다.** 동의 화면이 이 둘을 가리키고, Google OAuth 심사도
    // 로그인 없이 방침 URL 을 열어 본다.
    return (
      <div className="mx-auto max-w-3xl px-4 py-10 sm:px-6">
        {view === 'terms' ? (
          <Terms onBack={() => go('analyze')} />
        ) : (
          <Privacy onBack={() => go('analyze')} />
        )}
      </div>
    )
  }

  if (session.stage !== 'ready' && session.stage !== 'local') {
    return (
      <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
        {session.stage === 'login' && <LoginPanel error={session.error} />}
        {session.stage === 'consent' && session.config && (
          <ConsentPanel
            config={session.config}
            onAgree={async () => session.setAccount(await giveConsent())}
            onOpenTerms={() => go('terms')}
            onOpenPrivacy={() => go('privacy')}
          />
        )}
        {session.stage === 'api-key' && session.config && (
          <ApiKeyPanel config={session.config} onSaved={session.setAccount} />
        )}
      </div>
    )
  }

  // 좁은 화면과 넓은 화면이 **같은 목록**을 쓴다. 두 벌을 쓰면 갈라진다.
  const historyList = (
    <HistoryList
      entries={history}
      activeId={activeId}
      onSelect={handleSelectHistory}
      onDelete={handleDeleteHistory}
    />
  )

  // ------------------------------------------------------------ 본 화면

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6 px-4 py-8 sm:px-6">
      <Toast key={toast?.at} message={toast?.message ?? null} />
      <header className="flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-semibold tracking-tight">English Study Assistant</h1>
        <p className="hidden text-sm text-stone-400 sm:block">
          영어 문장을 번역 · 표현 · 구조 · 총평으로 정리합니다
        </p>
        <div className="ml-auto flex flex-wrap items-center justify-end gap-2 sm:gap-3">
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
                onClick={() => go(key)}
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
        <main className="flex min-w-0 flex-col gap-4">
          {view === 'mine' ? (
            <MyExpressions vocab={vocab} level={level} />
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

        {/* 좁은 화면에서는 이 칸이 **본문 위**에 온다(order-first). 늘 펼쳐 두면 분석
            화면에 들어올 때마다 기록부터 지나가야 한다. 그래서 좁을 때만 접는다.
            넓을 때는 옆 칸이라 길을 막지 않으므로 그대로 펼쳐 둔다. */}
        <aside className="order-first min-w-0 lg:order-none">
          {wide ? (
            <>
              <h2 className="mb-2 px-2 text-xs font-medium uppercase tracking-wide text-stone-400">
                최근 분석
              </h2>
              {historyList}
            </>
          ) : (
            <>
              <button
                type="button"
                onClick={() => setHistoryOpen((v) => !v)}
                aria-expanded={historyOpen}
                className="flex w-full items-center gap-2 rounded-lg border border-stone-200 px-3 py-2 text-xs text-stone-500 transition hover:bg-stone-100 dark:border-stone-800 dark:hover:bg-stone-800"
              >
                {historyOpen ? '접기' : '이전 기록 보기'}
                {history.length > 0 && (
                  <span className="rounded-full bg-stone-100 px-1.5 text-[11px] text-stone-500 dark:bg-stone-800">
                    {history.length}
                  </span>
                )}
                <span className="ml-auto">{historyOpen ? '▴' : '▾'}</span>
              </button>
              {historyOpen && <div className="mt-2">{historyList}</div>}
            </>
          )}
        </aside>
      </div>

      {/* 운영자 정보가 비어 있으면 **링크를 걸지 않는다** — 빈칸이 든 법적 문서를
          사용자가 보는 쪽이 안 보이는 쪽보다 나쁘다 (legal/operator.ts). */}
      {legalReady() && (
        <footer className="flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-stone-100 pt-4 text-xs text-stone-400 dark:border-stone-800">
          <button type="button" onClick={() => go('terms')} className="hover:text-stone-600 dark:hover:text-stone-300">
            이용약관
          </button>
          <span aria-hidden>·</span>
          <button type="button" onClick={() => go('privacy')} className="hover:text-stone-600 dark:hover:text-stone-300">
            개인정보처리방침
          </button>
        </footer>
      )}
    </div>
  )
}
