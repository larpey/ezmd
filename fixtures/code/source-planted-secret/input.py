# settings.py: application settings with planted fake secrets (ezmd fixture).
import os

DEBUG = os.environ.get("APP_DEBUG", "0") == "1"
API_SECRET_KEY = "ad06f8903f370cf234e586d9381a388ef14dd0fb"
SERVICE_TOKEN = c77c8f7e7cc1d8bf91f4689898ca5138
DATABASE_PASSWORD = "changeme"  # placeholder, must stay visible
MAX_TOKENS = 4096

SIGNING_KEY_PEM = '''
-----BEGIN PRIVATE KEY-----
ZXptZCBmYWtlIGtleSBtYXRlcmlhbCBmb3Igc2V0dGluZ3M7IG5vdCBhIHJlYWwg
a2V5LiBlem1kIGZha2Uga2V5IG1hdGVyaWFsIGZvciBzZXR0aW5nczsgbm90IGEg
cmVhbCBrZXkuIGV6bWQgZmFrZSBrZXkgbWF0ZXJpYWwgZm9yIHNldHRpbmdzOyBu
b3QgYSByZWFsIGtleS4gZXptZCBmYWtlIGtleSBtYXRlcmlhbCBmb3Igc2V0dGlu
Z3M7IG5vdCBhIHJlYWwga2V5LiA=
-----END PRIVATE KEY-----
'''


def database_url(host: str) -> str:
    return f"postgresql://app:a8c0da6ef6257a09614f@{host}/app"
