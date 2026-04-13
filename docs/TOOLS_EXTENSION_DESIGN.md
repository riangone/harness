# Harness ツール拡張設計書

**バージョン**: 1.0  
**対象**: harness v2.0 への段階的ツール統合  
**実装対象 AI**: 本文書を読んだ AI が実装可能なレベルの詳細度で記述する

---

## 概要

本設計書は harness に以下の能力を追加するための 3 フェーズ実装計画を定義する。

- **PDF 生成**（Markdown/HTML → PDF レンダリング）
- **PowerPoint 生成**（python-pptx による .pptx 出力）
- **Excel 生成**（openpyxl による .xlsx 出力）
- **Word 生成**（python-docx による .docx 出力）
- **Marp スライド生成**（Marp CLI による Markdown → PDF/HTML スライド）
- **ブラウザ操作**（Playwright による UI 自動操作・スクリーンショット）
- **HermesAgent パターン**（Tool-use / ReAct / 構造化出力 / 並列ツール呼び出し）

---

## フェーズ定義

| フェーズ | 名称 | 依存関係 | 難易度 |
|---------|------|---------|--------|
| P1 | ツールスクリプト + テンプレート追加 | なし | 低 |
| P2 | core/tools/ レイヤー + Pipeline `tool_call` ステップ | P1 | 中 |
| P3 | MCP サーバー + HermesAgent パターン | P2 | 高 |

---

## P1: ツールスクリプト + Pipeline テンプレート

### P1-1: ディレクトリ構成

```
harness/
  scripts/
    tools/
      __init__.py
      render_pdf.py          ← Markdown/HTML → PDF
      render_pptx.py         ← JSON/Markdown → PowerPoint
      render_excel.py        ← JSON/CSV → Excel
      render_docx.py         ← Markdown → Word
      render_marp.py         ← Markdown → Marp スライド (PDF/HTML)
      browser_action.py      ← Playwright スクリーンショット・操作
      http_call.py           ← 外部 REST API 呼び出し
      tool_runner.py         ← 統合エントリーポイント（CLI から呼び出し可能）
```

### P1-2: 各スクリプトの仕様

#### render_pdf.py

```python
"""
使用法:
  python render_pdf.py --input content.md --output report.pdf
  python render_pdf.py --input content.html --output report.pdf --engine weasyprint

依存パッケージ:
  pip install weasyprint markdown2
"""

import argparse, sys
from pathlib import Path

ENGINES = ["weasyprint", "pdfkit"]

def render_md_to_pdf(input_path: str, output_path: str, engine: str = "weasyprint") -> dict:
    """
    Markdown または HTML を PDF に変換する。
    
    戻り値:
        {"success": bool, "output_path": str, "error": str|None, "size_bytes": int}
    """
    # 実装詳細:
    # 1. input_path の拡張子を確認（.md なら markdown2 で HTML に変換）
    # 2. engine == "weasyprint" なら weasyprint.HTML(string=html_str).write_pdf(output_path)
    # 3. ファイルサイズを返す
    ...

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--engine", default="weasyprint", choices=ENGINES)
    args = parser.parse_args()
    result = render_md_to_pdf(args.input, args.output, args.engine)
    import json; print(json.dumps(result))
    sys.exit(0 if result["success"] else 1)
```

#### render_pptx.py

```python
"""
使用法:
  python render_pptx.py --input slides.json --output presentation.pptx
  python render_pptx.py --input slides.md  --output presentation.pptx

入力 JSON フォーマット（slides.json）:
{
  "title": "プレゼンテーションタイトル",
  "theme": "default",   // default / dark / minimal
  "slides": [
    {
      "layout": "title",     // title / content / two_column / image / blank
      "title": "スライドタイトル",
      "content": ["箇条書き1", "箇条書き2"],
      "notes": "発表者ノート（省略可）",
      "image_path": "path/to/image.png"  // layout=image の場合
    },
    ...
  ]
}

入力 Markdown フォーマット（スライドは --- で区切る）:
# スライドタイトル
## サブタイトル
- 箇条書き1
- 箇条書き2

---

# 次のスライド

依存パッケージ:
  pip install python-pptx
"""

def parse_markdown_to_slides(md_content: str) -> dict:
    """Markdown をスライド JSON 構造に変換"""
    # --- で分割、各セクションを解析して title/content を抽出
    ...

def render_slides_to_pptx(slides_data: dict, output_path: str) -> dict:
    """
    スライドデータを .pptx ファイルに変換。
    
    python-pptx を使用。テーマごとに Presentation オブジェクトを設定。
    layout 別にスライドマスタを選択して追加。
    """
    ...
```

#### render_excel.py

```python
"""
使用法:
  python render_excel.py --input data.json --output report.xlsx
  python render_excel.py --input data.csv  --output report.xlsx --title "月次レポート"

入力 JSON フォーマット（data.json）:
{
  "title": "レポートタイトル",
  "sheets": [
    {
      "name": "シート名",
      "headers": ["列A", "列B", "列C"],
      "rows": [
        ["値1", "値2", "値3"],
        ...
      ],
      "charts": [                  // 省略可
        {
          "type": "bar",           // bar / line / pie
          "title": "グラフタイトル",
          "data_range": "A1:C10",
          "position": "E1"
        }
      ],
      "styles": {
        "header_color": "4472C4",  // ヘッダー背景色（省略可）
        "freeze_header": true
      }
    }
  ]
}

依存パッケージ:
  pip install openpyxl
"""

def render_json_to_excel(input_path: str, output_path: str, title: str = "") -> dict:
    """JSON または CSV データを Excel に変換"""
    ...
```

#### render_marp.py

```python
"""
Marp CLI を使ったスライド生成

使用法:
  python render_marp.py --input slides.md --output slides.pdf
  python render_marp.py --input slides.md --output slides.html --format html
  python render_marp.py --input slides.md --output slides.pptx --format pptx

Marp Markdown フォーマット（slides.md）:
  ---
  marp: true
  theme: default        # default / gaia / uncover
  paginate: true
  backgroundColor: #fff
  ---

  # タイトルスライド
  ## サブタイトル

  ---

  # コンテンツスライド

  - 箇条書き1
  - 箇条書き2

  ---

  <!-- _class: lead -->
  # まとめ

依存ツール:
  npm install -g @marp-team/marp-cli
  （Node.js 18+ 必須）

依存パッケージ（Python 側）:
  subprocess のみ（標準ライブラリ）
"""

import subprocess, shutil, sys, json
from pathlib import Path

SUPPORTED_FORMATS = ["pdf", "html", "pptx"]

def check_marp_available() -> bool:
    """marp コマンドが PATH に存在するか確認"""
    return shutil.which("marp") is not None

def render_marp_slides(
    input_path: str,
    output_path: str,
    output_format: str = "pdf",
    theme: str = None,
    allow_local_files: bool = True
) -> dict:
    """
    Marp CLI で Markdown スライドをレンダリング。
    
    処理フロー:
    1. marp コマンド存在確認
    2. コマンドリスト構築:
       ["marp", input_path, "-o", output_path,
        "--allow-local-files" (if allow_local_files),
        "--theme", theme (if theme),
        "--pdf" / "--html" / "--pptx" (format 選択)]
    3. subprocess.run() で実行
    4. 成功/失敗・ファイルサイズを返す
    
    戻り値:
        {"success": bool, "output_path": str, "format": str,
         "size_bytes": int, "error": str|None, "marp_version": str}
    """
    if not check_marp_available():
        return {
            "success": False,
            "error": "marp command not found. Run: npm install -g @marp-team/marp-cli",
            "output_path": output_path
        }
    
    cmd = ["marp", input_path, "-o", output_path]
    if allow_local_files:
        cmd.append("--allow-local-files")
    if theme:
        cmd.extend(["--theme", theme])
    # format フラグ: --pdf, --html, --pptx
    if output_format == "pdf":
        cmd.append("--pdf")
    elif output_format == "html":
        cmd.append("--html")
    elif output_format == "pptx":
        cmd.append("--pptx")
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        success = result.returncode == 0
        size = Path(output_path).stat().st_size if success and Path(output_path).exists() else 0
        return {
            "success": success,
            "output_path": output_path,
            "format": output_format,
            "size_bytes": size,
            "error": result.stderr if not success else None
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Marp rendering timed out (120s)", "output_path": output_path}
    except Exception as e:
        return {"success": False, "error": str(e), "output_path": output_path}

def inject_marp_frontmatter(md_content: str, theme: str = "default", paginate: bool = True) -> str:
    """
    既存の Markdown に Marp フロントマターを注入する。
    すでに marp: true が含まれる場合はスキップ。
    """
    if "marp: true" in md_content:
        return md_content
    frontmatter = f"---\nmarp: true\ntheme: {theme}\npaginate: {str(paginate).lower()}\n---\n\n"
    return frontmatter + md_content
```

