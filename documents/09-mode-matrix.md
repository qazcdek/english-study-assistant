# 09. 모드별 차이 한눈에 보기

> **층** 규약 · **상태** 유효 · **강제** `backend/tests/test_mode_matrix.py`
> **읽어야 할 때** **모드에 따라 갈리는 것을 추가·변경할 때 — 코드를 고치기 전에**
> **위** [문서 지도](00-index.md) · **함께** [아키텍처](02-architecture.md) · [API 명세](03-api-spec.md) · [웹 배포](07-web-deployment.md)
>
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
| **탈퇴** | 없음 (지울 계정이 없다) | `DELETE /api/auth/account` |
| **오류 수집** | 없음 | Sentry (`SENTRY_DSN` 있을 때) |
| **프론트 서빙** | vite dev 서버 | 백엔드와 같은 오리진 |

## 3. 값이 갈리는 것 — 실수하기 쉬운 곳

### 3.1 입력 상한

```
local  2000자   혼자 쓰고 llama-server 한도만 신경 쓰면 된다
cloud   800자   회원 각자의 Gemini 한도를 소모한다
```

**`Settings.max_input_chars` 하나만 본다.** 스키마의 `ABSOLUTE_MAX_INPUT_CHARS` 는
어떤 모드에서도 넘을 수 없는 **절대 상한**(2000)이고, 모드별 제한은 라우터에서 그보다 좁게 건다.

값이 사는 곳 `→ backend/app/config.py::Settings.max_input_chars` ·
거는 곳 `→ backend/app/routers/analyze.py::_check_length`

```
schemas.ABSOLUTE_MAX_INPUT_CHARS = 2000   ← Pydantic 이 막는 하드 천장
Settings.local_max_input_chars   = 2000   ← 실제 적용
Settings.cloud_max_input_chars   =  800   ← 실제 적용
```

프론트는 이 값을 하드코딩하지 않는다. `GET /api/config` 의 `max_input_chars` 를 쓴다.
**프론트에 숫자를 적어 넣으면 모드가 바뀔 때 어긋난다.**

### 3.2 LLM 프로바이더

**전에는 모드가 제공자를 정했다** — local 은 llama-server, cloud 는 Gemini.
이제 **회원이 고르고, 고를 수 있는 범위만 모드로 갈린다.**

```
local    llama-server + cloud LLM 전부
cloud    cloud LLM 만 — llama-server 는 내 PC 에 있어서 Render 에서 닿지 않는다
```

목록은 `app/providers/registry.py` 한 곳에 있고, 프론트는 그것을 `/api/config` 로 받는다.
**프론트에 적지 않는다** — 적으면 모드가 바뀔 때 어긋난다.

**아직 안 되는 제공자는 목록에 안 나온다.** 고를 수 있는데 안 되는 것은 목록에 없는 것보다
나쁘다. `implemented` 는 선언이 아니라 **구현 표에서 끌어온다** — 손으로 적었더니
거짓으로 적어도 아무것도 안 잡혔다.

**고른 것은 회원 전역 설정이다** (`users.active_provider` · `active_model`).
바꿔 저장하면 그 뒤의 모든 작업이 그것으로 간다. 분석할 때마다 고르게 하지 않는다 —
한 번 쓰고 마는 선택이 되고, 한도 소모가 어느 제공자에서 일어났는지 추적도 어려워진다.

**제공자마다 스키마를 받아 주는 범위가 다르다.** 모드가 아니라 제공자로 갈리는 차이라서
여기 표에는 없다 — [04 §10](04-prompt-design.md) 이 든다. 다만 **두 모드 모두에서
확인해야 하는 이유**가 하나 늘었다: 로컬에서 고를 수 있는 제공자가 cloud 보다 많으므로
로컬에서만 닿는 조합이 생긴다.

**제공자를 늘리면 방침도 늘어난다** — [07 §10.6](07-web-deployment.md).

**저장된 값을 그대로 믿지 않는다.** local 에서 llama-server 를 고른 회원이 cloud 로
들어올 수 있고, 그대로 믿으면 **Render 에서 내 PC 의 서버를 부르려 든다.**
고를 수 없는 것이 저장돼 있으면 모드 기본값으로 떨어진다 (`services/keys.py`).

**키는 제공자마다 따로 둔다** (`provider_keys`). 그래서 "키가 있다" 는 더 이상 회원
단위 사실이 아니다 — **지금 고른 제공자**의 키를 본다. 다른 제공자 키가 있어도 지금
쓸 것이 없으면 호출할 수 없다.

