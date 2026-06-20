import sqlite3
import re
from collections import Counter
from email.utils import parseaddr

import pandas as pd
from sklearn.cluster import MiniBatchKMeans
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.feature_extraction import text as sklearn_text

from gmail_cleaner.config import DB_FILE, AUTO_DELETE_EMAIL_PATTERNS, PROTECTED_EMAIL_PATTERNS


def matches_pattern(email, patterns):
    email = (email or "").lower()
    for pattern in patterns:
        pattern = pattern.lower()
        if pattern.startswith("@"):
            domain = pattern[1:]
            if email.endswith("@" + domain) or email.endswith("." + domain):
                return True
        elif email == pattern:
            return True
    return False


def extract_email(sender):
    return parseaddr(sender or "")[1].lower()


def extract_domain(sender):
    email = extract_email(sender)
    if "@" not in email:
        return "(unknown)"
    return email.split("@", 1)[1].lower()


def canonical_email(sender):
    email = extract_email(sender)
    return email.lower() if email else ""


def matches_auto_delete(email):
    return matches_pattern(email, AUTO_DELETE_EMAIL_PATTERNS)


def matches_protected(email):
    return matches_pattern(email, PROTECTED_EMAIL_PATTERNS)


def load_data():
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql(
        """
        SELECT id, sender, subject, internal_date, snippet, body_text, deleted
        FROM gmail_messages
        WHERE COALESCE(deleted, 0) = 0
        """,
        conn,
    )
    conn.close()

    df["email"] = df["sender"].fillna("").apply(canonical_email)
    df = df[~df["email"].apply(matches_protected)]
    df["domain"] = df["sender"].fillna("").apply(extract_domain)

    return df


def run_analysis():
    df = load_data()

    print("\n" + "=" * 100)
    print(f"EMAILS: {len(df):,}")
    print("=" * 100)

    # --------------------------------------------------
    # TOP DOMAINS
    # --------------------------------------------------
    print("\nTOP DOMAINS")
    print("-" * 100)
    for domain, count in df["domain"].value_counts().head(50).items():
        print(f"{count:8,d}  {domain}")

    # --------------------------------------------------
    # TOP SENDERS
    # --------------------------------------------------
    print("\nTOP SENDERS")
    print("-" * 100)
    for sender, count in df["email"].value_counts().head(100).items():
        print(f"{count:8,d}  {sender}")

    # --------------------------------------------------
    # SUBJECT WORD ANALYSIS
    # --------------------------------------------------
    subject_words = []
    for subject in df["subject"].fillna(""):
        tokens = re.findall(r"[a-zA-Z]{4,}", subject.lower())
        subject_words.extend(tokens)

    print("\nTOP SUBJECT WORDS")
    print("-" * 100)
    for word, count in Counter(subject_words).most_common(50):
        print(f"{count:8,d}  {word}")

    # --------------------------------------------------
    # TF-IDF TOPICS
    # --------------------------------------------------
    print("\nTOPIC CLUSTERS")
    print("-" * 100)
    documents = df["subject"].fillna("") + " " + df["snippet"].fillna("")
    vectorizer = TfidfVectorizer(
        stop_words="english", max_features=5000, min_df=5)

    if len(documents) > 0:
        X = vectorizer.fit_transform(documents)
        cluster_count = min(20, max(2, len(df) // 100))
        model = MiniBatchKMeans(n_clusters=cluster_count,
                                random_state=42, batch_size=2048)
        model.fit(X)
        terms = vectorizer.get_feature_names_out()

        for cluster_id in range(cluster_count):
            center = model.cluster_centers_[cluster_id]
            top_indices = center.argsort()[-12:][::-1]
            keywords = [terms[i] for i in top_indices]
            size = (model.labels_ == cluster_id).sum()
            print(f"\nCluster {cluster_id + 1} ({size:,} emails)")
            print(", ".join(keywords))

    print("\nDone.")
