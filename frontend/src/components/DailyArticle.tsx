import { useCallback, useEffect, useState } from 'react'

import { finishedState, type AnalysisState } from '../lib/analysis'
import { ApiError, getDailyArticle, getParagraphAnalysis } from '../lib/api'
import type { DailyArticle as Article, DailyParagraph, Level } from '../lib/types'
import type { VocabularyStore } from '../lib/useVocabulary'
import { ResultView } from './ResultView'

/** 펼쳐 본 문단 하나. **응답이 준 모델 이름을 함께 들고 있는다** — 머리줄이 적는다.
 *
 *  전에는 난이도도 들고 있었는데 `M16` 이 분석에서 난이도를 걷어냈다. */
interface Prepared {
  state: AnalysisState
  model: string
}

/**
 * 오늘의 글감 — **모든 회원이 같은 문단별 분석을 본다** (M13-T6).
 *
 * ### 본문과 분석을 따로 가져온다
 *
 * 한 편을 통째로 받으면 128KB 다 (`result` 49KB + `markdown` 82KB, 16문단 실측).
 * 읽는 흐름도 한 문단씩이므로 **본문만 먼저** 받고 펼칠 때 하나를 가져온다.
 * 가져온 것은 들고 있어서 접었다 펴도 다시 묻지 않는다.
 *
 * ### 날짜를 숨기지 않는다
 *
 * 오늘 것이 아직 없으면 어제 것이 온다 (09 §3.8). 그러니 "오늘의 글감" 이라고
 * 적고 **적힌 날짜를 함께** 보여준다 — 언제 것인지 모르고 읽는 쪽이 나쁘다.
 *
 * ### 난이도는 예문에만 있다
 *
 * 분석에 난이도가 없다 (M16). 머리줄이 "중급으로 미리 분석" 을 적던 자리가
 * 사라졌고, 회원이 고르는 예문 난이도는 **표현 풀이 표 안에서** 고른다.
 */
