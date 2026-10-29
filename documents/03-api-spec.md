# 03. API 명세

> **층** 설계 · **상태** 유효
> **읽어야 할 때** 라우터를 건드릴 때. 프론트가 쓰는 응답 모양을 바꿀 때
> **위** [문서 지도](00-index.md) · **함께** [아키텍처](02-architecture.md) · [모드별 차이](09-mode-matrix.md)

Base URL: `http://127.0.0.1:8000` (local 개발). 배포본은 프론트와 같은 출처다.

**모드에 따라 갈리는 응답과 문턱은 [09 모드별 차이](09-mode-matrix.md) 를 함께 본다** —
`GET /api/config` 의 값, 입력 상한, 로그인·동의·키 요구 여부가 모드마다 다르다.

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
| `text` | string (1~2000) | O | 분석할 영어 문장/문단. 상한은 `GET /api/config` 의 `max_input_chars` 로도 알려준다 |
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
        "fragment": "It is unlikely to find its way",
        "name": "형식주어 it 구문",
        "role": "실제 주어는 뒤의 to부정사구다. it 은 자리만 채운다.",
        "rewrite": "The chance that it will spread is low",
        "pitfall": "한국어에는 형식주어가 없어 it 을 대명사로 잘못 읽기 쉽다."
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
  "level": "intermediate",
  "type": "고급 어휘",
  "source_text": "..."
}
```

`prompt_ko` 와 `model_answer` 는 분석 결과의 `expressions[].example_ko` / `example` 을 그대로 넘긴다.

`type` 과 `source_text` 는 **채점에 쓰이지 않는다.** 서버가 이 표현을 나의 표현에
올릴 때 쓴다 — 채점과 등록을 두 번 호출하게 하면 뒤쪽이 실패해 **입구 없는 기록**이
남는다. 한 트랜잭션에서 함께 한다 (아래 나의 표현).

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

## 제공자·모델 선택과 키

**두 모드 공통이다.** 전에는 `/api/auth/*` 에 있었고 그 라우터는 cloud 전용이라
**로컬에서는 제공자를 고를 수도 키를 넣을 수도 없었다** (M12-T4).
local 은 llama-server 와 cloud LLM 전부를, cloud 는 cloud LLM 만 고를 수 있다
([09 §3.2](09-mode-matrix.md)).

| 메서드 | 경로 | 하는 일 |
|---|---|---|
| `GET` | `/api/account/settings` | 지금 무엇으로 일하나, 어디에 키가 있나 |
| `PUT` | `/api/account/settings` | 제공자·모델을 고른다 — **회원 전역 설정** |
| `PUT` | `/api/account/api-key` | 제공자별 키를 넣는다 (`{provider, api_key}`) |
| `DELETE` | `/api/account/api-key?provider=` | 그 제공자의 키만 지운다 |

**응답**
```json
{
  "active_provider": "gemini",
  "active_model": "gemini-3.5-flash-lite",
  "keys": { "gemini": "••••0000" },
  "ready": true
}
```

- `keys` 는 **끝 네 자리만** 담는다. 평문 키는 서버 밖으로 나가지 않는다.
- `ready` 는 **지금 고른 제공자**로 호출할 수 있는지다. 키가 필요 없는 제공자
  (내 PC 의 llama-server)는 항상 참이다.
- **고를 수 있는 목록은 여기 없다.** `GET /api/config` 의 `providers` 가 모드에 맞는
  것만 내려준다 — 프론트가 목록을 들고 있으면 모드가 바뀔 때 어긋난다.
- 고를 수 없는 제공자나 그 제공자가 제공하지 않는 모델은 **400** 이다. 저장해 두고
  나중에 기본값으로 떨어지면 회원은 자기가 고른 것으로 돌아간다고 믿는다.
- 로컬에서 cloud LLM 키를 넣으려면 `ENCRYPTION_KEY` 가 필요하다. 없으면 400 으로
  안내한다 — **llama-server 만 쓰는 로컬에는 여전히 필요 없다.**

---

## 나의 표현

담아 둔 표현과, 그 표현으로 직접 써본 기록. **두 모드 모두** 있다 — 둘 다 DB 에 쌓는다.
경로 이름은 `vocabulary` 이고 **화면에서 부르는 이름만 "나의 표현"** 이다.

| 메서드 | 경로 | 하는 일 |
|---|---|---|
| `GET` | `/api/vocabulary` | 담아 둔 표현 전부. 최신순 |
| `POST` | `/api/vocabulary` | 담는다. 같은 표현이면 **덮어쓴다** |
| `DELETE` | `/api/vocabulary/{id}` | 제외한다. **그 표현의 연습 기록도 함께 지운다** |
| `GET` | `/api/practice/history` | 직접 써본 기록. `expression` · `verdict` · `limit` 으로 좁힌다 |

**목록 응답**
```json
[
  {
    "id": 1,
    "expression": "refer to",
    "type": "Phrasal Verb",
    "meaning": "참조하다, 언급하다",
    "example": "Please refer to the appendix for the full table.",
    "example_ko": "전체 표는 부록을 참조해 주세요.",
    "source_text": "...",
    "created_at": "2026-10-22T08:34:25+00:00",
    "practice_count": 2
  }
]
```

`practice_count` 는 **화면이 한 번 더 묻기 위한 값**이다. 0 이 아니면 제외할 때
사라지는 기록이 있다는 뜻이므로 확인을 받는다. 행마다 세지 않고 한 번에 모아 온다.

**제외 응답**
```json
{ "ok": true, "expression": "refer to", "practices_deleted": 2 }
```

몇 건이 사라졌는지 돌려준다. 화면이 미리 물어봤더라도 **실제 건수는 서버만 안다** —
그 사이에 다른 기기에서 연습했을 수 있다.

### 왜 연습 기록이 함께 사라지나

나의 표현이 연습 기록으로 가는 **유일한 입구**다. 제외하고 기록만 남기면 어느 화면에도
나타나지 않는 유령 데이터가 된다. 반대로 연습하면 자동으로 담기는 것도 같은 이유다 —
[06 3절](06-practice.md) 과 `→ backend/app/services/vocabulary.py`.

둘을 잇는 열쇠는 **표현 문자열**(`practices.expression` ↔ `vocabulary.expression`)이다.
외래키를 쓰지 않았다. 연습 기록이 먼저 쌓여 있어서 옮겨 붙이려면 짝 없는 행을 버리게 된다.
`unique(user_id, expression)` 이 이미 걸려 있어 이 쌍은 자연키로 충분하다.

- **되돌릴 수 없다.** 확인은 화면이 받는다. API 는 묻지 않는다.
- `POST` 는 덮어쓰고, **연습을 통한 자동 등록은 빈 칸만 채운다.** 담아 둔 풍부한 행을
  연습 요청의 빈 값으로 덮으면 목록이 가난해진다.

---

## 기록 정리

같은 문단을 여러 번 분석하면 기록이 그만큼 쌓인다. **중복은 최신 하나만** 남긴다.
**두 모드 모두** 있다.

| 메서드 | 경로 | 하는 일 |
|---|---|---|
| `GET` | `/api/history/duplicates` | 정리하면 몇 건이 사라지나. **묻기 전에** 쓴다 |
| `POST` | `/api/history/tidy` | 오래된 중복을 지운다 |

둘 다 같은 모양을 돌려준다.

```json
{ "removed": 3 }
```

- **무엇을 "같은 문단" 으로 보는지**는 `→ backend/app/services/history.py` —
  공백 문자를 다 지운 결과가 같으면 중복이다. 대소문자와 문장부호는 건드리지 않는다.
- **되돌릴 수 없다.** 확인은 화면이 받는다. API 는 묻지 않는다.
- 세는 경로가 따로 있는 이유는 **지울 것이 없으면 묻지 않기 위해서**다.
  `removed: 0` 이면 화면은 확인 상자를 띄우지 않는다.
- 미리 센 값과 실제 건수가 다를 수 있다 — 그 사이에 다른 기기에서 분석했을 수 있다.
  그래서 `POST` 도 건수를 돌려준다.
- **고정 경로를 `/api/history/{id}` 보다 먼저 선언한다.** 순서가 뒤면 `duplicates` 가
  기록 id 로 읽혀 404 가 난다 — 실제로 그랬다.

---

## 데이터 삭제와 탈퇴

개인정보 관점에서 **지우는 수단**이다. 모으는 기능만 있으면 회원이 자기 데이터를
회수할 방법이 없다. 두 응답 모두 같은 모양이고, **무엇이 몇 건 지워졌는지**를 돌려준다.

```json
{ "analyses": 3, "practices": 1, "vocabulary": 2, "usage_counters": 1 }
```

| 메서드 | 경로 | 하는 일 | 모드 |
|---|---|---|---|
| `GET` | `/api/account/data` | 몇 건인지만 센다 (지우기 전 확인용) | 두 모드 |
| `DELETE` | `/api/account/data` | 기록 전부 삭제. **계정은 남는다** | 두 모드 |
| `DELETE` | `/api/auth/account` | 탈퇴. 기록 + 계정 + 세션 쿠키 | **cloud 만** |

- **탈퇴는 로컬에 없다.** 지울 계정이 없어서다 — 왜 그런지는
  [09 §3.6](09-mode-matrix.md).
- 암호화된 Gemini 키는 계정 행에 있으므로 탈퇴와 함께 사라진다.
- **되돌릴 수 없다.** 확인은 화면이 받는다. API 는 묻지 않는다.

---

## 에러 응답 (공통)

```json
{ "error": { "code": "llm_unavailable", "message": "로컬 LLM 서버에 연결할 수 없습니다.", "detail": "..." } }
```

| code | HTTP | 의미 |
|---|---|---|
| `validation_error` | 422 | 요청 본문 검증 실패 |
| `not_found` | 404 | 그 기록이 없다 — **또는 내 것이 아니다** (아래) |
| `app_error` | 400 | 그 밖에 요청을 처리할 수 없는 경우 |
| `auth_required` | 401 | 로그인이 필요하다 (cloud) |
| `consent_required` | 403 | 이용 동의 전이다 (cloud) |
| `api_key_required` | 403 | Gemini 키 미등록 (cloud) |
| `usage_limit` | 429 | 오늘 사용 한도 초과 (cloud) |
| `llm_unavailable` | 503 | llama-server 연결 실패 |
| `llm_timeout` | 504 | 응답 시간 초과 |
| `llm_bad_output` | 502 | 스키마에 맞는 JSON을 2회 시도 후에도 얻지 못함 |
| `llm_truncated` | 502 | `max_tokens` 한도에서 응답이 잘림 (reasoning 모델에서 흔함) |

### 없는 기록과 남의 기록을 구별하지 않는다

둘 다 **`404 not_found`** 다. 메시지도 같다.

**다르게 답하면 id 를 훑어 "있는지 없는지" 를 알아낼 수 있다.** 404 와 403 을 나눠 주면
"403 이 떴다 = 그 번호의 기록이 존재한다" 가 되고, 그것만으로 다른 회원이 몇 건을
쌓았는지 셀 수 있다. 내용은 못 봐도 그건 이미 누출이다.

전에는 둘 다 **400** 이었다. 구별하지 않는다는 성질은 지켜지고 있었지만 숫자가 틀렸다 —
클라이언트가 "내 요청이 잘못됐나" 와 "그런 것이 없나" 를 가릴 수 없었다 (H-012).

적용 범위는 단건 경로 셋이다 — `GET`/`DELETE /api/history/{id}` ·
`DELETE /api/vocabulary/{id}`. 불변식과 장치는 [14 §3.1](14-data-layer.md).
