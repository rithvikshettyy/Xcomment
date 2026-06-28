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
    import config
    date_str = "2026-05-30"
    cap = get_or_create_daily_cap(date_str)
    assert config.MIN_DAILY_REPLIES <= cap <= config.MAX_DAILY_REPLIES
    
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


def test_ollama_exception():
    from replier import OllamaException
    
    with pytest.raises(OllamaException):
        raise OllamaException("Ollama request failed")


def test_dynamic_spacing_calculation():
    from bot import calculate_even_spacing_delay
    import config
    from unittest.mock import patch
    
    # 1. Test Fixed Pacing Mode (with random pacing turned off)
    with patch("config.USE_RANDOM_PACING", False), patch("config.USE_FIXED_PACING", True), patch("config.PACING_SECS", 1200):
        assert calculate_even_spacing_delay(replies_sent_today=0, daily_cap=30) == 1200
        
    # 2. Test Dynamic Pacing Mode (with random pacing turned off)
    with patch("config.USE_RANDOM_PACING", False), patch("config.USE_FIXED_PACING", False), patch("config.MIN_PACING_SECS", 30), patch("config.MAX_PACING_SECS", 1200), patch("bot.get_seconds_remaining_in_window", return_value=10800):
        # Outside the window (or before start), it should use the full 3 hours (10800 seconds)
        # If 30 replies remaining: spacing should be 10800 / 30 = 360 seconds (6 minutes)
        assert calculate_even_spacing_delay(replies_sent_today=0, daily_cap=30) == 360
        
        # If 60 replies remaining: spacing should be 10800 / 60 = 180 seconds (3 minutes)
        assert calculate_even_spacing_delay(replies_sent_today=0, daily_cap=60) == 180

    # 3. Test New Randomized Pacing Mode
    with patch("config.USE_RANDOM_PACING", True), patch("config.MIN_PACING_SECS", 300), patch("config.MAX_PACING_SECS", 1800):
        for _ in range(20):
            val = calculate_even_spacing_delay(replies_sent_today=0, daily_cap=30)
            assert 300 <= val <= 1800

