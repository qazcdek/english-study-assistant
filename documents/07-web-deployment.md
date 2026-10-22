# 07. 웹 배포 (cloud 모드)

> **층** 운영 · **상태** 유효
> **읽어야 할 때** 인증·배포·저장 스키마를 바꿀 때. 배포가 깨졌을 때
> **위** [문서 지도](00-index.md) · **함께** [모드별 차이](09-mode-matrix.md) · [아키텍처](02-architecture.md)

`APP_MODE=local` 은 내 PC 의 llama-server 에 붙는 1인용 도구다.
`APP_MODE=cloud` 는 같은 코드에 **Google 로그인과 회원별 Gemini 키**를 얹어 웹에 배포한다.

전에는 `local` 과 `main` 두 브랜치로 갈라 두었으나 지금은 한 코드베이스이고,
`APP_MODE` 하나로 갈린다.

| | `APP_MODE=local` | `APP_MODE=cloud` |
|---|---|---|
| LLM | 내 PC 의 llama-server | 회원이 등록한 Gemini 키 |
| 로그인 | 없음 | Google OAuth |
| 저장 | 브라우저 localStorage | Postgres (회원별) |
| 프로바이더 수명 | 앱 시작 시 하나 | **요청마다 새로** |

---

## 1. 먼저 짚어야 할 것 — Google 로그인으로는 회원 한도를 쓸 수 없다

기획 단계에서 "Google 로그인만 하면 회원이 구독 중인 Google AI 한도로 돌린다"는 안이 있었다.
**이는 기술적으로 불가능하다.**

- Google 로그인(OpenID Connect)은 **신원**(이메일·프로필)만 준다.
- Google AI Pro/Ultra 같은 구독은 **Gemini 앱 이용권**이지 API 호출 권한이 아니다.
- 제3자 웹앱이 사용자 계정에 Gemini API 사용량을 청구할 수 있는 OAuth 범위는 존재하지 않는다.

의도("각자 본인 한도로 쓴다")를 살리는 유일한 방법은 **회원이 자기 Gemini API 키를 등록**하는 것이다.
그래서 이렇게 나눴다.

```
Google 로그인  →  신원 확인 (누가 쓰는지, 데이터를 누구 것으로 저장할지)
Gemini API 키  →  실제 호출 (누구의 한도가 소모되는지)
```

키는 Google AI Studio 에서 무료로 발급받을 수 있고, 무료 등급으로도 쓸 수 있다.

## 2. 가입 절차와 동의

회원가입은 세 관문을 차례로 지난다. 각 관문은 서버가 강제한다 —
프론트를 우회해도 API 가 거부한다(`tests/test_cloud.py`).

```
1. Google 로그인        없으면 401 auth_required
2. 이용 방식 동의        없으면 403 consent_required
3. Gemini API 키 등록    없으면 403 api_key_required
```

동의 화면에서 고지하는 내용:

1. **문장 분석과 작문 연습 채점 모두** 회원이 등록한 Gemini API 키로 호출된다.
   서버가 비용을 내지 않는다.
2. 따라서 **회원 Google 계정의 사용 한도(무료 등급 포함)가 소모**된다.
3. 사용 모델과 호출 횟수. 이 부분은 회원이 소모량을 예측할 수 있어야 하므로 구체적으로 적는다.
   - 문장 분석 1회 = LLM 호출 **4회** (번역 · 표현 · 구조 · 총평)
   - 작문 연습 채점 1회 = LLM 호출 **1회**
   - 표현마다 따로 연습할 수 있어, 한 문장을 분석하고 표현 6개를 모두 연습하면 **총 10회**
4. 입력한 영어 원문이 Google 에 전송되며, 무료 등급은 서비스 개선에 쓰일 수 있다는 점.
5. 이 서비스가 두는 하루 한도(`DAILY_ANALYSIS_LIMIT` / `DAILY_PRACTICE_LIMIT`)와,
   그것이 안전장치일 뿐 실제 차감은 회원 Gemini 한도에서 이뤄진다는 점.
6. 키는 암호화 보관하고 끝 네 자리만 보여주며 언제든 삭제할 수 있다는 점.

동의는 `users.consented_at` 에 시각으로 남긴다.

## 3. 회원 키 취급

| 단계 | 처리 |
|---|---|
| 등록 | 저장 **전에** 짧은 요청 하나로 실제 동작을 확인한다 (`verify_api_key`) |
| 저장 | Fernet 대칭키(`ENCRYPTION_KEY`)로 암호화해 `users.encrypted_api_key` 에 |
| 조회 | 평문은 어떤 API 로도 나가지 않는다. `api_key_hint` 로 끝 네 자리만 |
| 사용 | 요청마다 복호화해 **그 요청 전용 프로바이더**를 만든다. 공유하지 않는다 |
| 삭제 | `DELETE /api/auth/api-key` |

