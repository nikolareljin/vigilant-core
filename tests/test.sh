#!/bin/bash
# SCRIPT: test.sh
# DESCRIPTION: Run tests for VigilantCore application.
# AUTHOR: Nik Reljin
# PARAMETERS: Search Text
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SCRIPT_HELPERS_DIR="${SCRIPT_HELPERS_DIR:-$SCRIPT_DIR/script-helpers}"
ALT_HELPERS_DIRS=(
  "$ROOT_DIR/scripts/script-helpers"
  "$ROOT_DIR/vendor/script-helpers"
  "$ROOT_DIR/.github/ci-helpers/vendor/script-helpers"
)

if [[ ! -f "$SCRIPT_HELPERS_DIR/helpers.sh" ]]; then
  for alt in "${ALT_HELPERS_DIRS[@]}"; do
    echo "Locating script-helpers..."
    echo "Current SCRIPT_HELPERS_DIR: $SCRIPT_HELPERS_DIR"
    echo "Root Directory: $ROOT_DIR"
    echo "alt: $alt"

    if [[ -f "$alt/helpers.sh" ]]; then
      SCRIPT_HELPERS_DIR="$alt"
      break
    fi
  done
fi

if [[ ! -f "$SCRIPT_HELPERS_DIR/helpers.sh" ]]; then
  echo "script-helpers not found. Using fallback logging." >&2
  print_info() { echo "[info] $*"; }
  print_success() { echo "[ok] $*"; }
else
  # shellcheck disable=SC1091
  source "$SCRIPT_HELPERS_DIR/helpers.sh"
  shlib_import logging os
fi

# source ./scripts/script-helpers/helpers.sh
# shlib_import logging os

print_info "Running tests."
cd "$ROOT_DIR"

# Constants ----------------
# URL of the service
NEWS_API_URL="https://newsapi.org"
NEWS_API_ENDPOINT="/v2/everything"
NEWS_API_KEY_ENV_VAR="NEWS_API_KEY"
NEWS_API_OUTPUT_FILE="$ROOT_DIR/tests/newsapi_test_output.json"

# Initialize results JSON structure
RESULTS_FILE="$ROOT_DIR/tests/results.json"
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
OVERALL_STATUS="PASS"
TEST_RESULTS=()

# Read API key from app config .env if present
APP_ENV="$HOME/.config/VigilantCore/.env"
if [[ -f "$APP_ENV" ]]; then
  # shellcheck disable=SC1090
  source "$APP_ENV"
fi

SEARCH_TEXT=${1:-"top-headlines"}
SEARCH_URL="${NEWS_API_URL}${NEWS_API_ENDPOINT}?q=${SEARCH_TEXT}"

# Helper function to add test result
add_test_result() {
  local name="$1"
  local status="$2"
  local description="$3"
  local details="$4"
  local api_response="${5:-}"
  
  if [[ "$status" == "FAIL" ]]; then
    OVERALL_STATUS="FAIL"
  fi
  
  local result
  local TEST_NAME="$name" 
  local TEST_STATUS="$status" 
  local TEST_DESCRIPTION="$description" 
  local TEST_DETAILS="$details"
  local API_RESPONSE_DATA="$api_response"
  
  # Export values to env
  export TEST_NAME TEST_STATUS TEST_DESCRIPTION TEST_DETAILS API_RESPONSE_DATA

  result=$(python3 - <<'PY'
import json, os
name = os.environ["TEST_NAME"]
status = os.environ["TEST_STATUS"]
description = os.environ["TEST_DESCRIPTION"]
details = os.environ["TEST_DETAILS"]
api_data = os.environ.get("API_RESPONSE_DATA", "")

result = {
    "name": name,
    "status": status,
    "description": description,
    "details": details,
}
if api_data:
    try:
        result["api_response"] = json.loads(api_data)
    except json.JSONDecodeError:
        result["api_response"] = {"raw": api_data}
print(json.dumps(result))
PY
)
  TEST_RESULTS+=("$result")
}

# Test curl availability
if ! command -v curl >/dev/null 2>&1; then
  print_info "curl not found. Skipping NewsAPI test."
  add_test_result "curl_availability" "SKIP" "Check if curl is available" "curl command not found"
  add_test_result "newsapi_test" "SKIP" "Test NewsAPI connectivity" "Skipped due to missing curl"
