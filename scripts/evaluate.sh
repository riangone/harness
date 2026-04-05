#!/bin/bash
# evaluate.sh — Claude評価フェーズの呼び出し
# 使い方: ./scripts/evaluate.sh "評価対象の説明"

set -e

TARGET="$1"
if [ -z "$TARGET" ]; then
  echo "Usage: $0 '<evaluation target description>'"
  exit 1
fi

echo "=== [Claude] 評価フェーズ開始 ==="
echo "対象: $TARGET"
echo ""

claude "以下を評価してください（AGENTS.mdの基準に従い、問題があれば具体的な修正箇所を指摘）: $TARGET"

echo ""
echo "=== [Claude] 評価完了 ==="
echo "問題があった場合: AGENTS.md を更新してQwenに再実行を依頼してください"
