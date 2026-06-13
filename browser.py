import asyncio
import math
import re
import logging
import random
from playwright.async_api import async_playwright, Page, BrowserContext
import config
from config import USER_DATA_DIR, MIN_TWEET_VIEWS, MIN_REPLY_VIEWS

logger = logging.getLogger("bot.browser")


# ──────────────────────────────────────────────────────────────────
# UTILITY — Number parsing
# ──────────────────────────────────────────────────────────────────

def parse_x_number(text: str) -> int:
    """Parses standard X notation numbers (e.g., '1.2M', '750K', '5,400', '5.4K') into integers."""
    if not text:
        return 0

    # Strip whitespace and commas
    cleaned = text.strip().replace(",", "")

    # Check for M (millions)
    match_m = re.match(r"^([\d\.]+)\s*M$", cleaned, re.IGNORECASE)
    if match_m:
        try:
            return int(float(match_m.group(1)) * 1_000_000)
        except ValueError:
            return 0

    # Check for K (thousands)
    match_k = re.match(r"^([\d\.]+)\s*K$", cleaned, re.IGNORECASE)
    if match_k:
        try:
            return int(float(match_k.group(1)) * 1_000)
        except ValueError:
            return 0

    # Standard integer
    try:
        digits_only = re.sub(r"[^\d]", "", cleaned)
        return int(digits_only) if digits_only else 0
    except ValueError:
        return 0


# ──────────────────────────────────────────────────────────────────
# STEALTH — Human mouse movement (Bezier curves)
# ──────────────────────────────────────────────────────────────────

def _bezier_point(t: float, p0: tuple, p1: tuple, p2: tuple, p3: tuple) -> tuple:
    """Calculates a point on a cubic bezier curve at parameter t."""
    x = (1 - t) ** 3 * p0[0] + 3 * (1 - t) ** 2 * t * p1[0] + 3 * (1 - t) * t ** 2 * p2[0] + t ** 3 * p3[0]
    y = (1 - t) ** 3 * p0[1] + 3 * (1 - t) ** 2 * t * p1[1] + 3 * (1 - t) * t ** 2 * p2[1] + t ** 3 * p3[1]
    return (int(x), int(y))


def _generate_bezier_path(start: tuple, end: tuple, steps: int = None) -> list:
    """Generates a natural-looking mouse path from start to end using cubic bezier curves."""
    steps = steps or config.MOUSE_MOVE_STEPS

    # Create control points with natural randomness
    dx = end[0] - start[0]
    dy = end[1] - start[1]

    # Control points offset from the straight line — creates natural arc
    cp1 = (
        start[0] + dx * random.uniform(0.15, 0.4) + random.randint(-80, 80),
        start[1] + dy * random.uniform(0.0, 0.3) + random.randint(-60, 60)
    )
    cp2 = (
        start[0] + dx * random.uniform(0.6, 0.85) + random.randint(-80, 80),
        start[1] + dy * random.uniform(0.7, 1.0) + random.randint(-60, 60)
    )

    path = []
    for i in range(steps + 1):
        t = i / steps
        point = _bezier_point(t, start, cp1, cp2, end)
        path.append(point)

    return path


async def human_mouse_move(page: Page, x: int, y: int):
    """Moves the mouse to (x, y) via a natural bezier curve path."""
    try:
        # Get current mouse position (defaults to center of viewport if unknown)
        current = await page.evaluate("() => ({x: window._mouseX || 960, y: window._mouseY || 540})")
        start = (current.get("x", 960), current.get("y", 540))
        end = (x, y)

        path = _generate_bezier_path(start, end)

        for px, py in path:
            await page.mouse.move(px, py)
            await asyncio.sleep(random.uniform(config.MOUSE_MOVE_SPEED * 0.5, config.MOUSE_MOVE_SPEED * 1.5))

        # Track position for next movement
        await page.evaluate(f"() => {{ window._mouseX = {x}; window._mouseY = {y}; }}")
    except Exception as e:
        # Fallback to direct move if bezier fails
        logger.debug(f"Bezier mouse move failed, using direct: {e}")
        await page.mouse.move(x, y)


