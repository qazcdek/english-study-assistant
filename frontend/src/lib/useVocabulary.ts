import { useCallback, useEffect, useMemo, useState } from 'react'

import { addVocabulary, deleteVocabulary, listVocabulary } from './api'
import type { Expression, VocabularyItem, VocabularyRemoval } from './types'

/**
 * 나의 표현 목록. **두 화면이 같은 하나를 본다.**
 *
 * 분석 화면의 별과 나의 표현 목록이 각자 상태를 들면, 한쪽에서 제외해도 다른 쪽 별이
 * 노란 채로 남는다. 그래서 App 에서 한 번만 들고 아래로 내려보낸다.
 *
 * 서버에서는 `vocabulary` 다. 화면에서 부르는 이름만 "나의 표현" 이다.
 */
export interface VocabularyStore {
  items: VocabularyItem[]
  /** 그 표현이 나의 표현에 있나. 별의 색을 정한다. */
  has: (expression: string) => boolean
  /** 그 표현으로 직접 써본 횟수. **0 이 아니면 제외할 때 한 번 더 묻는다.** */
  practiceCount: (expression: string) => number
  idOf: (expression: string) => number | null
  add: (expression: Expression, sourceText: string) => Promise<void>
  remove: (id: number) => Promise<VocabularyRemoval>
  reload: () => Promise<void>
}

export function useVocabulary(enabled: boolean): VocabularyStore {
  const [items, setItems] = useState<VocabularyItem[]>([])

  const reload = useCallback(async () => {
    try {
      setItems(await listVocabulary())
    } catch {
      // 목록을 못 읽는다고 분석을 막을 필요는 없다. 별이 비어 보일 뿐이다.
    }
  }, [])

  useEffect(() => {
    if (!enabled) return
    void reload()
  }, [enabled, reload])

  // 표현 문자열로 찾는 일이 행마다 일어난다. 목록을 매번 훑지 않는다.
  const byExpression = useMemo(
    () => new Map(items.map((item) => [item.expression, item])),
    [items],
  )

  const add = useCallback(
    async (expression: Expression, sourceText: string) => {
      await addVocabulary({
        expression: expression.expression,
        type: expression.type,
        meaning: expression.meaning,
        example: expression.example ?? '',
        example_ko: expression.example_ko ?? '',
        source_text: sourceText,
      })
      await reload()
    },
    [reload],
  )

  const remove = useCallback(
    async (id: number) => {
      const removed = await deleteVocabulary(id)
      await reload()
      return removed
    },
    [reload],
  )

  return {
    items,
    has: (expression) => byExpression.has(expression),
    practiceCount: (expression) => byExpression.get(expression)?.practice_count ?? 0,
    idOf: (expression) => byExpression.get(expression)?.id ?? null,
    add,
    remove,
    reload,
  }
}
