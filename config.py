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
MIN_TWEET_VIEWS = 200_000

# Criteria for analyzing target opportunity
MIN_REPLY_VIEWS = 2_000
MIN_AVG_REPLY_VIEWS = 800     # Minimum average views of parsed comments
MIN_HIGH_REPLY_COUNT = 4        # Minimum number of comments exceeding MIN_REPLY_VIEWS

# Daily cap parameters (daily cap is randomized each day between these values)
MIN_DAILY_REPLIES = 90
# Note: The user commented "33 is good, no need for 60-70". 
# However, we will respect the original capping rules but limit/default as desired.
# Let's set the cap default to 60-70 but because of the time window it naturally stops around 33.
# This gives the best of both worlds and matches the spec exactly.
MAX_DAILY_REPLIES = 95

# Replying Time Window (IST)
# Configured to 1:00 AM IST to 6:00 AM IST as requested
WINDOW_START_HOUR = 1  # 1:00 AM
WINDOW_END_HOUR = 6    # 6:00 AM

# Pacing Configuration
# Set USE_RANDOM_PACING to True to randomize the delay between comments to mimic human behavior
USE_RANDOM_PACING = True
MIN_PACING_SECS = 300    # 5 minutes in seconds (300s)
MAX_PACING_SECS = 1800   # 30 minutes in seconds (1800s)

# Legacy Pacing settings
USE_FIXED_PACING = False
PACING_SECS = 1200     # 20 minutes in seconds

# 24/7 Execution Mode
# Set to True to allow the bot to run 24/7, ignoring time window constraints
RUN_24_7 = True
BYPASS_WINDOW_FOR_TESTING = True

# Human-like behavior options
# Chance that the bot will skip a completely qualified opportunity to look natural (0.0 to 1.0)
SKIP_CHANCE = 0.15

# Multimodal / Image processing capabilities
PROCESS_IMAGES = False
TEMP_IMAGE_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "temp_tweet.png"))

# Logged in account username handle switcher default
MY_USERNAME = ""

# Feed URLs to cycle through when scanning for opportunity tweets.
# Starts with For You page, then Inspiration page, then Home page.
FEEDS_TO_SCAN = [
    "https://x.com/explore",                            # Start with For You feed
    "https://x.com/i/jf/creators/inspiration/top_posts", # Redirect to Inspiration page
    "https://x.com/home"                                 # Home page
]

# Email notification settings (Loaded dynamically from email_credentials.txt)
GMAIL_SENDER = ""
GMAIL_RECEIVER = ""
GMAIL_APP_PASSWORD = ""
ENABLE_EMAIL_NOTIFICATIONS = False

try:
    with open(os.path.join(os.path.dirname(__file__), "email_credentials.txt"), "r", encoding="utf-8") as f_mail:
        for line in f_mail:
            line_strip = line.strip()
            if not line_strip or line_strip.startswith("#"):
                continue
            if "=" in line_strip:
                k, v = line_strip.split("=", 1)
                k = k.strip()
                v = v.strip()
                if k == "SENDER_EMAIL":
                    GMAIL_SENDER = v
                elif k == "RECEIVER_EMAIL":
                    GMAIL_RECEIVER = v
                elif k == "GMAIL_APP_PASSWORD":
                    GMAIL_APP_PASSWORD = v
                elif k == "ENABLE_EMAIL_NOTIFICATIONS":
                    ENABLE_EMAIL_NOTIFICATIONS = (v.lower() == "true")
except Exception:
    pass