async def human_click(page: Page, selector: str = None, element=None):
    """Clicks an element with natural mouse movement to it first."""
    try:
        target = element
        if selector and not target:
            target = await page.query_selector(selector)

        if not target:
            if selector:
                await page.click(selector)
            return

        # Get element bounding box
        bbox = await target.bounding_box()
        if not bbox:
            await target.click()
            return

        # Click at a slightly randomized position within the element (not dead center)
        click_x = bbox["x"] + bbox["width"] * random.uniform(0.25, 0.75)
        click_y = bbox["y"] + bbox["height"] * random.uniform(0.3, 0.7)

        # Move mouse naturally to the target
        await human_mouse_move(page, int(click_x), int(click_y))

        # Small pre-click pause (humans don't click instantly after stopping mouse)
        await asyncio.sleep(random.uniform(0.08, 0.25))

        await page.mouse.click(click_x, click_y)

    except Exception as e:
        logger.debug(f"Human click failed, falling back to direct click: {e}")
        if selector:
            try:
                await page.click(selector)
            except Exception:
                pass
        elif element:
            try:
                await element.click()
            except Exception:
                pass


# ──────────────────────────────────────────────────────────────────
# STEALTH — Human-like typing with typos
# ──────────────────────────────────────────────────────────────────

async def human_type(page: Page, text: str):
    """Types text character by character with human-like timing, word pauses, and occasional typos."""
    nearby_keys = {
        'a': 'sq', 'b': 'vn', 'c': 'xv', 'd': 'sf', 'e': 'wr', 'f': 'dg',
        'g': 'fh', 'h': 'gj', 'i': 'uo', 'j': 'hk', 'k': 'jl', 'l': 'k',
        'm': 'n', 'n': 'bm', 'o': 'ip', 'p': 'o', 'q': 'w', 'r': 'et',
        's': 'ad', 't': 'ry', 'u': 'yi', 'v': 'cb', 'w': 'qe', 'x': 'zc',
        'y': 'tu', 'z': 'x', ' ': ' '
    }

    for i, char in enumerate(text):
        # Word boundary pause — humans slow down between words
        if char == ' ':
            await asyncio.sleep(random.uniform(config.TYPING_WORD_PAUSE_MIN, config.TYPING_WORD_PAUSE_MAX))
            await page.keyboard.type(char)
            continue

        # Random "thinking" pause — humans sometimes pause mid-word
        if random.random() < config.TYPING_THINK_PAUSE_CHANCE:
            await asyncio.sleep(random.uniform(0.4, 1.2))

        # Typo simulation — type wrong char then correct it
        if random.random() < config.TYPING_TYPO_CHANCE and char.lower() in nearby_keys:
            wrong_char = random.choice(nearby_keys.get(char.lower(), char))
            await page.keyboard.type(wrong_char)
            await asyncio.sleep(random.uniform(0.1, 0.35))
            await page.keyboard.press("Backspace")
            await asyncio.sleep(random.uniform(0.05, 0.15))

        # Type the correct character
        await page.keyboard.type(char)

        # Variable typing speed — faster for common keys, slower for stretches
        delay = random.uniform(config.TYPING_MIN_DELAY, config.TYPING_MAX_DELAY)
        # Speed up slightly mid-word (humans type faster once they get momentum)
        if i > 0 and text[i - 1] != ' ' and char != ' ':
            delay *= random.uniform(0.7, 1.0)
        await asyncio.sleep(delay)


# ──────────────────────────────────────────────────────────────────
# STEALTH — View extraction
# ──────────────────────────────────────────────────────────────────

