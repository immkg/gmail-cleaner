import pytest
import sqlite3
import pandas as pd
from unittest.mock import patch

# Setup synthetic configurations for tests
@pytest.fixture(autouse=True)
def mock_config(monkeypatch):
    monkeypatch.setattr("gmail_cleaner.analyze.DB_FILE", ":memory:")
    monkeypatch.setattr("gmail_cleaner.delete.DB_FILE", ":memory:")
    monkeypatch.setattr("gmail_cleaner.config.AUTO_DELETE_EMAIL_PATTERNS", ["spam@trash.com", "@junk.com"])
    monkeypatch.setattr("gmail_cleaner.analyze.AUTO_DELETE_EMAIL_PATTERNS", ["spam@trash.com", "@junk.com"])
    
    monkeypatch.setattr("gmail_cleaner.config.PROTECTED_EMAIL_PATTERNS", ["vip@bank.com", "@mywork.com"])
    monkeypatch.setattr("gmail_cleaner.analyze.PROTECTED_EMAIL_PATTERNS", ["vip@bank.com", "@mywork.com"])

@pytest.fixture
def synthetic_df():
    data = [
        # Normal email
        {"id": "msg1", "sender": "friend@gmail.com", "subject": "Lunch?", "snippet": "Hey, lunch tomorrow?", "body_text": "Let me know", "internal_date": 1000},
        # Newsletter
        {"id": "msg2", "sender": "daily@news.com", "subject": "Your daily newsletter", "snippet": "Read more...", "body_text": "Click here to unsubscribe.", "internal_date": 1001},
        # Promotion
        {"id": "msg3", "sender": "marketing@store.com", "subject": "50% Discount on Shoes!", "snippet": "Limited time offer", "body_text": "Big sale today only", "internal_date": 1002},
        # Protected (should normally be filtered by load_data)
        {"id": "msg4", "sender": "alerts@mywork.com", "subject": "Server Down", "snippet": "Urgent", "body_text": "", "internal_date": 1003},
        # Auto Delete
        {"id": "msg5", "sender": "spam@trash.com", "subject": "Win a prize", "snippet": "You won", "body_text": "Click link", "internal_date": 1004},
        # Another from top sender
        {"id": "msg6", "sender": "marketing@store.com", "subject": "Another coupon", "snippet": "Save more", "body_text": "Sale sale sale", "internal_date": 1005},
        # Another newsletter
        {"id": "msg7", "sender": "daily@news.com", "subject": "Weekly digest", "snippet": "More news...", "body_text": "Unsubscribe below.", "internal_date": 1006},
    ]
    df = pd.DataFrame(data)
    from gmail_cleaner.analyze import canonical_email, extract_domain
    df["email"] = df["sender"].apply(canonical_email)
    df["domain"] = df["sender"].apply(extract_domain)
    return df

@pytest.fixture
def mock_db(synthetic_df):
    conn = sqlite3.connect(":memory:")
    synthetic_df.to_sql("gmail_messages", conn, index=False)
    
    # Add 'deleted' column as expected by load_data
    conn.execute("ALTER TABLE gmail_messages ADD COLUMN deleted INTEGER NOT NULL DEFAULT 0")
    
    with patch("sqlite3.connect", return_value=conn):
        yield conn
