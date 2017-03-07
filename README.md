# gShared

SETUP

Python 2.7 and python pip is required

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
location = '' # Storing location of music (music folder)
tokenLocation = 'token.json' # Location of APP Firebase Instance Token (used for Push notification)´´´

´´´python
pip install -r requirements.txt
python setup.py install
´´´


