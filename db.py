import sqlite3
import datetime
import random
from config import DB_PATH, MIN_DAILY_REPLIES, MAX_DAILY_REPLIES

def get_connection():
    """Returns a connection to the SQLite database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initializes database tables if they do not exist."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Table to track processed tweets and our replies
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS processed_tweets (
            tweet_id TEXT PRIMARY KEY,
            tweet_url TEXT NOT NULL,
            tweet_text TEXT,
            reply_posted TEXT,
            tweet_views INTEGER,
            reply_views INTEGER,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Table to track daily limits and reply caps
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS daily_stats (
            date TEXT PRIMARY KEY,
            reply_cap INTEGER NOT NULL,
            replies_sent INTEGER DEFAULT 0
        )
    """)
    
    conn.commit()
    conn.close()

def has_replied(tweet_id: str) -> bool:
    """Checks if a tweet has already been replied to."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM processed_tweets WHERE tweet_id = ?", (tweet_id,))
    res = cursor.fetchone()
    conn.close()
    return res is not None

def save_reply(tweet_id: str, tweet_url: str, tweet_text: str, reply_posted: str, tweet_views: int, reply_views: int):
    """Saves a reply transaction details into database."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT OR REPLACE INTO processed_tweets (tweet_id, tweet_url, tweet_text, reply_posted, tweet_views, reply_views)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (tweet_id, tweet_url, tweet_text, reply_posted, tweet_views, reply_views))
        conn.commit()
    except Exception as e:
        print(f"[DB ERROR] Failed to save reply: {e}")
    finally:
        conn.close()

def get_or_create_daily_cap(date_str: str) -> int:
    """Gets or randomly initializes a daily cap (min 60, max 70) for the given date string."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT reply_cap FROM daily_stats WHERE date = ?", (date_str,))
    row = cursor.fetchone()
    
    if row:
        cap = row["reply_cap"]
    else:
        # Create a new randomized daily cap
        cap = random.randint(MIN_DAILY_REPLIES, MAX_DAILY_REPLIES)
        try:
            cursor.execute("""
                INSERT OR IGNORE INTO daily_stats (date, reply_cap, replies_sent)
                VALUES (?, ?, 0)
            """, (date_str, cap))
            conn.commit()
        except Exception as e:
            print(f"[DB ERROR] Failed to create daily stats row: {e}")
            
    conn.close()
    return cap

def get_replies_sent_today(date_str: str) -> int:
    """Returns number of replies sent for the given date."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT replies_sent FROM daily_stats WHERE date = ?", (date_str,))
    row = cursor.fetchone()
    conn.close()
    return row["replies_sent"] if row else 0

def increment_replies_sent(date_str: str):
    """Increments the daily reply count."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE daily_stats 
            SET replies_sent = replies_sent + 1 
            WHERE date = ?
        """, (date_str,))
        conn.commit()
    except Exception as e:
        print(f"[DB ERROR] Failed to increment replies: {e}")
    finally:
        conn.close()
