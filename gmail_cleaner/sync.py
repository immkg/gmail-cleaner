import json
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from tqdm import tqdm

from .config import MAX_WORKERS, COMMIT_BATCH
from .db import set_state
from .auth import gmail_call, get_gmail_service


def decode_body(data):
    if not data:
        return ""
    try:
        return base64.urlsafe_b64decode(data.encode("UTF-8")).decode("utf-8", errors="ignore")
    except Exception:
        return ""


def extract_text(payload):
    body = payload.get("body", {}).get("data")
    if body:
        return decode_body(body)

    for part in payload.get("parts", []):
        mime = part.get("mimeType")
        if mime == "text/plain":
            return decode_body(part.get("body", {}).get("data"))

    return ""


def fetch_message(message_id):
    try:
        service = get_gmail_service()
        request = service.users().messages().get(
            userId="me", id=message_id, format="metadata")
        return gmail_call(request)
    except Exception as e:
        print(f"\nFAILED {message_id}: {e}")
        return None


def save_message(conn, msg):
    headers = {h["name"]: h["value"]
               for h in msg["payload"].get("headers", [])}
    body_text = extract_text(msg["payload"])

    conn.execute("""
        INSERT OR REPLACE INTO gmail_messages (
            id, thread_id, history_id, internal_date, label_ids,
            subject, sender, recipients, snippet, body_text, raw_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        msg["id"],
        msg["threadId"],
        int(msg.get("historyId", 0)),
        int(msg.get("internalDate", 0)),
        json.dumps(msg.get("labelIds", [])),
        headers.get("Subject"),
        headers.get("From"),
        headers.get("To"),
        msg.get("snippet"),
        body_text,
        json.dumps(msg)
    ))


def full_sync(conn):
    print("Starting full sync...")
    service = get_gmail_service()
    all_ids = []

    request = service.users().messages().list(userId="me", maxResults=500)
    while request:
        response = gmail_call(request)
        all_ids.extend(response.get("messages", []))
        print(f"\rFound {len(all_ids):,} emails...", end="", flush=True)
        request = service.users().messages().list_next(request, response)

    total = len(all_ids)
    print(f"\nFound {total:,} emails")

    max_history_id = 0
    processed = 0
    BATCH_SIZE = 500

    for batch_start in range(0, total, BATCH_SIZE):
        batch = all_ids[batch_start:batch_start + BATCH_SIZE]
        print(
            f"\nBatch {batch_start:,}-{batch_start + len(batch):,} of {total:,}")

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = [executor.submit(fetch_message, item["id"])
                       for item in batch]
            for future in tqdm(as_completed(futures), total=len(futures), desc="Downloading"):
                try:
                    msg = future.result()
                    if not msg:
                        continue
                    save_message(conn, msg)
                    max_history_id = max(
                        max_history_id, int(msg.get("historyId", 0)))
                    processed += 1
                    if processed % COMMIT_BATCH == 0:
                        conn.commit()
                except Exception as e:
                    print(f"\nWorker error: {e}")

        conn.commit()
        print(f"Saved {processed:,}/{total:,}")

    set_state(conn, "history_id", max_history_id)
    conn.commit()
    print(f"\nFull sync complete ({processed:,})")


def incremental_sync(conn, last_history_id):
    print(f"Incremental sync from history {last_history_id}")
    service = get_gmail_service()
    request = service.users().history().list(
        userId="me", startHistoryId=last_history_id)

    new_ids = []
    newest_history = int(last_history_id)

    while request:
        response = gmail_call(request)
        for item in response.get("history", []):
            newest_history = max(newest_history, int(item["id"]))
            for added in item.get("messagesAdded", []):
                new_ids.append(added["message"]["id"])
        request = service.users().history().list_next(request, response)

    new_ids = list(set(new_ids))

    if not new_ids:
        print("No new emails")
        return

    print(f"Found {len(new_ids):,} new emails")
    lock = Lock()
    processed = 0

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(
            fetch_message, msg_id): msg_id for msg_id in new_ids}
        for future in tqdm(as_completed(futures), total=len(new_ids), desc="Fetching"):
            msg = future.result()
            if msg:
                with lock:
                    save_message(conn, msg)
                    processed += 1
                    if processed % COMMIT_BATCH == 0:
                        conn.commit()

    set_state(conn, "history_id", newest_history)
    conn.commit()
    print(f"Incremental sync complete ({processed:,})")