#### tool_runner.py（統合 CLI）

```python
"""
統合ツールランナー。エージェントから呼び出す単一エントリーポイント。

使用法:
  python tool_runner.py --tool pdf --input content.md --output report.pdf
  python tool_runner.py --tool pptx --input slides.json --output deck.pptx
  python tool_runner.py --tool excel --input data.json --output sheet.xlsx
  python tool_runner.py --tool marp --input slides.md --output slides.pdf --format pdf
  python tool_runner.py --tool marp --input slides.md --output slides.html --format html
  python tool_runner.py --tool docx --input doc.md --output doc.docx
  python tool_runner.py --tool browser --action screenshot --url https://example.com --output screen.png
  python tool_runner.py --tool http --method POST --url http://api.example.com/v1/data --body '{"key":"val"}'

全ツールの戻り値（標準出力に JSON）:
  {"success": bool, "output_path": str|null, "error": str|null, "metadata": dict}
"""
```

### P1-3: Pipeline テンプレート追加

#### templates/pdf_report.yaml

```yaml
name: pdf_report_pipeline
version: 1
description: Markdown/HTML を PDF レポートとして出力するパイプライン

trigger:
  task_type: pdf_report
  auto_apply: true

steps:
  - id: planning
    agent:
      role: planner
      model_selector:
        strategy: quality
    action: plan
    output_file: plan.md
    prompt_hint: |
      PDF レポート作成の計画を plan.md に出力してください：
      1. レポートの目的・構成・セクション一覧
      2. 含めるべきデータ・図表の種類
      3. スタイル指針（フォーマル/カジュアル/技術文書）
      4. 出力ファイル名（report.md → report.pdf）

  - id: generating
    agent:
      role: generator
      model_selector:
        strategy: balanced
    action: generate
    output_file: report.md
    prompt_hint: |
      計画に従い、PDF レンダリング用の Markdown を report.md に出力してください。
      - 標準 Markdown フォーマットを使用（見出し/表/コードブロック対応）
      - 画像参照は相対パスで記述
      - report.md 生成後、以下を実行して PDF に変換してください:
        python /home/ubuntu/ws/harness/scripts/tools/render_pdf.py \
          --input report.md --output report.pdf
      - 変換成功を確認し、report.pdf のファイルサイズを出力すること

  - id: evaluating
    agent:
      role: evaluator
      model_selector:
        strategy: quality
    action: evaluate
    output_file: eval-report.md
    verdict_required: true
    prompt_hint: |
      report.md の内容と report.pdf の存在を確認してください。
      評価基準:
      - [ ] report.pdf が存在し、0 バイト以上
      - [ ] 要求された全セクションが含まれている
      - [ ] Markdown 文法エラーがない
      - [ ] 表・見出し・コードブロックが適切に使われている

on_success:
  - action: collect_file
    file: report.pdf
  - action: collect_file
    file: report.md
```

#### templates/marp_slides.yaml

```yaml
name: marp_slides_pipeline
version: 1
description: Marp Markdown からスライド (PDF/HTML/PPTX) を生成するパイプライン

trigger:
  task_type: marp_slides
  auto_apply: true

metadata:
  output_formats: [pdf, html, pptx]
  requires_tool: marp

steps:
  - id: planning
    agent:
      role: planner
      model_selector:
        strategy: quality
    action: plan
    output_file: plan.md
    prompt_hint: |
      スライド作成計画を plan.md に出力してください：
      1. 発表の目的・対象聴衆
      2. スライド枚数（目安）とページ構成
      3. 各スライドのタイトルと主要メッセージ（1行）
      4. 使用テーマ（default / gaia / uncover）
      5. 出力フォーマット（pdf / html / pptx）- task_meta の output_format を参照

  - id: generating
    agent:
      role: generator
      model_selector:
        strategy: balanced
    action: generate
    output_file: slides.md
    prompt_hint: |
      計画に従い、Marp Markdown 形式でスライドを slides.md に出力してください。

      必須フォーマット:
      ```markdown
      ---
      marp: true
      theme: default
      paginate: true
      ---

      # タイトル
      ## サブタイトル

      ---

      # スライド2
      - ポイント1
      - ポイント2

      ---
      ```

      slides.md 生成後、以下を実行してレンダリングしてください:
      ```bash
      python /home/ubuntu/ws/harness/scripts/tools/render_marp.py \
        --input slides.md --output slides.pdf --format pdf
      ```
      ※ HTML 版も必要な場合は --format html で slides.html も生成すること

  - id: evaluating
    agent:
      role: evaluator
      model_selector:
        strategy: quality
    action: evaluate
    output_file: eval-report.md
    verdict_required: true
    prompt_hint: |
      slides.md の内容と slides.pdf（または slides.html）の存在を確認。
      評価基準:
      - [ ] marp: true フロントマターが含まれている
      - [ ] スライドが --- で正しく区切られている
      - [ ] 出力ファイル（.pdf/.html/.pptx）が存在し 0 バイト以上
      - [ ] 計画で指定されたスライド枚数と一致する（±2枚以内）
      - [ ] タイトルスライドが先頭に存在する

on_success:
  - action: collect_file
    file: slides.pdf
  - action: collect_file
    file: slides.html
  - action: collect_file
    file: slides.md
```

#### templates/pptx_deck.yaml

```yaml
name: pptx_deck_pipeline
version: 1
description: python-pptx で PowerPoint ファイルを生成するパイプライン

trigger:
  task_type: pptx_deck
  auto_apply: true

steps:
  - id: planning
    agent:
      role: planner
      model_selector:
        strategy: quality
    action: plan
    output_file: plan.md

  - id: generating
    agent:
      role: generator
      model_selector:
        strategy: balanced
    action: generate
    output_file: slides.json
    prompt_hint: |
      計画に従い、スライドデータを slides.json に出力してください。

      必須フォーマット:
      {
        "title": "プレゼン全体タイトル",
        "theme": "default",
        "slides": [
          {
            "layout": "title",
            "title": "タイトルスライド",
            "content": ["サブタイトル"],
            "notes": "発表者ノート（省略可）"
          },
          {
            "layout": "content",
            "title": "コンテンツスライド",
            "content": ["箇条書き1", "箇条書き2", "箇条書き3"]
          },
          {
            "layout": "two_column",
            "title": "2カラムスライド",
            "left": ["左カラム内容"],
            "right": ["右カラム内容"]
          }
        ]
      }

      slides.json 出力後、以下を実行:
      python /home/ubuntu/ws/harness/scripts/tools/render_pptx.py \
        --input slides.json --output presentation.pptx

  - id: evaluating
    agent:
      role: evaluator
      model_selector:
        strategy: quality
    action: evaluate
    output_file: eval-report.md
    verdict_required: true

on_success:
  - action: collect_file
    file: presentation.pptx
```

#### templates/excel_report.yaml

