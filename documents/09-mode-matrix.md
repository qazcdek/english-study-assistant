# 09. 모드별 차이 한눈에 보기

> 한 코드베이스가 `APP_MODE` 로 두 가지 배포 형태를 낸다.
> **모드에 따라 달라지는 것은 전부 여기에 적는다.** 새로 갈리는 항목을 만들면 이 표를 먼저 고친다.

## 1. 왜 이 문서가 필요한가

전에는 `local` 과 `main` 을 따로 두었다. 같은 변경을 양쪽에 옮기는 일이 열 번쯤 반복됐고,
그 과정에서 한쪽만 고쳐 어긋나는 일이 실제로 생겼다. 그래서 하나로 합쳤다.

합치고 나면 반대 위험이 생긴다 — **한쪽 모드만 생각하고 고쳐서 다른 쪽을 깨뜨리는 것.**
특히 값이 조용히 갈리는 항목(입력 상한 같은)은 테스트를 통과하면서도 틀릴 수 있다.

## 2. 한눈에 보기

| | `APP_MODE=local` | `APP_MODE=cloud` |
|---|---|---|
| **누가 쓰나** | 나 혼자, 내 PC | 회원 여럿, 웹 |
| **LLM** | llama-server (내 GPU) | Gemini (회원 각자의 API 키) |
| **모델** | `LLM_MODEL` (예: qwen3.8-27b) | `GEMINI_MODEL` (gemini-3.5-flash-lite) |
| **프로바이더 수명** | 앱 시작 시 하나를 공유 | **요청마다 새로** (키가 회원 것이므로) |
| **로그인** | 없음 (`session_user` 가 `id=1` 을 돌려준다) | Google OAuth |
| **입력 상한** | **2000자** | **800자** |
| **DB** | Postgres (docker, 15432) | Postgres (Neon) |
| **사용자 행** | 시작할 때 만드는 `id=1` 하나 | Google 로그인마다 생성 |
| **사용량 한도** | 없음 | 하루 분석 60 / 연습 200 |
| **세션 쿠키** | 없음 | HttpOnly JWT |
| **CORS 자격 증명** | 끔 | 켬 |
| **프론트 서빙** | vite dev 서버 | 백엔드와 같은 오리진 |

## 3. 값이 갈리는 것 — 실수하기 쉬운 곳

### 3.1 입력 상한

```
local  2000자   혼자 쓰고 llama-server 한도만 신경 쓰면 된다
cloud   800자   회원 각자의 Gemini 한도를 소모한다
```

**`Settings.max_input_chars` 하나만 본다.** 스키마의 `ABSOLUTE_MAX_INPUT_CHARS` 는
어떤 모드에서도 넘을 수 없는 **절대 상한**(2000)이고, 모드별 제한은 라우터에서 그보다 좁게 건다.

```
schemas.ABSOLUTE_MAX_INPUT_CHARS = 2000   ← Pydantic 이 막는 하드 천장
Settings.local_max_input_chars   = 2000   ← 실제 적용
Settings.cloud_max_input_chars   =  800   ← 실제 적용
```

프론트는 이 값을 하드코딩하지 않는다. `GET /api/config` 의 `max_input_chars` 를 쓴다.
**프론트에 숫자를 적어 넣으면 모드가 바뀔 때 어긋난다.**

### 3.2 LLM 프로바이더

| | local | cloud |
|---|---|---|
| 만드는 곳 | `main.lifespan` — 앱당 하나 | `deps.get_provider` — 요청당 하나 |
| 키 | 없거나 `LLM_API_KEY` | 회원이 등록한 키를 복호화 |
| 정리 | 앱 종료 시 | 요청 끝날 때 |

cloud 에서 프로바이더를 공유하면 **다른 회원의 키로 호출된다.** 절대 캐시하지 않는다.

### 3.3 사용량 한도

local 에는 없다. cloud 만 `usage_counters` 에 세고 한도를 넘으면 429 를 낸다.
**호출 전에** 센다 — 실패한 호출도 회원의 Gemini 한도를 소모하기 때문이다.

