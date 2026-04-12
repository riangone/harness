"""
Harness 外部 AI 后端 — MailMindHub 集成

适配 harness API v2.0.0（Webhook 回调模式）

用法（在 MailMindHub 侧）：
1. 在 MailMindHub 的 AI_BACKENDS 注册此客户端
2. 邮件到达时，MailMindHub 调用 call_harness() 创建任务
3. harness 执行完成后，通过 Webhook 回调通知 MailMindHub
4. MailMindHub 收到回调后，用 email_content 回复用户邮件

两种模式：
- Webhook 模式（推荐）：创建任务时传入 callback_url，harness 完成后主动通知
- 轮询模式（兼容）：创建任务后轮询获取状态

环境变量：
    HARNESS_API_URL       harness API 地址（默认 http://localhost:7500）
    HARNESS_API_TOKEN     API 认证 Token
    MAILMINDHUB_CALLBACK_URL  MailMindHub 的回调接收地址
"""

import os
import time
import logging
from typing import Optional, Dict, Any

try:
    import requests
except ImportError:
    requests = None

logger = logging.getLogger(__name__)

# ============================================
# 配置
# ============================================
HARNESS_API_URL = os.environ.get("HARNESS_API_URL", "http://localhost:7500")
HARNESS_API_TOKEN = os.environ.get("HARNESS_API_TOKEN", "")
MAILMINDHUB_CALLBACK_URL = os.environ.get("MAILMINDHUB_CALLBACK_URL", "")
POLL_INTERVAL = int(os.environ.get("HARNESS_POLL_INTERVAL", "10"))  # 轮询间隔（秒）
MAX_WAIT_TIME = int(os.environ.get("HARNESS_MAX_WAIT", "600"))  # 最大等待时间（秒）