```yaml
name: excel_report_pipeline
version: 1
description: openpyxl で Excel ファイルを生成するパイプライン

trigger:
  task_type: excel_report
  auto_apply: true

steps:
  - id: planning
    agent:
      role: planner
      model_selector:
        strategy: quality
    action: plan
    output_file: plan.md

  - id: generating
    agent:
      role: generator
      model_selector:
        strategy: balanced
    action: generate
    output_file: data.json
    prompt_hint: |
      計画に従い、Excel データを data.json に出力してください。

      必須フォーマット:
      {
        "title": "レポートタイトル",
        "sheets": [
          {
            "name": "月次データ",
            "headers": ["月", "売上", "費用", "利益"],
            "rows": [
              ["2026-01", 1000000, 600000, 400000],
              ["2026-02", 1200000, 650000, 550000]
            ],
            "styles": {
              "header_color": "4472C4",
              "freeze_header": true,
              "auto_filter": true
            },
            "charts": [
              {
                "type": "bar",
                "title": "月次売上推移",
                "data_range": "A1:D3",
                "position": "F1"
              }
            ]
          }
        ]
      }

      data.json 出力後、以下を実行:
      python /home/ubuntu/ws/harness/scripts/tools/render_excel.py \
        --input data.json --output report.xlsx

  - id: evaluating
    agent:
      role: evaluator
    action: evaluate
    output_file: eval-report.md
    verdict_required: true

on_success:
  - action: collect_file
    file: report.xlsx
```

### P1-4: executor.py / database.py への変更

#### `_collect_result()` に新タスクタイプを追加

`webui/app/services/executor.py` の `output_files` 辞書に追記：

```python
output_files = {
    # 既存エントリ ...
    'pdf_report':   ['report.pdf', 'report.md'],
    'marp_slides':  ['slides.pdf', 'slides.html', 'slides.md'],
    'pptx_deck':    ['presentation.pptx', 'slides.json'],
    'excel_report': ['report.xlsx', 'data.json'],
    'browser_ops':  ['screenshot.png', 'output.json'],
}
```

#### `database.py` seed_agents() に追加

```python
Agent(
    name='Tool Renderer',
    cli_command='python',  # python scripts/tools/tool_runner.py として呼び出す
    role=AgentRole.generator,
    priority=5,
    system_prompt='ドキュメント・スライド・表計算ツールのレンダリングを担当します。',
    is_active=True
),
```

### P1-5: 依存パッケージのインストール

```bash
# PDF 生成
pip install weasyprint markdown2

# PowerPoint 生成
pip install python-pptx

# Excel 生成
pip install openpyxl

# Word 生成
pip install python-docx

# ブラウザ操作
pip install playwright
python -m playwright install chromium

# Marp CLI (Node.js 18+ 必要)
npm install -g @marp-team/marp-cli
```

---

## P2: core/tools/ レイヤー + `tool_call` ステップ型

### P2-1: ディレクトリ構成

```
core/
  tools/
    __init__.py
    base.py              ← BaseTool 抽象クラス + ToolResult
    registry.py          ← ToolRegistry（名前解決・スキーマ管理）
    sandbox.py           ← ToolSandbox（承認フロー・コスト上限）
    renderers/
      __init__.py
      pdf.py             ← PDFRenderer(BaseTool)
      pptx.py            ← PPTXRenderer(BaseTool)
      excel.py           ← ExcelRenderer(BaseTool)
      docx.py            ← DocxRenderer(BaseTool)
      marp.py            ← MarpRenderer(BaseTool)
    operators/
      __init__.py
      browser.py         ← BrowserOperator(BaseTool)
      http.py            ← HttpCaller(BaseTool)
      shell.py           ← ShellExecutor(BaseTool)  # 承認必須
      file.py            ← FileOperator(BaseTool)
```

### P2-2: base.py 詳細仕様

```python
"""core/tools/base.py"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from abc import ABC, abstractmethod
from enum import Enum


class ToolCategory(str, Enum):
    RENDERER = "renderer"      # ファイル生成系
    OPERATOR = "operator"      # 外部システム操作系
    ANALYZER = "analyzer"      # データ解析系（将来）
    RETRIEVER = "retriever"    # 情報取得系（将来）


@dataclass
class ToolParam:
    """ツールパラメータ定義（JSON Schema 準拠）"""
    name: str
    type: str              # string / integer / number / boolean / array / object
    description: str
    required: bool = True
    default: Any = None
    enum: List[Any] = field(default_factory=list)


@dataclass
class ToolResult:
    """ツール実行結果"""
    success: bool
    output: Any = None              # ファイルパス、JSON、テキスト等
    error: Optional[str] = None
    duration_ms: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    artifacts: List[str] = field(default_factory=list)  # 生成されたファイルパスのリスト


class BaseTool(ABC):
    """
    全ツールの基底クラス。
    
    実装クラスは以下を定義すること:
    - name: ツール名（英小文字 + アンダースコア）
    - description: ツールの説明（LLM に提示する）
    - category: ToolCategory
    - params: List[ToolParam]
    - run(): 実際の処理
    """
    
    name: str = ""
    description: str = ""
    category: ToolCategory = ToolCategory.RENDERER
    params: List[ToolParam] = []
    requires_approval: bool = False  # True なら sandbox で承認確認
    
    def get_schema(self) -> Dict:
        """
        JSON Schema 形式でツール仕様を返す。
        MCP サーバー・LLM の tool_use 両方で使用。
        """
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": {
                    p.name: {
                        "type": p.type,
                        "description": p.description,
                        **({"enum": p.enum} if p.enum else {}),
                        **({"default": p.default} if p.default is not None else {}),
                    }
                    for p in self.params
                },
                "required": [p.name for p in self.params if p.required]
            }
        }
    
    @abstractmethod
    async def run(self, params: Dict[str, Any], work_dir: str = ".") -> ToolResult:
        """
        ツールを実行する。
        
        Args:
            params: get_schema() で定義したパラメータ
            work_dir: 作業ディレクトリ（相対パスの基点）
        
        Returns:
            ToolResult
        """
        raise NotImplementedError
    
    def validate_params(self, params: Dict) -> Optional[str]:
        """
        パラメータをバリデーションする。
        エラーがあれば文字列で返す。なければ None。
        """
        for p in self.params:
            if p.required and p.name not in params:
                return f"必須パラメータ '{p.name}' が不足しています"
            if p.enum and params.get(p.name) not in p.enum:
                return f"'{p.name}' は {p.enum} のいずれかである必要があります"
        return None
```

### P2-3: registry.py 詳細仕様

```python
"""core/tools/registry.py"""
from typing import Dict, List, Optional, Type
from .base import BaseTool, ToolCategory


class ToolRegistry:
    """
    ツールレジストリ。
    
    ツールを名前で登録・解決し、LLM に渡すスキーマリストを提供する。
    シングルトンパターンで使用する。
    """
    
    _instance: Optional["ToolRegistry"] = None
    
    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}
    
    @classmethod
    def get_instance(cls) -> "ToolRegistry":
        if cls._instance is None:
            cls._instance = cls()
            cls._instance._register_defaults()
        return cls._instance
    
    def _register_defaults(self):
        """デフォルトツールを全て登録する"""
        from .renderers.pdf import PDFRenderer
        from .renderers.pptx import PPTXRenderer
        from .renderers.excel import ExcelRenderer
        from .renderers.docx import DocxRenderer
        from .renderers.marp import MarpRenderer
        from .operators.browser import BrowserOperator
        from .operators.http import HttpCaller
        from .operators.file import FileOperator
        
        defaults = [
            PDFRenderer(), PPTXRenderer(), ExcelRenderer(),
            DocxRenderer(), MarpRenderer(), BrowserOperator(),
            HttpCaller(), FileOperator(),
        ]
        for tool in defaults:
            self.register(tool)
    
    def register(self, tool: BaseTool):
        """ツールを登録する"""
        self._tools[tool.name] = tool
    
    def get(self, name: str) -> Optional[BaseTool]:
        """名前でツールを取得する"""
        return self._tools.get(name)
    
    def list_all(self) -> List[BaseTool]:
        return list(self._tools.values())
    
    def list_by_category(self, category: ToolCategory) -> List[BaseTool]:
        return [t for t in self._tools.values() if t.category == category]
    
    def get_schemas_for_llm(self, names: List[str] = None) -> List[Dict]:
        """
        LLM の tool_use 用スキーマリストを返す。
        names が指定された場合はそのツールのみ返す。
        """
        tools = self.list_all() if names is None else [
            self._tools[n] for n in names if n in self._tools
        ]
        return [t.get_schema() for t in tools]
```

