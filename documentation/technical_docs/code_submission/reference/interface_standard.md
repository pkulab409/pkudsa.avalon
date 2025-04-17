# 前端上传区设计 & FastAPI后端接口定义

## 前端上传区设计
### 草图说明

- **输入字段**：
    
    - 上传框：选择 .zip 文件
        
    - 队伍名称：文本框，自动填充为zip 文件中间名
        
    - 提交按钮：上传文件并提交至服务器
        
    
- **UI 设计**：
	
	- 进度条（如有必要）
        
    - 提交反馈：上传成功或上传失败（格式错误、文件损坏等）
        
    
---

## FastAPI 后端接口设计

### 上传接口

- **接口**：POST /api/upload_ai/

- **请求体**：
	
	- file: 上传的 .zip 文件
		
	- team_name: 队伍名称，确保与文件夹名一致
		
	- token: 用于身份验证（可选）
		
	
- **处理流程**：
	
	- 接收到文件后存储于临时目录
		
	- 解压文件并校验文件夹结构，标准文件结构见[README](README.md)
		
	- 提交反馈给前端，若成功则进行后续对局模拟等操作
		
	
### 示例代码（FastAPI 后端处理）

```python
from fastapi import FastAPI, File, UploadFile, Form
import zipfile
import os
from io import BytesIO

app = FastAPI()

@app.post("/api/upload_ai/")
async def upload_ai(file: UploadFile = File(...), team_name: str = Form(...)):
    # 保存上传的文件
    file_location = f"uploads/{team_name}.zip"
    with open(file_location, "wb") as f:
        f.write(await file.read())

    # 解压 zip 文件
    try:
        with zipfile.ZipFile(file_location, 'r') as zip_ref:
            zip_ref.extractall(f"ai_submissions/{team_name}")
            # 校验文件结构
            if not os.path.exists(f"ai_submissions/{team_name}/strategy.py") or not os.path.exists(f"ai_submissions/{team_name}/__init__.py"):
                raise ValueError("Invalid structure")
    except Exception as e:
        return {"error": str(e)}

    # 返回成功消息
    return {"message": "AI submitted successfully!"}
```