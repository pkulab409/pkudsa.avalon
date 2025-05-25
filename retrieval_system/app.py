import os
import atexit
import zipfile
import tempfile
import time
from flask import Flask, render_template, send_file, request, jsonify
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


# 动态路径
def auto_get_data_path():
    # 获取当前文件所在目录的父级目录
    current_dir = Path(__file__).resolve()
    # print(f"当前目录: {current_dir}")
    # 向上回退到 pkudsa.avalon
    project_root = current_dir.parent.parent
    # 组合生成数据目录路径
    data_path = project_root / "data"

    # 增加安全性验证
    if not data_path.exists():
        raise ValueError(f"数据目录不存在：{data_path}")

    return data_path


def validate_path(path):
    """防止目录遍历攻击"""
    try:
        full_path = (DATA_ROOT / path).resolve()
        if DATA_ROOT not in full_path.parents:
            return None
        return full_path
    except:
        return None


class DataScanner:
    _last_scan = 0
    _cache = None
    CACHE_TTL = 300

    @classmethod
    def get_stats(cls, force_refresh=False):
        if (
            force_refresh
            or not cls._cache
            or (time.time() - cls._last_scan) > cls.CACHE_TTL
        ):
            folder_count = 0
            file_count = 0
            total_size = 0

            for entry in DATA_ROOT.iterdir():
                # 跳过符号链接
                if entry.is_symlink():
                    continue

                if entry.is_file():
                    file_count += 1
                    total_size += entry.stat().st_size
                elif entry.is_dir():
                    folder_count += 1
                    # 递归处理子目录
                    for sub_entry in entry.rglob("*"):
                        if sub_entry.is_symlink():
                            continue
                        if sub_entry.is_file():
                            file_count += 1
                            total_size += sub_entry.stat().st_size

            cls._cache = {
                "folders": folder_count,
                "files": file_count,
                "total_size_mb": round(total_size / 1024 / 1024, 2),
            }
            cls._last_scan = time.time()
        return cls._cache


class FileChangeHandler(FileSystemEventHandler):
    def on_any_event(self, event):
        """文件系统事件处理器"""
        # 只响应特定事件类型
        if event.event_type in ("created", "deleted", "modified"):
            app.logger.info(f"文件变更检测: {event.src_path}")
            DataScanner.get_stats(force_refresh=True)


DATA_ROOT = auto_get_data_path()
app = Flask(__name__)


def init_file_watcher():
    """初始化文件监控"""
    global observer
    observer = Observer()
    event_handler = FileChangeHandler()

    try:
        observer.schedule(
            event_handler, path=str(DATA_ROOT), recursive=True  # 监控子目录
        )
        observer.start()
        app.logger.info("文件监控服务已启动")
    except Exception as e:
        app.logger.error(f"监控初始化失败: {str(e)}")


@app.route("/api/stats")
def get_system_stats():
    # 获取强制刷新参数
    force_refresh = request.args.get("force", "0") == "1"
    return jsonify(DataScanner.get_stats(force_refresh=force_refresh))


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/search")
def handle_search():
    keyword = request.args.get("q", "").lower()
    results = []

    for game_dir in DATA_ROOT.iterdir():
        if not game_dir.is_dir():
            continue

        # 匹配文件夹
        if keyword in game_dir.name.lower():
            results.append(
                {"type": "folder", "name": game_dir.name, "path": game_dir.name}
            )

        # 匹配文件
        for file in game_dir.iterdir():
            if keyword in file.name.lower():
                results.append(
                    {
                        "type": "file",
                        "name": file.name,
                        "path": f"{game_dir.name}/{file.name}",
                    }
                )
    return jsonify(results)


@app.route("/api/preview")
def handle_preview():
    from charset_normalizer import detect  # 延迟导入优化性能

    file_path = request.args.get("path", "")
    full_path = validate_path(file_path)

    if not full_path or not full_path.is_file():
        return jsonify({"error": "文件不存在"}), 404

    try:
        with open(full_path, "rb") as f:
            raw_content = f.read(2048 * 2048)

            # 自动检测编码
            detected = detect(raw_content)
            encoding = detected["encoding"] or "utf-8"

            try:
                content = raw_content.decode(encoding)
            except UnicodeDecodeError:
                content = raw_content.decode(encoding, errors="replace")

            return jsonify({"content": content})

    except Exception as e:
        app.logger.error(f"解码失败: {str(e)}")
        return jsonify({"error": "文件编码异常"}), 500


@app.route("/download/<path:filepath>")
def handle_download(filepath):
    full_path = validate_path(filepath)

    if not full_path:
        return "Invalid path", 400

    if full_path.is_dir():
        # 打包文件夹
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
        try:
            with zipfile.ZipFile(temp_file, "w") as zipf:
                for root, _, files in os.walk(full_path):
                    for file in files:
                        file_path = Path(root) / file
                        zipf.write(file_path, file_path.relative_to(full_path.parent))
            return send_file(
                temp_file.name,
                as_attachment=True,
                download_name=f"{full_path.name}.zip",
            )
        finally:
            temp_file.close()
    elif full_path.is_file():
        return send_file(full_path, as_attachment=True)
    else:
        return "Not found", 404


if __name__ == "__main__":
    # 启动文件监控
    init_file_watcher()
    # 注册退出清理
    atexit.register(lambda: observer.stop() and observer.join())
    app.run(port=5050, debug=True)