`ENCRYPTION_KEY` 가 유출되지 않는 한 DB 만으로는 키를 복원할 수 없다.

## 4. 사용량 한도

회원 본인 키를 쓰더라도 오작동 한 번으로 그 사람의 하루 한도가 날아가면 안 된다.
`usage_counters` 에 일 단위로 세고, 한도를 넘으면 `429 usage_limit` 으로 막는다.

- **호출 전에** 센다. 실패한 호출도 회원의 API 한도를 소모하기 때문이다.
- 분석 1회 = LLM 호출 4회로 계산한다.
- 기본값은 하루 분석 60회 / 작문 연습 200회. 환경변수로 조정한다.

Gemini 무료 등급은 모델별로 분당·일일 요청 수가 정해져 있어, 분석 한 번이 4회를 쓰는 점을 감안해
한도를 잡아야 한다. 실제 한도는 Google 문서를 확인할 것.

## 5. 인프라 — 10명 기준 전액 무료

| 계층 | 선택 | 근거 |
|---|---|---|
| 앱 | **Render 무료 웹 서비스** | 신용카드 없이 쓸 수 있는 몇 안 남은 상시 무료 티어. 15분 미사용 시 잠들고 첫 요청에 최대 1분 걸린다 |
| DB | **Neon 무료 Postgres** | Render 무료 Postgres 는 **생성 30일 뒤 삭제**된다. Neon/Supabase 는 영구 무료 |
| 프론트 | 백엔드와 **같은 오리진** | 아래 참고 |

### 5.1 프론트를 왜 같은 오리진에서 서빙하나

프론트와 API 를 다른 도메인에 두면 세션 쿠키가 cross-site 가 되어
`SameSite=None; Secure` 와 CORS 자격 증명 설정을 모두 맞춰야 하고, 브라우저 정책 변화에 취약하다.

Docker 빌드 1단계에서 프론트를 만들어 백엔드 이미지 안 `static/` 에 넣고
FastAPI 가 SPA 로 서빙한다. 서비스가 **하나**라 무료 플랜 하나로 끝나고 쿠키 문제도 사라진다.

## 6. 배포 절차

### 6.1 Google OAuth 클라이언트

1. Google Cloud 콘솔 → API 및 서비스 → OAuth 동의 화면 구성
2. 사용자 인증 정보 → OAuth 클라이언트 ID (웹 애플리케이션)
3. **승인된 리디렉션 URI** 에 다음을 등록
   ```
   https://<배포주소>/api/auth/google/callback
   ```
4. 클라이언트 ID 와 보안 비밀을 받아 둔다

### 6.2 Neon Postgres

1. https://neon.tech 에서 프로젝트 생성 (무료)
2. 연결 문자열 복사 → `DATABASE_URL`
   `postgres://` 로 시작해도 코드가 알아서 `postgresql+psycopg://` 로 바꾼다

### 6.3 Render

1. Render 대시보드 → New → Blueprint → 이 저장소 연결 (`render.yaml` 을 읽는다)
2. `sync: false` 로 표시된 환경변수를 채운다
   - `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`
   - `DATABASE_URL` (Neon)
   - `ENCRYPTION_KEY`
     ```bash
     python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"
     ```
   - `PUBLIC_BASE_URL`, `FRONTEND_BASE_URL` — 배포 후 받은 주소로 **둘 다 같게**
3. `SESSION_SECRET` 은 Render 가 생성한다
4. `SENTRY_DSN` 은 **비워 두어도 된다.** 채우면 오류가 모인다 (9절).
   Sentry 에서 프로젝트를 만들면 `https://...@...ingest.../1` 꼴의 주소를 준다

첫 배포 후 주소가 정해지면 `PUBLIC_BASE_URL`/`FRONTEND_BASE_URL` 과
Google 콘솔의 리디렉션 URI 를 그 주소로 맞추고 재배포한다.

### 6.4 로컬에서 cloud 모드 돌려보기

```bash
cd backend
APP_MODE=cloud \
GOOGLE_CLIENT_ID=... GOOGLE_CLIENT_SECRET=... \
SESSION_SECRET=$(python -c "import secrets;print(secrets.token_urlsafe(48))") \
ENCRYPTION_KEY=$(python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())") \
DATABASE_URL=sqlite+pysqlite:///./local-cloud.db \
.venv/bin/uvicorn app.main:app --reload --port 8000
```

DB 는 SQLite 로도 돌아간다. 테이블은 시작할 때 자동으로 만들어진다.

### 6.5 스키마를 바꿀 때 (Alembic)

**테이블 구조는 Alembic 이 만든다.** 앱이 뜰 때 `upgrade head` 가 돈다 —
Render 무료 티어에는 배포 전 단계가 없어서 거기 걸 자리가 없다. 수십 밀리초라
콜드 스타트에 영향이 없다.