| | local | cloud |
|---|---|---|
| 만드는 곳 | `main.lifespan` — 앱당 하나 | `deps.get_provider` — 요청당 하나 |
| 키 | 없거나 `LLM_API_KEY` | 회원이 등록한 키를 복호화 |
| 정리 | 앱 종료 시 | 요청 끝날 때 |

cloud 에서 프로바이더를 공유하면 **다른 회원의 키로 호출된다.** 절대 캐시하지 않는다.

**제공자가 늘면 다섯 곳이 함께 늘어난다** — 구현 · 키 저장 · 프롬프트 계열([04 §9](04-prompt-design.md)) ·
선택 UI · **개인정보처리방침의 국외 이전 수탁자**([07 §10](07-web-deployment.md)).
빼먹은 것이 방침이면 **적지 않은 곳으로 데이터가 나간다.** `test_provider_registry.py` 가
목록과 나머지를 대조한다.

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

### 3.6 데이터 삭제와 탈퇴

```
기록 삭제   DELETE /api/account/data     두 모드 공통
탈퇴        DELETE /api/auth/account     cloud 만
```

**기록 삭제는 두 모드가 같다.** 두 모드 모두 DB 에 쌓으므로 지우는 동작도 같다.

**탈퇴는 cloud 에만 있다.** 로컬에는 지울 계정이 없다 — 앱이 시작할 때 만드는
사용자 행 하나(`id=1`)가 전부이고, 그걸 지우면 다음 요청이 깨진다.

그런데 **이 분기는 코드에 쓰지 않았다.** 탈퇴를 `auth` 라우터에 두면,
그 라우터가 cloud 에서만 등록되므로(3.4) 로컬에서는 **경로 자체가 없다.**
모드 분기를 쓰지 않고 모드 차이를 만드는 자리다 — 쓸 수 있으면 이 방식이 낫다.

암호화된 Gemini 키는 계정 행에 있으므로 탈퇴와 함께 사라진다. 따로 지우지 않는다.

### 3.7 오류 수집

```
local   없음.  내 PC 에서 난 오류를 외부로 보낼 이유가 없다
cloud   Sentry.  SENTRY_DSN 이 있을 때만 켠다
```

**두 겹으로 막는다** — DSN 이 비어 있으면 안 켜고, 차 있어도 local 이면 안 켠다.
한 겹만 두면 `.env` 에 DSN 이 섞여 들어온 날 로컬 오류가 나가기 시작한다.

무엇을 지우고 보내는지는 [07 §9.1](07-web-deployment.md).

### 3.8 매일 읽을 글 (공용 글감)

```
local   없음.  문단을 직접 넣는다
cloud   서버가 하루 한 편 골라 미리 문단별로 분석해 둔다 (M13)
```

**local 에 두지 않는 이유는 쓸모가 아니라 쓰임이다.** 이 기능은 "읽을 문단을
가져오는 것이 귀찮다" 를 푸는 것인데, local 은 혼자 쓰므로 읽고 싶은 글을 그때
붙여 넣으면 된다. 하루 한 편을 서버가 미리 준비해 둘 이유가 없다.

**표는 두 모드에 다 있다.** 스키마와 리비전은 하나이므로(§4) `articles` ·
`article_paragraphs` · `paragraph_analyses` 는 local 에도 만들어진다.
갈리는 것은 **채우는 쪽**이다.

#### 운영자 플래그

공용 글감을 만들려면 LLM 키가 필요한데 **회원 키를 쓸 수 없다** — 회원은 자기
분석에 쓰라고 등록한 것이다. 그래서 `users.is_operator` 가 켜진 회원 하나의 키로
돌린다 (`→ backend/app/services/operator.py`).

```
local   부트스트랩 사용자에게 **켜지 않는다.** find() 가 None 이고 기능이 꺼진다
cloud   운영자가 로그인할 때 켜진다. 구글이 검증한 이메일에서만
```

**local 에서도 꺼 두는 것이 이 절의 장치다.** 모드 분기 하나를 더 두는 대신
데이터가 비어 있게 해서, 분기를 빼먹어도 local 에서 돌지 않는다.

#### 언제 도나

**시계에 걸지 않는다. 요청이 방아쇠다.** cloud 는 Render 무료 티어라 15분 미사용이면
잠들고(§3.7 과 같은 사정), 상주 스케줄러를 믿을 수 없다. 오늘 것이 없으면 요청이
들어온 그때 고르고 분석하며, **그동안 어제 것을 보여준다.**