async def extract_views_from_tweet_element(elem) -> int:
    """Extracts views from a tweet or reply DOM element using multiple robust strategies."""
    # Strategy 1: Check elements with data-testid="app-bar-view-analytics" or containing "view" in aria-label
    view_selectors = [
        'a[href*="/analytics"]',
        '[data-testid="app-bar-view-analytics"]',
        'a[aria-label*="view" i]',
        'div[aria-label*="view" i]',
        'button[aria-label*="view" i]',
        '[aria-label*="view" i]'
    ]

    for selector in view_selectors:
        try:
            view_elem = await elem.query_selector(selector)
            if view_elem:
                # Try getting aria-label
                aria_label = await view_elem.get_attribute("aria-label")
                if aria_label:
                    match = re.search(r"([\d\.,]+[MK]?)\s*view", aria_label, re.IGNORECASE)
                    if match:
                        return parse_x_number(match.group(1))

                # Try getting title attribute
                title = await view_elem.get_attribute("title")
                if title:
                    match = re.search(r"([\d\.,]+[MK]?)\s*view", title, re.IGNORECASE)
                    if match:
                        return parse_x_number(match.group(1))

                # Try getting inner text
                inner_text = await view_elem.inner_text()
                if inner_text:
                    val = parse_x_number(inner_text)
                    if val > 0:
                        return val
        except Exception:
            continue

    # Strategy 2: Fallback to reading role="group" items
    try:
        group_elem = await elem.query_selector('div[role="group"]')
        if group_elem:
            anchors = await group_elem.query_selector_all('a')
            for a in anchors:
                aria_label = await a.get_attribute("aria-label")
                if aria_label and "view" in aria_label.lower():
                    match = re.search(r"([\d\.,]+[MK]?)\s*view", aria_label, re.IGNORECASE)
                    if match:
                        return parse_x_number(match.group(1))
                    val = parse_x_number(aria_label)
                    if val > 0:
                        return val
    except Exception:
        pass

    return 0


# ──────────────────────────────────────────────────────────────────
# STEALTH — Browser context with anti-detection
# ──────────────────────────────────────────────────────────────────

async def get_browser_context(playwright) -> BrowserContext:
    """Launches a stealth persistent context with anti-detection measures."""
    # Pick a random user agent for this session
    user_agent = random.choice(config.STEALTH_USER_AGENTS)

    # Randomize viewport dimensions slightly each session
    vp_width = config.VIEWPORT_BASE_WIDTH + random.randint(-config.VIEWPORT_JITTER, config.VIEWPORT_JITTER)
    vp_height = config.VIEWPORT_BASE_HEIGHT + random.randint(-config.VIEWPORT_JITTER, config.VIEWPORT_JITTER)

    logger.info(f"[STEALTH] Launching browser — UA: ...{user_agent[-40:]} | Viewport: {vp_width}x{vp_height}")

    context = await playwright.chromium.launch_persistent_context(
        user_data_dir=USER_DATA_DIR,
        channel="chrome",
        headless=False,
        user_agent=user_agent,
        viewport={"width": vp_width, "height": vp_height},
        locale="en-US",
        timezone_id="Asia/Kolkata",
        args=[
            "--disable-blink-features=AutomationControlled",
            "--disable-features=IsolateOrigins,site-per-process",
            "--disable-infobars",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-background-timer-throttling",
            "--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding",
            "--disable-dev-shm-usage",
            "--lang=en-US",
        ],
        ignore_default_args=["--enable-automation"],
    )

    # Inject stealth scripts into every new page to defeat navigator.webdriver detection
    await context.add_init_script("""
        // Override navigator.webdriver to undefined
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

        // Override Chrome.runtime to appear as normal Chrome
        window.chrome = { runtime: {}, loadTimes: function(){}, csi: function(){} };

        // Override permissions query
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) =>
            parameters.name === 'notifications'
                ? Promise.resolve({ state: Notification.permission })
                : originalQuery(parameters);

        // Override plugins to look like a real browser
        Object.defineProperty(navigator, 'plugins', {
            get: () => [1, 2, 3, 4, 5]
        });

        // Override languages
        Object.defineProperty(navigator, 'languages', {
            get: () => ['en-US', 'en']
        });

        // Override platform
        Object.defineProperty(navigator, 'platform', {
            get: () => 'Win32'
        });

        // Override hardware concurrency with a realistic value
        Object.defineProperty(navigator, 'hardwareConcurrency', {
            get: () => 8
        });

        // Spoof WebGL vendor and renderer
        const getParameter = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(parameter) {
            if (parameter === 37445) return 'Google Inc. (NVIDIA)';
            if (parameter === 37446) return 'ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)';
            return getParameter.call(this, parameter);
        };

        // Track mouse position for bezier calculations
        document.addEventListener('mousemove', (e) => {
            window._mouseX = e.clientX;
            window._mouseY = e.clientY;
        });
    """)

    return context


# ──────────────────────────────────────────────────────────────────
# NAVIGATION — Popup handling
# ──────────────────────────────────────────────────────────────────

