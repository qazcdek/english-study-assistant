# 10. 코드 규약

> **층** 규약 · **상태** 유효 · **강제** `backend/tests/`, `ruff`
> **읽어야 할 때** 코드를 쓰기 전에. [CLAUDE.md](../CLAUDE.md) 6절의 원칙을 구체적으로 풀어 둔 곳
> **위** [문서 지도](00-index.md) · **함께** [아키텍처](02-architecture.md) · [프롬프트 설계](04-prompt-design.md) · [모드별 차이](09-mode-matrix.md)

CLAUDE.md 에는 **원칙**만 둔다. 값·파일명·프로바이더 차이처럼 **바뀌는 것**은 여기 적는다.

## 1. 언어와 문체

주석과 문서는 한국어, 설명체(`~이다` / `~한다`)로 쓴다.
주석은 **무엇을 하는지가 아니라 왜 그런지**를 적는다. 코드가 이미 말하는 것을 되풀이하지 않는다.

```python
# 나쁨: is_cloud 면 사용량을 센다          ← 코드가 이미 말한다
# 좋음: 회원 각자의 Gemini 한도를 쓰는 cloud 에서만 센다 (09-mode-matrix.md 3.3)
```

## 2. LLM 에 거는 제약은 스키마로

부탁하면 안 지켜지고, 스키마로 요구하면 지켜진다. 개수·필수 필드는 전부 `response_format` 쪽에 둔다.

**프로바이더마다 지원 범위가 다르다.** 실측은 [05-benchmark.md](05-benchmark.md).

| 제약 | Gemini | llama-server |
|---|---|---|
| `minItems` / `maxItems` | 지킴 | 지킴 |
| `pattern` | 지킴 | **폭주하거나 무시한다** |
| `maxLength` | 지킴 | **낱말 중간에서 잘라 버린다** |
| `minLength` | 지킴 | **계속 생성해 `max_tokens` 를 넘긴다** |

양쪽에서 도는 스키마에는 아래 셋을 쓰지 않는다. 길이나 모양을 맞춰야 하면
프롬프트의 정오 예시로 유도하고, 코드(`app/services/refine.py`)에서 다듬는다.

## 3. 모드별 값은 한 곳에서만 갈린다

`app/config.py` 바깥에 모드 분기를 흩뿌리지 않는다. 갈리는 항목 전체는
[09-mode-matrix.md](09-mode-matrix.md) 가 들고 있고, `tests/test_mode_matrix.py` 가 그 표를 고정한다.

테스트를 어디에 두는지도 규약이다.

- **두 모드 공통 기능** → `tests/test_both_modes.py` 의 `both_modes` 픽스처. 모드마다 한 번씩 돈다.
- **모드 전용 동작** → `tests/test_cloud.py`

공통 기능을 한쪽에만 두면 다른 쪽이 깨져도 안 잡힌다. 자세한 것은 [09 6절](09-mode-matrix.md).

## 4. 저장된 결과의 형식이 바뀔 때

프롬프트를 손볼 때마다 결과 스키마가 바뀌는데, DB 에는 그때그때의 형식으로 남아 있다.

**Pydantic 모델을 느슨하게 만들어 해결하지 않는다.** 같은 모델이 LLM 응답 검증에도 쓰이므로,
모델이 필드를 빠뜨려도 조용히 통과하게 된다. 대신:

1. 모델은 엄격하게 둔다.
2. `app/services/records.py` 에서 **읽을 때만** 형식을 올린다.
3. 스키마를 바꿀 때마다 `RESULT_VERSION` 을 올리고 변환 규칙을 추가한다.

근거와 실제 사고 기록은 [07 §8.1](07-web-deployment.md).

## 5. 비밀값

- `backend/.env*` 는 gitignore 되어 있다. 값을 커밋이나 대화에 남기지 않는다.
- 회원의 Gemini 키는 Fernet 으로 암호화해 저장한다. 평문은 서버 밖으로 나가지 않고,
  돌려주는 것은 마지막 네 자리뿐이다.
- **`ENCRYPTION_KEY` 는 교체하지 않는다.** 바꾸면 이미 등록된 회원 키를 복호화할 수 없다.

## 6. 검증의 한계

- **hover 같은 포인터 동작은 headless 브라우저로 확인되지 않는다.**
  headless Chrome 은 `hover: hover` 와 `pointer: fine` 을 false 로 보고해서,
  멀쩡한 기능이 깨진 것처럼 보인다. 직접 띄워 본다.
- **LLM 응답 품질은 테스트로 고정되지 않는다.** 프롬프트를 바꾸면 실제로 돌려 보고
  달라진 점을 [05-benchmark.md](05-benchmark.md) 나 해당 설계 문서에 남긴다.
