#!/usr/bin/env bash
#
# 개발 서버 실행 스크립트.
#
#   ./dev.sh              백엔드 + 프론트엔드 동시 실행 (local 모드)
#   ./dev.sh cloud        웹 배포와 같은 cloud 모드로 띄운다 (.env.cloud 사용)
#   ./dev.sh backend      백엔드만
#   ./dev.sh frontend     프론트엔드만
#   ./dev.sh stop         다른 데서 띄워 둔 서버를 내린다 (DB 컨테이너는 그대로 둔다)
#   ./dev.sh db           Postgres 컨테이너만 띄운다
#   ./dev.sh status       지금 뭐가 떠 있는지 본다
#   ./dev.sh next         열린 작업을 모아 본다 (./dev.sh next M2 처럼 좁힐 수 있다)
#   ./dev.sh docs         문서 계층 점검 (그래프 · 주소 · 머리말 · 색인 · 태그)
#   ./dev.sh ptr          문서 → 코드 포인터 점검 (--write 로 코드 쪽을 갱신)
#   ./dev.sh refs         한 문서(또는 절)로 들어오는 참조를 센다 — 옮기기 전에 본다
#   ./dev.sh check        llama-server 연결만 확인하고 종료
#
# 모드는 앞에 붙여도 된다: ./dev.sh cloud backend
#
# 처음 실행하면 venv 생성, 의존성 설치, .env 복사까지 알아서 한다.
# 터미널에 붙여 띄웠다면 Ctrl+C, 백그라운드로 돌렸다면 ./dev.sh stop 으로 내린다.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
PIDFILE="$ROOT/.dev.pid"

# 어느 모드로 띄울지. cloud 는 웹 배포와 같은 구성(로그인 + 회원 Gemini 키)으로 돈다.
# 띄워 보지 않고 머지하면 cloud 쪽 회귀를 Render 에 올려야 발견하게 된다 (09-mode-matrix.md).
MODE="${APP_MODE:-local}"
if [[ "${1:-}" == "cloud" || "${1:-}" == "local" ]]; then
  MODE="$1"; shift
fi
ENV_FILE="$BACKEND/.env"
[[ "$MODE" == "cloud" ]] && ENV_FILE="$BACKEND/.env.cloud"

if [[ -t 1 ]]; then
  BOLD=$'\e[1m'; DIM=$'\e[2m'; RED=$'\e[31m'; GREEN=$'\e[32m'; YELLOW=$'\e[33m'; RESET=$'\e[0m'
else
  BOLD=''; DIM=''; RED=''; GREEN=''; YELLOW=''; RESET=''
fi

info() { printf '%s\n' "${DIM}·${RESET} $*"; }
ok()   { printf '%s\n' "${GREEN}✓${RESET} $*"; }
warn() { printf '%s\n' "${YELLOW}!${RESET} $*"; }
die()  { printf '%s\n' "${RED}✗${RESET} $*" >&2; exit 1; }

# --------------------------------------------------------------------- 사전 점검

