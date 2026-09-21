# English Study Assistant

> **브랜치 두 개**
> - `local` — 내 PC 의 llama-server 로 돌리는 1인용. 로그인 없음.
> - `main` — 웹 배포용. Google 로그인 + 회원별 Gemini API 키. ([배포 문서](documents/07-web-deployment.md))
>
> 같은 코드에 `APP_MODE` 로 갈린다. 아래 1~3절은 `local` 기준이다.

영어 문장이나 문단을 붙여넣으면 로컬 LLM이 **자연스러운 번역 · 표현 풀이 · 문장 구조 · 총평**
네 가지로 정리해 주는 1인용 학습 웹 앱.

네 섹션은 각각 독립된 LLM 호출로 처리되어, 완성되는 순서대로 화면에 채워진다
(SSE 스트리밍). 한 섹션이 실패해도 나머지는 그대로 나온다.

표현 풀이의 예문은 기본적으로 가려져 있다. **[✏ 직접 써보기]** 를 누르면 한국어 뜻만 보고
영작하고, LLM이 채점해 준다 — 읽고 이해하는 데서 멈추지 않도록.

```
eng_study/
├── dev.sh       개발 서버 실행 스크립트
├── Dockerfile   웹 배포용 (프론트 빌드 + 백엔드를 한 이미지로)
├── render.yaml  Render 블루프린트
├── documents/   기획·설계 문서
├── backend/     FastAPI + llama-server 프로바이더
└── frontend/    React + Vite + TypeScript
```

## 빠른 시작

llama-server 를 먼저 띄운 뒤 (아래 1절):

```bash
./dev.sh
```

의존성 설치, `.env` 생성, 백엔드 + 프론트엔드 실행을 한 번에 처리한다.
뜨고 나면 **http://localhost:5173** 으로 접속한다.

### 종료

터미널에 붙여 띄웠다면 **`Ctrl+C`** 로 둘 다 내려간다.
백그라운드(`./dev.sh &`)로 돌렸거나 터미널을 닫아 버렸다면:

```bash
./dev.sh stop
```

실행 시 `.dev.pid` 에 프로세스 번호를 남기므로, `stop` 은 그걸 읽어 백엔드와 프론트엔드를
자식 프로세스까지 함께 정리한다. 무엇이 떠 있는지는 `./dev.sh status` 로 본다.

### 전체 명령

| 명령 | 하는 일 |
|---|---|
| `./dev.sh` | 백엔드 + 프론트엔드 동시 실행 |
| `./dev.sh backend` | 백엔드만 (`http://127.0.0.1:8000/docs`) |
| `./dev.sh frontend` | 프론트엔드만 |
| `./dev.sh stop` | 떠 있는 서버를 내린다 |
| `./dev.sh status` | 무엇이 떠 있는지 + llama-server 연결 상태 |
| `./dev.sh check` | llama-server 연결만 확인하고 종료 |

포트를 바꾸려면 `BACKEND_PORT=9000 FRONTEND_PORT=3000 ./dev.sh`.
같은 포트 값을 `stop` / `status` 에도 똑같이 넘겨야 한다.
아래 2·3절은 수동으로 띄우거나 내부 동작을 확인할 때 참고한다.

문서: [기획서](documents/01-product-spec.md) ·
[아키텍처](documents/02-architecture.md) ·
[API 명세](documents/03-api-spec.md) ·
[프롬프트 설계](documents/04-prompt-design.md) ·
[실측 기록](documents/05-benchmark.md) ·
[작문 연습](documents/06-practice.md) ·
[웹 배포](documents/07-web-deployment.md) ·
[난이도 설계(기획안)](documents/08-level-design.md)

---

## 1. llama-server 띄우기 (직접 준비)

이 저장소는 LLM 서버를 관리하지 않는다. 별도로 띄운 뒤 주소만 알려 주면 된다.

```bash
llama-server -m /path/to/model.gguf -c 65536 -ngl 99 -fa on --jinja \
  --host 127.0.0.1 --port 8080 --alias my-model
```

`.env` 의 `LLM_MODEL` 을 `--alias` 값과 맞춘다. 한국어 설명 품질이 핵심이므로
한국어가 되는 7B 이상 instruct 모델을 권장한다.
JSON 스키마 강제는 llama-server가 GBNF로 처리하므로 function calling 지원 여부는 상관없다.

