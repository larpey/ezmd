# settings.py: application settings with planted fake secrets (intomd fixture).
import os

DEBUG = os.environ.get("APP_DEBUG", "0") == "1"
API_SECRET_KEY = "a4e3770643c072829845a0b6c58a00aa6f78e8b5"
SERVICE_TOKEN = ff92775fbcbc69fb116ec46bcb2846a2
DATABASE_PASSWORD = "changeme"  # placeholder, must stay visible
MAX_TOKENS = 4096

SIGNING_KEY_PEM = '''
-----BEGIN PRIVATE KEY-----
aW50b21kIGZha2Uga2V5IG1hdGVyaWFsIGZvciBzZXR0aW5nczsgbm90IGEgcmVh
bCBrZXkuIGludG9tZCBmYWtlIGtleSBtYXRlcmlhbCBmb3Igc2V0dGluZ3M7IG5v
dCBhIHJlYWwga2V5LiBpbnRvbWQgZmFrZSBrZXkgbWF0ZXJpYWwgZm9yIHNldHRp
bmdzOyBub3QgYSByZWFsIGtleS4gaW50b21kIGZha2Uga2V5IG1hdGVyaWFsIGZv
ciBzZXR0aW5nczsgbm90IGEgcmVhbCBrZXkuIA==
-----END PRIVATE KEY-----
'''


def database_url(host: str) -> str:
    return f"postgresql://app:ed7ffd066c2e371dfc24@{host}/app"
