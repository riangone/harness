#!/bin/bash
# qwen-task.sh — Qwenへのタスク実行ラッパー
# 使い方: ./scripts/qwen-task.sh "タスク内容"

set -e

TASK="$1"
if [ -z "$TASK" ]; then
  echo "Usage: $0 '<task description>'"
  exit 1
fi

echo "=== [Qwen] タスク開始 ==="
echo "タスク: $TASK"
echo ""

qwen "$TASK"

echo ""
echo "=== [Qwen] タスク完了 ==="
echo "次のステップ: Claude による評価を実行してください"
echo "  ./scripts/evaluate.sh '<評価対象の説明>'"
