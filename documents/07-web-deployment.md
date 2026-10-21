# 07. 웹 배포 (main 브랜치)

`local` 브랜치는 내 PC 의 llama-server 에 붙는 1인용 도구다.
`main` 브랜치는 같은 코드에 **Google 로그인과 회원별 Gemini 키**를 얹어 웹에 배포한다.

두 형태는 `APP_MODE` 하나로 갈린다.

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

## 7. 저장하는 데이터

| 테이블 | 내용 |
|---|---|
| `users` | Google 식별자, 이메일, 동의 시각, 암호화된 API 키 |
| `analyses` | 분석 히스토리 (기기 간 동기화) |
| `practices` | 작문 연습 채점 기록 (오답만 다시 풀기의 토대) |
| `vocabulary` | 단어장 |
| `usage_counters` | 일 단위 사용량 |

회원 본인 데이터만 읽을 수 있다. 남의 기록 id 를 찍어도 거부된다(테스트로 확인).

## 8. 남은 것

- **오답 다시 풀기 / 단어장 화면** — 데이터는 쌓이지만 이를 보여줄 프론트 화면이 아직 없다.
- **탈퇴와 데이터 삭제** — 계정 삭제 API 가 없다. 개인정보 관점에서 먼저 붙여야 할 항목이다.
- **Alembic 마이그레이션** — 지금은 시작 시 `create_all` 로 테이블을 만든다.
  **테이블 컬럼**이 바뀌면 수동 조치가 필요하다. 회원이 생기기 전에 Alembic 으로 옮기는 편이 낫다.
  (JSON 컬럼 안의 결과 스키마는 아래 방식으로 따로 다룬다.)

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
