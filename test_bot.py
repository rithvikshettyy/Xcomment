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
    assert 60 <= cap <= 200  # Widened range to accommodate config changes
    
    # Increment replies
    initial = get_replies_sent_today(date_str)
    increment_replies_sent(date_str)
    assert get_replies_sent_today(date_str) == initial + 1

def test_safety_check():
    # Valid replies
    assert safety_check("Interesting perspective!", "This is a great tweet context")
    assert safety_check("lmao this is actually so real", "Some tweet about tech")
    assert safety_check("ngl this hit different", "A relatable tweet")
    
    # Empty
    assert not safety_check("", "Valid context")
    
    # Too long
    assert not safety_check("A" * 300, "Valid context")
    
    # AI giveaway phrases (expanded)
    assert not safety_check("This is a delve into the tapestry of the realm.", "Valid context")
    assert not safety_check("This is indeed, a game-changer for the industry.", "Valid context")
    assert not safety_check("Let that sink in for a moment.", "Valid context")
    assert not safety_check("This is a paradigm shift in how we think.", "Valid context")
    assert not safety_check("I couldn't agree more with this take.", "Valid context")
    assert not safety_check("Beautifully put, couldn't have said it better.", "Valid context")
    assert not safety_check("Let's dive in to this fascinating topic.", "Valid context")
    assert not safety_check("Hot take: this changes everything.", "Valid context")
    assert not safety_check("This is a revolutionary approach to coding.", "Valid context")
    assert not safety_check("It goes without saying that this matters.", "Valid context")
    
    # Harm word safety assertions
    assert not safety_check("We should kill this idea.", "Valid context")
    assert not safety_check("I would die of laughter!", "Valid context")
    assert not safety_check("He died yesterday.", "Valid context")
    assert not safety_check("This is a rape joke.", "Valid context")
    
    # Substring safety assertions (no false positives)
    assert safety_check("I need to start a healthy diet.", "Valid context")
    assert safety_check("Such a friendly atmosphere here.", "Valid context")
    
    # Numbered list format rejection
    assert not safety_check("1. First point about this tweet", "Valid context")
    assert not safety_check("2) Second observation here", "Valid context")
    
    # Excessive caps rejection
    assert not safety_check("THIS IS ABSOLUTELY AMAZING AND INCREDIBLE", "Valid context")
    
    # Multi-emoji rejection
    assert not safety_check("This is so good 🔥🚀💯", "Valid context")
    
    # Single emoji should pass
    assert safety_check("this is actually fire 🔥", "Valid context")


def test_quota_error_detection():
    from replier import is_quota_error, LLMException, GeminiQuotaExceededException
    
    # Test is_quota_error with simulated exceptions
    assert is_quota_error(ValueError("API quota exceeded"))
    assert is_quota_error(RuntimeError("429 resource exhausted"))
    assert is_quota_error(Exception("Rate limit reached on model"))
    assert not is_quota_error(ValueError("Normal API error message"))
    
    # Test LLMException and backward-compatible alias
    with pytest.raises(LLMException):
        raise LLMException("Ollama error!")
    
    with pytest.raises(GeminiQuotaExceededException):
        raise GeminiQuotaExceededException("Quota exhausted!")
    
    # Verify alias works
    assert LLMException is GeminiQuotaExceededException


def test_dynamic_spacing_calculation():
    from bot import calculate_even_spacing_delay
    import config
    from unittest.mock import patch
    
    # 1. Test Fixed Pacing Mode (with random pacing turned off)
    with patch("config.USE_RANDOM_PACING", False), patch("config.USE_FIXED_PACING", True), patch("config.PACING_SECS", 1200):
        assert calculate_even_spacing_delay(replies_sent_today=0, daily_cap=30) == 1200
        
    # 2. Test Dynamic Pacing Mode (with random pacing turned off)
    with patch("config.USE_RANDOM_PACING", False), patch("config.USE_FIXED_PACING", False), patch("config.MIN_PACING_SECS", 30), patch("config.MAX_PACING_SECS", 1200), patch("bot.get_seconds_remaining_in_window", return_value=10800):
        assert calculate_even_spacing_delay(replies_sent_today=0, daily_cap=30) == 360
        assert calculate_even_spacing_delay(replies_sent_today=0, daily_cap=60) == 180

    # 3. Test Randomized Pacing Mode
    with patch("config.USE_RANDOM_PACING", True), patch("config.MIN_PACING_SECS", 300), patch("config.MAX_PACING_SECS", 1800):
        for _ in range(20):
            val = calculate_even_spacing_delay(replies_sent_today=0, daily_cap=30)
            assert 300 <= val <= 1800


def test_tech_tweet_detection():
    from bot import is_tech_tweet
    
    # Tech tweets should be detected
    assert is_tech_tweet("Just shipped a new AI model that outperforms GPT-4")
    assert is_tech_tweet("Python 4.0 is finally here and it's amazing")
    assert is_tech_tweet("NVIDIA stock up 15% after earnings report")
    assert is_tech_tweet("New startup just raised $50M in Series A funding")
    assert is_tech_tweet("Docker containers are so much better than VMs")
    
    # Non-tech tweets should not match
    assert not is_tech_tweet("Just had the best pizza in New York")
    assert not is_tech_tweet("My cat is sleeping on my keyboard again")
    assert not is_tech_tweet("Beautiful sunset at the beach today")


def test_proactive_target_picking():
    from bot import pick_proactive_target
    
    candidates = [
        {"id": "1", "url": "https://x.com/1", "text": "New AI breakthrough in deep learning", "views": 10000},
        {"id": "2", "url": "https://x.com/2", "text": "Beautiful sunset today", "views": 50000},
        {"id": "3", "url": "https://x.com/3", "text": "Python 4.0 release notes", "views": 8000},
        {"id": "4", "url": "https://x.com/4", "text": "Low views tweet", "views": 100},  # Below threshold
    ]
    
    # Should return a target (not the low-views one)
    for _ in range(10):
        target = pick_proactive_target(candidates)
        assert target is not None
        assert target["views"] >= 5000
    
    # Empty list should return None
    assert pick_proactive_target([]) is None
    
    # All below threshold should return None
    low_candidates = [{"id": "5", "url": "x", "text": "test", "views": 100}]
    assert pick_proactive_target(low_candidates) is None