async def dismiss_popups(page: Page):
    """Dismisses common X popups like 'Views', cookie consent, or notifications if they appear."""
    selectors = [
        'button:has-text("Dismiss")',
        'div[role="button"]:has-text("Dismiss")',
        'div[aria-label="Close"]',
        'div[data-testid="app-bar-close"]',
        'button:has-text("Got it")',
        'div[role="button"]:has-text("Got it")'
    ]
    for selector in selectors:
        try:
            btn = await page.query_selector(selector)
            if btn and await btn.is_visible():
                await human_click(page, element=btn)
                logger.info(f"Dismissed popup using selector: '{selector}'")
                await asyncio.sleep(random.uniform(0.4, 0.8))
        except Exception:
            pass


# ──────────────────────────────────────────────────────────────────
# STEALTH — Human-like scrolling
# ──────────────────────────────────────────────────────────────────

async def human_scroll(page: Page, scrolls: int = 3):
    """Performs natural-looking scrolls with variable speeds, pauses, and reading simulation."""
    # Dismiss any active blocking popups first
    await dismiss_popups(page)

    logger.info(f"Performing {scrolls} human-like scrolls...")
    for i in range(scrolls):
        # Variable scroll distance
        distance = random.randint(250, 800)

        # Smooth scroll in smaller increments (not one big jump)
        scroll_chunks = random.randint(3, 6)
        chunk_size = distance // scroll_chunks
        for _ in range(scroll_chunks):
            jittered_chunk = chunk_size + random.randint(-30, 30)
            await page.evaluate(f"window.scrollBy(0, {jittered_chunk})")
            await asyncio.sleep(random.uniform(0.05, 0.15))

        # Post-scroll pause (reading the content)
        read_time = random.uniform(1.0, 3.5)
        await asyncio.sleep(read_time)

        # Occasionally scroll up slightly to "re-read" something (25% chance)
        if random.random() < 0.25:
            up_distance = random.randint(-200, -60)
            await page.evaluate(f"window.scrollBy(0, {up_distance})")
            await asyncio.sleep(random.uniform(0.6, 1.8))

        # Occasionally hover over a random tweet element (mimics reading)
        if random.random() < 0.2:
            try:
                tweets = await page.query_selector_all('article[data-testid="tweet"]')
                if tweets:
                    random_tweet = random.choice(tweets)
                    bbox = await random_tweet.bounding_box()
                    if bbox:
                        hover_x = bbox["x"] + bbox["width"] * random.uniform(0.2, 0.8)
                        hover_y = bbox["y"] + bbox["height"] * random.uniform(0.2, 0.5)
                        await human_mouse_move(page, int(hover_x), int(hover_y))
                        await asyncio.sleep(random.uniform(0.3, 1.0))
            except Exception:
                pass

        # Random micro-pause between scroll sets
        if i < scrolls - 1:
            await asyncio.sleep(random.uniform(0.3, 1.2))


async def idle_browse(page: Page):
    """Simulates a user casually browsing without taking action — scroll, read, hover, do nothing."""
    logger.info("[IDLE] Simulating idle browsing behavior...")
    idle_duration = random.uniform(30, 90)  # 30-90 seconds of idle
    elapsed = 0

    while elapsed < idle_duration:
        action = random.choice(["scroll", "hover", "wait", "scroll_up"])

        if action == "scroll":
            await human_scroll(page, scrolls=1)
            elapsed += random.uniform(2, 5)
        elif action == "hover":
            try:
                tweets = await page.query_selector_all('article[data-testid="tweet"]')
                if tweets:
                    tweet = random.choice(tweets)
                    bbox = await tweet.bounding_box()
                    if bbox:
                        await human_mouse_move(page, int(bbox["x"] + bbox["width"] / 2), int(bbox["y"] + bbox["height"] / 3))
                        await asyncio.sleep(random.uniform(1.5, 4.0))
                        elapsed += random.uniform(2, 5)
            except Exception:
                pass
        elif action == "scroll_up":
            await page.evaluate(f"window.scrollBy(0, {random.randint(-400, -100)})")
            await asyncio.sleep(random.uniform(1.0, 2.5))
            elapsed += random.uniform(1.5, 3)
        else:
            wait = random.uniform(3, 8)
            await asyncio.sleep(wait)
            elapsed += wait

    logger.info(f"[IDLE] Finished idle browsing ({idle_duration:.0f}s)")


# ──────────────────────────────────────────────────────────────────
# FEED — Tweet extraction
# ──────────────────────────────────────────────────────────────────

