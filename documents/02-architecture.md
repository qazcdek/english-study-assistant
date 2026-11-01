# 02. 아키텍처

> **층** 설계 · **상태** 유효
> **읽어야 할 때** 모듈을 더하거나 요청 흐름을 바꿀 때
> **위** [문서 지도](00-index.md) · **함께** [API 명세](03-api-spec.md) · [모드별 차이](09-mode-matrix.md) · [실측 기록](05-benchmark.md)

## 1. 전체 구성

```
┌─────────────────┐      HTTP/JSON       ┌──────────────────┐   OpenAI 호환 API   ┌───────────────┐
│  frontend       │ ───────────────────▶ │  backend         │ ──────────────────▶ │  llama-server │
│  React + Vite   │                      │  FastAPI         │                     │  (사용자가 별도 │
│  TypeScript     │ ◀─────────────────── │  Python 3.11+    │ ◀────────────────── │   기동)        │
└─────────────────┘   마크다운 + 원본 JSON └──────────────────┘   구조화된 JSON      └───────────────┘
```

- **llama-server 는 이 저장소가 관리하지 않는다.** 사용자가 직접 띄우고, 백엔드는 `LLM_BASE_URL` 로 가리키기만 한다.
- 백엔드는 프로바이더 인터페이스(`LLMProvider`) 뒤에 llama-server 구현을 숨긴다. 나중에 다른 백엔드로 교체 가능.

> 모드에 따라 달라지는 것의 전체 목록은 [09-mode-matrix.md](09-mode-matrix.md) 에 있다.

## 2. 책임 분리

| 레이어 | 책임 | 하지 않는 것 |
|---|---|---|
| frontend | 입력 UI, 결과 렌더링, 로컬 히스토리 | 프롬프트 작성, LLM 직접 호출 |
| backend/api | HTTP 경계, 요청 검증, 에러 매핑 | 프롬프트 문자열 보관 |
| backend/services | 프롬프트 조립 → LLM 호출 → 검증 → 마크다운 변환 | HTTP 세부사항 |
| backend/providers | LLM 전송 계층 (httpx, 타임아웃, 재시도) | 프롬프트 내용 이해 |
| backend/prompts | 시스템/유저 프롬프트, JSON 스키마 | 네트워크 |

## 3. 요청 처리 순서

분석은 **네 파트를 각각 독립된 LLM 호출로** 처리한다 (근거는 05-benchmark.md).

1. `POST /api/analyze/stream` 으로 `{ "text": "..." }` 수신
2. `AnalyzeRequest` 로 길이/공백 검증 (절대 상한 2000자 — `schemas.ABSOLUTE_MAX_INPUT_CHARS`).
   **모드별 상한은 이보다 좁고 라우터가 건다** — 09-mode-matrix.md §3.1
3. `PART_SPECS` 를 순서대로 돌며 파트마다:
   - `build_messages(spec, ...)` 가 그 파트 전용 시스템 프롬프트 + 작은 JSON 스키마 구성
   - `LlamaServerProvider.complete()` 가 `response_format` 으로 스키마 강제
   - 파트 모델(Pydantic)로 파싱 — 실패하면 temperature 0 으로 **1회 재시도**
   - 성공하면 `services.markdown.render_part()` 로 조각을 만들어 **즉시 SSE 로 내보낸다**
   - 실패하면 `part_error` 이벤트만 내보내고 **다음 파트로 넘어간다**
4. 모든 파트가 끝나면 합쳐진 `result` + 전체 마크다운 + `meta` 를 `done` 이벤트로 내보낸다

### 3.1 파트 순서와 의존성

```
translation      (독립)
     │
expressions ─┬─→ structures   이미 다룬 어구를 구조 해설에서 되풀이하지 않도록 목록을 넘긴다
             └─→ overview     key_expressions 가 표의 값과 일치해야 하므로 목록을 넘긴다
```

번역만 독립이고 나머지 둘은 표현 목록을 받아야 한다.
llama-server 를 `-np 1` 로 띄우면 동시 요청이 어차피 직렬화되므로 순차 실행한다.

앞 파트의 결과를 뒤 파트 프롬프트에 실어 보내는 것은 품질 장치이기도 하다.
"단어 뜻 풀이를 하지 말라"는 금지만으로는 어휘 항목이 구조 해설로 새는 것을 막지 못했는데,
실제 표현 목록을 넘겨 주자 사라졌다 (04-prompt-design.md 2.4).

### 3.2 부분 실패 처리