### P2-4: MarpRenderer の詳細実装仕様

```python
"""core/tools/renderers/marp.py"""
from ..base import BaseTool, ToolCategory, ToolParam, ToolResult
import subprocess, shutil, time
from pathlib import Path
from typing import Dict, Any


class MarpRenderer(BaseTool):
    """
    Marp CLI を使ってスライドをレンダリングする。
    
    Marp Markdown → PDF / HTML / PPTX 変換。
    入力が通常 Markdown の場合は自動的に Marp フロントマターを注入する。
    """
    
    name = "marp_renderer"
    description = (
        "Marp Markdown 形式のスライドをレンダリングします。"
        "PDF・HTML・PowerPoint 形式での出力に対応。"
        "入力ファイルに marp: true フロントマターがない場合は自動注入します。"
    )
    category = ToolCategory.RENDERER
    requires_approval = False
    
    params = [
        ToolParam("input_file", "string", "入力 Markdown ファイルパス (.md)", required=True),
        ToolParam("output_file", "string", "出力ファイルパス (.pdf/.html/.pptx)", required=True),
        ToolParam("format", "string", "出力フォーマット", required=False, default="pdf",
                  enum=["pdf", "html", "pptx"]),
        ToolParam("theme", "string", "Marp テーマ", required=False, default="default",
                  enum=["default", "gaia", "uncover"]),
        ToolParam("auto_inject_frontmatter", "boolean",
                  "フロントマターが存在しない場合に自動注入するか", required=False, default=True),
        ToolParam("allow_local_files", "boolean",
                  "ローカルファイル（画像等）の参照を許可するか", required=False, default=True),
    ]
    
    async def run(self, params: Dict[str, Any], work_dir: str = ".") -> ToolResult:
        """
        処理フロー:
        1. marp コマンド存在確認
        2. 入力ファイル読み込み
        3. auto_inject_frontmatter が True かつフロントマターなしなら注入して一時ファイル保存
        4. marp コマンド実行
        5. 出力ファイル確認・ToolResult 返却
        
        エラーケース:
        - marp not found → error に npm インストール手順を含める
        - タイムアウト（120秒）→ error メッセージ
        - 出力ファイル未生成 → stderr を error に含める
        """
        start = time.time()
        
        # 1. marp 存在確認
        if not shutil.which("marp"):
            return ToolResult(
                success=False,
                error=(
                    "marp コマンドが見つかりません。\n"
                    "インストール: npm install -g @marp-team/marp-cli\n"
                    "（Node.js 18+ が必要）"
                ),
                duration_ms=int((time.time() - start) * 1000)
            )
        
        input_path = Path(work_dir) / params["input_file"]
        output_path = Path(work_dir) / params["output_file"]
        fmt = params.get("format", "pdf")
        theme = params.get("theme", "default")
        
        # 2. 入力ファイル確認
        if not input_path.exists():
            return ToolResult(
                success=False,
                error=f"入力ファイルが見つかりません: {input_path}",
                duration_ms=int((time.time() - start) * 1000)
            )
        
        # 3. フロントマター注入
        actual_input = input_path
        if params.get("auto_inject_frontmatter", True):
            content = input_path.read_text(encoding="utf-8")
            if "marp: true" not in content:
                injected = (
                    f"---\nmarp: true\ntheme: {theme}\npaginate: true\n---\n\n"
                    + content
                )
                tmp_path = input_path.with_suffix(".marp_tmp.md")
                tmp_path.write_text(injected, encoding="utf-8")
                actual_input = tmp_path
        
        # 4. コマンド構築・実行
        cmd = ["marp", str(actual_input), "-o", str(output_path)]
        if params.get("allow_local_files", True):
            cmd.append("--allow-local-files")
        cmd.append(f"--{fmt}")
        
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                cwd=work_dir, timeout=120
            )
            
            # 一時ファイルの削除
            if actual_input != input_path and actual_input.exists():
                actual_input.unlink()
            
            if result.returncode != 0:
                return ToolResult(
                    success=False,
                    error=f"Marp エラー:\n{result.stderr}",
                    duration_ms=int((time.time() - start) * 1000)
                )
            
            if not output_path.exists():
                return ToolResult(
                    success=False,
                    error=f"出力ファイルが生成されませんでした: {output_path}",
                    duration_ms=int((time.time() - start) * 1000)
                )
            
            size = output_path.stat().st_size
            return ToolResult(
                success=True,
                output=str(output_path),
                artifacts=[str(output_path)],
                metadata={"format": fmt, "size_bytes": size, "theme": theme},
                duration_ms=int((time.time() - start) * 1000)
            )
        
        except subprocess.TimeoutExpired:
            return ToolResult(
                success=False,
                error="Marp のレンダリングがタイムアウトしました（120秒）",
                duration_ms=int((time.time() - start) * 1000)
            )
```

### P2-5: Pipeline `tool_call` ステップ型の追加

#### core/pipeline/template.py への変更

`PipelineStep` データクラスに `type` フィールドを追加する：

```python
# 既存の PipelineStep に追加するフィールド
@dataclass
class PipelineStep:
    id: str
    type: str = "agent"          # "agent" (既存) | "tool_call" (新規)
    agent: Optional[Any] = None  # type == "agent" の場合
    tool: Optional[str] = None   # type == "tool_call" の場合 (ToolRegistry のキー名)
    tool_params: Dict = field(default_factory=dict)  # ツール呼び出しパラメータ
    action: Optional[str] = None
    input: Optional[Any] = None
    output_file: Optional[str] = None
    condition: Optional[str] = None
    max_retries: int = 3
    prompt_hint: Optional[str] = None
```

#### core/pipeline/engine.py への変更

`_execute_single_step()` に `tool_call` ブランチを追加する：

```python
async def _execute_single_step(self, step, context, prev_results, attempt):
    import time
    start_time = time.time()
    
    try:
        # ── tool_call ステップの処理 ──────────────────────────────
        if step.type == "tool_call":
            return await self._execute_tool_call_step(step, context, prev_results, attempt)
        
        # ── agent ステップの処理（既存ロジック） ──────────────────
        model = None
        if step.agent:
            model = self.registry.select(...)
        # ... 既存の処理 ...
    
    except Exception as e:
        ...

async def _execute_tool_call_step(self, step, context, prev_results, attempt):
    """
    tool_call ステップを実行する。
    
    処理フロー:
    1. ToolRegistry から step.tool に対応するツールを取得
    2. ツールのパラメータを解決（step.tool_params の {{...}} プレースホルダを展開）
    3. sandbox.check_approval() で承認確認（requires_approval == True の場合）
    4. tool.run() を実行
    5. ToolResult を StepResult に変換して返す
    
    パラメータ解決規則:
    - "{{steps.generating.output}}" → prev_results["generating"].output
    - "{{context.work_dir}}" → context["work_dir"]
    - "{{task.title}}" → context["task_input"] の先頭50文字
    """
    import time
    start_time = time.time()
    
    if not self.tool_registry:
        from core.tools.registry import ToolRegistry
        self.tool_registry = ToolRegistry.get_instance()
    
    tool = self.tool_registry.get(step.tool)
    if not tool:
        return StepResult(
            step_id=step.id, success=False,
            error=f"ツール '{step.tool}' が見つかりません",
            duration_ms=0, attempt=attempt
        )
    
    # パラメータ解決
    resolved_params = self._resolve_tool_params(step.tool_params, context, prev_results)
    
    # バリデーション
    err = tool.validate_params(resolved_params)
    if err:
        return StepResult(step_id=step.id, success=False, error=err,
                         duration_ms=0, attempt=attempt)
    
    # 実行
    tool_result = await tool.run(resolved_params, work_dir=context.get("work_dir", "."))
    duration_ms = int((time.time() - start_time) * 1000)
    
    return StepResult(
        step_id=step.id,
        success=tool_result.success,
        output=tool_result.output,
        error=tool_result.error,
        duration_ms=duration_ms,
        attempt=attempt
    )
```

