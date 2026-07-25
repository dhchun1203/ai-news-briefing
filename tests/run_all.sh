#!/usr/bin/env bash
# 전체 테스트 실행. CI(.github/workflows)와 로컬에서 같은 명령을 쓴다.
#   bash tests/run_all.sh
set -u
cd "$(dirname "$0")/.."

fail=0

run() {
  echo ""
  echo "=== $1 ==="
  shift
  if "$@"; then
    echo "-> OK"
  else
    echo "-> FAILED"
    fail=1
  fi
}

# 파이썬 인터프리터 고르기 (CI는 python3, 로컬 Windows는 py)
PY=""
for exe in python3 py python; do
  if command -v "$exe" >/dev/null 2>&1 && "$exe" -c "import sys" >/dev/null 2>&1; then
    PY="$exe"
    break
  fi
done
if [ -z "$PY" ]; then
  echo "no working python interpreter found"
  exit 1
fi

run "python: 문법 검사" "$PY" -m py_compile scripts/kst_date.py scripts/fetch_articles.py \
  scripts/generate_site.py scripts/generate_weekly_site.py scripts/seo_utils.py \
  scripts/og_image.py scripts/send_broadcast.py

# pytest 대신 표준 라이브러리 unittest — 이 저장소는 의존성을 최소로 유지한다.
run "python: 단위 테스트" "$PY" -m unittest discover -s tests -p "test_*.py"

run "node: 문법 검사" bash -c 'for f in api/*.js api/_lib/*.js; do node --check "$f" || exit 1; done'

run "node: api 핸들러 동작" node tests/api_handlers.test.js

run "node: Python<->Node HMAC 동등성" node tests/hmac_parity.test.js

# jsdom이 있으면 실제 생성된 HTML로 인터랙션까지 확인한다(없으면 스스로 SKIP).
run "node: 브라우저 동작 스모크(jsdom)" node tests/dom_smoke.test.js

echo ""
if [ "$fail" -eq 0 ]; then
  echo "ALL TESTS PASSED"
else
  echo "SOME TESTS FAILED"
fi
exit "$fail"
