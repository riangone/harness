#!/bin/bash
# run.sh — メインハーネス実行スクリプト
# 使い方: ./scripts/run.sh "やりたいこと"

set -e

TASK="$1"
if [ -z "$TASK" ]; then
  echo "Usage: $0 '<high-level task>'"
  exit 1
fi

echo "========================================"
echo "  Multi-AI Harness 実行開始"
echo "========================================"
echo "タスク: $TASK"
echo ""

# Phase 1: Claude で仕様策定・タスク分解
echo "--- Phase 1: [Claude] 仕様策定 ---"
claude "以下のタスクをQwenが実装できる単位に分解し、具体的な指示を出してください（DESIGN.mdの役割分担に従う）: $TASK"

echo ""
echo "--- Phase 2: [Qwen] 実装 ---"
echo "上記の分解結果をQwenに渡してください:"
echo "  ./scripts/qwen-task.sh '<Qwenへの具体的な指示>'"

echo ""
echo "--- Phase 3: [Claude] 評価 ---"
echo "Qwenの実装完了後:"
echo "  ./scripts/evaluate.sh '<評価対象>'"