async def extract_tweets_from_feed(page: Page) -> list:
    """Scrapes the current feed and extracts basic metrics for tweets found."""
    tweets = []

    # X uses article elements for tweets
    tweet_elements = await page.query_selector_all('article[data-testid="tweet"]')
    logger.info(f"Found {len(tweet_elements)} tweets in current view.")

    for elem in tweet_elements:
        try:
            # 1. Get the Tweet ID and URL from the link
            link_elem = await elem.query_selector('a[href*="/status/"]')
            if not link_elem:
                continue
            href = await link_elem.get_attribute("href")
            if not href:
                continue

            tweet_url = f"https://x.com{href}"
            tweet_id = href.split("/status/")[-1].split("?")[0]

            # 2. Extract Tweet Text
            text_elem = await elem.query_selector('div[data-testid="tweetText"]')
            tweet_text = await text_elem.inner_text() if text_elem else ""

            # 3. Extract Views Count
            views = await extract_views_from_tweet_element(elem)

            # 4. Extract Likes
            like_elem = await elem.query_selector('div[data-testid="like"]')
            likes_text = await like_elem.inner_text() if like_elem else "0"
            likes = parse_x_number(likes_text)

            # 5. Extract Reposts
            repost_elem = await elem.query_selector('div[data-testid="retweet"]')
            reposts_text = await repost_elem.inner_text() if repost_elem else "0"
            reposts = parse_x_number(reposts_text)

            tweets.append({
                "id": tweet_id,
                "url": tweet_url,
                "text": tweet_text,
                "views": views,
                "likes": likes,
                "reposts": reposts
            })
        except Exception as e:
            logger.debug(f"Failed to parse individual tweet: {e}")
            continue

    return tweets


# ──────────────────────────────────────────────────────────────────
# ANALYSIS — Tweet detail page
# ──────────────────────────────────────────────────────────────────

