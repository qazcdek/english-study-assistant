# 03. API 명세

Base URL: `http://127.0.0.1:8000`

---

## GET /api/health

백엔드와 llama-server 상태를 함께 확인한다.

**200**
```json
{
  "status": "ok",
  "llm": { "reachable": true, "base_url": "http://127.0.0.1:8080/v1", "models": ["qwen2.5-7b-instruct"] }
}
```
llama-server 가 죽어 있어도 백엔드는 200을 주고 `llm.reachable: false` 로 알린다.

---

## POST /api/analyze/stream

파트가 완성되는 대로 SSE(`text/event-stream`)로 흘려보낸다. **프론트엔드가 쓰는 주 경로.**
요청 본문은 `/api/analyze` 와 같다.

```
data: {"type":"part","field":"translation","title":"자연스러운 번역","index":0,"total":4,
       "data":{"translation":"..."},"markdown":"### 자연스러운 번역\n\n...",
       "elapsed_ms":3521,"retried":false}

data: {"type":"part","field":"expressions", ...}

data: {"type":"part_error","field":"structures","title":"문장 구조","index":2,"total":4,
       "code":"llm_bad_output","message":"...","detail":"..."}

data: {"type":"done","result":{...},"markdown":{...},"meta":{...}}
```

| 이벤트 | 의미 |
|---|---|
| `part` | 한 파트 완성. `data` 는 결과 조각, `markdown` 은 그 섹션의 마크다운 |
| `part_error` | 그 파트만 실패. 스트림은 계속된다 |
| `done` | 합쳐진 결과 + 전체 마크다운 + `meta`. 스트림의 마지막 |
| `error` | 스트림 자체를 이어갈 수 없음 (연결 불가 등) |

파트 순서는 `translation` → `expressions` → `structures` → `overview` 로 고정이다.
총평은 표현 목록에 의존하므로 순서를 바꿀 수 없다.

---

## POST /api/analyze

네 파트를 모두 끝낸 뒤 한 번에 돌려준다. 스크립트나 `curl` 로 쓰기 편한 경로.

**요청**
```json
{
  "text": "It's unlikely to find its way across the pond into the lexicon of Wall Street.",
  "level": "intermediate"
}
```

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `text` | string (1~2000) | O | 분석할 영어 문장/문단 |
| `level` | `beginner` \| `intermediate` \| `advanced` | X | 설명 난이도. 기본 `intermediate` |

**200** — 일부 파트가 실패해도 200 이다. 실패한 파트는 `meta.failed_parts` 에 이름이 들어가고
결과에서는 비어 있다(`overview` 는 `null`). **모든** 파트가 실패하면 502 다.

```json
{
  "result": {
    "source_text": "...",
    "translation": "이 영국식 표현은 ...",
    "expressions": [
      {
        "expression": "across the pond",
        "type": "관용구",
        "meaning": "(비격식) 대서양을 건너, 영미 사이를 오갈 때 쓰는 표현",
        "example": "She moved across the pond last spring.",
        "example_ko": "그녀는 지난봄에 대서양을 건너갔다."
      }
    ],
    "structures": [
      {
        "fragment": "It's unlikely to find...",
        "explanation": "`be unlikely to`는 '~할 것 같지 않다'라는 뜻으로 ..."
      }
    ],
    "overview": {
      "domain": "경제·금융 시사 논평",
      "tone": "유머와 비유를 섞은 분석적 어조",
      "formality": "격식",
      "style": "문어체",
      "key_expressions": ["across the pond", "sum up"],
      "comment": "금융 뉴스를 읽을 때 맥락 파악에 도움이 되는 표현들이다."
    }
  },
  "markdown": {
    "translation": "### 자연스러운 번역\n\n...",
    "expressions": "### 표현 풀이\n\n| 표현 (영어) | 유형 | 의미 및 설명 |\n| --- | --- | --- |\n...",
    "structures": "### 문장 구조\n\n* ...",
    "overview": "### 총평\n\n* **분야**: 경제·금융 시사 논평\n...",
    "full": "### 자연스러운 번역\n\n...\n\n---\n\n### 표현 풀이\n..."
  },
  "meta": {
    "model": "local-model",
    "elapsed_ms": 43100,
    "retried_parts": [],
    "failed_parts": []
  }
}
```

