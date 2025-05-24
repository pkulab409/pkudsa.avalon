# 直接运行即可
import os
import re
import shutil


def debug_print(*args):
    """启用调试信息打印"""
    print("[DEBUG]", *args)


def process_files(data_dir="../data"):
    """处理文件，将文件移动到指定目录并重命名"""

    # 设置相对路径
    script_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.normpath(os.path.join(script_dir, data_dir))

    if not os.path.exists(data_dir):
        print(f"错误：数据目录不存在 {data_dir}")
        return

    print(f"正在处理目录：{data_dir}")  # 设置跨平台的相对路径

    processed_files = 0
    error_files = []

    for filename in os.listdir(data_dir):
        file_path = os.path.join(data_dir, filename)

        # 跳过目录（保留原始目录结构）
        if os.path.isdir(file_path):
            debug_print(f"跳过目录：{filename}")
            continue

        debug_print("\n处理文件：", filename)

        # 匹配所有类型的文件格式
        match = re.match(
            r"game_([^_]+)_(public|archive|player_\d+_private)\.json", filename
        )
        if not match:
            error_files.append(filename)
            debug_print("不匹配的文件格式")
            continue

        game_id = match.group(1)
        file_type = match.group(2)
        debug_print(f"提取参数 | ID: {game_id} | 类型: {file_type}")

        # 构建新文件名
        if file_type == "public":
            new_name = f"public_game_{game_id}.json"
        elif file_type == "archive":
            new_name = f"archive_game_{game_id}.json"
        elif "player_" in file_type:
            player_num = file_type.split("_")[1]
            new_name = f"private_player_{player_num}_game_{game_id}.json"
        else:
            error_files.append(filename)
            continue

        # 移动文件
        try:
            target_dir = os.path.join(data_dir, game_id)
            os.makedirs(target_dir, exist_ok=True)
            new_path = os.path.join(target_dir, new_name)

            debug_print(f"移动操作：{file_path} -> {new_path}")
            shutil.move(file_path, new_path)
            processed_files += 1
        except Exception as e:
            error_files.append(filename)
            debug_print(f"移动失败：{str(e)}")

    # 输出执行报告
    print("\n执行结果：")
    print(f"成功处理文件数: {processed_files}")
    print(f"未处理文件数: {len(error_files)}")
    if error_files:
        print("\n以下文件未能处理：")
        for f in error_files:
            print(f" - {f}")


if __name__ == "__main__":
    print("=== 开始处理文件 ===")
    process_files()
    print("=== 处理完成 ===")
