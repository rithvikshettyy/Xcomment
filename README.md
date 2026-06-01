# X Automation Bot 🤖💬

An advanced, highly resilient, and cost-optimized autonomous X (Twitter) commenting bot powered by **Playwright** and the **Google Gemini API**. 

Designed specifically for accounts with **Premium+** checkmarks to capture massive impressions by executing instant, hyper-contextual replies to qualified viral tweets.

---

## 🌟 Key Features

* **Instant-Post-Then-Sleep Pacing**: Structured specifically to leverage X's algorithmic premium boost. The bot sleeps *after* a successful reply rather than before, ensuring your reply is posted within seconds of discovery to stay pinned at the very top of the thread.
* **Unified Gemini AI Call (85% Cost Optimization)**: 
  * Generates 3 candidate replies and selects the single best one in **one single API call** (50% requests savings).
  * Strips out all heavy JSON metadata (views, likes, retweets) and trims the context payload down to the top 3 replies (**70%+ token savings**).
  * Together, these reduce prompt billing costs by up to **85%**.
* **Self-Healing & Resilient**: Fully equipped with dynamic connection and context self-healing. If Chromium crashes or X closes the connection, the bot dynamically restarts Playwright, recovers the session, and resumes operations silently.
* **Smart SQLite Dynamic Caps**: Dynamically generates and persists a daily reply cap (set to **90–95 replies**) in a local SQLite database (`bot_data.db`) to ensure the account mimics natural human limits.
* **Persistent Sessions**: Saves your login state (cookies, local storage, profile data) locally in `chrome_profile/` so you never have to re-authenticate on bot startups.
* **Strict Safety Guards**: Multi-stage validation filters out AI giveaway clichés ("delve", "indeed"), double-replies, and sensitive/harm words to ensure your account remains safe from suspensions.

---

## 📋 System Requirements

* **OS**: Windows, macOS, or Linux
* **Python**: 3.10+
* **Dependencies**: `playwright`, `google-generativeai`

---

## 🚀 Setup & Installation

### Step 1: Install Dependencies
Clone the repository, navigate to the folder, and install the required Python packages:
```bash
pip install -r requirements.txt
```

### Step 2: Install Playwright Browsers
Download the Chromium binaries managed by Playwright:
```bash
playwright install
```

### Step 3: Configure Gemini API Key
Create a new file named `api_key.txt` in the root directory of the project, and paste your Gemini API key inside it:
```text
YOUR_GEMINI_API_KEY_HERE
```
*(Note: `api_key.txt` is automatically ignored by Git to keep your credentials secure).*

### Step 4: Configure Email Notifications (Optional/Disabled by Default)
Create a file named `email_credentials.txt` to manage error alert emails. For silent operations, keep notifications disabled:
```text
SENDER_EMAIL=your_email@gmail.com
RECEIVER_EMAIL=your_email@gmail.com
GMAIL_APP_PASSWORD=your_16_character_app_password
ENABLE_EMAIL_NOTIFICATIONS=False
```

### Step 5: Authenticate Your X Account
Run the included login helper. This opens a headful Chromium window where you can log in to X manually:
```bash
python login_helper.py
```
Once logged in, close the browser window. Your active session (cookies, profile data) is saved securely inside `chrome_profile/`.

### Step 6: Start the Bot
Run the bot directly in your terminal to watch the real-time opportunity scanning and posting logs:
```bash
python bot.py
```

*To run in a non-posting test mode first, use the dry-run flag:*
```bash
python bot.py --dry-run
```

---

## 📂 Codebase Architecture

* `bot.py`: The central event loop. Handles feed switching, scrolling, opportunity qualification, pacing, and resilient error recovery.
* `browser.py`: Lower-level Playwright utilities. Manages browser contexts, navigations, human-like scrolling, and DOM extraction of tweets/views.
* `replier.py`: Interface for the Gemini API. Builds optimized prompts and parses JSON candidate replies using the unified single-call model.
* `config.py`: Centralized configuration settings (daily limits, feed URLs, pacing gaps, view thresholds).
* `db.py`: SQLite database manager. Tracks processed tweets to prevent double replying and records daily cap statistics.
* `login_helper.py`: Quick wrapper to authenticate your X account and persist profile state.
* `notifier.py`: SMTP-based Gmail notifier for critical loop warnings (inactive by default).