| 실패 종류 | 동작 |
|---|---|
| 형식 오류 / 잘림 | 그 파트만 `part_error`, 나머지 파트는 계속 진행 |
| 연결 불가 / 타임아웃 | 남은 파트도 어차피 실패하므로 즉시 중단 |
| 모든 파트 실패 (`/api/analyze`) | 502 `llm_bad_output` |

## 4. 왜 백엔드에서 마크다운으로 변환하는가

- LLM에는 **구조화된 JSON만** 요구한다 → 스키마 강제(`json_schema`)가 가능하고 형식이 흔들리지 않는다.
- 표 정렬, 항목 순서, 라벨 한글화 같은 **표현 규칙은 코드로 고정**한다 → 모델이 바뀌어도 출력 모양이 같다.
- 프론트는 JSON(구조적 렌더링)과 마크다운(복사/내보내기) 둘 다 받아서 상황에 맞게 쓴다.

## 5. 디렉토리 구조

```
eng_study/
├── dev.sh                # 개발 서버 실행/종료 (설치 + 기동 + stop/status)
├── documents/            # 기획·설계 문서
├── backend/
│   ├── app/
│   │   ├── main.py           # FastAPI 앱, CORS, 라우터
│   │   ├── config.py         # 환경변수 설정
│   │   ├── schemas.py        # 요청/응답 + 분석 결과 Pydantic 모델
│   │   ├── errors.py         # 도메인 예외 → HTTP 매핑
│   │   ├── routers/analyze.py
│   │   ├── providers/
│   │   │   ├── base.py       # LLMProvider 추상 클래스
│   │   │   └── llama_server.py
│   │   ├── prompts/
│   │   │   ├── analysis.py   # 분석 4파트
│   │   │   └── practice.py   # 작문 연습 채점
│   │   └── services/
│   │       ├── analyzer.py   # 파트별 오케스트레이션
│   │       ├── practice.py   # 작문 연습 채점
│   │       └── markdown.py   # JSON → 마크다운
│   └── tests/
└── frontend/
    ├── public/
    │   └── favicon.svg   # Eng 마크. 빌드 시 dist/ 로 그대로 복사된다
    └── src/
        ├── App.tsx
        ├── components/       # InputPanel, ResultView, 섹션 카드들
        └── lib/              # api 클라이언트, 타입, 히스토리, 주소(routes.ts)
```

## 6. 설정 (환경변수)

| 변수 | 기본값 | 설명 |
|---|---|---|
| `LLM_BASE_URL` | `http://127.0.0.1:8080/v1` | llama-server 의 OpenAI 호환 엔드포인트 |
| `LLM_MODEL` | `local-model` | llama-server 는 보통 무시하지만 필드는 필요 |
| `LLM_API_KEY` | `""` | llama-server 를 `--api-key` 로 띄웠을 때만 |
| `LLM_TIMEOUT` | `300` | 초. 긴 문단은 로컬 모델에서 수 분이 걸린다 |
| `LLM_TEMPERATURE` | `0.3` | 분석 작업이라 낮게 |
| `LLM_MAX_TOKENS` | `4096` | |
| `LLM_ENABLE_THINKING` | `false` | reasoning 모델의 사고 과정 사용 여부 |
| `LLM_JSON_MODE` | `json_schema` | `json_schema` / `json_object` / `none` |
| `CORS_ORIGINS` | `http://localhost:5173` | 쉼표 구분 |
| `GEMINI_REASONING_EFFORT` | `low` | Gemini 의 사고 수준. 빈 문자열이면 안 보낸다 ([13 §2.2](13-gemini-benchmark.md)) |

## 7. 에러 처리 방침

| 상황 | 백엔드 응답 | 프론트 표시 |
|---|---|---|
| llama-server 연결 불가 | 503 `llm_unavailable` | "로컬 LLM 서버에 연결할 수 없습니다" + 확인 명령 안내 |
| 타임아웃 | 504 `llm_timeout` | 재시도 버튼 |
| JSON 파싱 2회 실패 | 502 `llm_bad_output` | 원문 일부와 함께 재시도 안내 |
| `max_tokens` 한도에서 잘림 | 502 `llm_truncated` | 한도를 늘리거나 thinking 을 끄라는 안내 |
| 입력 초과/공백 | 422 | 필드 아래 인라인 메시지 |

## 8. reasoning 모델 주의사항

