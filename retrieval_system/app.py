import os
from flask import Flask, render_template, send_file, request, jsonify
from pathlib import Path
import zipfile
import tempfile


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

# 在配置中使用
DATA_ROOT = auto_get_data_path()
app = Flask(__name__)

def validate_path(path):
    """防止目录遍历攻击"""
    try:
        full_path = (DATA_ROOT / path).resolve()
        if DATA_ROOT not in full_path.parents:
            return None
        return full_path
    except:
        return None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/search')
def handle_search():
    keyword = request.args.get('q', '').lower()
    results = []
    
    for game_dir in DATA_ROOT.iterdir():
        if not game_dir.is_dir():
            continue
            
        # 匹配文件夹
        if keyword in game_dir.name.lower():
            results.append({
                'type': 'folder',
                'name': game_dir.name,
                'path': game_dir.name
            })
        
        # 匹配文件
        for file in game_dir.iterdir():
            if keyword in file.name.lower():
                results.append({
                    'type': 'file',
                    'name': file.name,
                    'path': f"{game_dir.name}/{file.name}"
                })
    return jsonify(results)

@app.route('/api/preview')
def handle_preview():
    from charset_normalizer import detect  # 延迟导入优化性能

    file_path = request.args.get('path', '')
    full_path = validate_path(file_path)
    
    if not full_path or not full_path.is_file():
        return jsonify({'error': '文件不存在'}), 404
    
    try:
        with open(full_path, 'rb') as f:
            raw_content = f.read(2048*2048)
            
            # 自动检测编码
            detected = detect(raw_content)
            encoding = detected['encoding'] or 'utf-8'
            
            try:
                content = raw_content.decode(encoding)
            except UnicodeDecodeError:
                content = raw_content.decode(encoding, errors='replace')
                
            return jsonify({'content': content})
    
    except Exception as e:
        app.logger.error(f"解码失败: {str(e)}")
        return jsonify({'error': '文件编码异常'}), 500

@app.route('/download/<path:filepath>')
def handle_download(filepath):
    full_path = validate_path(filepath)
    
    if not full_path:
        return "Invalid path", 400
    
    if full_path.is_dir():
        # 打包文件夹
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
        try:
            with zipfile.ZipFile(temp_file, 'w') as zipf:
                for root, _, files in os.walk(full_path):
                    for file in files:
                        file_path = Path(root) / file
                        zipf.write(file_path, file_path.relative_to(full_path.parent))
            return send_file(temp_file.name, as_attachment=True,
                           download_name=f"{full_path.name}.zip")
        finally:
            temp_file.close()
    elif full_path.is_file():
        return send_file(full_path, as_attachment=True)
    else:
        return "Not found", 404

if __name__ == '__main__':
    app.run(port=5050, debug=False)