```
1  app/db/models.py 를 고친다
2  cd backend && .venv/bin/alembic revision --autogenerate -m "무엇을 바꿨는지"
3  migrations/versions/ 에 생긴 파일을 읽어 본다 (autogenerate 는 완벽하지 않다)
4  uv run pytest tests/test_migrations.py
5  커밋한다. 배포하면 앱이 뜰 때 알아서 올라간다
```

**2번을 빼먹으면 `test_migrations.py` 가 잡는다.** 모델과 리비전의 차이를 그대로
찍어 주고 실패한다 — `create_all` 시절에는 모델만 고쳐도 테이블이 따라왔지만
이제는 아니다.

`alembic.ini` 에는 URL 을 적지 않는다. `migrations/env.py` 가 앱 설정에서 읽어
엔진과 **같은 변환**(`normalize_url`)을 거친다. 두 모드가 각자 다른 DB 를 쓰므로
한 곳에 못 박으면 틀린 DB 에 거는 사고가 난다.

**`alembic.ini` 와 `migrations/` 는 이미지에 들어가야 한다.** 처음 넣을 때 실제로
빠뜨려서 배포본이 부팅하다 죽을 상태였다. `Dockerfile` 이 `backend/app` 만
복사하고 있었다 — 지금은 `test_migrations.py` 가 그것까지 본다.

#### 한 번만 필요한 분기

이미 `create_all` 로 만들어진 DB(로컬 개발용과 배포본)에는 테이블이 있는데
`alembic_version` 이 없다. 거기에 `upgrade` 를 걸면 "이미 있는 테이블" 로 깨지므로,
그 경우에만 **첫 리비전을 찍고 넘어간다**(`app/db/migrate.py`).
지금 스키마가 첫 리비전과 같아서 안전하다.

**두 DB 가 모두 넘어온 뒤에는 이 분기를 지운다.** 남겨 두면, 마이그레이션이 깨진
DB 를 조용히 "최신" 으로 찍어 버릴 수 있다.

---

## 7. 저장하는 데이터

**표 목록과 불변식은 [14 데이터 레이어](14-data-layer.md) 가 든다.**
전에는 여기에 표를 두었는데, 소유 모델과 격리 규칙까지 적을 자리가 아니어서 옮겼다 —
여기는 배포를 다루는 문서다.

회원 본인 데이터만 읽을 수 있다. 남의 기록 id 를 찍어도 거부된다
([14 §3.1](14-data-layer.md), 검사로 고정).

**지우는 수단도 있다.** 기록 전체 삭제는 두 모드 공통이고, 탈퇴는 cloud 에만 있다
([03 데이터 삭제와 탈퇴](03-api-spec.md), [09 §3.6](09-mode-matrix.md)).
탈퇴하면 암호화된 Gemini 키도 계정 행과 함께 사라진다.

## 8. 남은 것

- **오답 다시 풀기 / 단어장 화면** — 데이터는 쌓이지만 이를 보여줄 프론트 화면이 아직 없다.

### 8.1 저장된 분석 결과의 스키마 변경

프롬프트를 손볼 때마다 결과 스키마가 바뀌는데, DB 에는 그때그때의 형식으로 저장돼 있다.
실제로 총평을 재정의하고 구문 해설을 네 필드로 쪼갠 뒤,
**그 전에 저장된 기록을 열면 500 이 났다** (`result.structures.0.role Field required`).
목록은 `result` 를 파싱하지 않아 멀쩡했고 상세 조회에서만 터져 알아채기 어려웠다.

Pydantic 모델을 느슨하게 만들어 해결하면 안 된다. 같은 모델이 **LLM 응답 검증에도 쓰이므로**
모델이 필드를 빠뜨려도 조용히 통과하게 된다. 그래서 모델은 엄격하게 두고
`app/services/records.py` 에서 **읽을 때만** 형식을 올린다.

- 새로 저장하는 기록에는 `schema_version` 을 함께 남긴다.
- 옛 기록에는 버전이 없으므로 모양을 보고 판단한다.
- 구문 해설의 `explanation` 은 쪼갤 수 없어 `role` 자리에 그대로 두고 `name` 은 비운다.
  화면과 마크다운은 이름이 비면 표시를 생략한다.
- 걷어낸 `frequency` 는 옮길 곳이 없으므로 버린다.

**스키마를 또 바꿀 때는 `RESULT_VERSION` 을 올리고 변환 규칙을 추가한다.**
- **Render 무료 티어의 콜드 스타트** — 15분 미사용 후 첫 요청이 최대 1분 걸린다.
- **Gemini 응답 품질 미검증** — 프롬프트는 Qwen3.8-27B 로 다듬은 것이다.
  Flash-Lite 에서 같은 품질이 나오는지는 실제 키로 확인해야 한다.

