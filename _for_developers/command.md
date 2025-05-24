# 给开发者
```cmd
conda activate dsa
bash reformat.sh
python3 startup.py
git clean -fdx # 删除所有未跟踪的文件（包括被忽略的文件）
# 先cd到项目的根目录
djlint . --reformat --profile=jinja # 格式化所有的html模板文件
black . # 格式化所有的python代码
```