class HarnessClient:
    """harness API v2.0 客户端 — 支持 Webhook 和轮询两种模式"""

    def __init__(
        self,
        base_url: str = HARNESS_API_URL,
        api_token: str = HARNESS_API_TOKEN,
        callback_url: str = MAILMINDHUB_CALLBACK_URL
    ):
        self.base_url = base_url.rstrip("/")
        self.api_token = api_token
        self.callback_url = callback_url
        self.headers = {"Content-Type": "application/json"}
        if api_token:
            self.headers["X-API-Key"] = api_token

    # ─────────────────────────────────────────────
    # 通用任务 API
    # ─────────────────────────────────────────────

    def create_task(
        self,
        title: str,
        prompt: str,
        success_criteria: Optional[str] = None,
        pipeline_mode: bool = True,
        agent_id: Optional[int] = None,
        project_id: Optional[int] = None,
        callback_url: Optional[str] = None,
        source: str = "mailmindhub",
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[int]:
        """
        创建任务（通用 API）

        Args:
            title: 任务标题
            prompt: 任务提示
            success_criteria: 成功标准
            pipeline_mode: Pipeline 模式
            agent_id: 指定 Agent
            callback_url: Webhook 回调地址（默认使用全局配置）
            source: 来源标识
            metadata: 额外元数据

        Returns:
            task_id 或 None
        """
        if requests is None:
            logger.error("requests 库未安装")
            return None

        payload = {
            "title": title,
            "prompt": prompt,
            "success_criteria": success_criteria or "",
            "pipeline_mode": pipeline_mode,
            "source": source,
        }
        if agent_id is not None:
            payload["agent_id"] = agent_id
        if project_id is not None:
            payload["project_id"] = project_id
        if callback_url or self.callback_url:
            payload["callback_url"] = callback_url or self.callback_url
        if metadata:
            payload["metadata"] = metadata

        try:
            resp = requests.post(
                f"{self.base_url}/api/v1/tasks",
                headers=self.headers,
                json=payload,
                timeout=30
            )
            resp.raise_for_status()
            data = resp.json()
            task_id = data.get("task_id")
            logger.info(f"✅ harness task created: id={task_id}, title={title}")
            return task_id
        except Exception as e:
            logger.error(f"❌ Failed to create harness task: {e}")
            return None

    def create_task_from_email(
        self,
        subject: str,
        body: str,
        from_addr: str,
        callback_url: Optional[str] = None
    ) -> Optional[int]:
        """
        从邮件内容创建任务

        harness 会自动解析邮件内容、匹配路由规则、创建对应 Pipeline 任务。

        Args:
            subject: 邮件主题
            body: 邮件正文
            from_addr: 发件人地址
            callback_url: Webhook 回调地址

        Returns:
            task_id 或 None（如果无法识别命令则返回 None）
        """
        if requests is None:
            logger.error("requests 库未安装")
            return None

        payload = {
            "subject": subject,
            "body": body,
            "from_addr": from_addr,
        }
        if callback_url or self.callback_url:
            payload["callback_url"] = callback_url or self.callback_url

        try:
            resp = requests.post(
                f"{self.base_url}/api/v1/tasks/from-email",
                headers=self.headers,
                json=payload,
                timeout=30
            )
            resp.raise_for_status()
            data = resp.json()

            status = data.get("status", "")
            task_id = data.get("task_id")
            help_sent = data.get("help_sent", False)

            if status == "unknown_command" and help_sent:
                logger.info(f"⚠️ 无法识别的邮件命令，已返回帮助信息")
                return None  # 特殊：无法创建任务

            if task_id:
                logger.info(f"✅ Email task created: id={task_id}, subject={subject[:50]}")
                return task_id
            else:
                logger.warning(f"⚠️ Email task creation returned no task_id: {data}")
                return None

        except Exception as e:
            logger.error(f"❌ Failed to create email task: {e}")
            return None

    def get_task_status(self, task_id: int) -> Optional[Dict[str, Any]]:
        """查询任务状态"""
        if requests is None:
            return None

        try:
            resp = requests.get(
                f"{self.base_url}/api/v1/tasks/{task_id}",
                headers=self.headers,
                timeout=10
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"❌ Failed to get task status: {e}")
            return None

    def cancel_task(self, task_id: int) -> bool:
        """取消正在执行的任务"""
        if requests is None:
            return False

        try:
            resp = requests.post(
                f"{self.base_url}/api/v1/tasks/{task_id}/cancel",
                headers=self.headers,
                timeout=10
            )
            resp.raise_for_status()
            return True
        except Exception as e:
            logger.error(f"❌ Failed to cancel task: {e}")
            return False

    def wait_for_completion(
        self,
        task_id: int,
        poll_interval: int = POLL_INTERVAL,
        max_wait: int = MAX_WAIT_TIME
    ) -> Optional[Dict[str, Any]]:
        """
        等待任务完成（轮询模式）

        注意：推荐使用 Webhook 模式而非此方法。
        """
        start_time = time.time()
        while time.time() - start_time < max_wait:
            status = self.get_task_status(task_id)
            if not status:
                return None

            task_status = status.get("status", "")
            if task_status in ("completed", "failed"):
                return status

            logger.info(f"⏳ Task {task_id} status: {task_status}, waiting...")
            time.sleep(poll_interval)

        logger.warning(f"⏰ Task {task_id} timed out after {max_wait}s")
        return None

    def test_callback(self, callback_url: Optional[str] = None) -> bool:
        """
        测试 Webhook 回调端点
        """
        if requests is None:
            return False

        url = callback_url or self.callback_url
        if not url:
            logger.error("No callback URL configured")
            return False

        try:
            resp = requests.post(
                f"{self.base_url}/api/v1/callback/test",
                headers={
                    **self.headers,
                    "X-Callback-URL": url
                },
                timeout=15
            )
            resp.raise_for_status()
            data = resp.json()
            logger.info(f"✅ Callback test OK: {data}")
            return True
        except Exception as e:
            logger.error(f"❌ Callback test failed: {e}")
            return False

    def list_agents(self) -> list:
        """查询可用 Agent 列表"""
        if requests is None:
            return []

        try:
            resp = requests.get(
                f"{self.base_url}/api/v1/agents",
                headers=self.headers,
                timeout=10
            )
            resp.raise_for_status()
            return resp.json().get("agents", [])
        except Exception as e:
            logger.error(f"❌ Failed to list agents: {e}")
            return []

    def health_check(self) -> bool:
        """健康检查"""
        if requests is None:
            return False

        try:
            resp = requests.get(
                f"{self.base_url}/api/v1/health",
                headers=self.headers,
                timeout=5
            )
            return resp.status_code == 200
        except Exception:
            return False


# ============================================
# Webhook 回调接收器（MailMindHub 侧的实现示例）
# ============================================

def handle_harness_callback(callback_data: Dict[str, Any]) -> Optional[str]:
    """
    处理 harness 的 Webhook 回调

    此函数应由 MailMindHub 的 HTTP 服务器在收到回调时调用。

    Args:
        callback_data: harness POST 的回调数据

    Returns:
        邮件正文（供 MailMindHub 回复用户），或 None（如果处理失败）
    """
    task_id = callback_data.get("task_id")
    status = callback_data.get("status", "unknown")
    title = callback_data.get("title", "")
    result = callback_data.get("result", "")
    email_content = callback_data.get("email_content")

    logger.info(f"📨 Harness callback: task={task_id}, status={status}, title={title}")

    if status == "completed":
        logger.info(f"✅ Task {task_id} completed: {title}")
    elif status == "failed":
        logger.warning(f"❌ Task {task_id} failed: {title}")
        if result:
            logger.warning(f"   Result: {result[:200]}")

    # 返回格式化好的邮件内容（harness 已经根据模板生成好了）
    if email_content:
        subject = email_content.get("subject", f"[harness] Task #{task_id} {status}")
        body = email_content.get("body", f"Task {task_id} {status}")
        logger.info(f"📧 Email ready: subject='{subject}'")
        return body

    # 如果没有 email_content，手动构建
    runs = callback_data.get("runs", [])
    output_lines = []

    if status == "completed":
        output_lines.append(f"✅ **harness 任务完成**")
    else:
        output_lines.append(f"❌ **harness 任务失败**")

    output_lines.append(f"\n**任务**: {title}")
    output_lines.append(f"**状态**: {status}")

    if runs:
        output_lines.append("\n**执行步骤**:")
        for run in runs:
            phase = run.get("phase", "unknown")
            run_status = run.get("status", "unknown")
            agent = run.get("agent", "")
            verdict = run.get("eval_verdict", "")
            line = f"  - [{phase}] {agent}: {run_status}"
            if verdict:
                line += f" (Verdict: {verdict})"
            output_lines.append(line)

    if result:
        output_lines.append(f"\n**最终结果**:\n{result[:500]}")

    return "\n".join(output_lines)


# ============================================
# 便捷函数
# ============================================

def call_harness(
    title: str,
    prompt: str,
    success_criteria: Optional[str] = None,
    pipeline_mode: bool = True,
    wait_for_result: bool = False,
    callback_url: Optional[str] = None
) -> Optional[str]:
    """
    便捷函数：创建 harness 任务

    Args:
        title: 任务标题
        prompt: 任务提示
        success_criteria: 成功标准
        pipeline_mode: Pipeline 模式
        wait_for_result: 是否等待结果（False = Webhook 模式, True = 轮询模式）
        callback_url: 回调地址

    Returns:
        任务结果文本
    """
    client = HarnessClient(callback_url=callback_url)

    # 创建任务
    task_id = client.create_task(title, prompt, success_criteria, pipeline_mode)
    if task_id is None:
        return "❌ harness 任务创建失败，请检查 harness 是否运行"

    if not wait_for_result:
        return (f"✅ harness 任务已创建 (ID: {task_id})，正在后台执行。\n"
                f"完成后将通过 Webhook 通知。")

    # 轮询等待（不推荐用于长任务）
    result = client.wait_for_completion(task_id)
    if result is None:
        return f"⏰ harness 任务超时 (ID: {task_id})"

    task_status = result.get("status", "unknown")
    task_result = result.get("result", "")
    runs = result.get("runs", [])

    output_lines = [
        f"✅ **harness 任务完成**" if task_status == "completed" else f"❌ **harness 任务失败**",
        f"\n**任务**: {title}",
        f"**状态**: {task_status}"
    ]

    if runs:
        output_lines.append("\n**执行步骤**:")
        for run in runs:
            phase = run.get("phase", "unknown")
            r_status = run.get("status", "unknown")
            r_result = run.get("result", "")
            agent = run.get("agent", "")
            output_lines.append(f"\n- [{phase}] {agent}: {r_status}")
            if r_result:
                output_lines.append(f"  {r_result[:200]}")

    if task_result:
        output_lines.append(f"\n**最终结果**:\n{task_result[:500]}")

    return "\n".join(output_lines)


def call_harness_from_email(
    subject: str,
    body: str,
    from_addr: str,
    callback_url: Optional[str] = None
) -> Optional[str]:
    """
    便捷函数：从邮件创建 harness 任务

    Returns:
        任务结果文本，或 None（无法识别命令时）
    """
    client = HarnessClient(callback_url=callback_url)

    task_id = client.create_task_from_email(subject, body, from_addr)
    if task_id is None:
        # 无法识别的命令
        return None

    return (f"✅ harness 任务已创建 (ID: {task_id})。\n"
            f"主题: {subject[:60]}\n"
            f"完成后将通过 Webhook 通知。")


# ============================================
# CLI 测试入口
# ============================================
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("用法: python harness_backend.py <提示词>")
        print("      python harness_backend.py --from-email <subject> <body> <from_addr>")
        sys.exit(1)

    if sys.argv[1] == "--from-email":
        if len(sys.argv) < 5:
            print("用法: python harness_backend.py --from-email <subject> <body> <from_addr>")
            sys.exit(1)
        result = call_harness_from_email(sys.argv[2], sys.argv[3], sys.argv[4])
        if result:
            print(result)
        else:
            print("⚠️ 无法识别的邮件命令")
    else:
        prompt = " ".join(sys.argv[1:])
        result = call_harness("CLI 任务", prompt)
        print(result)