#### `tool_call` ステップを使った YAML の例

```yaml
# templates/marp_slides_v2.yaml（P2 版：tool_call ステップを使用）
steps:
  - id: planning
    type: agent
    agent:
      role: planner
    action: plan
    output_file: plan.md

  - id: generating
    type: agent
    agent:
      role: generator
    action: generate
    output_file: slides.md

  - id: render_marp         # ← tool_call ステップ
    type: tool_call
    tool: marp_renderer
    tool_params:
      input_file: "slides.md"
      output_file: "slides.pdf"
      format: "pdf"
      theme: "default"
      auto_inject_frontmatter: true

  - id: render_marp_html    # HTML 版も同時生成
    type: tool_call
    tool: marp_renderer
    tool_params:
      input_file: "slides.md"
      output_file: "slides.html"
      format: "html"

  - id: evaluating
    type: agent
    agent:
      role: evaluator
    action: evaluate
    output_file: eval-report.md
    condition: "{{ steps.render_marp.success }}"
```

---

## P3: MCP サーバー + HermesAgent パターン

### P3-1: HermesAgent パターンとは

**Hermes** とは Nous Research が開発した、ツール使用・構造化出力・ReAct（Reason+Act）に特化した LLM ファミリーから着想を得たエージェントパターン。以下の特徴を harness に取り入れる：

| 機能 | 説明 | harness での実装箇所 |
|------|------|---------------------|
| **ReAct ループ** | Think → Act → Observe を繰り返す | `HermesAgent._react_loop()` |
| **Tool-use プロトコル** | JSON Schema でツール定義、構造化呼び出し | `ToolRegistry.get_schemas_for_llm()` |
| **構造化出力強制** | `<tool_call>` XML タグで出力を解析 | `HermesAgent._parse_tool_call()` |
| **並列ツール呼び出し** | 依存しない複数ツールを同時実行 | `HermesAgent._execute_parallel_tools()` |
| **文脈圧縮** | 長い観測結果を圧縮してコンテキスト節約 | 既存 `ContextCompressor` を活用 |
| **自動リトライ** | ツール失敗時にパラメータを修正して再試行 | `HermesAgent._retry_with_correction()` |

### P3-2: MCP サーバー構成

```
core/
  mcp/
    __init__.py
    server.py            ← FastMCP サーバー（メインエントリーポイント）
    tool_adapter.py      ← core/tools/ → MCP ツール定義への変換
    config.py            ← MCP サーバー設定
```

#### core/mcp/server.py

```python
"""
Harness MCP サーバー

Claude Code のエージェントが直接 harness ツールを呼び出せるようにする。
MCP (Model Context Protocol) を実装し、全ての core/tools/ を公開する。

起動:
  python -m core.mcp.server

MCP 設定（~/.claude/mcp_servers.json または mcp_config.json）:
  {
    "harness-tools": {
      "command": "python",
      "args": ["-m", "core.mcp.server"],
      "cwd": "/home/ubuntu/ws/harness"
    }
  }

エージェントの cli_command への組み込み:
  claude --mcp-config /home/ubuntu/ws/harness/mcp_config.json -p "..."
"""

from mcp.server.fastmcp import FastMCP
from core.tools.registry import ToolRegistry
import asyncio

mcp = FastMCP("harness-tools")
registry = ToolRegistry.get_instance()


def _register_all_tools():
    """
    ToolRegistry の全ツールを MCP ツールとして登録する。
    
    各ツールの get_schema() から MCP の @mcp.tool() 相当の登録を動的に行う。
    パラメータは Pydantic モデルに変換する。
    """
    for tool in registry.list_all():
        _register_tool(tool)


def _register_tool(tool):
    """
    1つの BaseTool を MCP ツールとして動的登録する。
    
    処理:
    1. tool.get_schema() からパラメータ定義を取得
    2. exec() または動的関数生成で @mcp.tool() デコレータを適用
    3. 関数本体は tool.run() を呼び出す
    
    実装上の注意:
    - FastMCP は関数シグネチャからスキーマを推論するため、
      動的生成時は typing.get_type_hints() を活用する
    - または tool ごとに個別登録を手書きし、
      tool_adapter.py に切り出す方が確実
    """
    pass  # 詳細実装は tool_adapter.py を参照


# ── 個別ツール登録（明示的な方法） ──────────────────────────────

@mcp.tool()
async def render_pdf(input_file: str, output_file: str, engine: str = "weasyprint") -> dict:
    """Markdown/HTML を PDF に変換する"""
    tool = registry.get("pdf_renderer")
    result = await tool.run({"input_file": input_file, "output_file": output_file, "engine": engine})
    return {"success": result.success, "output": result.output, "error": result.error}


@mcp.tool()
async def render_marp_slides(
    input_file: str,
    output_file: str,
    format: str = "pdf",
    theme: str = "default",
    auto_inject_frontmatter: bool = True
) -> dict:
    """
    Marp Markdown スライドをレンダリングする。
    format: pdf / html / pptx
    theme: default / gaia / uncover
    """
    tool = registry.get("marp_renderer")
    result = await tool.run({
        "input_file": input_file,
        "output_file": output_file,
        "format": format,
        "theme": theme,
        "auto_inject_frontmatter": auto_inject_frontmatter
    })
    return {"success": result.success, "output": result.output,
            "error": result.error, "metadata": result.metadata}


@mcp.tool()
async def render_pptx(input_file: str, output_file: str) -> dict:
    """JSON または Markdown からPowerPoint ファイルを生成する"""
    tool = registry.get("pptx_renderer")
    result = await tool.run({"input_file": input_file, "output_file": output_file})
    return {"success": result.success, "output": result.output, "error": result.error}


@mcp.tool()
async def render_excel(input_file: str, output_file: str, title: str = "") -> dict:
    """JSON または CSV から Excel ファイルを生成する"""
    tool = registry.get("excel_renderer")
    result = await tool.run({"input_file": input_file, "output_file": output_file, "title": title})
    return {"success": result.success, "output": result.output, "error": result.error}


@mcp.tool()
async def browser_screenshot(url: str, output_file: str, wait_ms: int = 1000) -> dict:
    """指定 URL のスクリーンショットを撮影する"""
    tool = registry.get("browser_operator")
    result = await tool.run({"action": "screenshot", "url": url,
                              "output_file": output_file, "wait_ms": wait_ms})
    return {"success": result.success, "output": result.output, "error": result.error}


@mcp.tool()
async def http_call(
    method: str, url: str, body: str = "", headers: str = "{}", timeout: int = 30
) -> dict:
    """外部 REST API を呼び出す。body・headers は JSON 文字列で渡す"""
    import json
    tool = registry.get("http_caller")
    result = await tool.run({
        "method": method.upper(), "url": url,
        "body": json.loads(body) if body else {},
        "headers": json.loads(headers),
        "timeout": timeout
    })
    return {"success": result.success, "output": result.output, "error": result.error}


if __name__ == "__main__":
    _register_all_tools()
    mcp.run()
```

### P3-3: HermesAgent の実装仕様

```
core/
  agents/
    __init__.py
    hermes.py            ← HermesAgent 本体
    react_loop.py        ← ReAct ループエンジン
    tool_parser.py       ← LLM 出力からのツール呼び出しパース
    parallel_executor.py ← 並列ツール実行
```

#### core/agents/hermes.py

