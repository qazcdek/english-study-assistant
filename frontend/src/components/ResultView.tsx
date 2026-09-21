import { useState } from 'react'

import { isFinished, type AnalysisState } from '../lib/analysis'
import type { Level } from '../lib/types'
import { ExpressionTable } from './ExpressionTable'
import { OverviewCard } from './OverviewCard'
import { Section } from './Section'

export function ResultView({ state, level }: { state: AnalysisState; level: Level }) {
  const { result, status, meta } = state
  const [copied, setCopied] = useState(false)
  const done = isFinished(state)

  async function copyMarkdown() {
    const text = state.fullMarkdown ?? Object.values(state.markdown).join('\n\n---\n\n')
    await navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-3 text-xs text-stone-400">
        {meta ? (
          <>
            <span>{meta.model}</span>
            <span>·</span>
            <span>총 {(meta.elapsed_ms / 1000).toFixed(1)}초</span>
            {meta.failed_parts.length > 0 && (
              <span className="text-red-500">· {meta.failed_parts.length}개 파트 실패</span>
            )}
          </>
        ) : (
          <span>파트별로 분석하는 중…</span>
        )}
        <button
          type="button"
          onClick={copyMarkdown}
          disabled={!done}
          className="ml-auto rounded-lg border border-stone-200 px-2.5 py-1 transition hover:bg-stone-100 disabled:opacity-40 dark:border-stone-700 dark:hover:bg-stone-800"
        >
          {copied ? '복사됨' : '마크다운 복사'}
        </button>
      </div>

      <Section title="자연스러운 번역" status={status.translation}>
        <p className="leading-loose text-stone-700 dark:text-stone-200">{result.translation}</p>
      </Section>

      <Section
        title="표현 풀이"
        status={status.expressions}
        badge={
          <span className="rounded-full bg-stone-100 px-2 py-0.5 text-xs text-stone-500 dark:bg-stone-800">
            {result.expressions.length}
          </span>
        }
      >
        <ExpressionTable
          expressions={result.expressions}
          keyExpressions={result.overview?.key_expressions ?? []}
          level={level}
        />
      </Section>

      <Section title="문장 구조" status={status.structures}>
        {result.structures.length === 0 ? (
          <p className="text-sm text-stone-400">특별히 설명할 구문이 없습니다.</p>
        ) : (
          <ul className="flex flex-col gap-3">
            {result.structures.map((s, i) => (
              <li key={`${s.fragment}-${i}`} className="text-sm leading-relaxed">
                <span className="font-mono font-medium text-indigo-600 dark:text-indigo-300">
                  {s.fragment}
                </span>
                <p className="mt-1 text-stone-600 dark:text-stone-300">{s.explanation}</p>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title="총평" status={status.overview}>
        {result.overview && <OverviewCard overview={result.overview} />}
      </Section>
    </div>
  )
}
