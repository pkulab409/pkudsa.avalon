import sqlite3
import os

# 数据库文件名
DB_FILE = "platform.db"


def migrate(conn):
    """
    在 users 表中添加 partition 列
    """
    print("Applying migration.")
    cursor = conn.cursor()
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN partition INTEGER;")
        conn.commit()
        print("Column 'partition' added to users table.")
    except sqlite3.OperationalError as e:
        # 常见错误：列已存在。对于简单脚本，可以忽略或记录。
        # 更复杂的迁移工具会有更完善的错误处理和检查机制。
        if "duplicate column name" in str(e).lower():
            print("Column 'partition' already exists in users table. Skipping.")
        else:
            raise e  # 其他错误则抛出


# 将所有迁移函数按顺序放入列表
MIGRATIONS = [migrate]


def get_current_version(conn):
    """获取当前数据库版本"""
    cursor = conn.cursor()
    try:
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL UNIQUE);"
        )
        # 尝试插入初始版本号0，如果表已存在且有记录，则会失败，这是预期的
        try:
            cursor.execute("INSERT INTO schema_version (version) VALUES (0);")
            conn.commit()
        except sqlite3.IntegrityError:  # 通常是因为版本0已存在
            pass  # 表已存在且有版本号，或0已存在

        cursor.execute("SELECT MAX(version) FROM schema_version;")
        row = cursor.fetchone()
        if row and row[0] is not None:
            return row[0]
        return 0  # 如果表中没有记录，则认为是版本0
    except sqlite3.Error as e:
        print(f"Error accessing schema_version table: {e}")
        return 0  # 出错时，假设是初始状态


def set_version(conn, version):
    """设置数据库版本"""
    cursor = conn.cursor()
    # 使用 REPLACE INTO 来确保版本号被更新或插入
    cursor.execute("REPLACE INTO schema_version (version) VALUES (?);", (version,))
    conn.commit()
    print(f"Database schema version set to {version}.")


def run_migrations():
    """执行数据库迁移"""
    # 检查数据库文件是否存在，如果不存在，sqlite3.connect 会创建它
    db_exists = os.path.exists(DB_FILE)
    if not db_exists:
        print(f"Database file '{DB_FILE}' not found, will be created.")

    conn = None
    try:
        conn = sqlite3.connect(DB_FILE)
        print(f"Connected to database: {DB_FILE}")

        current_version = get_current_version(conn)
        print(f"Current database schema version: {current_version}")

        target_version = len(MIGRATIONS)  # 目标版本是已定义的迁移数量

        if current_version < target_version:
            print(
                f"Need to apply migrations from version {current_version + 1} to {target_version}."
            )
            for i in range(current_version, target_version):
                migration_function = MIGRATIONS[i]
                new_version = i + 1
                print(f"\n--- Running migration for version {new_version} ---")
                migration_function(conn)
                set_version(conn, new_version)
                print(
                    f"--- Migration for version {new_version} applied successfully ---"
                )
            print("\nAll pending migrations applied.")
        else:
            print("Database schema is up to date.")

    except sqlite3.Error as e:
        print(f"An error occurred during migration: {e}")
        if conn:
            conn.rollback()  # 如果发生错误，回滚事务
    finally:
        if conn:
            conn.close()
            print("Database connection closed.")


if __name__ == "__main__":
    run_migrations()
