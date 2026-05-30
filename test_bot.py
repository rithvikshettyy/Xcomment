import pytest
from db import init_db, has_replied, save_reply, get_or_create_daily_cap, get_replies_sent_today, increment_replies_sent, get_connection
from browser import parse_x_number
from replier import safety_check

def test_parse_x_number():
    assert parse_x_number("700K") == 700000
    assert parse_x_number("1.2M") == 1200000
    assert parse_x_number("5,400") == 5400
    assert parse_x_number("5.4K") == 5400
    assert parse_x_number("0") == 0
    assert parse_x_number("") == 0
    assert parse_x_number("abc") == 0

def test_db_operations():
    # Initialize in-memory or default DB
    init_db()
    
    # Clean up test records
    conn = get_connection()
    conn.execute("DELETE FROM processed_tweets WHERE tweet_id = ?", ("fake_id_123",))
    conn.commit()
    conn.close()
    
    # Test checking non-existent
    assert not has_replied("fake_id_123")
    
    # Save reply and check
    save_reply("fake_id_123", "https://x.com/status/123", "Orig text", "My reply", 800000, 6000)
    assert has_replied("fake_id_123")
    
    # Test daily cap values
    date_str = "2026-05-30"
    cap = get_or_create_daily_cap(date_str)
    assert 60 <= cap <= 70
    
    # Increment replies
    initial = get_replies_sent_today(date_str)
    increment_replies_sent(date_str)
    assert get_replies_sent_today(date_str) == initial + 1

def test_safety_check():
    assert safety_check("Interesting perspective!", "This is a great tweet context")
    assert not safety_check("", "Valid context")
    assert not safety_check("A" * 300, "Valid context") # Too long
    assert not safety_check("This is a delve into the tapestry of the realm.", "Valid context") # AI words
    
    # Harm word safety assertions
    assert not safety_check("We should kill this idea.", "Valid context")
    assert not safety_check("I would die of laughter!", "Valid context")
    assert not safety_check("He died yesterday.", "Valid context")
    assert not safety_check("This is a rape joke.", "Valid context")
    
    # Substring safety assertions (no false positives)
    assert safety_check("I need to start a healthy diet.", "Valid context")
    assert safety_check("Such a friendly atmosphere here.", "Valid context")


def test_quota_error_detection():
    from replier import is_quota_error, GeminiQuotaExceededException
    
    # 1. Test is_quota_error with simulated exceptions
    assert is_quota_error(ValueError("API quota exceeded"))
    assert is_quota_error(RuntimeError("429 resource exhausted"))
    assert is_quota_error(Exception("Rate limit reached on model"))
    assert not is_quota_error(ValueError("Normal API error message"))
    
    # 2. Test raising GeminiQuotaExceededException
    with pytest.raises(GeminiQuotaExceededException):
        raise GeminiQuotaExceededException("Quota exhausted!")

