#!/usr/bin/env bash
#
# 개발 서버 실행 스크립트.
#
#   ./dev.sh              백엔드 + 프론트엔드 동시 실행
#   ./dev.sh backend      백엔드만
#   ./dev.sh frontend     프론트엔드만
#   ./dev.sh stop         다른 데서 띄워 둔 서버를 내린다 (DB 컨테이너는 그대로 둔다)
#   ./dev.sh db           Postgres 컨테이너만 띄운다
#   ./dev.sh status       지금 뭐가 떠 있는지 본다
#   ./dev.sh check        llama-server 연결만 확인하고 종료
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
  base="$(grep -E '^LLM_BASE_URL=' "$BACKEND/.env" 2>/dev/null | cut -d= -f2- || true)"
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
  spawn bash -c "cd '$BACKEND' && exec .venv/bin/uvicorn app.main:app --reload --port '$BACKEND_PORT'"
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
  check_llm
}

main() {
  case "${1:-all}" in
    check)
      check_llm
      ;;
    db)
      start_db
      ;;
    stop)
      stop_servers
      ;;
    status)
      show_status
      ;;
    backend)
      require_free_port "$BACKEND_PORT" backend
      setup_backend; start_db; check_llm
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
      setup_backend; setup_frontend; start_db; check_llm
      trap cleanup INT TERM EXIT
      run_backend
      run_frontend
      printf '%s\n' "$$" "${PIDS[@]}" > "$PIDFILE"
      printf '\n%s\n' "  ${BOLD}웹${RESET}      http://localhost:${FRONTEND_PORT}"
      printf '%s\n'   "  ${BOLD}API 문서${RESET} http://127.0.0.1:${BACKEND_PORT}/docs"
      printf '%s\n\n' "  ${DIM}Ctrl+C 또는 다른 터미널에서 ./dev.sh stop 으로 종료${RESET}"
      wait
      ;;
    -h|--help|help)
      sed -n '3,14p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
      ;;
    *)
      die "알 수 없는 인자: $1  (backend | frontend | db | stop | status | check | help)"
      ;;
  esac
}

main "$@"
