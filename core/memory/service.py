"""
Memory Service - 轻量记忆服务

提供：
- 短期记忆：当前会话上下文
- 长期记忆：SQLite持久化的任务经验
- 经验沉淀：成功/失败模式自动记录
- 相似性召回：用于few-shot注入
"""

import sqlite3
import json
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)


class MemoryService:
    """
    记忆服务：管理任务执行的历史经验和模式
    """
    
    def __init__(self, db_path: str = "data/memory.db"):
        self.db_path = db_path
        self._ensure_db_dir()
        self._init_db()

    def _ensure_db_dir(self):
        """确保数据库目录存在"""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

    def _init_db(self):
        """初始化数据库表"""
        with sqlite3.connect(self.db_path) as conn:
            # 记忆表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_type TEXT NOT NULL,
                    agent_role TEXT,
                    outcome TEXT NOT NULL CHECK(outcome IN ('success', 'failed')),
                    template TEXT,
                    lesson TEXT,
                    patterns TEXT,
                    metrics TEXT,
                    tags TEXT,
                    source TEXT DEFAULT 'manual',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_memaries_type_outcome
                ON memories(task_type, outcome)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_memaries_created
                ON memories(created_at DESC)
            """)

            # 短期记忆表（会话级）
            conn.execute("""
                CREATE TABLE IF NOT EXISTS session_context (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT,
                    token_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(session_id, key)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_session_key
                ON session_context(session_id, key)
            """)

            logger.info(f"Memory DB initialized: {self.db_path}")

    def retrieve_similar(
        self,
        task_type: str,
        role: str = None,
        limit: int = 3,
        outcome_filter: str = 'success'
    ) -> List[Dict[str, Any]]:
        """
        召回相似历史任务
        
        Args:
            task_type: 任务类型
            role: 代理角色（可选）
            limit: 返回数量
            outcome_filter: 结果过滤 ('success'/'failed'/None)
            
        Returns:
            历史记录列表
        """
        query = """
            SELECT * FROM memories
            WHERE task_type = ?
              AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
        """
        params: list = [task_type]
        
        if outcome_filter:
            query += " AND outcome = ?"
            params.append(outcome_filter)
        
        if role:
            query += " AND agent_role = ?"
            params.append(role)
        
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(query, params)
                rows = cursor.fetchall()
            
            return [self._row_to_dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to retrieve memories: {e}")
            return []

    def store_experience(
        self,
        task_type: str,
        outcome: str,
        data: Dict[str, Any],
        agent_role: str = None,
        retention_days: int = 90
    ) -> int:
        """
        任务完成后沉淀经验
        
        Args:
            task_type: 任务类型
            outcome: 结果 ('success'/'failed')
            data: 经验数据
            agent_role: 代理角色
            retention_days: 保留天数
            
        Returns:
            插入的记录ID
        """
        expires_at = datetime.now() + timedelta(days=retention_days)
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                if outcome == 'success':
                    cursor = conn.execute(
                        """
                        INSERT INTO memories
                        (task_type, agent_role, outcome, template, metrics, tags, expires_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            task_type,
                            agent_role,
                            outcome,
                            json.dumps(data.get('template', {}), ensure_ascii=False),
                            json.dumps(data.get('metrics', {})),
                            json.dumps(data.get('tags', [])),
                            expires_at
                        )
                    )
                else:
                    cursor = conn.execute(
                        """
                        INSERT INTO memories
                        (task_type, agent_role, outcome, lesson, patterns, tags, expires_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            task_type,
                            agent_role,
                            outcome,
                            data.get('lesson', ''),
                            json.dumps(data.get('patterns', [])),
                            json.dumps(data.get('tags', [])),
                            expires_at
                        )
                    )
                
                memory_id = cursor.lastrowid
                logger.info(f"Stored experience: id={memory_id}, type={task_type}, outcome={outcome}")
                return memory_id
                
        except Exception as e:
            logger.error(f"Failed to store experience: {e}")
            return -1

    def build_context_from_memories(
        self,
        memories: List[Dict[str, Any]],
        max_length: int = 4000
    ) -> str:
        """
        将历史记忆转换为可注入的上下文字符串
        
        Args:
            memories: 历史记录列表
            max_length: 最大长度
            
        Returns:
            格式化的上下文字符串
        """
        if not memories:
            return ""
        
        context_parts = []
        current_length = 0
        
        for mem in memories:
            part = ""
            if mem.get('template'):
                template = mem['template']
                if isinstance(template, str):
                    part = f"【成功案例】\n{template}"
                else:
                    part = f"【成功案例】\n{json.dumps(template, ensure_ascii=False, indent=2)}"
            elif mem.get('lesson'):
                part = f"【失败教训】\n{mem['lesson']}"
            
            if part and (current_length + len(part)) <= max_length:
                context_parts.append(part)
                current_length += len(part)
            elif part:
                break
        
        if not context_parts:
            return ""
        
        return "## 历史经验参考\n\n" + "\n\n---\n\n".join(context_parts)

    # --- 短期记忆（会话级） ---

    def set_session_context(
        self,
        session_id: str,
        key: str,
        value: str,
        token_count: int = None
    ):
        """设置会话上下文"""
        if token_count is None:
            token_count = len(value) // 4  # 粗略估算
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO session_context (session_id, key, value, token_count)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(session_id, key) DO UPDATE SET
                        value = excluded.value,
                        token_count = excluded.token_count,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (session_id, key, value, token_count)
                )
        except Exception as e:
            logger.error(f"Failed to set session context: {e}")

    def get_session_context(
        self,
        session_id: str,
        key: str = None
    ) -> Dict[str, str]:
        """获取会话上下文"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                
                if key:
                    cursor = conn.execute(
                        "SELECT * FROM session_context WHERE session_id = ? AND key = ?",
                        (session_id, key)
                    )
                else:
                    cursor = conn.execute(
                        "SELECT * FROM session_context WHERE session_id = ? ORDER BY created_at",
                        (session_id,)
                    )
                
                return {row['key']: row['value'] for row in cursor.fetchall()}
        except Exception as e:
            logger.error(f"Failed to get session context: {e}")
            return {}

    def clear_session_context(self, session_id: str):
        """清除会话上下文"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "DELETE FROM session_context WHERE session_id = ?",
                    (session_id,)
                )
        except Exception as e:
            logger.error(f"Failed to clear session context: {e}")

    # --- 辅助方法 ---

    def get_statistics(self) -> Dict[str, Any]:
        """获取记忆统计信息"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                total = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
                success = conn.execute(
                    "SELECT COUNT(*) FROM memories WHERE outcome = 'success'"
                ).fetchone()[0]
                failed = conn.execute(
                    "SELECT COUNT(*) FROM memories WHERE outcome = 'failed'"
                ).fetchone()[0]
                
                # 按任务类型统计
                type_stats = conn.execute(
                    """
                    SELECT task_type, COUNT(*) as cnt,
                           SUM(CASE WHEN outcome = 'success' THEN 1 ELSE 0 END) as success_cnt
                    FROM memories
                    GROUP BY task_type
                    ORDER BY cnt DESC
                    """
                ).fetchall()
                
                return {
                    'total': total,
                    'success': success,
                    'failed': failed,
                    'by_type': [
                        {'type': row[0], 'count': row[1], 'success': row[2]}
                        for row in type_stats
                    ]
                }
        except Exception as e:
            logger.error(f"Failed to get statistics: {e}")
            return {'total': 0, 'success': 0, 'failed': 0, 'by_type': []}

    def cleanup_expired(self) -> int:
        """清理过期记忆"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    "DELETE FROM memories WHERE expires_at < CURRENT_TIMESTAMP"
                )
                deleted = cursor.rowcount
                if deleted > 0:
                    logger.info(f"Cleaned up {deleted} expired memories")
                return deleted
        except Exception as e:
            logger.error(f"Failed to cleanup: {e}")
            return 0

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
        """将Row对象转换为字典"""
        result = dict(row)
        # 解析JSON字段
        for json_field in ['template', 'patterns', 'metrics', 'tags']:
            if result.get(json_field):
                try:
                    result[json_field] = json.loads(result[json_field])
                except (json.JSONDecodeError, TypeError):
                    pass
        return result
