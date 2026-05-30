import asyncio
import re
import logging
import random
from playwright.async_api import async_playwright, Page, BrowserContext
import config
from config import USER_DATA_DIR, MIN_TWEET_VIEWS, MIN_REPLY_VIEWS

logger = logging.getLogger("bot.browser")

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
        # Match only digits
        digits_only = re.sub(r"[^\d]", "", cleaned)
        return int(digits_only) if digits_only else 0
    except ValueError:
        return 0

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

async def get_browser_context(playwright) -> BrowserContext:
    """Launches and returns a persistent context matching your configuration."""
    # To reduce bot detection issues, we start headful by default, disable the Automation flag,
    # and use standard user agents.
    context = await playwright.chromium.launch_persistent_context(
        user_data_dir=USER_DATA_DIR,
        headless=False,  # Headless is easily blocked by Cloudflare and X
        args=[
            "--disable-blink-features=AutomationControlled",
            "--start-maximized"
        ],
        no_viewport=True
    )
    return context

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
                await btn.click()
                logger.info(f"Dismissed popup using selector: '{selector}'")
                await asyncio.sleep(0.5)
        except Exception:
            pass

async def human_scroll(page: Page, scrolls: int = 3):
    """Performs natural-looking scrolls with random pauses to simulate a human user."""
    # Dismiss any active blocking popups first
    await dismiss_popups(page)
    
    logger.info(f"Performing {scrolls} human-like scrolls...")
    for i in range(scrolls):
        # Determine a random scroll distance
        distance = random.randint(300, 700)
        await page.evaluate(f"window.scrollBy(0, {distance})")
        # Random sleep between scrolls
        await asyncio.sleep(random.uniform(0.8, 2.2))
        
        # Occasionally scroll up slightly to look human
        if random.random() < 0.2:
            up_distance = random.randint(-150, -50)
            await page.evaluate(f"window.scrollBy(0, {up_distance})")
            await asyncio.sleep(random.uniform(0.5, 1.2))

async def extract_tweets_from_feed(page: Page) -> list[dict]:
    """Scrapes the current feed and extracts basic metrics for tweets found."""
    tweets = []
    
    # X uses article elements for tweets
    tweet_elements = await page.query_selector_all('article[data-testid="tweet"]')
    logger.info(f"Found {len(tweet_elements)} tweets in current view.")
    
    for elem in tweet_elements:
        try:
            # 1. Get the Tweet ID and URL from the link
            # The link usually matches /username/status/123456789
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
        
    # Get original tweet text
    main_tweet = await page.query_selector('article[data-testid="tweet"]')
    original_text = ""
    has_image = False
    
    if main_tweet:
        text_elem = await main_tweet.query_selector('div[data-testid="tweetText"]')
        original_text = await text_elem.inner_text() if text_elem else ""
        
        # Check if visual media is present (photo, video, link previews, or custom card wrappers)
        if config.PROCESS_IMAGES:
            try:
                media_elem = await main_tweet.query_selector(
                    'div[data-testid="tweetPhoto"], div[data-testid="videoPlayer"], div[data-testid="card.wrapper"], img[src*="media"]'
                )
                if media_elem:
                    logger.info("Visual media detected inside tweet. Capturing tweet screenshot for Gemini multimodal input...")
                    # Take screenshot of the entire main_tweet block
                    await main_tweet.screenshot(path=config.TEMP_IMAGE_PATH)
                    has_image = True
            except Exception as e_snap:
                logger.error(f"Failed to capture tweet media screenshot: {e_snap}")
        
    # Scroll once or twice to load replies
    await human_scroll(page, scrolls=2)
    
    # Extract replies
    # Replies are articles but we must exclude the original tweet (which is the first article).
    articles = await page.query_selector_all('article[data-testid="tweet"]')
    logger.info(f"Found {len(articles)} total articles on details page.")
    
    top_replies = []
    
    # Skip index 0 because that is the original parent tweet. Limit to maximum 10 comments for context.
    for elem in articles[1:11]:
        try:
            # Extract Reply Text
            text_elem = await elem.query_selector('div[data-testid="tweetText"]')
            reply_text = await text_elem.inner_text() if text_elem else ""
            if not reply_text:
                continue
                
            # Extract Reply Views
            views = await extract_views_from_tweet_element(elem)
                    
            # Extract Likes
            like_elem = await elem.query_selector('div[data-testid="like"]')
            likes_text = await like_elem.inner_text() if like_elem else "0"
            likes = parse_x_number(likes_text)
            
            # Extract Reposts
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
        "has_image": has_image
    }

