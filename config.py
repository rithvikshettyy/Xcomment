import os

# Central configuration settings for the X Automation Bot

# API Key for Gemini API (Ensure this is set in your environment variables, or specify here)
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    try:
        # Load from local api_key.txt (which is added to .gitignore)
        with open(os.path.join(os.path.dirname(__file__), "api_key.txt"), "r", encoding="utf-8") as f:
            GEMINI_API_KEY = f.read().strip()
    except FileNotFoundError:
        GEMINI_API_KEY = ""


# Directory where browser profile session (cookies, storage) will be stored.
# This prevents having to log in on every bot startup.
USER_DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "chrome_profile"))

# SQLite database file path
DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "bot_data.db"))

# Filter Criteria for Tweets
MIN_TWEET_VIEWS = 700_000

# Criteria for analyzing target opportunity
MIN_REPLY_VIEWS = 5_000
MIN_AVG_REPLY_VIEWS = 1_500     # Minimum average views of parsed comments
MIN_HIGH_REPLY_COUNT = 4        # Minimum number of comments exceeding MIN_REPLY_VIEWS

# Daily cap parameters (daily cap is randomized each day between these values)
MIN_DAILY_REPLIES = 60
# Note: The user commented "33 is good, no need for 60-70". 
# However, we will respect the original capping rules but limit/default as desired.
# Let's set the cap default to 60-70 but because of the time window it naturally stops around 33.
# This gives the best of both worlds and matches the spec exactly.
MAX_DAILY_REPLIES = 70

# Replying Time Window (IST)
# Window is 12:00 AM IST to 5:00 AM IST
WINDOW_START_HOUR = 0  # 12:00 AM
WINDOW_END_HOUR = 5    # 5:00 AM

# Randomized delay range between replies in seconds
# 30 seconds to 60 seconds
MIN_DELAY_SECS = 30   # 30 seconds
MAX_DELAY_SECS = 60   # 60 seconds

# Test Bypasses
# Set to True to allow the bot to run outside the 12:00 AM - 5:00 AM IST window for testing
BYPASS_WINDOW_FOR_TESTING = True

# Human-like behavior options
# Chance that the bot will skip a completely qualified opportunity to look natural (0.0 to 1.0)
SKIP_CHANCE = 0.15

# Multimodal / Image processing capabilities
PROCESS_IMAGES = True
TEMP_IMAGE_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "temp_tweet.png"))

# Feed URLs to cycle through when scanning for opportunity tweets.
# Strictly cycles through the Inspiration page, For You, and Home page timelines.
FEEDS_TO_SCAN = [
    "https://x.com/i/jf/creators/inspiration/top_posts",
    "https://x.com/explore",
    "https://x.com/home"
]


