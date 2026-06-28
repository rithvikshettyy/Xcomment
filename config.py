import os
import random

# Central configuration settings for the X Automation Bot

# ──────────────────────────────────────────────────────────────────
# LLM BACKEND — Ollama (qwen3-vl:235b-cloud)
# ──────────────────────────────────────────────────────────────────
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3-coder:480b-cloud")
OLLAMA_TIMEOUT = 120  # seconds to wait for Ollama response

# Legacy Gemini API key (kept for backward compatibility, no longer primary)
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    try:
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
MIN_TWEET_VIEWS = 50_000

# Criteria for analyzing target opportunity
MIN_REPLY_VIEWS = 2_000
MIN_AVG_REPLY_VIEWS = 800     # Minimum average views of parsed comments
MIN_HIGH_REPLY_COUNT = 4        # Minimum number of comments exceeding MIN_REPLY_VIEWS
MIN_REPLY_IMPRESSIONS_FOR_ENGAGEMENT = 10_000  # Must have at least one reply with >= 10K impressions


# Daily cap parameters (daily cap is randomized each day between these values)
MIN_DAILY_REPLIES = 145
# Note: The daily cap has been increased to range around 150 to maximize impression-generating efficiency.
MAX_DAILY_REPLIES = 155

# Replying Time Window (IST)
# Configured to 1:00 AM IST to 6:00 AM IST as requested
WINDOW_START_HOUR = 1  # 1:00 AM
WINDOW_END_HOUR = 6    # 6:00 AM

# Pacing Configuration
# Set USE_RANDOM_PACING to True to randomize the delay between comments to mimic human behavior
USE_RANDOM_PACING = True
MIN_PACING_SECS = 300    # 5 minutes in seconds (300s)
MAX_PACING_SECS = 600    # 10 minutes in seconds (600s)

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

# ──────────────────────────────────────────────────────────────────
# PROACTIVE POSTING MODE — Posts on random + tech content
# ──────────────────────────────────────────────────────────────────
PROACTIVE_POSTING_ENABLED = True
# Minimum views for proactive targets (much lower than reactive MIN_TWEET_VIEWS)
PROACTIVE_MIN_VIEWS = 5_000
# How often proactive mode triggers (1 in N scan cycles)
PROACTIVE_CYCLE_FREQUENCY = 3  # every 3rd cycle is proactive
# Keywords that identify tech-related content for priority proactive targeting
PROACTIVE_TECH_KEYWORDS = [
    "ai", "machine learning", "deep learning", "llm", "gpt", "openai", "google",
    "apple", "microsoft", "tesla", "elon", "spacex", "crypto", "bitcoin", "ethereum",
    "blockchain", "web3", "startup", "saas", "coding", "programming", "python",
    "javascript", "rust", "devops", "cloud", "aws", "azure", "docker", "kubernetes",
    "api", "open source", "github", "linux", "cybersecurity", "data science",
    "neural network", "robotics", "automation", "vr", "ar", "metaverse",
    "semiconductor", "chip", "nvidia", "amd", "intel", "software", "hardware",
    "tech", "developer", "engineer", "founder", "vc", "funding", "ipo",
    "android", "ios", "react", "nextjs", "typescript", "database", "sql",
]

# ──────────────────────────────────────────────────────────────────
# STEALTH / ANTI-BOT-DETECTION — Browser fingerprint evasion
# ──────────────────────────────────────────────────────────────────
# Realistic user-agent strings (rotated per session launch)
STEALTH_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.6668.100 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
]

# Human typing simulation settings
TYPING_MIN_DELAY = 0.03   # Minimum delay per character (seconds)
TYPING_MAX_DELAY = 0.14   # Maximum delay per character (seconds)
TYPING_WORD_PAUSE_MIN = 0.15  # Pause between words (min)
TYPING_WORD_PAUSE_MAX = 0.45  # Pause between words (max)
TYPING_TYPO_CHANCE = 0.04     # 4% chance of simulated typo per character
TYPING_THINK_PAUSE_CHANCE = 0.08  # 8% chance of a longer "thinking" pause mid-sentence

# Mouse movement simulation
MOUSE_MOVE_STEPS = 15       # Number of intermediate points in bezier curve
MOUSE_MOVE_SPEED = 0.008    # Delay between each mouse step (seconds)

# Session break settings (mimics user stepping away)
SESSION_BREAK_AFTER_REPLIES = random.randint(8, 15)  # Take a break after N replies
SESSION_BREAK_MIN_SECS = 900    # 15 minutes minimum break
SESSION_BREAK_MAX_SECS = 1800   # 30 minutes maximum break

# Idle browsing simulation (chance per scan cycle to just browse without posting)
IDLE_BROWSE_CHANCE = 0.12  # 12% chance to idle-browse a cycle

# Viewport randomization (±pixels from base)
VIEWPORT_BASE_WIDTH = 1920
VIEWPORT_BASE_HEIGHT = 1080
VIEWPORT_JITTER = 60  # ±60px

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
