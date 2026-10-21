# CLAUDE.md

LLM 으로 영어 문장을 분석해 **번역 · 표현 풀이 · 문장 구조 · 총평** 네 파트로 보여주고,
표현마다 **작문 연습**을 시키는 웹 도구.

한 코드베이스가 두 모드로 돈다. 어느 쪽을 건드리는지 항상 의식한다.

| | `APP_MODE=local` | `APP_MODE=cloud` |
|---|---|---|
| LLM | llama-server (직접 띄움) | Gemini (회원이 등록한 키) |
| 로그인 | 없음 (`user_id=1` 고정) | Google OAuth |
| 입력 상한 | 2000자 | 800자 |

**모드별로 갈리는 것은 전부 [09-mode-matrix.md](documents/09-mode-matrix.md) 에 모여 있다.
한쪽만 고치면 다른 쪽이 조용히 어긋난다 — 모드 관련 변경 전에 먼저 읽는다.**

모드를 건드렸으면 **세 가지를 함께** 한다 ([09 6절](documents/09-mode-matrix.md)):

1. 공통 기능이면 테스트를 `tests/test_both_modes.py` 에 `both_modes` 픽스처로 쓴다
   — 두 모드에서 각각 돈다. 모드 전용만 `tests/test_cloud.py` 로 간다.
2. 09 의 표에 있는 값을 바꿨으면 **문서와 `tests/test_mode_matrix.py` 를 함께** 고친다.
3. `./dev.sh cloud` 로 띄워서 눈으로 본다. **cloud 를 띄워 보지 않고 머지하지 않는다.**

## 작업 절차

1. **시작 전** — [ROADMAP](documents/plan/ROADMAP.md) 과 [ISSUES](documents/plan/ISSUES.md) 를 읽고,
   지금 하는 일이 어느 **태그**(`M2-T3` / `H-012`)인지 정한다. 없으면 먼저 추가한다.
2. **진행 중** — ROADMAP(또는 ISSUES)의 해당 줄을 `[~]` 로 바꾼다.
3. **끝내면**
   - 그 줄을 `[x]` 로 바꾼다. **줄을 지우지 않는다** — 한 줄 요약은 그대로 남긴다
   - [DONE](documents/plan/DONE.md) 에 **같은 태그로** 세부를 적는다 — 무엇을 / 왜 / 어떻게 / PR 번호
   - 설계 판단이 바뀌었으면 `documents/01~NN` 의 해당 문서도 같이 고친다
4. **커밋** — 메시지 끝에 태그 한 줄 (`M2-T3`). **PR 제목 앞에도 태그** (`[M2-T3] 단어장 화면`).
5. 브랜치는 `dev-web` 에서 작업하고 푸시 후 PR 을 올린다. **머지는 사용자가 한다.**

태그 번호는 **재사용하지 않는다.** 지운 번호를 다시 쓰면 커밋과 코드 주석의 링크가 조용히 썩는다.

## 명령

```bash
./dev.sh              # local 모드 — 백엔드 + 프론트엔드 (llama-server 를 먼저 띄울 것)
./dev.sh cloud        # cloud 모드 — .env.cloud 로 웹 배포와 같은 구성
./dev.sh stop         # 내리기
./dev.sh status       # 떠 있는 것 + llama-server 연결 상태
./dev.sh db           # 로컬 Postgres (docker, 15432 포트)

cd backend && uv run pytest      # 테스트
cd backend && uv run ruff check  # 린트
```

포트를 바꾸려면 `BACKEND_PORT=9000 FRONTEND_PORT=3000 ./dev.sh` — 같은 값을 `stop`/`status` 에도 넘긴다.

## 코드 규칙

- **주석과 문서는 한국어.** 설명체(`~이다` / `~한다`)로 쓴다.
- **LLM 에 거는 제약은 프롬프트가 아니라 JSON 스키마로 건다.**
  부탁하면 안 지켜지고, 스키마로 요구하면 지켜진다. 개수·필수 필드는 전부 스키마 쪽에 있다.
  단 `pattern` / `maxLength` / `minLength` 는 llama-server 에서 깨진다 — [05-benchmark.md](documents/05-benchmark.md).