port_in_use() {
  # ss 가 없는 환경도 있으므로 bash 의 /dev/tcp 로 확인한다.
  (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null && exec 3>&- && return 0
  return 1
}

require_free_port() {
  local port=$1 what=$2
  if port_in_use "$port"; then
    die "$port 포트가 이미 사용 중입니다 ($what). 먼저 내리거나 ${what^^}_PORT 로 다른 포트를 지정하세요."
  fi
}

DB_PORT="${DB_PORT:-15432}"

start_db() {
  command -v docker >/dev/null 2>&1 || die "docker 를 찾을 수 없습니다. 분석 기록을 Postgres 에 저장합니다."

  if port_in_use "$DB_PORT"; then
    ok "Postgres 이미 떠 있음 ${DIM}127.0.0.1:${DB_PORT}${RESET}"
    return 0
  fi

  info "Postgres 컨테이너를 띄웁니다…"
  (cd "$ROOT" && docker compose up -d) >/dev/null 2>&1 || die "docker compose up 에 실패했습니다."

  for _ in $(seq 1 40); do
    if (cd "$ROOT" && docker compose exec -T db pg_isready -U eng -d eng_study) >/dev/null 2>&1; then
      ok "Postgres 준비됨 ${DIM}127.0.0.1:${DB_PORT}${RESET}"
      return 0
    fi
    sleep 0.5
  done
  die "Postgres 가 준비되지 않았습니다. docker compose logs db 를 확인하세요."
}

check_llm() {
  local url base
  base="$(grep -E '^LLM_BASE_URL=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)"
  base="${base:-http://127.0.0.1:8080/v1}"
  url="${base%/}/models"

  if ! command -v curl >/dev/null 2>&1; then
    warn "curl 이 없어 llama-server 확인을 건너뜁니다."
    return 0
  fi

  local body
  if body="$(curl -sf -m 5 "$url" 2>/dev/null)"; then
    local model
    model="$(printf '%s' "$body" | sed -n 's/.*"id"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)"
    ok "llama-server 연결됨 ${DIM}${base}${RESET}${model:+ — ${BOLD}${model}${RESET}}"
  else
    warn "llama-server 에 연결할 수 없습니다 ${DIM}(${base})${RESET}"
    warn "웹은 뜨지만 분석 요청은 503 으로 실패합니다. 모델 서버를 먼저 띄우세요."
  fi
}

# --------------------------------------------------------------------- 부트스트랩

setup_backend() {
  if [[ ! -x "$BACKEND/.venv/bin/uvicorn" ]]; then
    info "백엔드 의존성을 설치합니다 (최초 1회)…"
    if command -v uv >/dev/null 2>&1; then
      (cd "$BACKEND" && uv venv --quiet && uv pip install --quiet -e ".[dev]")
    else
      (cd "$BACKEND" && python3 -m venv .venv && .venv/bin/pip install --quiet -e ".[dev]")
    fi
    ok "백엔드 의존성 설치 완료"
  fi

  if [[ ! -f "$BACKEND/.env" ]]; then
    cp "$BACKEND/.env.example" "$BACKEND/.env"
    warn ".env 를 새로 만들었습니다. LLM_MODEL 을 llama-server 의 --alias 값과 맞추세요."
  fi
}

setup_frontend() {
  command -v npm >/dev/null 2>&1 || die "npm 을 찾을 수 없습니다."
  if [[ ! -d "$FRONTEND/node_modules" ]]; then
    info "프론트엔드 의존성을 설치합니다 (최초 1회)…"
    (cd "$FRONTEND" && npm install --no-audit --no-fund)
    ok "프론트엔드 의존성 설치 완료"
  fi
}

check_docs() {
  # 문서 계층이 성한지 본다: 링크 그래프 · 머리말 누락 · 색인에 없는 문서 · 태그 정합성.
  # 규약은 documents/00-index.md 4절, 꼭대기는 CLAUDE.md 다.
  local index="$ROOT/documents/00-index.md" bad=0

  # 1) 링크 그래프와 주소 — 꼭대기에서 닿는지, 코드가 가리키는 문서 주소가 살아 있는지,
  #    머리말이 다 있는지. 전부 글자가 아니라 구조를 보는 검사라 파이썬 쪽에 둔다.
  #    구현은 backend/tests/test_docs_graph.py · test_doc_references.py 두 곳뿐이다.
  if [[ -x "$BACKEND/.venv/bin/pytest" ]]; then
    local out; out="$(cd "$BACKEND" && .venv/bin/pytest \
                        tests/test_docs_graph.py tests/test_doc_references.py \
                        -q -p no:cacheprovider --no-header 2>&1)" || {
      printf '%s\n' "$out" | sed -n 's/^E *//p' | grep -v '^assert ' |
        while IFS= read -r l; do warn "$l"; done
      bad=1
    }
  else
    warn "링크 그래프를 검사하지 못했습니다 — ./dev.sh backend 로 의존성을 먼저 설치하세요."
    bad=1
  fi

  # 2) 색인이 모든 문서를 가리키는가
  for f in "$ROOT"/documents/*.md "$ROOT"/documents/plan/*.md; do
    [[ -e "$f" && "$f" != "$index" ]] || continue
    local rel="${f#$ROOT/documents/}"
    grep -q "(${rel%.md}.md)" "$index" || { warn "색인에 없음  documents/$rel"; bad=1; }
  done

  # 3) 추적 정합성은 pytest 쪽에서 본다 (1번에 포함) — 세부의 자리가 상태에 따라
  #    갈리므로(ONGOING / DONE) 글자 비교로는 부족하다.

  if [[ $bad -eq 0 ]]; then
    ok "문서 계층 이상 없음 ${DIM}(그래프 · 주소 · 머리말 · 색인 · 태그)${RESET}"
  else
    die "문서 계층에 문제가 있습니다. 규약은 documents/00-index.md 4절."
  fi
}

needs_local_db() {
  # DATABASE_URL 이 docker Postgres 를 가리킬 때만 컨테이너를 띄운다.
  # .env.cloud 처럼 sqlite 나 원격 DB 를 가리키면 띄울 필요가 없다.
  local url
  url="$(grep -E '^DATABASE_URL=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)"
  [[ -z "$url" ]] && return 0          # 값이 없으면 config.py 의 기본값(= docker Postgres)
  [[ "$url" == *":$DB_PORT/"* ]]
}

preflight() {
  if [[ "$MODE" == "cloud" ]]; then
    [[ -f "$ENV_FILE" ]] || die "$ENV_FILE 가 없습니다. .env.example 을 복사해 cloud 값을 채우세요."
    local missing=()
    for key in APP_MODE GOOGLE_CLIENT_ID GOOGLE_CLIENT_SECRET SESSION_SECRET ENCRYPTION_KEY; do
      grep -qE "^${key}=.+" "$ENV_FILE" || missing+=("$key")
    done
    [[ ${#missing[@]} -eq 0 ]] || die "$ENV_FILE 에 값이 비어 있습니다: ${missing[*]}"
    warn "${BOLD}cloud${RESET} 모드 — 로그인과 회원 Gemini 키가 필요합니다 ${DIM}($(basename "$ENV_FILE"))${RESET}"
  fi

  if needs_local_db; then start_db; fi
  if [[ "$MODE" == "local" ]]; then check_llm; fi
}

# --------------------------------------------------------------------- 실행

PIDS=()

# npm run dev 는 sh -c vite -> node 로 갈라지고, uvicorn --reload 는 reloader 자식을 둔다.
# 부모 PID 만 죽이면 자식이 살아남아 포트를 쥐고 있으므로, 각 서버를 별도 프로세스 그룹으로
# 띄운 뒤 그룹 전체에 신호를 보낸다.
spawn() {
  if command -v setsid >/dev/null 2>&1; then
    setsid "$@" &
  else
    "$@" &
  fi
  PIDS+=("$!")
}

cleanup() {
  trap - INT TERM EXIT
  rm -f "$PIDFILE"
  [[ ${#PIDS[@]} -gt 0 ]] && printf '\n%s\n' "${DIM}서버를 내리는 중…${RESET}"
  for pid in ${PIDS+"${PIDS[@]}"}; do
    kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
  done
  sleep 1
  for pid in ${PIDS+"${PIDS[@]}"}; do
    kill -KILL -- "-$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
}

run_backend() {
  # --env-file 로 넣은 값은 os.environ 에 올라가 pydantic-settings 의 .env 보다 우선한다.
  # 그래서 cloud 모드에서도 코드를 고치지 않고 .env.cloud 로 갈아끼울 수 있다.
  spawn bash -c "cd '$BACKEND' && exec .venv/bin/uvicorn app.main:app --reload --port '$BACKEND_PORT' --env-file '$ENV_FILE'"
}

run_frontend() {
  # vite 의 /api 프록시가 실제 백엔드 포트를 보게 한다.
  # .env.local 등으로 이미 지정했다면 그 값을 존중한다.
  local target="${VITE_API_TARGET:-http://127.0.0.1:$BACKEND_PORT}"
  spawn bash -c "cd '$FRONTEND' && VITE_API_TARGET='$target' exec npm run dev -- --port '$FRONTEND_PORT'"
}

# 현재 실행 중인 dev.sh 의 PID. 없으면 빈 문자열.
running_pid() {
  [[ -f "$PIDFILE" ]] || return 0
  local pid
  pid="$(head -1 "$PIDFILE" 2>/dev/null || true)"
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null && printf '%s' "$pid"
}

stop_servers() {
  local pid
  pid="$(running_pid)"

  if [[ -n "$pid" ]]; then
    info "dev.sh (pid $pid) 를 내리는 중…"
    kill -TERM "$pid" 2>/dev/null || true
    # cleanup 트랩이 자식 프로세스 그룹까지 정리한다.
    for _ in $(seq 1 20); do
      kill -0 "$pid" 2>/dev/null || break
      sleep 0.5
    done
    kill -0 "$pid" 2>/dev/null && kill -KILL "$pid" 2>/dev/null || true
  else
    rm -f "$PIDFILE"
  fi

  local leftover=0
  for port in "$BACKEND_PORT" "$FRONTEND_PORT"; do
    if port_in_use "$port"; then
      warn "$port 포트를 아직 무언가 쥐고 있습니다."
      leftover=1
    fi
  done

  if [[ $leftover -eq 1 ]]; then
    warn "dev.sh 가 띄운 것이 아닐 수 있습니다. 확인: ${BOLD}./dev.sh status${RESET}"
  elif [[ -n "$pid" ]]; then
    ok "모두 내렸습니다."
  else
    info "떠 있는 서버가 없습니다."
  fi
}

show_status() {
  info "모드 ${BOLD}${MODE}${RESET} ${DIM}($(basename "$ENV_FILE"))${RESET}"
  local pid
  pid="$(running_pid)"
  if [[ -n "$pid" ]]; then
    ok "dev.sh 실행 중 (pid $pid)"
  else
    info "dev.sh 는 실행 중이 아닙니다."
  fi

  for entry in "백엔드:$BACKEND_PORT" "프론트엔드:$FRONTEND_PORT" "Postgres:$DB_PORT"; do
    local name="${entry%%:*}" port="${entry##*:}"
    if port_in_use "$port"; then
      ok "$name  ${DIM}http://127.0.0.1:${port}${RESET}"
    else
      info "$name  ${DIM}(꺼져 있음, 포트 $port)${RESET}"
    fi
  done
  if [[ "$MODE" == "local" ]]; then check_llm; fi
}

main() {
  case "${1:-all}" in
    check)
      check_llm
      ;;
    db)
      start_db
      ;;
    docs)
      check_docs
      ;;
    next|todo)
      # 열린 작업(ROADMAP + ISSUES)을 한 곳에 모아 본다. 인자로 태그 접두사를 좁힐 수 있다.
      [[ -x "$BACKEND/.venv/bin/python" ]] || die "먼저 ./dev.sh backend 로 의존성을 설치하세요."
      shift
      (cd "$BACKEND" && .venv/bin/python tools/tasks.py "$@")
      ;;
    ptr)
      # 문서 → 코드 포인터를 코드 docstring 에 반영한다. 인자 없이 쓰면 검사만 한다.
      [[ -x "$BACKEND/.venv/bin/python" ]] || die "먼저 ./dev.sh backend 로 의존성을 설치하세요."
      shift
      (cd "$BACKEND" && .venv/bin/python tools/docptr.py "$@") &&
        ok "문서 → 코드 포인터 이상 없음"
      ;;
    refs)
      # 내용을 다른 문서로 옮기기 **전에** 무엇이 딸려 오는지 본다 (11 §3.6).
      [[ -x "$BACKEND/.venv/bin/python" ]] || die "먼저 ./dev.sh backend 로 의존성을 설치하세요."
      shift
      (cd "$BACKEND" && .venv/bin/python tools/refs.py "$@")
      ;;
    stop)
      stop_servers
      ;;
    status)
      show_status
      ;;
    backend)
      require_free_port "$BACKEND_PORT" backend
      setup_backend; preflight
      trap cleanup INT TERM EXIT
      run_backend
      printf '%s\n' "$$" "${PIDS[@]}" > "$PIDFILE"
      ok "백엔드 ${BOLD}http://127.0.0.1:${BACKEND_PORT}/docs${RESET}"
      wait
      ;;
    frontend)
      require_free_port "$FRONTEND_PORT" frontend
      setup_frontend
      trap cleanup INT TERM EXIT
      run_frontend
      printf '%s\n' "$$" "${PIDS[@]}" > "$PIDFILE"
      wait
      ;;
    all)
      require_free_port "$BACKEND_PORT" backend
      require_free_port "$FRONTEND_PORT" frontend
      setup_backend; setup_frontend; preflight
      trap cleanup INT TERM EXIT
      run_backend
      run_frontend
      printf '%s\n' "$$" "${PIDS[@]}" > "$PIDFILE"
      printf '\n%s\n' "  ${BOLD}모드${RESET}    ${MODE}"
      printf '%s\n'   "  ${BOLD}웹${RESET}      http://localhost:${FRONTEND_PORT}"
      printf '%s\n'   "  ${BOLD}API 문서${RESET} http://127.0.0.1:${BACKEND_PORT}/docs"
      printf '%s\n\n' "  ${DIM}Ctrl+C 또는 다른 터미널에서 ./dev.sh stop 으로 종료${RESET}"
      wait
      ;;
    -h|--help|help)
      sed -n '3,20p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
      ;;
    *)
      die "알 수 없는 인자: $1  (cloud | backend | frontend | db | docs | ptr | next | stop | status | check | help)"
      ;;
  esac
}

main "$@"
