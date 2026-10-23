"""운영자 — **공용 글감을 만드는 데 쓰이는 회원.**

**cloud 전용이다** (09-mode-matrix.md §3.8). local 은 혼자 쓰므로 문단을 직접
넣으면 되고, 하루 한 편을 서버가 준비해 둘 이유가 없다. 그래서 local 부트스트랩
사용자에게는 이 플래그를 켜지 않는다 — `find()` 가 `None` 을 돌려주고 기능이 꺼진다.

공용 글감(`M13`)은 누구의 것도 아니지만 **만드는 데는 LLM 키가 필요하다.**
회원 키를 쓸 수는 없다 — 회원은 자기 분석에 쓰라고 등록한 것이고, 남이 볼 글감을
자기 한도로 만들라고 준 것이 아니다. 그래서 **운영자 한 명의 키로** 돌린다.

### 키를 새로 두지 않는다

운영자도 회원이므로 `provider_keys` 에 이미 자기 키가 있다. 설정 화면에서 등록한
그것을 그대로 쓴다. **서버 환경변수에 LLM 키를 두지 않는다** — 둘이 되면 어느 쪽이
쓰이는지 흐려지고, 암호화해 보관하는 규약(`keys.py`)을 비켜 가게 된다.

### 이메일은 두 곳에 적히지만 갈라지지 않는다

법적 문서의 운영 주체 정보가 `frontend/src/legal/operator.ts` 에 이미 있다.
백엔드도 알아야 하므로 아래에 한 번 더 적는데, **두 값이 어긋나면 검사가 거부한다**
(`tests/test_operator.py`). 방침의 수탁자 목록을 레지스트리와 대조하는 것과
같은 장치다 (M12-T5).

### 플래그는 구글이 검증한 이메일에서만 온다

`is_operator` 는 **키를 쓸 권한**이다. 그래서 `email_verified` 가 참일 때만 켠다.
로그인 자체는 그것을 요구하지 않지만(기존 동작) 이 플래그는 요구한다.

로그인할 때마다 다시 맞춘다 — 이메일이 바뀌면 **꺼지기도 한다.** 한 번 켜고 두는
쪽은 운영자가 바뀐 뒤에도 옛 계정이 키 권한을 들고 있게 만든다.

[문서] 09-mode-matrix.md 운영자 플래그
"""

from sqlalchemy.orm import Session

from app.db import User

# `frontend/src/legal/operator.ts` 의 `연락처` 와 **같아야 한다.** 검사가 대조한다.
OPERATOR_EMAIL = "qazcde.k@gmail.com"

# 공용 글감을 만들 때 쓰는 제공자. **운영자의 활성 선택을 따르지 않는다** —
# 운영자가 설정 화면에서 제공자를 바꾸면 모든 회원이 보는 글감의 품질이 같이
# 흔들린다. 공용 글감은 회원 전역 설정과 **따로 움직여야 한다.**
#
# Gemini Flash-Lite 를 쓰는 이유는 값이다. 기사 한 편 18문단 × 네 파트 = 72 호출이고,
# 무료 등급이 일 250 호출이라 영·미 두 곳(144)까지 들어간다 (M13-T1 · M13-T3 실측).
JOB_PROVIDER = "gemini"


def is_operator_email(email: str, *, verified: bool) -> bool:
    """이 이메일이 운영자인가. **검증되지 않은 이메일은 아니다.**"""
    return verified and email.strip().lower() == OPERATOR_EMAIL


def find(db: Session) -> User | None:
    """플래그가 켜진 회원. 없으면 `None` — 공용 글감을 만들 수 없다는 뜻이다."""
    return db.query(User).filter(User.is_operator.is_(True)).order_by(User.id).first()