Qwen3 같은 하이브리드 reasoning 모델을 `--jinja` 로 띄우면 사고 과정이 `reasoning_content` 필드로
분리되어 나온다. `content` 는 깨끗한 JSON이라 파싱에는 문제가 없지만, **사고 토큰도 `max_tokens` 를
함께 소진한다.** 사고가 길어지면 한도가 사고에서 전부 소진되어 `content` 가 빈 문자열로 돌아오고,
`finish_reason` 은 `length` 가 된다.

측정 결과 (Qwen3.8-27B IQ4_XS, 짧은 한 문장 / `max_tokens=2048`):

| 설정 | 결과 |
|---|---|
| thinking 켬 | 2048 토큰 전부 사고에 소진, `content` 빈 문자열, 2분 30초 후 실패 |
| thinking 끔 | 52 토큰, 정상 JSON, 1.7초 |

그래서 기본값을 `LLM_ENABLE_THINKING=false` 로 둔다. 프로바이더는
`chat_template_kwargs: {"enable_thinking": ...}` 로 이를 전달하고,
`finish_reason == "length"` 를 감지해 `llm_truncated` 로 명확히 알린다.

### 8.1 Gemini 에서도 같은 일이 난다

**같은 현상이 cloud 에서도 났다.** `-lite` 가 아닌 Gemini flash 는 사고 모델이라,
`max_tokens=8` 로 짧은 확인 요청을 보냈더니 넷 모두 `finish_reason: length` 가
났다 — **멀쩡한 모델이 고장으로 보였다.**

손잡이 이름이 다르다. llama-server 는 `chat_template_kwargs`, Gemini 는
OpenAI 호환 `reasoning_effort` 다. Gemini 는 `low` 로 합계 523 → 61 토큰이었다
([13 §2.2](13-gemini-benchmark.md) 실측). 그래서 **모델별로 손잡이를 찾아
기본값을 낮춰 둔다** — 안 걸면 비용을 회원의 한도가 조용히 치른다.

## 9. 화면과 주소

**라우터를 들이지 않는다.** 화면이 넷이고 그중 하나만 매개변수를 받으므로
`history` API 로 충분하다. SPA 폴백이 어떤 경로든 `index.html` 을 주고
(`main._mount_frontend`), 앱이 뜰 때 `location.pathname` 을 보고 화면을 고른다.
같은 오리진에서 서빙하는 덕이다 ([07 §5.1](07-web-deployment.md)).

```
/               분석
/analysis/<id>  분석 — 저장된 기록 하나를 띄운 상태
/mine           나의 표현
/terms          이용약관
/privacy        개인정보처리방침
```

**짝은 `frontend/src/lib/routes.ts` 한 곳에 있다.** `App.tsx` 가 들고 있었는데,
거기 두면 검사가 화면을 띄워야만 주소 해석을 물을 수 있다. 주소 해석은 순수한
판단이라 따로 둔다.

### 9.1 주소가 필요한 이유 셋

1. **법적 문서 둘은 주소로 들어올 수 있어야 한다.** Google OAuth 심사가
   개인정보처리방침 URL 을 받고, 그것을 로그인 없이 열어 본다
   ([07 §10.2](07-web-deployment.md)).
2. **뒤로 가기.** 전에는 기록을 열어도 주소가 `/` 그대로였다 — 뒤로 누르면
   목록이 아니라 **앱 밖으로 나갔다** (H-038).
3. **기록 하나를 링크할 수 있다.** 같은 주소로 다시 들어오면 그 기록이 열린다.

### 9.2 무엇에 주소를 주지 않나

**관문 세 화면(로그인 · 동의 · 키 등록)에는 주소가 없다.** 무엇을 보여줄지는
서버가 아는 사실이 정한다 — 주소로 들어올 수 있게 하면 주소와 서버 상태가
어긋나고, 어긋난 쪽을 믿을 근거가 없다. 대신 **로그인은 보던 주소로 돌아온다**
(`next`).

**아코디언에도 주소가 없다** — 나의 표현의 연습 칸, 좁은 화면의 기록 목록,
계정·데이터 메뉴. 펼침은 화면의 상태이지 간 곳이 아니다.

### 9.3 기록을 띄우는 길은 하나다

목록에서 골랐을 때 · 뒤로 갔을 때 · 링크로 처음 들어왔을 때가 **모두 같은 길을
지난다.** 전에는 "고를 때 가져온다" 가 목록 항목에만 붙어 있어서, 주소로는
아무것도 열 수 없었다. 그래서 **주소를 옮기는 것이 기록을 가져오는 방아쇠**이고,
`App.tsx` 는 주소만 바꾼다.