async def analyze_tweet_details(page: Page, tweet_url: str) -> dict:
    """Navigates to the tweet, scrolls to load replies, and extracts details about top replies."""
    logger.info(f"Opening tweet details: {tweet_url}")
    await page.goto(tweet_url)

    # Wait for the main tweet to load
    try:
        await page.wait_for_selector('article[data-testid="tweet"]', timeout=10000)
    except Exception:
        logger.warning("Timeout waiting for tweet to load.")
        return {"original_text": "", "replies": [], "has_image": False}

    # Check for reply restrictions (locked/restricted tweets)
    is_restricted = False
    try:
        restricted_selectors = [
            'div:has-text("Only some accounts can reply")',
            'span:has-text("Only some accounts can reply")',
            'div:has-text("can reply.")',
            'span:has-text("can reply.")',
            'div:has-text("Who can reply?")'
        ]
        for selector in restricted_selectors:
            elem = await page.query_selector(selector)
            if elem:
                inner_text = await elem.inner_text()
                if "can reply" in inner_text or "Who can reply" in inner_text:
                    logger.warning(f"[RESTRICTION GUARD] Detected locked/restricted replies: '{inner_text.strip()}'. Skipping.")
                    is_restricted = True
                    break
    except Exception as e_res:
        logger.debug(f"Failed to check restricted status: {e_res}")

    if is_restricted:
        return {"original_text": "", "replies": [], "has_image": False, "is_restricted": True}

    # Get original tweet text
    main_tweet = await page.query_selector('article[data-testid="tweet"]')
    original_text = ""
    has_image = False

    if main_tweet:
        text_elem = await main_tweet.query_selector('div[data-testid="tweetText"]')
        original_text = await text_elem.inner_text() if text_elem else ""

        # Check if visual media is present
        if config.PROCESS_IMAGES:
            try:
                media_elem = await main_tweet.query_selector(
                    'div[data-testid="tweetPhoto"], div[data-testid="videoPlayer"], div[data-testid="card.wrapper"], img[src*="media"]'
                )
                if media_elem:
                    logger.info("Visual media detected inside tweet. Capturing screenshot for multimodal input...")
                    await main_tweet.screenshot(path=config.TEMP_IMAGE_PATH)
                    has_image = True
            except Exception as e_snap:
                logger.error(f"Failed to capture tweet media screenshot: {e_snap}")

    # Scroll once or twice to load replies (with human behavior)
    await human_scroll(page, scrolls=2)

    # Extract replies
    articles = await page.query_selector_all('article[data-testid="tweet"]')
    logger.info(f"Found {len(articles)} total articles on details page.")

    # Look for our own username in ANY loaded replies to prevent double replying
    has_self_reply = False
    my_username = getattr(config, "MY_USERNAME", "").lower()

    if my_username:
        for elem in articles[1:]:
            try:
                user_elem = await elem.query_selector('[data-testid="User-Name"]')
                if user_elem:
                    user_text = await user_elem.inner_text()
                    match = re.search(r"@(\w+)", user_text)
                    if match:
                        author_handle = match.group(1).lower()
                        if author_handle == my_username:
                            logger.warning(f"[DOUBLE REPLY GUARD] Detected existing reply by @{my_username} on this tweet. Skipping.")
                            has_self_reply = True
                            break
            except Exception:
                pass

        # Also perform profile link dynamic check to be 100% robust
        if not has_self_reply:
            try:
                profile_links = await page.query_selector_all(f'a[href="/{my_username}"]')
                for link in profile_links:
                    ancestor = await link.evaluate_handle("el => el.closest('article[data-testid=\"tweet\"]')")
                    if ancestor:
                        first_article = await page.query_selector('article[data-testid="tweet"]')
                        is_parent = False
                        if first_article:
                            is_parent = await page.evaluate("(el1, el2) => el1 === el2", ancestor, first_article)
                        if not is_parent:
                            logger.warning(f"[DOUBLE REPLY GUARD] Detected profile link for @{my_username} in a reply article. Skipping.")
                            has_self_reply = True
                            break
            except Exception as e_link:
                logger.debug(f"Failed profile links query: {e_link}")

    top_replies = []

    # Skip index 0 (original tweet). Limit to 10 comments.
    for elem in articles[1:11]:
        try:
            text_elem = await elem.query_selector('div[data-testid="tweetText"]')
            reply_text = await text_elem.inner_text() if text_elem else ""
            if not reply_text:
                continue

            views = await extract_views_from_tweet_element(elem)

            like_elem = await elem.query_selector('div[data-testid="like"]')
            likes_text = await like_elem.inner_text() if like_elem else "0"
            likes = parse_x_number(likes_text)

            repost_elem = await elem.query_selector('div[data-testid="retweet"]')
            reposts_text = await repost_elem.inner_text() if repost_elem else "0"
            reposts = parse_x_number(reposts_text)

            top_replies.append({
                "text": reply_text,
                "views": views,
                "likes": likes,
                "reposts": reposts
            })
        except Exception as e:
            logger.debug(f"Failed to parse individual reply: {e}")
            continue

    # Sort replies by views descending
    top_replies.sort(key=lambda x: x["views"], reverse=True)

    return {
        "original_text": original_text,
        "replies": top_replies,
        "has_image": has_image,
        "has_self_reply": has_self_reply
    }


# ──────────────────────────────────────────────────────────────────
# POSTING — Human-like reply posting
# ──────────────────────────────────────────────────────────────────

