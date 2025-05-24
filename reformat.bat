# commit 之前 ./reformat.bat
black .
djlint . --reformat --profile=jinja