- **모드별 값은 `app/config.py` 한 곳에서만** 갈린다. 라우터나 서비스에 모드 분기를 흩뿌리지 않는다.
- **Pydantic 모델을 느슨하게 만들어 옛 기록 호환을 해결하지 않는다.**
  같은 모델이 LLM 응답 검증에도 쓰이므로, 모델이 필드를 빠뜨려도 통과하게 된다.
  대신 `app/services/records.py` 에서 **읽을 때만** 형식을 올린다.
  결과 스키마를 바꿀 때마다 `RESULT_VERSION` 을 올리고 변환 규칙을 추가한다 — [07 §8.1](documents/07-web-deployment.md).
- **비밀값을 대화나 커밋에 남기지 않는다.** `backend/.env*` 는 gitignore 되어 있다.
  `ENCRYPTION_KEY` 는 **절대 교체하지 않는다** — 회원이 등록한 Gemini 키를 복호화할 수 없게 된다.
- hover 같은 포인터 동작은 **headless 브라우저로 검증되지 않는다**
  (headless Chrome 은 `hover: hover` 를 false 로 보고한다). 직접 띄워 확인한다.

## 문서 규약

**이 문서가 문서 계층의 꼭대기다.** 여기서 [문서 지도](documents/00-index.md) 로 가고,
지도에서 나머지 전부로 간다. 지도를 거치지 않는 문서는 없다.

```
CLAUDE.md                 ← 지금 읽고 있는 것. 메타 규약, 세션마다 자동으로 읽힌다
└── documents/00-index.md ← 유일한 색인. 층·상태·"읽어야 할 때" 가 여기 모인다
    ├── 제품 설계 규약 운영 기록   01~09
    └── 진행                      plan/ROADMAP · ISSUES · DONE
README.md                 ← 사람이 처음 띄울 때 보는 설치·실행 안내. 색인이 아니다 ([README](README.md))
```

지켜야 할 것은 넷이다.

1. **색인은 00-index 하나뿐.** 다른 문서에 목록을 복사하지 않는다. 둘이 되면 갈라진다.
2. **모든 문서는 표준 머리말을 단다** — 층 · 상태 · 읽어야 할 때 · 위 · 함께.
   `위` 가 되돌아 나가는 길이라서, 이게 있으면 **고아도 막다른 문서도 안 생긴다.**
   형식은 [00-index 4.1](documents/00-index.md).
3. **파일명과 절 번호를 바꾸지 않는다.** 코드 주석이 주소로 쓴다 ([00-index 3절](documents/00-index.md)).
   새 문서는 다음 번호로 이어 붙인다.
4. **상태는 셋뿐.** 유효(코드가 이대로다) · 기록(그때의 측정·판단, 손대지 않는다) · 대체됨.
   **기록 층 문서(05, 08)를 지금 사실에 맞춰 고치지 않는다.** 그때의 판단이 사라진다.

`./dev.sh docs` 가 끊긴 링크 · 머리말 누락 · 색인에 없는 문서 · 태그 불일치를 찾아 준다.

### 어떤 작업에 어떤 문서를 펴는가

문서를 안 보고 고치는 것이 가장 흔한 실패다. **코드를 고치기 전에** 짝을 맞춘다.

| 건드리는 것 | 함께 펴는 문서 |
|---|---|
| `app/prompts/` | [04 프롬프트 설계](documents/04-prompt-design.md) · [05 실측](documents/05-benchmark.md) |
| `app/routers/` | [03 API 명세](documents/03-api-spec.md) |
| 모드에 따라 갈리는 것 | **[09 모드별 차이](documents/09-mode-matrix.md) — 먼저** |
| 인증 · 배포 · 저장 스키마 | [07 웹 배포](documents/07-web-deployment.md) |
| 난이도 기준 | [08 난이도 설계](documents/08-level-design.md) |
| 작문 연습 | [06 작문 연습](documents/06-practice.md) |
| 화면에 보이는 것 | [01 제품 기획서](documents/01-product-spec.md) |
