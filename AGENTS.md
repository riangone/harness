# AGENTS.md — エージェント向けガイドライン

このファイルはエージェントのミスが発生するたびに更新される。
各行は実際に起きた問題への対策を表す。

---

## 全エージェント共通

- タスクを開始する前に `tasks/` ディレクトリで現在の状態を確認すること
- 実装完了後は必ずテストを実行して動作確認すること
- スタブ・モックで「完了」とせず、実際に動作するコードを実装すること

## Qwen向け

- 生成したコードは必ず構文チェックを行ってから渡すこと
- 大きなファイルを一度に生成せず、スプリント単位で分割すること

## Claude向け

- 評価時は具体的な修正箇所を指摘すること（「良いです」だけはNG）
- ハーネス改善の提案は `DESIGN.md` に反映すること

## 架构决策（2026-04-12 更新）

- harness **不包含** SMTP/IMAP 邮件收发代码，邮件收发由 MailMindHub 独占
- harness 是纯编排内核，通过 HTTP API 提供服务
- harness 提供 HTTP API（FastAPI），不适合 CLI 调用（Pipeline 执行需要几分钟，CLI 会一直等）
- `core/gateway/mail.py` 只做邮件内容解析和响应格式化，不做 SMTP 发送
- MailMindHub 是 harness 的调用者，通过 POST /api/v1/tasks 或 POST /api/v1/tasks/from-email 创建任务
- harness 任务完成后通过 Webhook 回调通知 MailMindHub（而非轮询）

---

*最終更新: 2026-04-12*