## 9. 오류 수집 (Sentry)

**없으면 터진 걸 모른다.** Render 무료 티어는 로그를 보관하지 않으므로, 500 이 나도
사실 자체가 남지 않는다. 그래서 예외만 외부로 모은다.

```
SENTRY_DSN=https://...        Render 환경변수에 넣는다. 비어 있으면 아무것도 안 한다
RENDER_GIT_COMMIT            Render 가 자동으로 넣는다. 어느 커밋에서 났는지 붙는다
```

**cloud 에서만 켠다.** 로컬은 내 PC 이고, 거기서 난 오류를 외부로 보낼 이유가 없다
([09 §3.7](09-mode-matrix.md)).

### 9.1 무엇을 보내지 않나 — 이쪽이 본체다

이 앱의 요청에는 **회원이 분석한 글 전체**가 들어 있다. 개인적인 글일 수 있다.
키를 등록하는 요청의 본문에는 **평문 Gemini 키**가 있다. 세션 쿠키 하나면 그 회원을
가장할 수 있다. **기본 설정대로 붙이면 그것들이 나간다.**

| 보내지 않는다 | 왜 |
|---|---|
| **스택 프레임의 지역 변수** | **진짜 누출 지점이었다** — 실측에서 요청 칸은 비어 있었고 비밀값이 전부 여기 있었다 (9.1.1) |
| 요청 본문 (`data`) | 회원의 글, 평문 키. 쓸모보다 위험이 크다 |
| 쿠키 · 환경변수 | 세션 하나로 회원을 가장할 수 있다 |
| 허용 목록 밖의 모든 헤더 | **금지 목록이 아니라 허용 목록이다** — 새 헤더가 생길 때 조용히 새지 않게 |
| 이름에 `key`·`secret`·`token`·`password` 가 든 칸 | 어디에 있든, 중첩되어 있어도 |
| 이름 · 이메일 · IP (`send_default_pii`) | 기본값이지만 **명시한다**. 기본값은 바뀔 수 있다 |

보내는 것은 **스택 트레이스 · 예외 메시지 · 경로 · 상태 코드 · 회원 id** 다.
id 를 남기는 이유는 "몇 명에게 났는지" 를 세기 위해서다 — 그게 없으면 한 명의 문제와
전원의 문제를 구별할 수 없다.

**이 목록은 선언이 아니라 검사다.** `backend/tests/test_observability.py` 가 걸러낸
결과를 직접 본다. 비밀값이 외부로 나가는 경로이므로 주의력에 맡기지 않는다.

#### 9.1.1 손으로 만든 이벤트만 보면 못 잡는다

처음에는 Sentry 가 보낼 이벤트 모양을 **손으로 흉내 내** 검사했다. 그 검사는 통과했다.
그리고 **진짜 예외를 흘려 보니 넷이 다 새어 나갔다.**

```
exception.values[0].stacktrace.frames[16].vars.body.api_key      ← 평문 Gemini 키
exception.values[0].stacktrace.frames[16].vars.body.text         ← 회원이 분석한 글
exception.values[0].stacktrace.frames[0].vars.scope.headers[7]   ← 세션 쿠키
```

요청 칸(`request.data`)은 **비어 있었다.** `send_default_pii=False` 가 그건 막는다.
비밀값은 전부 **스택 프레임의 지역 변수**에 있었고, 그건 내가 들여다보지 않은 자리였다.

**이름 기반으로는 못 막는다.** `body.text` 는 비밀처럼 생기지 않았고, 헤더는 이름 없는
쌍의 목록(`headers[7][1]`)으로 들어온다. 그래서 `vars` 를 **통째로** 뺀다.
디버깅에서 지역 변수를 잃지만, 여기 흐르는 것이 회원의 글과 평문 키이므로 그 교환은 분명하다.

그래서 검사도 **실제 예외를 흘려** 본다. 흉내 낸 모양만 보는 검사는 통과하면서 틀렸다.

### 9.2 Sentry 가 잡지 못하는 것

**예외가 아닌 품질 저하는 못 잡는다.** 예문이 비거나 작문 연습 입구가 사라지는
종류(H-019 · H-021)는 500 이 나지 않는다. 실제로 그 둘은 사용자가 화면을 보고 발견했다.

Sentry 가 없애는 것은 **"터진 걸 모르는 상태"** 하나다. 조용히 나빠지는 것은
검사와 실측이 맡는다 ([13 Gemini 실측](13-gemini-benchmark.md)).

### 9.3 개인정보처리방침과 묶인다

외부 처리자에게 데이터를 보내므로 방침에 적어야 한다 — 무엇을, 어디로, 왜.
순서는 **이쪽이 먼저**다. 무엇을 보내는지 확정한 뒤에 그 내용을 방침에 받아 적는다
(`M1-T2`).
