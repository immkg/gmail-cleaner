# config.py

DB_FILE = "gmail.db"
CREDS_FILE = "credentials.json"
TOKEN_FILE = "token.json"

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify"
]

MAX_WORKERS = 20
MAX_RETRIES = 8
COMMIT_BATCH = 100

# --------------------------------------------------
# CONFIGURABLE PATTERNS
# --------------------------------------------------
# Add email addresses or domains you want to automatically categorize for deletion here.
# Example: "newsletter@example.com", "@spamdomain.com"
AUTO_DELETE_EMAIL_PATTERNS = [
    # Add your auto delete patterns here
]

# Add email addresses or domains you want to protect from accidental deletion.
# Example: "personal@gmail.com", "@mybank.com"
PROTECTED_EMAIL_PATTERNS = [
    # Add your protected email patterns here
]