```python
"""
HermesAgent — ツール使用・ReAct ループ・並列実行に特化したエージェント

特徴:
1. ReAct パターン（Reason + Act + Observe の繰り返し）
2. LLM に渡すツールスキーマの自動構築（ToolRegistry 連携）
3. LLM 出力の <tool_call> タグ解析
4. 依存グラフ解析による並列ツール実行
5. 失敗時のパラメータ修正リトライ
6. 長い観測結果の自動圧縮（ContextCompressor 活用）

使用例:
    agent = HermesAgent(
        tools=["marp_renderer", "pdf_renderer", "browser_operator"],
        max_react_steps=8,
        model="claude"
    )
    result = await agent.run(
        task="以下の内容でスライドを作成し PDF にして: ...",
        work_dir="/tmp/task-123"
    )
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

from core.tools.registry import ToolRegistry
from core.tools.base import ToolResult
from core.memory.compressor import ContextCompressor

logger = logging.getLogger(__name__)


@dataclass
class ReActStep:
    """ReAct ループの1ステップ"""
    step_num: int
    thought: str                        # LLM の思考（<thinking> タグ内）
    tool_calls: List[Dict] = field(default_factory=list)   # 呼び出すツールリスト
    observations: List[ToolResult] = field(default_factory=list)  # ツール実行結果
    is_final: bool = False              # これが最終回答か
    final_answer: Optional[str] = None  # 最終回答テキスト


@dataclass
class HermesResult:
    """HermesAgent の実行結果"""
    success: bool
    final_answer: Optional[str] = None
    artifacts: List[str] = field(default_factory=list)  # 生成ファイルパスのリスト
    react_steps: List[ReActStep] = field(default_factory=list)
    total_duration_ms: int = 0
    error: Optional[str] = None


class HermesAgent:
    """
    Hermes パターンのエージェント実装。
    
    ─── ReAct ループの流れ ───────────────────────────────────
    
    1. システムプロンプト構築
       - タスク説明
       - 利用可能ツールのスキーマ（JSON）
       - ReAct フォーマット指示
    
    2. LLM に送信（最初のターン）
    
    3. LLM の出力を解析:
       a. <thinking>...</thinking> → thought を抽出
       b. <tool_call>{"name": "...", "params": {...}}</tool_call> → ツール呼び出しリスト
       c. <final_answer>...</final_answer> → 終了
    
    4. ツール実行:
       a. 依存関係なし → asyncio.gather() で並列実行
       b. 依存関係あり → 順次実行
    
    5. 観測結果を LLM に返す:
       <observation tool="marp_renderer">
       {"success": true, "output": "slides.pdf", "size_bytes": 245632}
       </observation>
    
    6. ループ続行（max_react_steps まで）
    
    ─────────────────────────────────────────────────────────
    """
    
    SYSTEM_PROMPT_TEMPLATE = """あなたはタスクを解決するために以下のツールを使えるエージェントです。

## 利用可能なツール

{tool_schemas_json}

## 応答フォーマット

思考と行動は以下のフォーマットで出力してください：

```
<thinking>
ここに思考過程を記述。何を達成しようとしているか、どのツールを使うべきかを考える。
並列実行できるツールは tool_call を複数並べて良い。
</thinking>

<tool_call>
{{"name": "ツール名", "params": {{"パラメータ": "値"}}}}
</tool_call>

<tool_call>
{{"name": "別のツール名", "params": {{...}}}}
</tool_call>
```

ツール実行結果が返ってきたら、それをもとに次の思考・行動を行うか、
全て完了したら以下で最終回答を出力してください：

```
<thinking>
全て完了した。最終回答をまとめる。
</thinking>

<final_answer>
タスクが完了しました。生成されたファイル: slides.pdf, slides.html
</final_answer>
```

## 重要ルール
- 1回の応答で複数の <tool_call> を出力することで並列実行できる
- ファイルを生成した後は必ず存在確認（file_operator の list_files 等）
- エラーが発生したら原因を分析し、パラメータを修正して再試行する
- 最大 {max_steps} ステップで完了すること
"""
    
    def __init__(
        self,
        tools: List[str] = None,      # 使用するツール名リスト（None = 全ツール）
        max_react_steps: int = 8,
        model: str = "claude",         # LLM CLI コマンド
        compressor: ContextCompressor = None,
        work_dir: str = "."
    ):
        self.registry = ToolRegistry.get_instance()
        self.tool_names = tools
        self.max_react_steps = max_react_steps
        self.model = model
        self.compressor = compressor or ContextCompressor()
        self.work_dir = work_dir
    
    async def run(self, task: str, context: Dict = None) -> HermesResult:
        """
        タスクを ReAct ループで実行する。
        
        Args:
            task: 自然言語タスク説明
            context: 追加コンテキスト（task_meta 等）
        
        Returns:
            HermesResult
        """
        start_time = datetime.now()
        react_steps: List[ReActStep] = []
        all_artifacts: List[str] = []
        
        # 1. システムプロンプト構築
        tool_schemas = self.registry.get_schemas_for_llm(self.tool_names)
        system_prompt = self.SYSTEM_PROMPT_TEMPLATE.format(
            tool_schemas_json=json.dumps(tool_schemas, ensure_ascii=False, indent=2),
            max_steps=self.max_react_steps
        )
        
        # 2. 会話履歴（LLM に渡す累積メッセージ）
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"タスク: {task}"}
        ]
        
        # 3. ReAct ループ
        for step_num in range(1, self.max_react_steps + 1):
            logger.info(f"HermesAgent: ReAct step {step_num}/{self.max_react_steps}")
            
            # LLM 呼び出し
            llm_response = await self._call_llm(messages)
            
            # 解析
            thought, tool_calls, is_final, final_answer = self._parse_response(llm_response)
            
            react_step = ReActStep(
                step_num=step_num,
                thought=thought,
                tool_calls=tool_calls,
                is_final=is_final,
                final_answer=final_answer
            )
            react_steps.append(react_step)
            
            # 最終回答
            if is_final:
                duration = int((datetime.now() - start_time).total_seconds() * 1000)
                return HermesResult(
                    success=True,
                    final_answer=final_answer,
                    artifacts=all_artifacts,
                    react_steps=react_steps,
                    total_duration_ms=duration
                )
            
            # ツール実行（並列）
            if tool_calls:
                observations = await self._execute_parallel_tools(tool_calls)
                react_step.observations = observations
                
                # 成果物収集
                for obs in observations:
                    all_artifacts.extend(obs.artifacts)
                
                # 観測結果を圧縮してメッセージに追加
                obs_text = self._format_observations(tool_calls, observations)
                messages.append({"role": "assistant", "content": llm_response})
                messages.append({"role": "user", "content": obs_text})
            else:
                # ツール呼び出しがなく最終回答でもない → プッシュ
                messages.append({"role": "assistant", "content": llm_response})
                messages.append({
                    "role": "user",
                    "content": "続けてください。ツールを使うか、<final_answer> で回答してください。"
                })
        
        # max_steps 超過
        duration = int((datetime.now() - start_time).total_seconds() * 1000)
        return HermesResult(
            success=False,
            artifacts=all_artifacts,
            react_steps=react_steps,
            total_duration_ms=duration,
            error=f"最大ステップ数 ({self.max_react_steps}) を超過しました"
        )
    
    async def _call_llm(self, messages: List[Dict]) -> str:
        """
        LLM を呼び出す。
        
        実装方針:
        - self.model == "claude" → subprocess で claude CLI を呼び出す
          （会話履歴は一つの大きな prompt としてフォーマット）
        - 将来的には Anthropic API の messages API に直接対応
        
        CLI 呼び出し時のプロンプト構築:
        messages を以下のフォーマットで連結する:
        
        [System]
        {system}
        
        [User]
        {user_content}
        
        [Assistant]
        {assistant_content}
        
        [User]
        {observation}
        """
        import subprocess
        prompt_text = self._messages_to_prompt(messages)
        
        cmd = ["claude", "-p", prompt_text, "--dangerously-skip-permissions"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300,
                                cwd=self.work_dir, env=self._build_env())
        
        if result.returncode != 0:
            raise RuntimeError(f"LLM 呼び出し失敗: {result.stderr}")
        
        return result.stdout
    
    def _parse_response(self, text: str) -> Tuple[str, List[Dict], bool, Optional[str]]:
        """
        LLM 出力から thought / tool_calls / is_final / final_answer を抽出する。
        
        パース規則:
        - <thinking>...</thinking> → thought
        - <tool_call>JSON</tool_call> → tool_calls に追加
        - <final_answer>...</final_answer> → is_final=True
        
        エラー処理:
        - JSON パース失敗 → そのツール呼び出しをスキップしてログ出力
        - タグなし → thought=text, tool_calls=[], is_final=False
        """
        import re
        
        thought = ""
        tool_calls = []
        is_final = False
        final_answer = None
        
        # thinking タグ
        thinking_match = re.search(r'<thinking>(.*?)</thinking>', text, re.DOTALL)
        if thinking_match:
            thought = thinking_match.group(1).strip()
        
        # tool_call タグ（複数）
        for tc_match in re.finditer(r'<tool_call>(.*?)</tool_call>', text, re.DOTALL):
            try:
                call_data = json.loads(tc_match.group(1).strip())
                tool_calls.append(call_data)
            except json.JSONDecodeError as e:
                logger.warning(f"tool_call パース失敗: {e}\n内容: {tc_match.group(1)}")
        
        # final_answer タグ
        fa_match = re.search(r'<final_answer>(.*?)</final_answer>', text, re.DOTALL)
        if fa_match:
            is_final = True
            final_answer = fa_match.group(1).strip()
        
        return thought, tool_calls, is_final, final_answer
    
    async def _execute_parallel_tools(
        self, tool_calls: List[Dict]
    ) -> List[ToolResult]:
        """
        複数のツール呼び出しを並列実行する。
        
        実装:
        - asyncio.gather(*[self._execute_single_tool(tc) for tc in tool_calls])
        - 各ツールの requires_approval が True の場合は sandbox を通す
        
        戻り値は tool_calls と同じ順序の ToolResult リスト。
        """
        tasks = [self._execute_single_tool(tc) for tc in tool_calls]
        return await asyncio.gather(*tasks, return_exceptions=False)
    
    async def _execute_single_tool(self, tool_call: Dict) -> ToolResult:
        """
        1つのツール呼び出しを実行する。
        
        エラー処理:
        - ツール名が存在しない → ToolResult(success=False, error="...")
        - requires_approval=True かつ非承認 → ToolResult(success=False, error="承認されませんでした")
        - 実行例外 → ToolResult(success=False, error=str(e))
        """
        name = tool_call.get("name", "")
        params = tool_call.get("params", {})
        
        tool = self.registry.get(name)
        if not tool:
            return ToolResult(success=False, error=f"ツール '{name}' は存在しません")
        
        err = tool.validate_params(params)
        if err:
            return ToolResult(success=False, error=f"パラメータエラー: {err}")
        
        try:
            return await tool.run(params, work_dir=self.work_dir)
        except Exception as e:
            return ToolResult(success=False, error=str(e))
    
    def _format_observations(
        self, tool_calls: List[Dict], observations: List[ToolResult]
    ) -> str:
        """
        ツール実行結果を LLM に返す観測テキストを生成する。
        
        フォーマット:
        <observation tool="marp_renderer" success="true">
        {"output": "slides.pdf", "size_bytes": 245632, "format": "pdf"}
        </observation>
        
        <observation tool="excel_renderer" success="false">
        エラー: openpyxl がインストールされていません
        </observation>
        
        長い結果は ContextCompressor で圧縮する。
        """
        parts = []
        for call, obs in zip(tool_calls, observations):
            name = call.get("name", "unknown")
            success_str = "true" if obs.success else "false"
            
            if obs.success:
                content = json.dumps({
                    "output": obs.output,
                    **obs.metadata
                }, ensure_ascii=False)
            else:
                content = f"エラー: {obs.error}"
            
            # 長い観測結果は圧縮
            if len(content) > 2000:
                content = self.compressor.compress(content, max_tokens=500)
            
            parts.append(
                f'<observation tool="{name}" success="{success_str}">\n{content}\n</observation>'
            )
        
        return "\n\n".join(parts)
    
    def _messages_to_prompt(self, messages: List[Dict]) -> str:
        """
        messages リストを CLI 用のフラットなプロンプトテキストに変換する。
        """
        parts = []
        for msg in messages:
            role = msg["role"].upper()
            if role == "SYSTEM":
                parts.append(f"[System]\n{msg['content']}")
            elif role == "USER":
                parts.append(f"[User]\n{msg['content']}")
            elif role == "ASSISTANT":
                parts.append(f"[Assistant]\n{msg['content']}")
        return "\n\n---\n\n".join(parts)
    
    def _build_env(self) -> dict:
        """PATH 拡張済み環境変数を返す（executor.py と同様）"""
        import os
        env = os.environ.copy()
        for p in [os.path.expanduser("~/.local/bin"), "/usr/local/bin"]:
            if p not in env.get("PATH", ""):
                env["PATH"] = p + os.pathsep + env.get("PATH", "")
        return env
```

