# gShared

SETUP

Python 2.7, python pip and ffmpeg are required

config File 
config.py
```python
#!/usr/bin/env python
acrcloud_config = {
            'host': '',
            'access_key': '',
            'access_secret': '',
            'timeout': 10  # seconds
        }  # ACRCloud API Keys
firebase_api = "" # firebase Cloud Messaging Key

logLocation = '' # Location of log file
tokenLocation = 'token.json' # Location of APP Firebase Instance Token (used for Push notification)


library = '{"libraries": [{"name":"Library name", "location":"/path"}, {"name":"Library name", "location":"/path"}]}'
```

Install

```python
pip install -r requirements.txt
python setup.py install
```