실패하면 **마지막 실패 시각으로부터 5분은 쉰다.** 하루 시도 상한이 아니라 쿨다운인
이유는, 상한은 다 쓰면 그날은 포기이고 문제가 10분 만에 풀려도 내일까지 글감이
없기 때문이다. 쿨다운은 풀리는 순간 회복된다.

## 4. 모드와 **무관한** 것

여기 있는 것은 두 모드가 똑같이 쓴다. 한쪽만 고치면 그 자체로 버그다.

- 프롬프트의 **교육 내용** (`app/prompts/analysis.py`) — 표현 유형 · 난이도 · 칸별 명세.
  **길들이기 지시는 모델 계열로 갈린다**(`app/prompts/models.py`) — 모드가 아니라 모델이
  기준이고, 지금은 네 계열이 같은 문구를 쓴다 ([04 §9](04-prompt-design.md))
- 결과 스키마와 난이도별 분기 (`app/schemas.py`, `PartSpec.schema_for`)
- 응답 정제 (`app/services/refine.py`)
- 마크다운 렌더링 (`app/services/markdown.py`)
- 저장 기록 형식 올리기 (`app/services/records.py`, `RESULT_VERSION`)
- DB 테이블 구조 (`app/db/models.py`) — 두 모드가 **같은 스키마**를 쓴다
- 분석 화면 전체 (`ResultView`, `ExpressionTable`, `PracticeBox`, `HistoryList`)
- 나의 표현 (`MyExpressions`, `/api/vocabulary`, `/api/practice/history`) —
  담아 두기와 연습 기록은 두 모드가 똑같다. **모드 분기를 쓰지 않았다**
  ([03 나의 표현](03-api-spec.md))

## 5. 무엇을 고칠 때 무엇을 함께 봐야 하나

| 이런 걸 바꾸면 | 이것도 확인한다 |
|---|---|
| 입력 상한 | `Settings.max_input_chars` 기본값 2개 · `/api/config` 응답 · 프론트가 서버 값을 쓰는지 |
| 결과 스키마 (필드 추가·이름 변경) | **`RESULT_VERSION` 올리고 `records.upgrade` 에 규칙 추가** · 마크다운 렌더러 · 화면 · 빈 값 처리 |
| 프롬프트 | 두 모델 모두에서 확인 (Gemini 와 llama-server 는 스키마 제약 지원이 다르다 — 08-level-design 3.2) |
| 새 API 엔드포인트 | cloud 에서 인증이 필요한가 · local 에서도 동작하는가 · `main.py` 라우터 등록이 모드별인가 |
| DB 테이블 | **모델만 고치면 안 된다. 리비전을 만든다** — `alembic revision --autogenerate -m "무엇을"`. 안 만들면 `test_migrations.py` 가 모델과의 차이를 찍고 실패한다. 두 모드가 같은 스키마를 쓰므로 리비전도 하나다 ([07 §6.5](07-web-deployment.md)) |
| 프론트 화면 | local 에서도 열리는가 (`cloud` 분기를 걸었는지) |

## 6. 두 모드를 함께 개발하는 방법

"두 모드를 함께 챙기자" 는 선언만으로는 안 지켜진다. **통합한 지 커밋 하나 만에
주석 세 곳이 이 문서와 어긋났다**(H-011). 그래서 세 가지 장치를 둔다.

### 6.1 공통 기능 테스트는 두 모드에서 돈다

```python
def test_vocabulary_add_list_delete(both_modes):   # local, cloud 각각 한 번씩
    api = both_modes
    ...
```

`both_modes` 픽스처(`tests/conftest.py`)가 모드별 환경을 세우고, 그 모드의
**요청 주인**까지 준비해 `Api(client, mode, user_id)` 로 넘긴다.
local 은 `id=1`, cloud 는 동의·키 등록까지 끝난 회원 + 세션 쿠키다.

- **공통 기능** → `tests/test_both_modes.py` (`both_modes` 사용)
- **모드 전용** → `tests/test_cloud.py` (`cloud` 사용)

전에는 기록 저장·단어장·옛 기록 호환이 cloud 쪽에만 있어서 **local 이 깨져도
잡히지 않았다.** 실제로 H-002 는 두 모드 모두의 버그였는데 따로 고쳤다.

### 6.2 이 문서의 표를 테스트가 고정한다

`→ backend/tests/test_mode_matrix.py`