### P3-4: Pipeline への HermesAgent 統合

`executor.py` の `_build_command()` に `hermes` エントリーポイントを追加：

```python
def _build_command(cli_command: str, prompt: str) -> list[str]:
    # 既存エントリ ...
    if cli_command == 'hermes':
        # HermesAgent をサブプロセスとして起動
        return [
            'python', '-m', 'core.agents.hermes_runner',
            '--prompt', prompt,
            '--tools', 'all'
        ]
    # ...
```

`core/agents/hermes_runner.py`（CLI エントリーポイント）：

```python
"""
hermes_runner.py — HermesAgent の CLI エントリーポイント

使用法:
  python -m core.agents.hermes_runner --prompt "スライドを作成して..." --tools marp_renderer,pdf_renderer
  python -m core.agents.hermes_runner --prompt "..." --tools all --max-steps 10 --work-dir /tmp/task-123
"""

import asyncio, argparse, sys, os

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--tools", default="all",
                        help="カンマ区切りのツール名 または 'all'")
    parser.add_argument("--max-steps", type=int, default=8)
    parser.add_argument("--work-dir", default=".")
    args = parser.parse_args()
    
    tools = None if args.tools == "all" else args.tools.split(",")
    
    from core.agents.hermes import HermesAgent
    agent = HermesAgent(
        tools=tools,
        max_react_steps=args.max_steps,
        work_dir=args.work_dir
    )
    
    result = await agent.run(task=args.prompt)
    
    # 標準出力に結果を出力（executor.py がログとして収集する）
    print(f"[HermesAgent] {'成功' if result.success else '失敗'}")
    if result.final_answer:
        print(f"[回答] {result.final_answer}")
    if result.artifacts:
        print(f"[成果物] {', '.join(result.artifacts)}")
    if result.error:
        print(f"[エラー] {result.error}", file=sys.stderr)
    
    # ReAct ステップサマリー
    for step in result.react_steps:
        print(f"\n[Step {step.step_num}] {step.thought[:100]}...")
        for tc in step.tool_calls:
            print(f"  → ツール: {tc.get('name')}({tc.get('params', {})})")
        for obs in step.observations:
            status = "✓" if obs.success else "✗"
            print(f"  {status} 結果: {str(obs.output)[:100]}")
    
    sys.exit(0 if result.success else 1)


if __name__ == "__main__":
    asyncio.run(main())
```

### P3-5: DB への HermesAgent シード追加

`database.py` の `seed_agents()` に追加：

```python
Agent(
    name='Hermes Agent (Tool-use)',
    cli_command='hermes',
    role=AgentRole.generator,
    priority=3,              # 高優先度：ツール操作を含むタスクに優先使用
    system_prompt=(
        'ツール使用・ドキュメント生成・ブラウザ操作に特化したエージェント。'
        'ReAct パターンで思考→行動→観測を繰り返す。'
        'PDF/PPTX/Excel/Marp スライドの生成が可能。'
    ),
    is_active=True
),
```

### P3-6: task_meta による自動ルーティング

タスク作成時に `task_meta.task_type` を設定することで自動的に適切なパイプラインが選択される：

```python
# API 呼び出し例
POST /api/v1/tasks
{
  "prompt": "Q1 売上データの Excel レポートを作成し、PDF 版と Marp スライド版も出力してください",
  "pipeline_mode": true,
  "metadata": {
    "task_type": "multi_render",   // 複数フォーマット出力
    "output_formats": ["xlsx", "pdf", "marp_html"],
    "hermes_tools": ["excel_renderer", "pdf_renderer", "marp_renderer"]
  }
}
```

---

