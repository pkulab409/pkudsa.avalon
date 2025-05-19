# commit 之前 ./reformat.sh
black .
djlint . --reformat --profile=jinja