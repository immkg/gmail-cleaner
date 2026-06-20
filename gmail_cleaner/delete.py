import re
import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter
from tqdm import tqdm

from gmail_cleaner.config import DB_FILE
from gmail_cleaner.auth import trash_email
from gmail_cleaner.analyze import load_data, matches_auto_delete
from sklearn.feature_extraction import text as sklearn_text
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import MiniBatchKMeans

DELETE_WORKERS = 10
PROMOTION_REGEX = r"sale|offer|discount|coupon|deal|cashback|save|limited time"
NEWSLETTER_REGEX = r"unsubscribe|newsletter|digest|weekly|daily"
DELETE_STRATEGIES = {
    "1": "top_senders",
    "2": "newsletter",
    "3": "promotions",
    "4": "subject_patterns",
    "5": "topic_clusters",
    "6": "auto_delete_matches",
}

pending_delete_ids = []


def normalize_subject(subject):
    if not subject:
        return ""
    subject = subject.lower()
    subject = re.sub(r"\d+", "<num>", subject)
    return re.sub(r"\s+", " ", subject).strip()


def choose_delete_strategy():
    print("\nDELETE STRATEGIES")
    print("-" * 100)
    print("[1] Top Senders")
    print("[2] Newsletters")
    print("[3] Promotions")
    print("[4] Subject Patterns")
    print("[5] Topic Clusters")
    print("[6] Auto Delete Matches")
    print("[q] Quit")
    while True:
        choice = input("\nStrategy: ").strip().lower()
        if choice == "q":
            return None
        if choice in DELETE_STRATEGIES:
            return DELETE_STRATEGIES[choice]
        print("Invalid choice")

# Strategy Builders


def get_top_sender_candidates(df):
    return df["email"].value_counts().head(100).items()


def get_newsletter_candidates(df):
    newsletter_df = df[
        (df["subject"].fillna("").str.contains(NEWSLETTER_REGEX, case=False, regex=True)) |
        (df["body_text"].fillna("").str.contains(
            NEWSLETTER_REGEX, case=False, regex=True))
    ]
    return newsletter_df["email"].value_counts().head(100).items()


def get_promotion_candidates(df):
    promo_df = df[
        (df["subject"].fillna("").str.contains(PROMOTION_REGEX, case=False, regex=True)) |
        (df["snippet"].fillna("").str.contains(
            PROMOTION_REGEX, case=False, regex=True))
    ]
    return promo_df["email"].value_counts().head(100).items()


def get_subject_pattern_candidates(df):
    patterns = Counter()
    for subject in df["subject"].fillna(""):
        patterns[normalize_subject(subject)] += 1
    return patterns.most_common(100)


