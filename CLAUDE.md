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
./dev.sh              # 백엔드 + 프론트엔드 (llama-server 를 먼저 띄울 것)
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

## 문서

[documents/00-index.md](documents/00-index.md) 에 지도가 있다. 성격이 셋으로 갈린다.

- `documents/01~NN` — **설계 결정 기록.** 왜 그렇게 했는지. 코드 주석이 절 번호로 가리키므로
  **파일명과 절 번호를 바꾸지 않는다.** 새 설계는 다음 번호로 이어 붙인다.
- `documents/plan/` — **진행 상황.** ROADMAP(의도한 계획) · ISSUES(의도치 않게 생긴 문제) · DONE(세부 기록).
  앞의 둘은 같은 방식으로 적는다 — 체크박스 + 태그 + 한 줄 요약. 세부는 DONE 에만.
- `README.md` — 사람이 처음 띄울 때 보는 안내.
