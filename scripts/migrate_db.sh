#!/bin/bash
# harness 数据库迁移脚本 - 添加 source 和 result 字段

DB_PATH="/home/ubuntu/ws/harness/webui/harness.db"

echo "🔧 开始迁移 harness 数据库..."

# 检查数据库是否存在
if [ ! -f "$DB_PATH" ]; then
    echo "❌ 数据库文件不存在: $DB_PATH"
    echo "   请先运行 harness WebUI 以创建数据库"
    exit 1
fi

# 检查字段是否已存在
check_column() {
    sqlite3 "$DB_PATH" "PRAGMA table_info(tasks);" | grep -q "$1"
    return $?
}

# 添加 source 字段
if check_column "source"; then
    echo "✅ source 字段已存在"
else
    echo "➕ 添加 source 字段..."
    sqlite3 "$DB_PATH" "ALTER TABLE tasks ADD COLUMN source TEXT DEFAULT 'webui';"
    if [ $? -eq 0 ]; then
        echo "✅ source 字段添加成功"
    else
        echo "❌ source 字段添加失败"
        exit 1
    fi
fi

# 添加 result 字段
if check_column "result"; then
    echo "✅ result 字段已存在"
else
    echo "➕ 添加 result 字段..."
    sqlite3 "$DB_PATH" "ALTER TABLE tasks ADD COLUMN result TEXT DEFAULT '';"
    if [ $? -eq 0 ]; then
        echo "✅ result 字段添加成功"
    else
        echo "❌ result 字段添加失败"
        exit 1
    fi
fi

echo ""
echo "🎉 数据库迁移完成！"
echo ""
echo "当前 tasks 表结构："
sqlite3 "$DB_PATH" "PRAGMA table_info(tasks);"