`example` 은 확신할 때만 넣으므로 생략될 수 있고, 그때는 `example_ko` 도 함께 없다.
둘 다 있어야 작문 연습(`POST /api/practice`)을 할 수 있다.

### 표현 유형 (`expressions[].type`)

`고급 어휘` · `관용구` · `Phrasal Verb` · `연어(Collocation)` · `문법 포인트` · `구어 표현` · `전문 용어`

### 총평 필드

| 필드 | 형태 | 설명 |
|---|---|---|
| `domain` | 자유 서술 | 어떤 분야의 글인지 |
| `tone` | 자유 서술 | 글쓴이의 태도·어조 |
| `formality` | 열거값 | `매우 격식` · `격식` · `중립` · `비격식` · `속어에 가까움` |
| `style` | 열거값 | `문어체` · `구어체` · `혼합` |
| `key_expressions` | 문자열 배열 | `expressions[].expression` 과 값이 일치하는 1~3개 |
| `comment` | 자유 서술 | 왜 중요하고 어디에 쓰는지 두세 문장 |

---

## POST /api/practice

예문을 가린 채 학습자가 쓴 영어 문장을 채점한다. 설계 근거는 [06-practice.md](06-practice.md).

**요청**
```json
{
  "expression": "trumpet",
  "meaning": "자랑하다, 과장되게 선전하다",
  "prompt_ko": "그 회사는 신제품을 획기적이라고 대대적으로 선전했다.",
  "model_answer": "The company trumpeted its new product as a game-changer.",
  "learner_answer": "The firm loudly trumpeted its latest product as a breakthrough.",
  "level": "intermediate"
}
```

`prompt_ko` 와 `model_answer` 는 분석 결과의 `expressions[].example_ko` / `example` 을 그대로 넘긴다.

**200**
```json
{
  "result": {
    "verdict": "정확함",
    "uses_target": true,
    "good_point": "trumpet 을 타동사로 목적어와 함께 자연스럽게 썼다.",
    "target_note": "loudly 와 함께 써서 '대대적으로'의 뜻을 정확히 전달했다.",
    "corrected": "",
    "other_notes": []
  },
  "model_answer": "The company trumpeted its new product as a game-changer.",
  "meta": { "model": "local-model", "elapsed_ms": 7195, "retried_parts": [], "failed_parts": [] }
}
```

| 필드 | 형태 | 설명 |
|---|---|---|
| `verdict` | 열거값 | `정확함` · `통함` · `다시` |
| `uses_target` | boolean | 목표 표현을 실제로 썼는지. 활용형이 달라도 true |
| `good_point` | 자유 서술 | 잘한 점 한 문장. `다시` 판정이어도 반드시 채운다 |
| `target_note` | 자유 서술 | 목표 표현 사용에 대한 평가. 틀렸다면 규칙을 설명한다 |
| `corrected` | 자유 서술 | 고쳐 쓴 문장. 고칠 것이 없으면 빈 문자열 |
| `other_notes` | 문자열 배열 | 부차적 지적. **최대 2개** |

**모범 답안과 다른 문장도 자연스럽고 뜻이 맞으면 `정확함` 이다.** `model_answer` 는 참고용이다.

---

## 에러 응답 (공통)

```json
{ "error": { "code": "llm_unavailable", "message": "로컬 LLM 서버에 연결할 수 없습니다.", "detail": "..." } }
```

| code | HTTP | 의미 |
|---|---|---|
| `llm_unavailable` | 503 | llama-server 연결 실패 |
| `llm_timeout` | 504 | 응답 시간 초과 |
| `llm_bad_output` | 502 | 스키마에 맞는 JSON을 2회 시도 후에도 얻지 못함 |
| `llm_truncated` | 502 | `max_tokens` 한도에서 응답이 잘림 (reasoning 모델에서 흔함) |
| `validation_error` | 422 | 요청 본문 검증 실패 |