> **reasoning 모델(Qwen3 등)을 쓴다면 thinking 을 꺼야 한다.**
> 사고 토큰이 `max_tokens` 를 함께 소진해서, 한도가 사고에서 전부 소진되면
> 본문이 빈 문자열로 돌아온다. 기본값 `LLM_ENABLE_THINKING=false` 가 이를 막는다
> (프로바이더가 `chat_template_kwargs.enable_thinking` 로 전달).
> 굳이 켜려면 `LLM_MAX_TOKENS` 를 16384 이상으로 올린다.

## 2. 백엔드 (수동 실행)

```bash
cd backend
uv venv && uv pip install -e ".[dev]"
cp .env.example .env          # LLM_MODEL 을 --alias 값과 맞춘다
.venv/bin/uvicorn app.main:app --reload --port 8000
```

- API 문서: http://127.0.0.1:8000/docs
- 상태 확인: `curl localhost:8000/api/health` → `llm.reachable` 로 연결 여부 확인
- 테스트: `.venv/bin/python -m pytest` (llama-server 없이 동작 — `tests/fake_provider.py`)

## 3. 프론트엔드 (수동 실행)

```bash
cd frontend
npm install
npm run dev     # http://localhost:5173
```

dev 서버가 `/api` 를 `127.0.0.1:8000` 으로 프록시하므로 별도 CORS 설정 없이 동작한다.
백엔드를 다른 주소에 띄웠다면 `.env.local` 에 `VITE_API_TARGET` 을 지정한다.

## 4. LLM 교체하기

`backend/app/providers/base.py` 의 `LLMProvider` 만 구현하면 다른 백엔드로 갈아끼울 수 있다.
`app/main.py` 의 `lifespan` 에서 프로바이더 생성 부분 한 줄만 바꾸면 된다.

llama-server 버전에 따라 `response_format` 지원이 다르므로 `LLM_JSON_MODE` 로 맞춘다.

| 값 | 보내는 형태 |
|---|---|
| `json_schema` (기본) | `{"type": "json_schema", "json_schema": {...}}` — 최신 llama-server |
| `json_object` | `{"type": "json_object", "schema": {...}}` — 구버전 |
| `none` | 스키마를 보내지 않고 프롬프트로만 유도 |

세 모드 모두 응답은 코드 펜스 제거 → JSON 파싱 → Pydantic 검증을 거치고,
실패하면 temperature 0으로 그 파트만 1회 재시도한다.
`finish_reason` 이 `length` 면 재시도하지 않고 `llm_truncated` 로 원인을 알린다.

## 5. 검증 환경

Qwen3.8-27B (UD-IQ4_XS, `-c 65536 -ngl 99 -fa on --jinja`) 에서 확인한 값:

| 항목 | 결과 |
|---|---|
| `response_format: json_schema` | 정상 동작, enum 값도 지켜짐 |
| 5문장 문단 전체 분석 (파트 분할) | 약 43초, 첫 섹션은 3~8초 |
| 같은 문단 단일 호출 | 32초. 다만 첫 글자까지 32초를 기다려야 한다 |
| thinking 켠 경우 | 4.3배 느려지고 품질 차이는 미미 — 끄는 것이 기본값 |

자세한 측정값과 파트 분할을 택한 근거는 [실측 기록](documents/05-benchmark.md) 참고.


---

## 6. 웹 배포 (main 브랜치)

Google 로그인으로 가입하고, **회원이 등록한 Gemini API 키**로 회원 본인의 사용 한도 안에서
동작한다. 서버는 키를 암호화해 보관만 한다.

> Google 로그인으로는 회원의 Gemini 사용 한도를 쓸 수 없다. 로그인은 신원 확인에만 쓰고,
> 호출에 쓸 키는 회원이 따로 등록한다. 이유는 [배포 문서 1절](documents/07-web-deployment.md) 참고.

10명 기준 전액 무료로 굴러가는 구성:

| 계층 | 선택 |
|---|---|
| 앱 | Render 무료 웹 서비스 (신용카드 불필요, 15분 미사용 시 절전) |
| DB | Neon 무료 Postgres (Render 무료 DB 는 30일 뒤 삭제된다) |
| 프론트 | 백엔드와 같은 오리진 — 서비스 하나로 끝나고 쿠키 문제가 없다 |

배포 절차는 [documents/07-web-deployment.md](documents/07-web-deployment.md) 6절에 있다.