else
  add_test_result "curl_availability" "PASS" "Check if curl is available" "curl command found"
  
  # Test NewsAPI
  if [[ -n "${NEWS_API_KEY:-}" ]]; then
    RESPONSE_CODE=$(curl -s -o "$NEWS_API_OUTPUT_FILE" -w "%{http_code}" -H "X-Api-Key: ${NEWS_API_KEY}" "$SEARCH_URL")
    API_RESPONSE=$(cat "$NEWS_API_OUTPUT_FILE" 2>/dev/null || echo '{"error": "No response data"}')
    
    if [[ "$RESPONSE_CODE" == "200" ]]; then
      print_success "NewsAPI test passed (200 OK with key)."
      # Extract summary info from API response
      TOTAL_RESULTS=$(echo "$API_RESPONSE" | python3 -c "import json, sys; data=json.load(sys.stdin); print(data.get('totalResults', 0))" 2>/dev/null || echo "0")
      ARTICLES_COUNT=$(echo "$API_RESPONSE" | python3 -c "import json, sys; data=json.load(sys.stdin); print(len(data.get('articles', [])))" 2>/dev/null || echo "0")
      add_test_result "newsapi_with_key" "PASS" "Test NewsAPI with authentication key" "HTTP $RESPONSE_CODE - Found $TOTAL_RESULTS total results, $ARTICLES_COUNT articles returned" "$API_RESPONSE"
    else
      print_info "NewsAPI test failed (expected 200 with key, got $RESPONSE_CODE)."
      add_test_result "newsapi_with_key" "FAIL" "Test NewsAPI with authentication key" "HTTP $RESPONSE_CODE - Expected 200" "$API_RESPONSE"
      OVERALL_STATUS="FAIL"
    fi
  else
    RESPONSE_CODE=$(curl -s -o "$NEWS_API_OUTPUT_FILE" -w "%{http_code}" "$SEARCH_URL")
    API_RESPONSE=$(cat "$NEWS_API_OUTPUT_FILE" 2>/dev/null || echo '{"error": "No response data"}')
    
    if [[ "$RESPONSE_CODE" == "401" ]]; then
      print_success "NewsAPI test passed (401 Unauthorized without key)."
      add_test_result "newsapi_without_key" "PASS" "Test NewsAPI without authentication key" "HTTP $RESPONSE_CODE - Expected unauthorized response" "$API_RESPONSE"
    else
      print_info "NewsAPI test failed (expected 401 without key, got $RESPONSE_CODE)."
      add_test_result "newsapi_without_key" "FAIL" "Test NewsAPI without authentication key" "HTTP $RESPONSE_CODE - Expected 401" "$API_RESPONSE"
      OVERALL_STATUS="FAIL"
    fi
  fi
fi

# Build final JSON structure
TEST_RESULTS_JOINED=$(printf '%s\n' "${TEST_RESULTS[@]}")
RESULTS_JSON=$(TEST_RESULTS="$TEST_RESULTS_JOINED" TIMESTAMP="$TIMESTAMP" OVERALL_STATUS="$OVERALL_STATUS" SEARCH_TEXT="$SEARCH_TEXT" python3 - <<'PY'
import json, os
tests = os.environ["TEST_RESULTS"].splitlines() if os.environ["TEST_RESULTS"] else []
tests_json = [json.loads(item) for item in tests]
payload = {
    "timestamp": os.environ["TIMESTAMP"],
    "overall_status": os.environ["OVERALL_STATUS"],
    "search_text": os.environ["SEARCH_TEXT"],
    "total_tests": len(tests_json),
    "tests": tests_json,
}
print(json.dumps(payload, indent=2))
PY
)

echo "$RESULTS_JSON" > "$RESULTS_FILE"
print_info "Test results saved to: $RESULTS_FILE"

# Display results with jq if available
if command -v jq >/dev/null 2>&1; then
  print_info "Displaying test results:"
  echo
  jq '.' "$RESULTS_FILE"
  echo
  print_info "Summary:"
  jq -r '"Overall Status: " + .overall_status + " | Tests: " + (.total_tests | tostring) + " | Timestamp: " + .timestamp' "$RESULTS_FILE"
else
  print_info "jq not available. Raw JSON output:"
  cat "$RESULTS_FILE"
fi

# Exit with appropriate code
if [[ "$OVERALL_STATUS" == "FAIL" ]]; then
  exit 1
fi