export function DailyArticle({
  vocab,
  level,
  onLevelChange,
}: {
  vocab: VocabularyStore
  /** 예문 난이도. 표에서 고른 것을 그대로 흘려보낸다 (M16). */
  level: Level
  onLevelChange: (level: Level) => void
}) {
  const [article, setArticle] = useState<Article | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<ApiError | null>(null)
  // 펼쳐 둔 문단. 하나씩만 펼친다 — 읽는 순서가 하나라서다.
  const [open, setOpen] = useState<number | null>(null)
  // 가져온 분석. **접어도 버리지 않는다** — 다시 펴면 또 묻게 된다.
  const [analyses, setAnalyses] = useState<Record<number, Prepared>>({})
  const [pending, setPending] = useState<number | null>(null)
  const [partError, setPartError] = useState<{ ordinal: number; message: string } | null>(null)

  useEffect(() => {
    let alive = true
    getDailyArticle()
      .then((body) => {
        if (!alive) return
        setArticle(body.article)
      })
      .catch((e) => {
        if (!alive) return
        setError(e instanceof ApiError ? e : new ApiError('unknown', '글감을 불러오지 못했습니다.'))
      })
      .finally(() => {
        if (alive) setLoading(false)
      })
    return () => {
      alive = false
    }
  }, [])

  const toggle = useCallback(
    async (paragraph: DailyParagraph) => {
      if (open === paragraph.ordinal) {
        setOpen(null)
        return
      }
      setOpen(paragraph.ordinal)
      setPartError(null)
      // 아직 준비되지 않은 문단은 **묻지 않는다.** 404 가 날 것을 알고 있다.
      if (!paragraph.prepared || analyses[paragraph.ordinal] || !article) return

      setPending(paragraph.ordinal)
      try {
        const detail = await getParagraphAnalysis(article.id, paragraph.ordinal)
        setAnalyses((kept) => ({
          ...kept,
          [paragraph.ordinal]: {
            state: finishedState(detail.result, detail.markdown, detail.failed_parts),
            model: detail.model,
          },
        }))
      } catch (e) {
        setPartError({
          ordinal: paragraph.ordinal,
          message: e instanceof ApiError ? e.message : '분석을 불러오지 못했습니다.',
        })
      } finally {
        setPending(null)
      }
    },
    [analyses, article, open],
  )

  if (loading) {
    return <p className="p-10 text-center text-sm text-stone-400">글감을 불러오는 중…</p>
  }

  if (error) {
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/40 dark:text-red-300">
        <p className="font-medium">{error.message}</p>
      </div>
    )
  }

  if (!article) {
    // **오류가 아니다.** 아직 한 편도 안 골랐거나 고르는 중에 실패한 상태다.
    return (
      <div className="rounded-2xl border border-dashed border-stone-300 p-10 text-center text-sm text-stone-400 dark:border-stone-700">
        아직 준비된 글감이 없습니다. 하루 한 편이 준비되면 여기에 표시됩니다.
      </div>
    )
  }

  const ready = article.paragraphs.filter((p) => p.prepared).length

  return (
    <div className="flex flex-col gap-4">
      <header className="flex flex-col gap-2 rounded-2xl border border-stone-200 p-5 dark:border-stone-800">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-stone-400">
          <span className="font-medium text-stone-500 dark:text-stone-400">
            {dayLabel(article.picked_for)} 글감
          </span>
          <span aria-hidden>·</span>
          <span>{sourceLabel(article.source)}</span>
          {article.section && (
            <>
              <span aria-hidden>·</span>
              <span>{article.section}</span>
            </>
          )}
          <OriginalLink url={article.url} className="ml-auto" />
        </div>

        <h2 className="text-lg font-semibold leading-snug text-stone-800 dark:text-stone-100">
          {article.title}
        </h2>

        {/* **기자 크레딧.** 출처 약관이 이름과 출처를 명확히 적으라고 요구한다. */}
        <p className="text-xs text-stone-500 dark:text-stone-400">
          {article.byline} · {sourceLabel(article.source)}
        </p>

        <p className="text-xs text-stone-400">
          문단 {article.paragraphs.length}개 · 분석 {ready}개 준비됨
        </p>
      </header>

      <ol className="flex flex-col gap-3">
        {article.paragraphs.map((paragraph) => {
          const expanded = open === paragraph.ordinal
          const analysis = analyses[paragraph.ordinal]
          return (
            <li
              key={paragraph.ordinal}
              className="min-w-0 rounded-2xl border border-stone-200 dark:border-stone-800"
            >
              <button
                type="button"
                onClick={() => void toggle(paragraph)}
                aria-expanded={expanded}
                className="flex w-full items-start gap-3 p-4 text-left transition hover:bg-stone-50 dark:hover:bg-stone-900"
              >
                <span className="shrink-0 pt-0.5 font-mono text-xs text-stone-400">
                  {paragraph.ordinal}
                </span>
                <span className="min-w-0 flex-1 leading-relaxed text-stone-700 dark:text-stone-200">
                  {paragraph.text}
                </span>
                <span className="shrink-0 pt-0.5 text-xs text-stone-400">
                  {paragraph.prepared ? (expanded ? '접기 ▴' : '분석 보기 ▾') : '준비 중'}
                </span>
              </button>

              {expanded && (
                <div className="border-t border-stone-100 p-4 dark:border-stone-800">
                  {!paragraph.prepared ? (
                    <p className="text-sm text-stone-400">
                      이 문단은 아직 분석이 준비되지 않았습니다.
                    </p>
                  ) : partError?.ordinal === paragraph.ordinal ? (
                    <p className="text-sm text-red-600 dark:text-red-400">{partError.message}</p>
                  ) : pending === paragraph.ordinal || !analysis ? (
                    <p className="text-sm text-stone-400">분석을 불러오는 중…</p>
                  ) : (
                    <ResultView
                      state={analysis.state}
                      level={level}
                      onLevelChange={onLevelChange}
                      vocab={vocab}
                      // **난이도와 모델을 적는다.** 미리 분석에는 소요 시간이 없어
                      // (`meta` 를 들지 않는다) 비워 두면 `ResultView` 가 끝난 분석을
                      // "진행 중" 으로 읽는다.
                      caption={caption(analysis)}
                    />
                  )}
                </div>
              )}
            </li>
          )
        })}
      </ol>

      {/* **바닥에도 크레딧과 링크를 둔다.** 약관은 "상단이나 하단" 이라 하나면
          되지만, 문단 아코디언이라 **번역은 화면 중간에서 펼쳐진다** — 머리의
          링크가 스크롤 밖으로 나간 채 번역을 읽게 되므로 아래에도 둔다. */}
      <footer className="flex flex-col gap-1 rounded-2xl border border-stone-200 p-4 text-xs text-stone-500 dark:border-stone-800 dark:text-stone-400">
        <p>
          {article.byline} · {sourceLabel(article.source)}
        </p>
        <p className="text-stone-400">
          원문에서 {EXCERPT_WORDS}단어 이내로 발췌해 번역했습니다.{' '}
          <OriginalLink url={article.url} />
        </p>
      </footer>
    </div>
  )
}

/** 원문으로 가는 백링크. **약관이 요구하므로 머리와 바닥에 같은 것을 둔다.** */
function OriginalLink({ url, className = '' }: { url: string; className?: string }) {
  return (
    <a
      href={url}
      target="_blank"
      rel="noreferrer noopener"
      className={`underline hover:text-stone-700 dark:hover:text-stone-200 ${className}`}
    >
      원문 보기 ↗
    </a>
  )
}

/** 출처를 **약관이 쓰는 이름으로** 적는다. 모르는 출처는 받은 값을 그대로 둔다. */
export function sourceLabel(source: string): string {
  return SOURCE_LABELS[source] ?? source
}

const SOURCE_LABELS: Record<string, string> = { guardian: 'The Guardian' }

/** 백엔드의 `paragraphs.WORD_LIMIT` 과 같은 수. **화면은 적기만 한다** — 자르는
 *  일은 앉힐 때 끝나 있고(`M13-T9`), 여기서 다시 세면 두 곳이 갈린다. */
const EXCERPT_WORDS = 500

/** `2026-11-01` → `11월 1일`. 비어 있으면 그대로 둔다 — 없는 날짜를 꾸미지 않는다. */
export function dayLabel(picked: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(picked)
  if (!match) return picked
  return `${Number(match[2])}월 ${Number(match[3])}일`
}

/** 머리줄 — 미리 분석임과 그 모델. **모델 이름이 비어 있으면 적지 않는다.**
 *
 *  전에는 난이도를 적었는데 분석에 난이도가 없어졌다 (M16). 그래도 비워 두면
 *  `ResultView` 가 **끝난 분석을 "진행 중" 으로 읽는다** — 그래서 말은 남긴다. */
function caption(prepared: Prepared): string {
  return prepared.model ? `미리 분석 · ${prepared.model}` : '미리 분석'
}
