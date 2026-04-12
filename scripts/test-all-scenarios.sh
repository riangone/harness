#!/bin/bash
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# harness 全シナリオ統合テスト（自然言語対応版）
# 使用方法: ./scripts/test-all-scenarios.sh
# 環境変数:
#   HARNESS_API_URL=http://localhost:7500
#   HARNESS_API_TOKEN=（未設定の場合は開発モード）
#   MAILMINDHUB_CALLBACK_URL=http://mailmindhub:8080/api/harness/callback
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

set -euo pipefail

HARNESS_URL="${HARNESS_API_URL:-http://localhost:7500}"
CALLBACK_URL="${MAILMINDHUB_CALLBACK_URL:-http://mailmindhub:8080/api/harness/callback}"
API_TOKEN="${HARNESS_API_TOKEN:-}"
HARNESS_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

PASS=0
FAIL=0
TASK_IDS=()

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_section() { echo -e "\n${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"; echo -e "${BLUE}$1${NC}"; echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"; }
log_pass()    { echo -e "  ${GREEN}✅ $1${NC}"; PASS=$((PASS+1)); }
log_fail()    { echo -e "  ${RED}❌ $1${NC}"; FAIL=$((FAIL+1)); }
log_info()    { echo -e "  ${YELLOW}ℹ  $1${NC}"; }

# ────────────────────────────────────────────────────────────
# Section 1: ルーティングルール単体テスト（API不要）
# ────────────────────────────────────────────────────────────
log_section "Section 1: ルーティングルール単体テスト"

check_route() {
    local subject="$1"
    local body="$2"
    local expected="$3"
    local label="${4:-$subject}"

    actual=$(cd "$HARNESS_ROOT" && python3 -c "
import sys; sys.path.insert(0, '.')
from core.gateway.mail import MailGateway
gw = MailGateway()
rule = gw.match_routing_rule('$subject', '$body')
print(rule.task_type if rule else 'no_match')
" 2>/dev/null || echo "error")

    if [ "$actual" = "$expected" ]; then
        log_pass "[$expected] $label"
    else
        log_fail "Expected=$expected Actual=$actual | $label"
    fi
}

echo ""
echo "  --- コード開発 ---"
check_route "/generate ソート関数" "" "code_generation" "明示コマンド /generate"
check_route "/review セキュリティ" "" "code_review"    "明示コマンド /review"
check_route "/fix NullPointerException" "" "bug_fix"   "明示コマンド /fix"
check_route "Pythonで二分探索を実装して" "" "code_generation" "自然語: 実装して"
check_route "バグを直してほしい" "エラーが発生" "code_generation" "自然語: バグを直して"
check_route "コードのレビューをお願い" "" "code_generation" "自然語: コード"

echo ""
echo "  --- 調査・リサーチ ---"
check_route "AIトレンドを調査してください" "" "research" "自然語: 調査して"
check_route "競合のレポートをまとめて" "" "research"   "自然語: レポート/まとめて"
check_route "最新ニュースを教えて" "" "research"        "自然語: ニュース"
check_route "市場調査をお願いします" "" "research"     "自然語: 調査"
check_route "株価のトレンドを調べて" "" "research"     "自然語: トレンド/調べて"

echo ""
echo "  --- 文章・執筆 ---"
check_route "ブログ記事を書いてください" "" "writing" "自然語: ブログ記事"
check_route "メール文を作って" "" "writing"            "自然語: メール文"
check_route "SNSの投稿文を作成して" "" "writing"      "自然語: SNS"
check_route "小説の冒頭を書いて" "" "writing"         "自然語: 小説"
check_route "手紙を書いてください" "" "writing"        "自然語: 手紙"
check_route "キャッチコピーを作って" "" "writing"      "自然語: キャッチコピー"

echo ""
echo "  --- ドキュメント・資料 ---"
check_route "PPTスライドを作って" "" "document"       "自然語: PPT/スライド"
check_route "プレゼン資料を作成して" "" "document"    "自然語: プレゼン"
check_route "仕様書を書いてほしい" "" "document"      "自然語: 仕様書"
check_route "議事録を作成して" "" "document"          "自然語: 議事録"
check_route "マニュアルを作って" "" "document"        "自然語: マニュアル"

echo ""
echo "  --- ファイル操作 ---"
check_route "フォルダを整理してほしい" "" "file_ops"  "自然語: フォルダを整理"
check_route "ファイルを一括リネームして" "" "file_ops" "自然語: 一括リネーム"

echo ""
echo "  --- 汎用フォールバック ---"
check_route "翻訳してください" "英文を日本語に" "general" "汎用: 翻訳"
check_route "教えてください" "円周率は" "general"     "汎用: 教えて"
check_route "困っています" "" "general"               "汎用: 不明確な指示"
check_route "今日の天気は" "" "general"               "汎用: 天気（無関係）"

# ────────────────────────────────────────────────────────────
# Section 2: API ヘルスチェック
# ────────────────────────────────────────────────────────────
log_section "Section 2: API ヘルスチェック"

HEALTH=$(curl -sf "$HARNESS_URL/api/v1/health" 2>/dev/null || echo '{"status":"error"}')
STATUS=$(echo "$HEALTH" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','error'))" 2>/dev/null || echo "error")

if [ "$STATUS" = "ok" ]; then
    log_pass "harness API 起動中: $HARNESS_URL"
else
    log_fail "harness API 未起動 ($HARNESS_URL)"
    echo ""
    echo "  → 起動コマンド: uvicorn harness_api:app --host 0.0.0.0 --port 7500 --reload"
    echo "  ※ API不要のテスト（Section 1）のみ有効です"
    echo ""
    echo -e "${YELLOW}ルーティング結果: ✅ $PASS件PASS / ❌ $FAIL件FAIL${NC}"
    exit 0
fi

# エージェント確認
AGENTS=$(curl -sf "$HARNESS_URL/api/v1/agents" 2>/dev/null || echo '{"agents":[]}')
AGENT_COUNT=$(echo "$AGENTS" | python3 -c "import sys,json; print(len(json.load(sys.stdin).get('agents',[])))" 2>/dev/null || echo "0")
log_info "利用可能エージェント: ${AGENT_COUNT}件"

# ────────────────────────────────────────────────────────────
# Section 3: タスク投入テスト（各タイプ代表1件）
# ────────────────────────────────────────────────────────────
log_section "Section 3: タスク投入テスト（各タイプ代表1件）"

submit_email_task() {
    local tag="$1"
    local subject="$2"
    local body="$3"
    local expected_type="$4"

    RESULT=$(curl -sf -X POST "$HARNESS_URL/api/v1/tasks/from-email" \
        -H "Content-Type: application/json" \
        ${API_TOKEN:+-H "X-API-Key: $API_TOKEN"} \
        -d "{
            \"subject\": \"$subject\",
            \"body\": \"$body\",
            \"from_addr\": \"test@example.com\",
            \"callback_url\": \"$CALLBACK_URL\"
        }" 2>/dev/null || echo '{"status":"error"}')

    TASK_ID=$(echo "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('task_id','N/A'))" 2>/dev/null || echo "N/A")
    STATUS=$(echo "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])" 2>/dev/null || echo "error")

    if [ "$STATUS" = "pending" ]; then
        log_pass "[$tag] task_id=$TASK_ID status=$STATUS (期待タイプ: $expected_type)"
        if [ "$TASK_ID" != "N/A" ]; then
            TASK_IDS+=("$TASK_ID:$tag")
        fi
    else
        log_fail "[$tag] status=$STATUS (期待: pending) subject='$subject'"
    fi
}

submit_email_task "CODE"     "Pythonで二分探索を実装してください" "型ヒント付き、単体テスト含む" "code_generation"
submit_email_task "RESEARCH" "2026年のAIトレンドを調査してレポートを作成してください" "主要モデルの動向とビジネス影響をまとめてください" "research"
submit_email_task "WRITING"  "Docker入門のブログ記事を書いてください" "初心者向け、約1000文字、親しみやすいトーン" "writing"
submit_email_task "DOCUMENT" "新サービス紹介PPTスライドを作ってください" "SaaS製品の提案スライド5枚構成で" "document"
submit_email_task "GENERAL"  "以下を翻訳してください" "Hello, World! を自然な日本語に翻訳してください" "general"

# ────────────────────────────────────────────────────────────
# Section 4: ヘルプコマンドのレスポンス確認
# ────────────────────────────────────────────────────────────
log_section "Section 4: ヘルプコマンド確認"

HELP_RESULT=$(curl -sf -X POST "$HARNESS_URL/api/v1/tasks/from-email" \
    -H "Content-Type: application/json" \
    -d '{"subject":"/help","body":"","from_addr":"test@example.com"}' 2>/dev/null || echo '{}')

HELP_STATUS=$(echo "$HELP_RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status',''))" 2>/dev/null || echo "")
HELP_SENT=$(echo "$HELP_RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('help_sent',False))" 2>/dev/null || echo "False")

if [ "$HELP_SENT" = "True" ]; then
    log_pass "/help → help_sent=True (status=$HELP_STATUS)"
else
    log_fail "/help → help_sent=$HELP_SENT (expected True)"
fi

# ────────────────────────────────────────────────────────────
# Section 5: 投入済みタスクの状態確認（非同期待機）
# ────────────────────────────────────────────────────────────
if [ ${#TASK_IDS[@]} -gt 0 ]; then
    log_section "Section 5: タスク実行状態確認（30秒後）"
    log_info "30秒後にタスク状態を確認します..."
    sleep 30

    for entry in "${TASK_IDS[@]}"; do
        IFS=':' read -r tid tag <<< "$entry"
        TASK_DETAIL=$(curl -sf "$HARNESS_URL/api/v1/tasks/$tid" 2>/dev/null || echo '{"status":"error"}')
        TASK_STATUS=$(echo "$TASK_DETAIL" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','error'))" 2>/dev/null)
        HAS_RESULT=$(echo "$TASK_DETAIL" | python3 -c "import sys,json; d=json.load(sys.stdin); print('yes' if d.get('result') else 'no')" 2>/dev/null)
        RUN_COUNT=$(echo "$TASK_DETAIL" | python3 -c "import sys,json; print(len(json.load(sys.stdin).get('runs',[])))" 2>/dev/null)

        log_info "[$tag] task=$tid status=$TASK_STATUS runs=$RUN_COUNT result=$HAS_RESULT"
    done
fi

# ────────────────────────────────────────────────────────────
# 最終サマリー
# ────────────────────────────────────────────────────────────
log_section "テスト結果サマリー"

TOTAL=$((PASS+FAIL))
if [ $FAIL -eq 0 ]; then
    echo -e "${GREEN}  ✅ 全 $TOTAL 件PASS${NC}"
else
    echo -e "${YELLOW}  結果: ✅ $PASS件PASS / ❌ $FAIL件FAIL / 合計 $TOTAL 件${NC}"
fi

echo ""
echo "  詳細確認:"
echo "  curl $HARNESS_URL/api/v1/tasks?limit=10 | python3 -m json.tool"
echo ""