def get_cluster_candidates(df):
    CUSTOM_STOPWORDS = {"email", "dear", "thank", "thanks",
                        "hi", "hello", "com", "www", "http", "https"}
    documents = df["subject"].fillna("")
    stop_words = sklearn_text.ENGLISH_STOP_WORDS.union(CUSTOM_STOPWORDS)
    vectorizer = TfidfVectorizer(stop_words=list(
        stop_words), max_features=10000, min_df=3, ngram_range=(1, 2))

    if len(documents) == 0:
        return []

    X = vectorizer.fit_transform(documents)
    cluster_count = min(100, max(20, len(df) // 20))
    model = MiniBatchKMeans(n_clusters=cluster_count,
                            random_state=42, batch_size=2048)
    model.fit(X)
    terms = vectorizer.get_feature_names_out()

    clusters = []
    for cluster_id in range(cluster_count):
        center = model.cluster_centers_[cluster_id]
        top_indices = center.argsort()[-5:][::-1]
        keywords = ", ".join(terms[i] for i in top_indices)
        size = (model.labels_ == cluster_id).sum()
        clusters.append((cluster_id, size, keywords, model.labels_))
    return clusters


def get_auto_delete_candidates(df):
    auto_df = df[df["email"].apply(matches_auto_delete)]
    return auto_df["email"].value_counts().items()

# Selection Parsing


def parse_selection(selection, max_index):
    indexes = set()
    for part in selection.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            if "-" in part:
                start, end = part.split("-", 1)
                if not start or not end:
                    continue
                for i in range(int(start), int(end) + 1):
                    if 1 <= i <= max_index:
                        indexes.add(i - 1)
            else:
                value = int(part)
                if 1 <= value <= max_index:
                    indexes.add(value - 1)
        except ValueError:
            pass
    return indexes


def build_pattern_deletes(sender_df, candidates, selection):
    if selection == "q":
        raise KeyboardInterrupt()
    if selection == "d":
        return []
    if selection.startswith("k") or selection == "p":
        keep = int(selection[1:] or "0")
        sender_df = sender_df.sort_values("internal_date", ascending=False)
        return sender_df.iloc[keep:]["id"].dropna().tolist()

    try:
        indexes = parse_selection(selection, len(candidates))
    except Exception:
        print("Invalid selection")
        return []

    delete_patterns = [candidates[idx][0] for idx in indexes]
    delete_ids = []
    for _, row in sender_df.iterrows():
        subject = normalize_subject(row["subject"])
        if subject in delete_patterns:
            delete_ids.append(row["id"])
    return delete_ids

# Handlers


def handle_sender(sender, sender_count, df):
    sender_df = df[df["email"] == sender]
    patterns = Counter()
    for subject in sender_df["subject"].fillna(""):
        patterns[normalize_subject(subject)] += 1
    candidates = list(patterns.most_common(20))

    print(f"\n{sender} ({sender_count:,})")
    for i, (pattern, count) in enumerate(candidates, start=1):
        print(f"[{i}] {count:,} {pattern[:120]}")

    selection = input("\nChoice: ").strip()
    return build_pattern_deletes(sender_df, candidates, selection)


def handle_newsletter(sender, sender_count, df):
    sender_df = df[df["email"] == sender]
    print(f"\nNEWSLETTER: {sender}\nEmails: {sender_count:,}")
    latest = sender_df.sort_values("internal_date", ascending=False).head(10)
    for _, row in latest.iterrows():
        print(row["subject"][:120])
    choice = input("\nDelete all? [y/N]: ")
    if choice.lower() != 'y':
        return []
    return sender_df["id"].tolist()


def handle_promotion(sender, sender_count, df):
    sender_df = df[df["email"] == sender]
    score = sender_df["subject"].fillna("").str.contains(
        PROMOTION_REGEX, case=False, regex=True).mean()
    print(f"\n{sender}\nEmails : {sender_count:,}\nPromo Score: {score:.2f}")
    choice = input("\nDelete all? [y/N]: ")
    if choice.lower() != 'y':
        return []
    return sender_df["id"].tolist()


def handle_subject_pattern(pattern, count, df):
    print(f"\nPATTERN\n{count:,} emails\n{pattern}")
    samples = df[df["subject"].fillna("").apply(
        normalize_subject) == pattern]["subject"].head(10)
    print("\nSamples")
    for s in samples:
        print(f"  - {s}")
    choice = input("\nDelete all? [y/N]: ")
    if choice.lower() != 'y':
        return []
    return df[df["subject"].fillna("").apply(normalize_subject) == pattern]["id"].tolist()


def handle_cluster(cluster_id, size, keywords, labels, df):
    print(
        f"\nCLUSTER {cluster_id + 1}\nEmails: {size:,}\nKeywords: {keywords}")
    choice = input("\nDelete cluster? [y/N]: ")
    if choice.lower() != 'y':
        return []
    return df[labels == cluster_id]["id"].tolist()


def handle_auto_delete(sender, sender_count, df):
    sender_df = df[df["email"] == sender]
    print(f"\nAUTO RULE MATCH\n{sender}\n{sender_count:,} emails")
    latest = sender_df["subject"].dropna().head(10)
    for s in latest:
        print(f"  - {s}")
    choice = input("\nDelete all? [Y/n]: ")
    if choice.lower() == 'n':
        return []
    return sender_df["id"].tolist()


def delete_gmail(ids, dry_run=False):
    ids_to_delete = list(set(ids))
    if not ids_to_delete:
        return []

    print(f"\nFinal delete pass: {len(ids_to_delete):,} emails")
    if dry_run:
        print("[DRY RUN] Would delete the following IDs:")
        for gid in ids_to_delete:
            print(f"  - {gid}")
        return []

    success = 0
    failed = 0
    successful_ids = []

    with ThreadPoolExecutor(max_workers=DELETE_WORKERS) as executor:
        future_to_id = {executor.submit(
            trash_email, gid): gid for gid in ids_to_delete}
        for future in tqdm(as_completed(future_to_id), total=len(future_to_id), desc="Deleting"):
            gmail_id = future_to_id[future]
            if future.result() is True:
                success += 1
                successful_ids.append(gmail_id)
            else:
                failed += 1

    if successful_ids:
        db_conn = sqlite3.connect(DB_FILE)
        db_conn.executemany("UPDATE gmail_messages SET deleted = 1 WHERE id = ?", [
                            (gid,) for gid in successful_ids])
        db_conn.commit()
        db_conn.close()

    print(f"\nDeleted: {success:,}")
    print(f"Failed : {failed:,}")
    return [x for x in ids_to_delete if x not in successful_ids]


def handle_delete(delete_ids, skip=False, dry_run=False):
    global pending_delete_ids
    pending_delete_ids.extend(delete_ids)
    print(f"\nPending delete queue: {len(pending_delete_ids):,} emails")

    if not skip:
        action = input("\n[yes | now | exit] : ").strip().lower()
        if action == "" or action == "yes" or action == "y":
            return
        if action == "exit":
            return "exit"
        if action == "now":
            pending_delete_ids = delete_gmail(
                pending_delete_ids, dry_run=dry_run)


def run_delete_flow(dry_run=False):
    global pending_delete_ids
    df = load_data()
    strategy = choose_delete_strategy()
    if not strategy:
        return

    try:
        if strategy == "top_senders":
            for sender, count in get_top_sender_candidates(df):
                ids = handle_sender(sender, count, df)
                if handle_delete(ids, True, dry_run=dry_run) == "exit":
                    break
        elif strategy == "newsletter":
            for sender, count in get_newsletter_candidates(df):
                ids = handle_newsletter(sender, count, df)
                if handle_delete(ids, dry_run=dry_run) == "exit":
                    break
        elif strategy == "promotions":
            for sender, count in get_promotion_candidates(df):
                ids = handle_promotion(sender, count, df)
                if handle_delete(ids, dry_run=dry_run) == "exit":
                    break
        elif strategy == "subject_patterns":
            for pattern, count in get_subject_pattern_candidates(df):
                ids = handle_subject_pattern(pattern, count, df)
                if handle_delete(ids, dry_run=dry_run) == "exit":
                    break
        elif strategy == "topic_clusters":
            for cluster_id, size, keywords, labels in get_cluster_candidates(df):
                ids = handle_cluster(cluster_id, size, keywords, labels, df)
                if handle_delete(ids, dry_run=dry_run) == "exit":
                    break
        elif strategy == "auto_delete_matches":
            for sender, count in get_auto_delete_candidates(df):
                ids = handle_auto_delete(sender, count, df)
                if handle_delete(ids, dry_run=dry_run) == "exit":
                    break
    except KeyboardInterrupt:
        print("\nExiting interactive loop.")

    if pending_delete_ids:
        delete_gmail(pending_delete_ids, dry_run=dry_run)
