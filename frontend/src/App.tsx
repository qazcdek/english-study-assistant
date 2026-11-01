import { useCallback, useEffect, useRef, useState } from 'react'

import { AccountBar } from './components/AccountBar'
import { DataMenu } from './components/DataMenu'
import { Gate } from './components/Gate'
import { HistoryList } from './components/HistoryList'
import { InputPanel } from './components/InputPanel'
import { MyExpressions } from './components/MyExpressions'
import { ResultView } from './components/ResultView'
import { StatusBar } from './components/StatusBar'
import { TidyButton } from './components/TidyButton'
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
  health as fetchHealth,
  listHistory,
} from './lib/api'
import type { HistoryEntry } from './lib/history'
import { pathOf, routeOf, type Route, type View } from './lib/routes'
import { useIsWide } from './lib/useIsWide'
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
  const [llmHealth, setLlmHealth] = useState<LlmHealth | null>(null)
  // **어느 화면을 보고 있나는 주소가 정한다.** 화면 상태를 따로 들면 둘이 어긋나고,
  // 어긋나면 뒤로 가기가 엉뚱한 데로 간다. 짝은 `lib/routes.ts` 한 곳에 있다.
  const [route, setRoute] = useState<Route>(() => routeOf(window.location.pathname))
  const view = route.view
  const activeId = route.recordId
  const abortRef = useRef<AbortController | null>(null)
  // 지금 띄워 둔 기록. **주소가 바뀌었는지 비교하는 데만** 쓴다.
  const shownRef = useRef<string | null>(null)
  // 같은 문구를 연달아 띄워도 다시 나타나야 해서, 띄운 시각을 key 로 쓴다.
  const [toast, setToast] = useState<{ message: string; at: number } | null>(null)
  // 좁은 화면에서 기록 목록을 펼쳤나. 기본은 접힘 — 본문 위를 막지 않는다.
  const [historyOpen, setHistoryOpen] = useState(false)

  // **두 가지를 구분한다.** 저장된 기록과 나의 표현을 읽는 데에는 키가 필요 없다
  // (`deps.session_user` 가 신원만 본다). 키가 필요한 것은 LLM 을 부를 때다.
  // 하나로 묶어 두면 키가 없는 회원에게서 **자기 기록까지 숨긴다** (H-041).
  const identified =
    session.stage === 'ready' || session.stage === 'local' || session.stage === 'api-key'
  const canAnalyze = session.stage === 'ready' || session.stage === 'local'
  // 키 단계를 넘겨 뒀나. 넘겨도 분석은 안 된다 — 보이는 것이 늘어날 뿐이다.
  const [skipKeyGate, setSkipKeyGate] = useState(false)

  const wide = useIsWide()

  /** 화면을 옮기고 주소도 맞춘다. **옮기는 길은 이 하나다** — 둘이 되면 갈라진다. */
  const go = useCallback((view: View, recordId: string | null = null) => {
    const next = { view, recordId }
    setRoute(next)
    const path = pathOf(next)
    if (window.location.pathname !== path) window.history.pushState({}, '', path)
  }, [])

  useEffect(() => {
    const onPop = () => setRoute(routeOf(window.location.pathname))
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
  }, [])
  // 나의 표현은 두 화면이 함께 본다 — 분석 화면의 별과 목록이 어긋나지 않게 한 곳에서 든다.
  const vocab = useVocabulary(identified)

  useEffect(() => {
    if (!identified) return
    fetchHealth()
      .then((h) => setLlmHealth(h.llm))
      .catch(() => setLlmHealth({ reachable: false, base_url: '백엔드 미응답', models: [] }))
    return () => abortRef.current?.abort()
  }, [identified])

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
    if (!identified) return
    void reloadServerHistory()
  }, [identified, reloadServerHistory])

  async function handleSubmit() {
    const trimmed = text.trim()
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller

    setRunning(true)
    setError(null)
    // 새 분석이다. 주소가 기록을 안 가리키므로 **효과가 방금 띄운 결과를 지우지
    // 않게** 띄워 둔 기록을 먼저 비운다 — 안 비우면 빈 화면이 된다.
    shownRef.current = null
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
    // 보고 있던 항목을 지웠다면 주소도 되돌린다 — 결과 화면은 효과가 비운다.
    if (entry.id === activeId) go('analyze')
  }

  /**
   * 주소가 가리키는 기록을 띄운다.
   *
   * **목록에서 골랐을 때·뒤로 갔을 때·링크로 처음 들어왔을 때가 모두 이 길을
   * 지난다.** 전에는 "고를 때 가져온다" 가 목록 항목에만 붙어 있어서, 주소로는
   * 아무것도 열 수 없었다 (H-038).
   */
  const loadRecord = useCallback(
    async (id: string) => {
      abortRef.current?.abort()
      setRunning(false)
      setError(null)

      // 목록에는 본문이 없다. 열 때 가져온다 — 링크로 들어오면 목록조차 없다.
      try {
        const detail = await getHistoryDetail(Number(id))
        setText(detail.source_text)
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
        setError(
          e instanceof ApiError ? e : new ApiError('unknown', '기록을 불러오지 못했습니다.'),
        )
        // 목록에만 남은 유령 항목이다. 목록을 다시 읽고 **주소도 되돌린다.**
        await reloadServerHistory()
        go('analyze')
      }
    },
    [reloadServerHistory, go],
  )

  useEffect(() => {
    // cloud 는 로그인·동의를 지나야 기록을 읽을 수 있다. 링크로 들어왔으면 기다린다.
    if (!identified) return
    if (route.recordId === shownRef.current) return
    shownRef.current = route.recordId
    if (route.recordId) void loadRecord(route.recordId)
    else setAnalysis(null)
  }, [identified, route.recordId, loadRecord])

  function handleSelectHistory(entry: HistoryEntry) {
    // 본문은 목록이 들고 있으니 먼저 비춘다. 나머지는 주소가 부른다.
    setText(entry.text)
    go('analyze', entry.id)
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

  // 키 단계는 **넘길 수 있다.** 로그인과 동의는 못 넘긴다 — 신원과 법적 근거다.
  const atGate = !canAnalyze && !(session.stage === 'api-key' && skipKeyGate)
  if (atGate) {
    return (
      <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
        {/* 분기는 `Gate` 가 든다 — 틀리면 사용자가 갇히는 판단이라 검사가 닿아야
            한다 (H-039). `next` 로 **보던 주소로 돌아온다** (H-038). */}
        <Gate
          session={session}
          next={pathOf(route)}
          onOpenTerms={() => go('terms')}
          onOpenPrivacy={() => go('privacy')}
          onSkipKey={() => setSkipKeyGate(true)}
        />
      </div>
    )
  }

  // 기록이 하나뿐이면 정리할 것이 없다. 버튼을 보여 줄 이유도 없다.
  const tidyButton = (
    <TidyButton
      onTidied={async (removed) => {
        if (removed > 0) await reloadServerHistory()
        setToast({
          message:
            removed > 0
              ? `중복 기록 ${removed}건을 정리했습니다`
              : removed === 0
                ? '정리할 중복 기록이 없습니다'
                : '정리하지 못했습니다',
          at: Date.now(),
        })
      }}
    />
  )

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
          {!cloud && identified && (
            <DataMenu
              config={session.config}
              settings={session.settings}
              onSettingsChanged={session.setSettings}
            />
          )}
          {cloud && session.account && (
            <AccountBar
              account={session.account}
              usage={session.usage}
              config={session.config!}
              settings={session.settings}
              onChanged={session.setAccount}
              onSettingsChanged={session.setSettings}
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
          {!canAnalyze && (
            // **분석만 막혀 있다.** 기록과 나의 표현은 위아래로 그대로 보인다.
            <div className="flex flex-wrap items-center gap-3 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-200">
              <p className="min-w-0 flex-1">
                API 키가 없어 <b>새 분석만</b> 시작되지 않습니다. 이전 기록과 나의 표현은
                그대로 보실 수 있습니다.
              </p>
              <button
                type="button"
                onClick={() => setSkipKeyGate(false)}
                className="shrink-0 rounded-lg bg-amber-600 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-amber-500"
              >
                키 등록하기
              </button>
            </div>
          )}

          <InputPanel
            text={text}
            level={level}
            loading={running}
            onTextChange={setText}
            maxChars={session.config?.max_input_chars}
            onLevelChange={setLevel}
            // 키가 없으면 **오류를 보여주는 대신 등록 화면으로 보낸다.**
            onSubmit={canAnalyze ? handleSubmit : () => setSkipKeyGate(false)}
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
              <div className="mb-2 flex items-center gap-2 px-2">
                <h2 className="text-xs font-medium uppercase tracking-wide text-stone-400">
                  최근 분석
                </h2>
                {history.length > 1 && <span className="ml-auto">{tidyButton}</span>}
              </div>
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
              {historyOpen && (
                <div className="mt-2 flex flex-col gap-2">
                  {history.length > 1 && <div className="self-end">{tidyButton}</div>}
                  {historyList}
                </div>
              )}
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