async def post_reply(page: Page, tweet_url: str, reply_text: str) -> bool:
    """Navigates to the tweet, types the reply naturally, clicks post, and verifies."""
    logger.info(f"Navigating to tweet to post reply: {tweet_url}")
    await page.goto(tweet_url)
    
    # Dismiss any active blocking popups
    await dismiss_popups(page)
    
    try:
        # Wait for reply editor to become available or visible
        # Standard reply box usually contains editor-rich-text or is triggered by a div/button
        reply_editor_selector = 'div[data-testid="tweetTextarea_0"]'
        await page.wait_for_selector(reply_editor_selector, timeout=10000)
        
        # Click on the editor to focus
        await page.click(reply_editor_selector)
        await asyncio.sleep(random.uniform(0.5, 1.5))
        
        # Human-like typing
        # Type character by character with random small delays
        logger.info(f"Typing reply: '{reply_text}'")
        for char in reply_text:
            await page.keyboard.type(char)
            # 20ms to 120ms random typing delay
            await asyncio.sleep(random.uniform(0.02, 0.12))
            
        await asyncio.sleep(random.uniform(1.0, 2.0))
        
        # Click reply/post button using multiple fallback selectors
        post_btn_selectors = [
            'div[data-testid="tweetButtonInline"]',
            'button[data-testid="tweetButtonInline"]',
            'div[data-testid="tweetButton"]',
            'button[data-testid="tweetButton"]',
            'div[role="button"] span:has-text("Reply")',
            'div[role="button"] span:has-text("Post")',
            'button:has-text("Reply")',
            'button:has-text("Post")'
        ]
        
        button_clicked = False
        for selector in post_btn_selectors:
            try:
                btn = await page.query_selector(selector)
                if btn and await btn.is_visible():
                    await btn.click()
                    button_clicked = True
                    logger.info(f"Successfully clicked reply button using selector: '{selector}'")
                    break
            except Exception as e_sel:
                logger.debug(f"Selector '{selector}' did not match or click: {e_sel}")
                
        if not button_clicked:
            raise RuntimeError("Could not find or click any visible Reply/Post button.")
            
        logger.info("Reply post button clicked. Waiting for confirmation...")
        await asyncio.sleep(random.uniform(3.0, 5.0)) # Wait to let the network request finish
        return True
        
    except Exception as e:
        logger.error(f"Failed to post reply: {e}")
        return False

async def setup_inspiration_feed(page: Page) -> bool:
    """Configures the X Creator Studio Inspiration page, switching country from India to All Countries if needed."""
    logger.info("[INSPIRATION] Setting up Inspiration feed filters...")
    try:
        # Check if country button is present and click it if it represents "IND" or "India"
        # The user has "IN IND" or "IND" pill visible at the top right of the Inspiration section
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
            
            # Locate the "All Countries" option in the overlay list
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
                        logger.info("[INSPIRATION] Found 'All Countries' option. Clicking to apply worldwide filter...")
                        await all_countries_opt.click()
                        selected_all = True
                        break
                except Exception:
                    pass
                    
            if selected_all:
                logger.info("[INSPIRATION] Country filter changed to 'All Countries' successfully. Waiting for feed updates...")
                await asyncio.sleep(4)
                return True
            else:
                logger.warning("[INSPIRATION] Could not find the 'All Countries' option in the filter modal.")
        else:
            logger.info("[INSPIRATION] Country filter button 'IND' not found. It might already be set to 'All Countries'.")
            
        return True
    except Exception as e:
        logger.error(f"[INSPIRATION] Error configuring Inspiration feed country filter: {e}")
        return False

