import { useEffect, useRef, useState } from 'react'

import { HistoryList } from './components/HistoryList'
import { InputPanel } from './components/InputPanel'
import { ResultView } from './components/ResultView'
import { StatusBar } from './components/StatusBar'
import { initialState, reduce, type AnalysisState } from './lib/analysis'
import { ApiError, analyzeStream, health as fetchHealth } from './lib/api'
import { addEntry, loadHistory, type HistoryEntry } from './lib/history'
import type { Level, LlmHealth } from './lib/types'

export default function App() {
  const [text, setText] = useState('')
  const [level, setLevel] = useState<Level>('intermediate')
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)
  const [analysis, setAnalysis] = useState<AnalysisState | null>(null)
  const [history, setHistory] = useState<HistoryEntry[]>(() => loadHistory())
  const [activeId, setActiveId] = useState<string | null>(null)
  const [llmHealth, setLlmHealth] = useState<LlmHealth | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    fetchHealth()
      .then((h) => setLlmHealth(h.llm))
      .catch(() => setLlmHealth({ reachable: false, base_url: '백엔드 미응답', models: [] }))
    return () => abortRef.current?.abort()
  }, [])

  async function handleSubmit() {
    const trimmed = text.trim()
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller

    setRunning(true)
    setError(null)
    setActiveId(null)

    // 파트가 도착할 때마다 화면을 갱신한다.
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
        const next = addEntry(history, state)
        setHistory(next)
        setActiveId(next[0]?.id ?? null)
      }
    } catch (e) {
      setError(e instanceof ApiError ? e : new ApiError('unknown', '알 수 없는 오류입니다.'))
      setAnalysis(null)
    } finally {
      setRunning(false)
    }
  }

  function handleSelectHistory(entry: HistoryEntry) {
    abortRef.current?.abort()
    setRunning(false)
    setText(entry.text)
    setAnalysis(entry.state)
    setActiveId(entry.id)
    setError(null)
  }

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6 px-4 py-8 sm:px-6">
      <header className="flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-semibold tracking-tight">English Study Assistant</h1>
        <p className="hidden text-sm text-stone-400 sm:block">
          영어 문장을 번역 · 표현 · 구조 · 총평으로 정리합니다
        </p>
        <div className="ml-auto">
          <StatusBar health={llmHealth} />
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
              {error.code === 'llm_unavailable' && (
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