### 3.4 사용자 의존성 두 가지

헷갈리기 쉬운 지점이다.

| 의존성 | 무엇을 보장하나 | 쓰는 곳 |
|---|---|---|
| `SessionUser` | **신원만.** cloud 는 세션 쿠키, local 은 `id=1` | 히스토리·단어장·사용량 조회 |
| `ActiveUser` | 신원 + **LLM 을 부를 수 있는 상태** (cloud 는 동의·API 키까지) | 분석·작문 연습 채점 |

저장된 기록을 읽는 데에는 동의나 API 키가 필요 없다. 그것들은 LLM 을 부를 때 필요한 것이다.
조회에까지 `ActiveUser` 를 걸면 키를 지운 회원이 자기 기록도 못 보게 된다.

### 3.5 프론트 화면

```
local   바로 분석 화면.  StatusBar(llama-server 연결 상태) 표시
cloud   로그인 → 이용 동의 → API 키 등록 → 분석 화면.  AccountBar 표시
```

`useSession` 의 `stage` 가 이 흐름을 관리한다. `config.requires_login` 이 분기점이다.

## 4. 모드와 **무관한** 것

여기 있는 것은 두 모드가 똑같이 쓴다. 한쪽만 고치면 그 자체로 버그다.

- 프롬프트 전부 (`app/prompts/`) — 분석 4파트, 작문 연습 채점
- 결과 스키마와 난이도별 분기 (`app/schemas.py`, `PartSpec.schema_for`)
- 응답 정제 (`app/services/refine.py`)
- 마크다운 렌더링 (`app/services/markdown.py`)
- 저장 기록 형식 올리기 (`app/services/records.py`, `RESULT_VERSION`)
- DB 테이블 구조 (`app/db/models.py`) — 두 모드가 **같은 스키마**를 쓴다
- 분석 화면 전체 (`ResultView`, `ExpressionTable`, `PracticeBox`, `HistoryList`)

## 5. 무엇을 고칠 때 무엇을 함께 봐야 하나

| 이런 걸 바꾸면 | 이것도 확인한다 |
|---|---|
| 입력 상한 | `Settings.max_input_chars` 기본값 2개 · `/api/config` 응답 · 프론트가 서버 값을 쓰는지 |
| 결과 스키마 (필드 추가·이름 변경) | **`RESULT_VERSION` 올리고 `records.upgrade` 에 규칙 추가** · 마크다운 렌더러 · 화면 · 빈 값 처리 |
| 프롬프트 | 두 모델 모두에서 확인 (Gemini 와 llama-server 는 스키마 제약 지원이 다르다 — 08-level-design 3.2) |
| 새 API 엔드포인트 | cloud 에서 인증이 필요한가 · local 에서도 동작하는가 · `main.py` 라우터 등록이 모드별인가 |
| DB 테이블 | **`create_all` 은 기존 테이블을 바꾸지 않는다.** 컬럼을 더하면 이미 있는 DB 에 직접 `ALTER TABLE` 을 해야 한다. 실제로 이 통합 과정에서 `users.google_sub does not exist` 로 앱이 뜨지 않았다. Alembic 도입 전까지는 두 DB(로컬 docker, Neon) 모두 손으로 맞춰야 한다 |
| 프론트 화면 | local 에서도 열리는가 (`cloud` 분기를 걸었는지) |

## 6. 모드별로 반드시 확인하는 것

고치고 나면 **두 모드 다** 띄워 본다.

```bash
# local
./dev.sh                       # Postgres + 백엔드 + 프론트
curl localhost:8000/api/config # mode=local, requires_login=false, max_input_chars=2000

# cloud (로컬에서)
cd backend && set -a && . ./.env.cloud && set +a
.venv/bin/uvicorn app.main:app --port 8000
curl localhost:8000/api/config # mode=cloud, requires_login=true, max_input_chars=800
```

테스트도 두 모드를 모두 돈다. `tests/test_cloud.py` 가 cloud, 나머지가 local 이다.
**한 모드에서만 테스트를 추가하면 다른 쪽이 조용히 깨진다.**