`tests/test_mode_matrix.py` 가 2절·3절의 값을 리터럴로 들고 있다.

- 문서에 적힌 기본값 == `Settings` 의 기본값 (`model_fields[...].default`)
- 두 모드를 띄워 `/api/config` 가 그 값을 내는가
- auth 라우트·프로바이더 수명·CORS 자격증명이 표대로인가

**값을 바꾸면 이 테스트가 깨진다. 고치려면 이 문서를 보게 된다.**
그래서 이 문서는 설명이 아니라 명세다. 한쪽을 고치면 반드시 다른 쪽도 고친다.

### 6.3 cloud 를 로컬에서 띄운다

```bash
./dev.sh              # local  — llama-server + docker Postgres
./dev.sh cloud        # cloud  — .env.cloud (로그인 + 회원 Gemini 키)
./dev.sh cloud status # 어느 모드로 무엇이 떠 있는지
```

`cloud` 는 `uvicorn --env-file .env.cloud` 로 띄운다. `--env-file` 값은 `os.environ`
에 올라가 pydantic-settings 의 `.env` 보다 우선하므로 코드를 고칠 필요가 없다.
`.env.cloud` 는 **운영과 같은 Neon 프로젝트의 `dev` 브랜치**를 가리킨다 — 같은
서비스의 다른 저장소다 (6.4). llama-server 확인과 docker Postgres 기동은 그 모드에
필요할 때만 한다.

**cloud 를 띄워 보지 않고 머지하지 않는다.** 안 그러면 cloud 쪽 회귀를
Render 에 올려야 발견하게 된다.

### 6.4 검사와 개발이 **운영과 같은 엔진**을 본다

모드가 갈리는 것은 **DB 의 내용**이고, **엔진은 갈리지 않는다.**

| 어디 | 엔진 | 저장소 |
|---|---|---|
| 단위 검사 (로컬 기본) | SQLite | 테스트마다 임시 파일 |
| 단위 검사 (`./dev.sh test --pg`) | Postgres 17 | `eng_study_test`, 테스트마다 스키마 하나 |
| CI | Postgres 17 | 서비스 컨테이너, 테스트마다 스키마 하나 |
| local 모드 | Postgres 17 | 도커 `eng_study` (포트 15432) |
| cloud 모드 | Neon Postgres | 운영과 같은 프로젝트의 `dev` 브랜치 |
| 운영 (Render) | Neon Postgres | 운영 브랜치 |

**왜 이렇게 두는가.** 전에는 검사도 CI 도 cloud 개발도 SQLite 였다. 그동안 엔진 전용
어긋남을 **아무것도 못 잡았다** (H-032). 재 보니 `String` 길이를 좁히는 사고에서
SQLite 는 검사 406개를 전부 통과시키고 Postgres 는 14개를 떨어뜨린다.

- **머지 게이트가 운영 엔진을 본다.** 거기만 막으면 어긋난 채로는 들어오지 못한다.
- **로컬 기본은 SQLite 로 둔다.** 반복 속도(13초 대 25초)와 오프라인이 더 중요하고,
  CI 가 뒤에서 받아 준다. 둘 다 보려면 `./dev.sh test --pg`.
- **격리는 스키마로 한다.** 테스트마다 DB 를 만들면 느리고, 하나를 공유하면 서로의
  행을 지운다. 주소에 `search_path` 를 실어 보내므로 앱 코드는 고칠 데가 없다
  (`backend/tests/dbs.py`).
- **cloud 개발은 운영 브랜치를 가리키지 않는다.** 앱은 뜰 때 `upgrade head` 를 돌리고
  개발 중에는 `downgrade` 도 돈다 — 운영에 걸면 회원 데이터가 사라진다.

**장치** `./dev.sh cloud` 는 `.env.cloud` 의 `DATABASE_URL` 이 Postgres 가 아니면
**띄우기를 거부한다.** 이 표를 글로만 적어 두면 또 어긋난다 (12-tooling.md §6).

## 7. 아직 안 한 것

- **모드 분기에 이름 붙이기** — `if settings.is_cloud:` 는 *왜* 갈리는지를 가린다.
  `settings.counts_usage` 처럼 능력으로 부르면 이유가 이름에 남는다.
  프론트는 이미 이렇게 한다 — 모드를 묻지 않고 `/api/config` 의 값만 본다. (M4-T4)
- **분기 전수 조사** — `# MODE:` 마커를 달아 `grep` 으로 세어 이 문서와 대조한다. (M4-T5)
