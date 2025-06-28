libs\python\python.exe -m pip install docopt-ng --no-cache-dir
libs\python\python.exe -m pip install python-chess --no-deps --no-cache-dir
libs\python\python.exe -m pip install -r requirements.txt --no-cache-dir
libs\python\python.exe libs\python\Scripts\pywin32_postinstall.py -install
pause