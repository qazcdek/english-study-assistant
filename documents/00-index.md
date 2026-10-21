# 00. 문서 지도

문서는 성격이 셋으로 갈린다. **무엇을 고칠 때 어디를 같이 고치는지**가 이 문서의 목적이다.

## 1. 설계 결정 기록 (`01~NN`)

왜 그렇게 했는지를 남긴다. 한 번 쓰고 끝이 아니라, 판단이 바뀌면 해당 문서를 고친다.

| 문서 | 다루는 것 | 언제 같이 고치나 |
|---|---|---|
| [01-product-spec](01-product-spec.md) | 제품 기획, 네 파트 정의, 사용 흐름 | 화면에 보이는 것이 늘거나 줄 때 |
| [02-architecture](02-architecture.md) | 계층 구조, 파트별 요청 흐름, 환경 변수 | 모듈을 추가하거나 흐름을 바꿀 때 |
| [03-api-spec](03-api-spec.md) | 엔드포인트, 요청·응답, 오류 코드 | 라우터를 건드릴 때 |
| [04-prompt-design](04-prompt-design.md) | 프롬프트 원칙, 컬럼별 명세, 정제 규칙 | `app/prompts/` 를 건드릴 때 |
| [05-benchmark](05-benchmark.md) | 단일 호출 vs 파트 분할 실측, 스키마 제약 지원 범위 | 새로 측정했을 때 |
| [06-practice](06-practice.md) | 작문 연습의 교육학적 근거, UI, 채점 | 연습 기능을 건드릴 때 |
| [07-web-deployment](07-web-deployment.md) | 로그인·키 보관·사용량·배포, **8.1 저장 스키마 변경** | 인증·배포·결과 스키마를 바꿀 때 |
| [08-level-design](08-level-design.md) | 난이도를 무엇으로 가르는지 (기획안 v2) | 초·중·고급 기준을 바꿀 때 |
| [09-mode-matrix](09-mode-matrix.md) | **모드별로 갈리는 모든 것** | 로컬/웹 중 한쪽만 바꿀 때 — **반드시** |

**파일명과 절 번호를 바꾸지 않는다.** 코드가 이렇게 가리키고 있다:

```
app/config.py:57         09-mode-matrix.md 3.1
app/schemas.py:16        09-mode-matrix.md 3.1
app/routers/analyze.py   09-mode-matrix.md 3.1, 3.3
app/services/records.py  04-prompt-design.md 7절
app/prompts/analysis.py  05-benchmark.md
app/prompts/practice.py  06-practice.md
app/providers/llama_server.py  05-benchmark.md
app/auth/google.py       07-web-deployment.md
```

새 설계 문서는 `10-`, `11-` 로 이어 붙이고 이 표에 한 줄 추가한다.

## 2. 진행 상황 (`plan/`)

| 문서 | 역할 | 들어가는 것 |
|---|---|---|
| [ROADMAP](plan/ROADMAP.md) | **구조** | 마일스톤(M)과 태스크(T). 체크박스 + 태그 + 한 줄 요약만 |
| [ISSUES](plan/ISSUES.md) | **큐** | 아직 안 고친 문제(H). 고치면 줄을 지운다 |
| [DONE](plan/DONE.md) | **기록** | 끝난 T·H 의 세부 내용. 날짜 역순 |

같은 정보를 두 군데 두지 않는다.
**상태는 ROADMAP 의 체크박스 하나뿐이고, 세부는 DONE 한 군데에만 있다.**

### T 와 H 를 가르는 기준

- **T (task)** — 만들 것. 마일스톤에 묶인다. `M2-T3`
- **H (hotfix)** — 고칠 것. 이미 있는 동작이 틀렸거나 어긋난 경우. 마일스톤에 묶이지 않고 전역 연번. `H-012`

"아직 안 만든 기능"은 H 가 아니라 T 다. 판단이 애매하면 **지금 동작이 잘못됐나**를 묻는다.

## 3. 안내 (`README.md`)

처음 띄우는 사람을 위한 설치·실행 안내. 개발 지침은 루트 [CLAUDE.md](../CLAUDE.md) 에 있다.