## 依存パッケージ一覧

### Python パッケージ（requirements_tools.txt として追加）

```
# ドキュメント生成
weasyprint>=60.0
markdown2>=2.4.0
python-pptx>=0.6.23
openpyxl>=3.1.2
python-docx>=1.1.0

# ブラウザ操作
playwright>=1.44.0

# MCP サーバー
mcp[cli]>=1.0.0

# HTTP クライアント（既存 requests と共存）
httpx>=0.27.0
```

### Node.js パッケージ

```bash
npm install -g @marp-team/marp-cli   # Marp CLI（Node.js 18+ 必要）
```

### Playwright ブラウザ

```bash
python -m playwright install chromium
```

---

## ファイル変更サマリー

### P1 で追加・変更するファイル

| 操作 | ファイルパス |
|------|------------|
| 新規作成 | `scripts/tools/__init__.py` |
| 新規作成 | `scripts/tools/render_pdf.py` |
| 新規作成 | `scripts/tools/render_pptx.py` |
| 新規作成 | `scripts/tools/render_excel.py` |
| 新規作成 | `scripts/tools/render_docx.py` |
| 新規作成 | `scripts/tools/render_marp.py` |
| 新規作成 | `scripts/tools/browser_action.py` |
| 新規作成 | `scripts/tools/http_call.py` |
| 新規作成 | `scripts/tools/tool_runner.py` |
| 新規作成 | `templates/pdf_report.yaml` |
| 新規作成 | `templates/marp_slides.yaml` |
| 新規作成 | `templates/pptx_deck.yaml` |
| 新規作成 | `templates/excel_report.yaml` |
| 変更 | `webui/app/services/executor.py`（`_collect_result` に新タスクタイプ追加） |
| 変更 | `webui/app/database.py`（`seed_agents` に Tool Renderer 追加） |

### P2 で追加・変更するファイル

| 操作 | ファイルパス |
|------|------------|
| 新規作成 | `core/tools/__init__.py` |
| 新規作成 | `core/tools/base.py` |
| 新規作成 | `core/tools/registry.py` |
| 新規作成 | `core/tools/sandbox.py` |
| 新規作成 | `core/tools/renderers/__init__.py` |
| 新規作成 | `core/tools/renderers/pdf.py` |
| 新規作成 | `core/tools/renderers/pptx.py` |
| 新規作成 | `core/tools/renderers/excel.py` |
| 新規作成 | `core/tools/renderers/docx.py` |
| 新規作成 | `core/tools/renderers/marp.py` |
| 新規作成 | `core/tools/operators/__init__.py` |
| 新規作成 | `core/tools/operators/browser.py` |
| 新規作成 | `core/tools/operators/http.py` |
| 新規作成 | `core/tools/operators/shell.py` |
| 新規作成 | `core/tools/operators/file.py` |
| 変更 | `core/pipeline/template.py`（`PipelineStep` に `type` フィールド追加） |
| 変更 | `core/pipeline/engine.py`（`tool_call` ステップ実行ブランチ追加） |

### P3 で追加・変更するファイル

| 操作 | ファイルパス |
|------|------------|
| 新規作成 | `core/mcp/__init__.py` |
| 新規作成 | `core/mcp/server.py` |
| 新規作成 | `core/mcp/tool_adapter.py` |
| 新規作成 | `core/mcp/config.py` |
| 新規作成 | `core/agents/__init__.py` |
| 新規作成 | `core/agents/hermes.py` |
| 新規作成 | `core/agents/react_loop.py` |
| 新規作成 | `core/agents/tool_parser.py` |
| 新規作成 | `core/agents/parallel_executor.py` |
| 新規作成 | `core/agents/hermes_runner.py` |
| 新規作成 | `mcp_config.json` |
| 変更 | `webui/app/services/executor.py`（`_build_command` に `hermes` 追加） |
| 変更 | `webui/app/database.py`（`seed_agents` に Hermes Agent 追加） |

---

## テスト計画

### P1 テスト

```python
# tests/test_tool_scripts.py

def test_render_marp_pdf():
    """Marp が利用可能な場合、PDF を生成できること"""
    # 前提: marp が PATH に存在すること
    result = subprocess.run(
        ["python", "scripts/tools/render_marp.py",
         "--input", "tests/fixtures/sample_slides.md",
         "--output", "/tmp/test_slides.pdf",
         "--format", "pdf"],
        capture_output=True, text=True
    )
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["success"] is True
    assert Path("/tmp/test_slides.pdf").exists()
    assert data["size_bytes"] > 0

def test_render_marp_auto_frontmatter():
    """フロントマターなし Markdown を渡しても PDF が生成されること"""
    md_content = "# テストスライド\n\n---\n\n# スライド2\n"
    # ... (一時ファイル作成→実行→確認)

def test_render_marp_html():
    """HTML 形式でも出力できること"""
    ...

def test_render_pptx_from_json():
    """JSON データから PPTX を生成できること"""
    ...

def test_render_excel_from_json():
    """JSON データから Excel を生成できること"""
    ...

def test_marp_not_available():
    """Marp が存在しない場合、明確なエラーメッセージを返すこと"""
    ...
```

### P2 テスト

```python
# tests/test_tool_layer.py

async def test_marp_renderer_tool():
    """MarpRenderer(BaseTool) が正しく動作すること"""
    from core.tools.renderers.marp import MarpRenderer
    tool = MarpRenderer()
    result = await tool.run(
        {"input_file": "slides.md", "output_file": "slides.pdf", "format": "pdf"},
        work_dir="/tmp/test"
    )
    assert result.success

async def test_tool_registry_get_schemas():
    """ToolRegistry が全ツールのスキーマを返すこと"""
    registry = ToolRegistry.get_instance()
    schemas = registry.get_schemas_for_llm()
    assert len(schemas) >= 5
    names = [s["name"] for s in schemas]
    assert "marp_renderer" in names
    assert "pdf_renderer" in names

async def test_pipeline_tool_call_step():
    """tool_call ステップが Pipeline から正しく実行されること"""
    ...
```

### P3 テスト

```python
# tests/test_hermes_agent.py

async def test_hermes_parse_response():
    """LLM レスポンスから tool_call を正しくパースできること"""
    agent = HermesAgent(tools=["marp_renderer"])
    response = """
<thinking>Marp でスライドを生成する</thinking>
<tool_call>
{"name": "marp_renderer", "params": {"input_file": "slides.md", "output_file": "slides.pdf"}}
</tool_call>
"""
    thought, tool_calls, is_final, final_answer = agent._parse_response(response)
    assert thought == "Marp でスライドを生成する"
    assert len(tool_calls) == 1
    assert tool_calls[0]["name"] == "marp_renderer"
    assert is_final is False

async def test_hermes_parallel_tools():
    """並列ツール実行が正しく動作すること"""
    ...
```

---

## 実装時の注意事項

1. **Marp CLI の冪等性**: 同じ入力ファイルに対して複数回実行しても同じ出力を生成すること。`--allow-local-files` を忘れると画像が埋め込まれない。

2. **python-pptx のフォント**: 日本語を含む場合、フォント指定が必要。デフォルト（Arial等）では文字化けすることがある。`slide.shapes.title.text_frame.paragraphs[0].runs[0].font.name = "Noto Sans CJK JP"` などを明示する。

3. **weasyprint の日本語フォント**: システムフォントが不足する場合は `fontconfig` の設定が必要。`fc-list | grep -i noto` で確認。

4. **HermesAgent の LLM 呼び出し**: 現在は Claude CLI を subprocess で呼び出す設計。将来的には Anthropic API の messages API を直接使用するとより高速・安定。tool_use API に対応すれば `_parse_response()` の XML パースが不要になる。

5. **並列ツール実行とファイルシステム**: 同じ出力ファイルに複数のツールが書き込む競合を避けること。`parallel_executor.py` でファイルパスの重複チェックを実装する。

6. **セキュリティ**: `ShellExecutor` は `requires_approval = True` を必ず設定し、`sandbox.py` で許可コマンドリストを管理する。任意コマンドの実行を許可しないこと。