async def post_reply(page: Page, tweet_url: str, reply_text: str) -> bool:
    """Navigates to the tweet, types the reply naturally with human simulation, and posts."""
    logger.info(f"Navigating to tweet to post reply: {tweet_url}")
    await page.goto(tweet_url)

    # Dismiss any active popups
    await dismiss_popups(page)

    # Simulate reading the tweet before replying (2-6 seconds)
    read_delay = random.uniform(2.0, 6.0)
    logger.info(f"[HUMAN] Reading tweet for {read_delay:.1f}s before replying...")
    await asyncio.sleep(read_delay)

    try:
        # Wait for reply editor
        reply_editor_selector = 'div[data-testid="tweetTextarea_0"]'
        await page.wait_for_selector(reply_editor_selector, timeout=10000)

        # Click on editor with human mouse movement
        await human_click(page, selector=reply_editor_selector)
        await asyncio.sleep(random.uniform(0.5, 1.2))

        # Focus the editor
        await page.focus(reply_editor_selector)
        await asyncio.sleep(random.uniform(0.3, 0.8))

        # Human-like typing with typos and variable speed
        logger.info(f"Typing reply: '{reply_text}'")
        await human_type(page, reply_text)

        # Post-typing pause — human reviews what they typed (1.5-4s)
        review_delay = random.uniform(1.5, 4.0)
        logger.info(f"[HUMAN] Reviewing typed reply for {review_delay:.1f}s...")
        await asyncio.sleep(review_delay)

        # Click reply/post button using human mouse movement
        post_btn_selectors = [
            'div[data-testid="tweetButtonInline"]',
            'button[data-testid="tweetButtonInline"]',
            '[data-testid="inlineCompose"] [role="button"]:has-text("Reply")',
            '[data-testid="inlineCompose"] button:has-text("Reply")',
            'div[role="button"] span:has-text("Reply")',
            'button:has-text("Reply")'
        ]

        button_clicked = False
        for selector in post_btn_selectors:
            try:
                btn = await page.query_selector(selector)
                if btn and await btn.is_visible():
                    await human_click(page, element=btn)
                    button_clicked = True
                    logger.info(f"Successfully clicked reply button using selector: '{selector}'")
                    break
            except Exception as e_sel:
                logger.debug(f"Selector '{selector}' did not match or click: {e_sel}")

        if not button_clicked:
            raise RuntimeError("Could not find or click any visible Reply/Post button.")

        logger.info("Reply post button clicked. Waiting for confirmation...")
        await asyncio.sleep(random.uniform(3.0, 5.0))
        return True

    except Exception as e:
        logger.error(f"Failed to post reply: {e}")
        return False


# ──────────────────────────────────────────────────────────────────
# FEED — Inspiration page setup
# ──────────────────────────────────────────────────────────────────

async def setup_inspiration_feed(page: Page) -> bool:
    """Configures the X Creator Studio Inspiration page, switching country from India to All Countries if needed."""
    logger.info("[INSPIRATION] Setting up Inspiration feed filters...")
    try:
        country_selectors = [
            "xpath=//div[contains(text(), 'IND')]",
            "xpath=//span[contains(text(), 'IND')]",
            "xpath=//div[contains(text(), 'IN IND')]",
            "text=IN IND",
            "text=IND",
            "xpath=//div[contains(@class, 'Inspiration')]//div[contains(text(), 'IND')]",
            "xpath=//div[contains(@style, 'border')]//div[contains(text(), 'IND')]"
        ]

        country_btn = None
        for sel in country_selectors:
            try:
                elem = page.locator(sel).first
                if await elem.is_visible():
                    country_btn = elem
                    break
            except Exception:
                pass

        if country_btn:
            logger.info("[INSPIRATION] Found 'IND' country filter button. Clicking to open location modal...")
            await country_btn.click()
            await asyncio.sleep(2)

            modal_selectors = [
                "text=All Countries",
                "xpath=//div[contains(text(), 'All Countries')]",
                "xpath=//span[contains(text(), 'All Countries')]",
                "xpath=//*[text()='All Countries']"
            ]

            selected_all = False
            for m_sel in modal_selectors:
                try:
                    all_countries_opt = page.locator(m_sel).first
                    if await all_countries_opt.is_visible():
                        logger.info("[INSPIRATION] Found 'All Countries' option. Clicking...")
                        await all_countries_opt.click()
                        selected_all = True
                        break
                except Exception:
                    pass

            if selected_all:
                logger.info("[INSPIRATION] Country filter changed to 'All Countries' successfully.")
                await asyncio.sleep(4)
                return True
            else:
                logger.warning("[INSPIRATION] Could not find the 'All Countries' option.")
        else:
            logger.info("[INSPIRATION] Country filter button 'IND' not found. Might already be set.")

        return True
    except Exception as e:
        logger.error(f"[INSPIRATION] Error configuring Inspiration feed: {e}")
        return False


# ──────────────────────────────────────────────────────────────────
# UTILITY — Username detection
# ──────────────────────────────────────────────────────────────────

async def get_logged_in_username(page: Page) -> str:
    """Extracts the logged-in user's handle from the sidebar switcher button."""
    try:
        switcher = await page.query_selector('[data-testid="SideNav_AccountSwitcher_Button"]')
        if switcher:
            text = await switcher.inner_text()
            match = re.search(r"@(\w+)", text)
            if match:
                username = match.group(1).lower()
                logger.info(f"Successfully detected logged-in user handle: @{username}")
                return username
    except Exception as e:
        logger.debug(f"Failed to extract logged-in username switcher: {e}")
    return ""
