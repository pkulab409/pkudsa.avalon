# commit 之前 ./reformat.bat
cd ..
# 运行格式化
black .
djlint . --reformat --profile=jinja
