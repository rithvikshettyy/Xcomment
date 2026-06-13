import asyncio
import datetime
import logging
import os
import random
import sys
import argparse
from playwright.async_api import async_playwright

import config
import db
import browser
import replier
import notifier

# Setup Rich and Premium Logger configuration
import logging.handlers
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.handlers.RotatingFileHandler(
            "bot.log",
            maxBytes=20 * 1024,  # 20 KB limit (keeps approx 150-200 lines of latest logs)
            backupCount=0,       # Discard older logs, no backup files
            encoding="utf-8"
        )
    ]
)
logger = logging.getLogger("bot.main")

def set_keep_awake(enabled: bool):
    """Prevents Windows system sleep and screen blanking during active cooling break using SetThreadExecutionState."""
    try:
        import ctypes
        if enabled:
            # ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001 | 0x00000002)
            logger.info("[KEEP AWAKE] Enabled Windows keep-awake state. Laptop will not sleep.")
        else:
            # ES_CONTINUOUS
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
            logger.info("[KEEP AWAKE] Restored normal sleep state settings.")
    except Exception as e:
        logger.warning(f"[KEEP AWAKE] Failed to configure SetThreadExecutionState: {e}")

def is_in_time_window() -> bool:
    """Checks if current time in IST is within active hours."""
    if getattr(config, "RUN_24_7", False) or config.BYPASS_WINDOW_FOR_TESTING:
        logger.info("[TIME CHECK] Running in 24/7 mode (or bypassing time window check).")
        return True
        
    # Get current UTC time and convert to IST (UTC + 5:30)
    utc_now = datetime.datetime.now(datetime.timezone.utc)
    ist_tz = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    ist_now = utc_now.astimezone(ist_tz)
    
    current_hour = ist_now.hour
    
    in_window = config.WINDOW_START_HOUR <= current_hour < config.WINDOW_END_HOUR
    logger.info(f"[TIME CHECK] Current IST time: {ist_now.strftime('%I:%M %p')}. In target window: {in_window}")
    return in_window

def get_seconds_until_window() -> int:
    """Returns number of seconds to sleep until the window starts (1:00 AM IST)."""
    utc_now = datetime.datetime.now(datetime.timezone.utc)
    ist_tz = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    ist_now = utc_now.astimezone(ist_tz)
    
    target = ist_now.replace(hour=config.WINDOW_START_HOUR, minute=0, second=0, microsecond=0)
    if ist_now >= target:
        # Move target to tomorrow
        target += datetime.timedelta(days=1)
        
    delta = target - ist_now
    return int(delta.total_seconds())

def get_seconds_remaining_in_window() -> int:
    """Returns the number of seconds remaining until the end of the active IST window today."""
    utc_now = datetime.datetime.now(datetime.timezone.utc)
    ist_tz = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    ist_now = utc_now.astimezone(ist_tz)
    
    # If we are before the window start, the full window duration is remaining
    if ist_now.hour < config.WINDOW_START_HOUR:
        return (config.WINDOW_END_HOUR - config.WINDOW_START_HOUR) * 3600
        
    target = ist_now.replace(hour=config.WINDOW_END_HOUR, minute=0, second=0, microsecond=0)
    if ist_now > target:
        return 0
    delta = target - ist_now
    return int(delta.total_seconds())

def calculate_even_spacing_delay(replies_sent_today: int, daily_cap: int) -> int:
    """Calculates the target spacing delay (in seconds) to evenly distribute replies across the remaining active window, or enforces a fixed pacing gap."""
    if getattr(config, "USE_RANDOM_PACING", False):
        import random
        return random.randint(config.MIN_PACING_SECS, config.MAX_PACING_SECS)
        
    if getattr(config, "USE_FIXED_PACING", False):
        return getattr(config, "PACING_SECS", 1200)
        
    remaining_replies = max(1, daily_cap - replies_sent_today)
    seconds_left = get_seconds_remaining_in_window()
    
    # If we haven't entered the window yet, use the full window duration
    if seconds_left <= 0:
        seconds_left = (config.WINDOW_END_HOUR - config.WINDOW_START_HOUR) * 3600
        
    spacing = int(seconds_left / remaining_replies)
    
    # Bound the spacing based on our config parameters
    spacing = max(config.MIN_PACING_SECS, min(spacing, config.MAX_PACING_SECS))
    return spacing


def is_tech_tweet(tweet_text: str) -> bool:
    """Checks if a tweet text contains tech-related keywords for proactive targeting."""
    import re
    text_lower = tweet_text.lower()
    for keyword in config.PROACTIVE_TECH_KEYWORDS:
        # For short keywords (<=3 chars), use word boundary to avoid false positives
        # e.g., "ai" should not match inside "again"
        if len(keyword) <= 3:
            if re.search(r'\b' + re.escape(keyword) + r'\b', text_lower):
                return True
        else:
            if keyword in text_lower:
                return True
    return False


def pick_proactive_target(candidates: list) -> dict:
    """
    Picks a tweet for proactive commenting from feed candidates.
    Prioritizes tech-related content, falls back to random selection.
    Requires minimum PROACTIVE_MIN_VIEWS.
    """
    # Filter candidates above minimum proactive threshold
    viable = [c for c in candidates if c["views"] >= config.PROACTIVE_MIN_VIEWS]
    
    if not viable:
        logger.info("[PROACTIVE] No viable candidates above proactive view threshold.")
        return None
    
    # Separate tech tweets from general tweets
    tech_tweets = [c for c in viable if is_tech_tweet(c["text"])]
    general_tweets = [c for c in viable if not is_tech_tweet(c["text"])]
    
    # 70% chance to pick tech, 30% chance random (if tech available)
    if tech_tweets and random.random() < 0.7:
        target = random.choice(tech_tweets)
        logger.info(f"[PROACTIVE] Selected TECH tweet: {target['url']} ({target['views']} views)")
    elif viable:
        target = random.choice(viable)
        logger.info(f"[PROACTIVE] Selected RANDOM tweet: {target['url']} ({target['views']} views)")
    else:
        return None
    
    return target


async def run_bot(dry_run: bool = False):
    """Main execution loop for X automation bot."""
    logger.info("=" * 60)
    logger.info(f"X AUTOMATION BOT STARTING (Dry Run: {dry_run})")
    logger.info(f"LLM Backend: Ollama ({config.OLLAMA_MODEL})")
    logger.info(f"Proactive Posting: {'ENABLED' if config.PROACTIVE_POSTING_ENABLED else 'DISABLED'}")
    logger.info("=" * 60)
    
    # Initialize SQLite database
    db.init_db()
    
    # Track session metrics for human-like session breaks
    session_reply_count = 0
    session_break_threshold = config.SESSION_BREAK_AFTER_REPLIES
    scan_cycle_counter = 0  # Tracks cycles for proactive mode triggering
    
    # Initialize Playwright
    async with async_playwright() as p:
        logger.info("Launching stealth browser...")
        try:
            context = await browser.get_browser_context(p)
            page = await context.new_page()
            
            # Go to X home/explore page to start
            logger.info("Navigating to initial target timeline feed...")
            initial_feed = config.FEEDS_TO_SCAN[0]
            await page.goto(initial_feed)
            await asyncio.sleep(random.uniform(4, 7))
            
            # Verify if user is logged in
            login_needed = await page.query_selector('a[data-testid="loginButton"]')
            if login_needed:
                logger.error("User is NOT logged in! Please run 'login_helper.py' first to authenticate.")
                await context.close()
                return
                
            logger.info("Successfully loaded logged-in session.")
            
            # Dynamically extract logged-in username handle for double-reply guards
            my_username = await browser.get_logged_in_username(page)
            if my_username:
                config.MY_USERNAME = my_username
                
            last_post_time = None
            current_feed_idx = 0
            
            while True:
                try:
                    # 1. Check time window
                    if not is_in_time_window():
                        sleep_secs = get_seconds_until_window()
                        logger.info(f"Outside of IST replying window. Sleeping for {sleep_secs} seconds ({sleep_secs / 3600:.2f} hours).")
                        await asyncio.sleep(sleep_secs)
                        continue
                        
                    # 2. Check and initialize daily cap
                    date_str = datetime.date.today().isoformat()
                    daily_cap = db.get_or_create_daily_cap(date_str)
                    replies_sent = db.get_replies_sent_today(date_str)
                    
                    logger.info(f"[DAILY STATS] Date: {date_str} | Reply Cap: {daily_cap} | Replies Sent: {replies_sent}")
                    
                    if replies_sent >= daily_cap:
                        logger.info("Daily reply cap reached. Sleeping until tomorrow...")
                        await asyncio.sleep(3600)
                        continue
                    
                    # ──────────────────────────────────────────────────────
                    # SESSION BREAK — Simulate stepping away after N replies
                    # ──────────────────────────────────────────────────────
                    if session_reply_count >= session_break_threshold:
                        break_duration = random.randint(config.SESSION_BREAK_MIN_SECS, config.SESSION_BREAK_MAX_SECS)
                        logger.info(f"[SESSION BREAK] Taking a human-like break after {session_reply_count} replies. "
                                    f"Sleeping {break_duration}s ({break_duration / 60:.1f} min)...")
                        
                        set_keep_awake(True)
                        await asyncio.sleep(break_duration)
                        set_keep_awake(False)
                        
                        # Reset session counter with new random threshold
                        session_reply_count = 0
                        session_break_threshold = random.randint(8, 15)
                        logger.info(f"[SESSION BREAK] Break over. Next break after {session_break_threshold} replies.")
                        continue
                    
                    # ──────────────────────────────────────────────────────
                    # IDLE BROWSE — Occasionally just scroll without posting
                    # ──────────────────────────────────────────────────────
                    if random.random() < config.IDLE_BROWSE_CHANCE:
                        logger.info("[IDLE] Random idle browsing cycle triggered (no posting this cycle).")
                        await browser.idle_browse(page)
                        scan_cycle_counter += 1
                        continue
                        
                    # 3. Scan main/explore timeline
                    target_feed = config.FEEDS_TO_SCAN[current_feed_idx]
                    if page.url != target_feed and target_feed not in page.url:
                        logger.info(f"Navigating to timeline feed: {target_feed} to scan...")
                        await page.goto(target_feed)
                        await asyncio.sleep(random.uniform(4, 7))
                        
                    if "inspiration" in target_feed:
                        await browser.setup_inspiration_feed(page)
                        
                    logger.info(f"Scanning timeline feed '{target_feed}' for opportunities...")
                    await browser.human_scroll(page, scrolls=random.randint(2, 4))
                    candidates = await browser.extract_tweets_from_feed(page)
                    
                    logger.info(f"Extracted {len(candidates)} candidates from view.")
                    
                    scan_cycle_counter += 1
                    
                    # ──────────────────────────────────────────────────────
                    # DECIDE: Proactive vs Reactive mode for this cycle
                    # ──────────────────────────────────────────────────────
                    is_proactive_cycle = (
                        config.PROACTIVE_POSTING_ENABLED
                        and scan_cycle_counter % config.PROACTIVE_CYCLE_FREQUENCY == 0
                    )
                    
                    if is_proactive_cycle:
                        logger.info("[PROACTIVE] This is a proactive posting cycle — targeting random/tech content.")
                    
                    qualified_tweet = None
                    target_views = 0
                    max_reply_views_observed = 0
                    
                    if is_proactive_cycle:
                        # ──────────────────────────────────────────────
                        # PROACTIVE MODE — Pick random/tech tweet
                        # ──────────────────────────────────────────────
                        # Filter out already-processed tweets
                        fresh_candidates = [c for c in candidates if not db.has_replied(c["id"])]
                        proactive_target = pick_proactive_target(fresh_candidates)
                        
                        if proactive_target:
                            # Open detail page to get context
                            detail_page = await context.new_page()
                            try:
                                details = await browser.analyze_tweet_details(detail_page, proactive_target["url"])
                                
                                if details.get("is_restricted", False):
                                    logger.info("[PROACTIVE] Target has restricted replies. Skipping.")
                                    db.save_reply(proactive_target["id"], proactive_target["url"],
                                                  proactive_target["text"], "[RESTRICTED_REPLIES_GUARD]",
                                                  proactive_target["views"], 0)
                                    await detail_page.close()
                                elif details.get("has_self_reply", False):
                                    logger.info("[PROACTIVE] Already replied to this tweet. Skipping.")
                                    db.save_reply(proactive_target["id"], proactive_target["url"],
                                                  details["original_text"] or proactive_target["text"],
                                                  "[EXISTING_REPLY_GUARD]",
                                                  proactive_target["views"], 0)
                                    await detail_page.close()
                                else:
                                    replies = details["replies"]
                                    best_reply_views = max([rep["views"] for rep in replies]) if replies else 0
                                    min_engagement = getattr(config, "MIN_REPLY_IMPRESSIONS_FOR_ENGAGEMENT", 10000)
                                    if best_reply_views >= min_engagement:
                                        qualified_tweet = proactive_target
                                        qualified_tweet["text"] = details["original_text"] or proactive_target["text"]
                                        qualified_tweet["top_replies"] = replies
                                        qualified_tweet["has_image"] = details.get("has_image", False)
                                        qualified_tweet["is_proactive"] = True
                                        target_views = proactive_target["views"]
                                        max_reply_views_observed = best_reply_views
                                        logger.info(f"[PROACTIVE] Target qualified! Best reply views: {best_reply_views}")
                                        await detail_page.close()
                                    else:
                                        logger.info(f"[PROACTIVE] Target does not have any reply with >= {min_engagement} views (best: {best_reply_views}). Skipping.")
                                        await detail_page.close()
                            except Exception as e_proactive:
                                logger.error(f"[PROACTIVE] Error analyzing proactive target: {e_proactive}")
                            finally:
                                if not detail_page.is_closed():
                                    await detail_page.close()
                    
                    if not qualified_tweet:
                        # ──────────────────────────────────────────────
                        # REACTIVE MODE — Standard high-view targeting
                        # ──────────────────────────────────────────────
                        for candidate in candidates:
                            tweet_id = candidate["id"]
                            tweet_url = candidate["url"]
                            tweet_views = candidate["views"]
                            
                            logger.info(f"Checking candidate: ID={tweet_id} | Views={tweet_views} | URL={tweet_url}")
                            
                            # Criteria 1: Already processed?
                            if db.has_replied(tweet_id):
                                logger.info(f"-> Already processed {tweet_id}. Skipping.")
                                continue
                                
                            # Criteria 2: Views threshold
                            if tweet_views < config.MIN_TWEET_VIEWS:
                                logger.info(f"-> Views ({tweet_views}) below limit ({config.MIN_TWEET_VIEWS}). Skipping.")
                                continue
                                
                            # Criteria 3: Open details, extract replies
                            logger.info(f"-> Target tweet qualifies for detailed analysis.")
                            
                            detail_page = await context.new_page()
                            try:
                                details = await browser.analyze_tweet_details(detail_page, tweet_url)
                                
                                if details.get("is_restricted", False):
                                    logger.info(f"-> [RESTRICTION GUARD] Tweet replies are locked/restricted. Skipping.")
                                    db.save_reply(tweet_id, tweet_url, candidate["text"],
                                                  "[RESTRICTED_REPLIES_GUARD]", tweet_views, 0)
                                    await detail_page.close()
                                    continue
                                    
                                if details.get("has_self_reply", False):
                                    logger.info(f"-> [DOUBLE REPLY GUARD] Already commented on this tweet.")
                                    db.save_reply(tweet_id, tweet_url,
                                                  details["original_text"] or candidate["text"],
                                                  "[EXISTING_REPLY_GUARD]", tweet_views, 0)
                                    await detail_page.close()
                                    continue
                                    
                                replies = details["replies"]
                                logger.info(f"-> Found {len(replies)} replies on details page.")
                                
                                # Criteria 4: Reply quality analysis
                                avg_views = 0
                                best_reply_views = 0
                                
                                if len(replies) > 0:
                                    total_reply_views = sum(rep["views"] for rep in replies)
                                    avg_views = total_reply_views / len(replies)
                                    
                                    for rep in replies:
                                        rep_views = rep["views"]
                                        if rep_views > best_reply_views:
                                            best_reply_views = rep_views
                                
                                min_engagement = getattr(config, "MIN_REPLY_IMPRESSIONS_FOR_ENGAGEMENT", 10000)
                                qualifies = (best_reply_views >= min_engagement)
                                
                                logger.info(f"-> Thread metrics: Avg Views={avg_views:.1f} | Best Reply Views={best_reply_views} (target >= {min_engagement})")
                                
                                if qualifies:
                                    qualified_tweet = candidate
                                    qualified_tweet["text"] = details["original_text"] or candidate["text"]
                                    qualified_tweet["top_replies"] = replies
                                    qualified_tweet["has_image"] = details.get("has_image", False)
                                    qualified_tweet["is_proactive"] = False
                                    target_views = tweet_views
                                    max_reply_views_observed = best_reply_views
                                    logger.info(f"-> SUCCESS: Qualified opportunity found! Max reply views = {max_reply_views_observed}")
                                    await detail_page.close()
                                    break
                                else:
                                    logger.info("-> Opportunity did not qualify (no reply with >= 10K views). Skipping.")
                                    
                            except Exception as e:
                                logger.error(f"Error checking tweet details: {e}")
                            finally:
                                if not detail_page.is_closed():
                                    await detail_page.close()
                                    
                    # 4. Process qualified opportunity
                    if qualified_tweet:
                        mode_label = "PROACTIVE" if qualified_tweet.get("is_proactive", False) else "REACTIVE"
                        
                        # Random skip chance for human behavior simulation
                        if random.random() < config.SKIP_CHANCE:
                            logger.info(f"[HUMAN BEHAVIOR] Randomly deciding to skip this [{mode_label}] opportunity: {qualified_tweet['url']}")
                            await asyncio.sleep(random.uniform(1, 3))
                            continue
                            
                        logger.info(f"[{mode_label}] Processing target: {qualified_tweet['url']}")
                        
                        # Generate candidate replies via Ollama
                        image_arg = config.TEMP_IMAGE_PATH if qualified_tweet.get("has_image", False) else None
                        is_proactive = qualified_tweet.get("is_proactive", False)
                        
                        try:
                            best_reply, candidates_replies = replier.generate_best_reply(
                                qualified_tweet["text"],
                                qualified_tweet.get("top_replies", [])[:5],
                                image_path=image_arg,
                                is_proactive=is_proactive
                            )
                            
                            logger.info(f"Generated {len(candidates_replies)} candidates:")
                            for idx, cand in enumerate(candidates_replies):
                                logger.info(f"  [{idx+1}] {cand}")
                                
                            logger.info(f"Selected strongest reply: '{best_reply}'")
                            
                        except replier.LLMException as eq:
                            logger.warning("=" * 60)
                            logger.warning(f"LLM ERROR: {eq}")
                            logger.warning("=" * 60)
                            
                            err_msg = str(eq)
                            
                            # Check if it's a connection error (Ollama not running)
                            if "cannot connect" in err_msg.lower():
                                logger.critical("Ollama is not running. Please start it with 'ollama serve'.")
                                logger.info("Waiting 60s before retrying...")
                                await asyncio.sleep(60)
                                continue
                            
                            # Check if model not found
                            if "not found" in err_msg.lower():
                                logger.critical(f"Model '{config.OLLAMA_MODEL}' not available. Pull it: 'ollama pull {config.OLLAMA_MODEL}'")
                                logger.info("Waiting 60s before retrying...")
                                await asyncio.sleep(60)
                                continue
                            
                            # Generic retry with backoff
                            logger.warning("LLM request failed. Retrying after 30s...")
                            await asyncio.sleep(30)
                            continue
                        
                        # Safety check
                        if replier.safety_check(best_reply, qualified_tweet["text"]):
                            if dry_run:
                                logger.info(f"[DRY RUN] Would post [{mode_label}] reply: '{best_reply}' on {qualified_tweet['url']}")
                                db.save_reply(
                                    qualified_tweet["id"],
                                    qualified_tweet["url"],
                                    qualified_tweet["text"],
                                    f"[DRY_RUN][{mode_label}] {best_reply}",
                                    target_views,
                                    max_reply_views_observed
                                )
                                db.increment_replies_sent(date_str)
                                session_reply_count += 1
                                
                                # Enforce pacing delay
                                target_delay = calculate_even_spacing_delay(replies_sent, daily_cap)
                                jitter = random.randint(-int(target_delay * 0.15), int(target_delay * 0.15)) if target_delay > 10 else 0
                                cooldown = max(config.MIN_PACING_SECS, target_delay + jitter)
                                logger.info(f"[DRY RUN COOLDOWN] Sleeping for {cooldown}s before next scan...")
                                await asyncio.sleep(cooldown)
                            else:
                                logger.info(f"Posting [{mode_label}] reply to X...")
                                success = await browser.post_reply(page, qualified_tweet["url"], best_reply)
                                if success:
                                    logger.info(f"[{mode_label}] Reply posted successfully!")
                                    db.save_reply(
                                        qualified_tweet["id"],
                                        qualified_tweet["url"],
                                        qualified_tweet["text"],
                                        f"[{mode_label}] {best_reply}",
                                        target_views,
                                        max_reply_views_observed
                                    )
                                    db.increment_replies_sent(date_str)
                                    session_reply_count += 1
                                    
                                    # Enforce cooling/pacing delay AFTER a successful post
                                    target_delay = calculate_even_spacing_delay(replies_sent + 1, daily_cap)
                                    jitter = random.randint(-int(target_delay * 0.15), int(target_delay * 0.15)) if target_delay > 10 else 0
                                    cooldown = max(config.MIN_PACING_SECS, target_delay + jitter)
                                    logger.info(f"[COOLING] Sleeping for {cooldown}s before next scan...")
                                    await asyncio.sleep(cooldown)
                                else:
                                    logger.error("Failed to post reply.")
                        else:
                            logger.warning("Reply failed safety validation. Skipping post.")
                            
                        # Cleanup the temporary screenshot if it was created
                        if image_arg and os.path.exists(image_arg):
                            try:
                                os.remove(image_arg)
                                logger.info(f"Cleaned up temporary multimodal screenshot '{image_arg}'")
                            except Exception as e_del:
                                logger.debug(f"Failed to delete temp screenshot: {e_del}")
                                
                        logger.info(f"Staying on feed index {current_feed_idx} ({config.FEEDS_TO_SCAN[current_feed_idx]}) for next scan.")
                        
                    else:
                        logger.info("No qualified opportunities in current view.")
                        current_feed_idx = (current_feed_idx + 1) % len(config.FEEDS_TO_SCAN)
                        logger.info(f"Switching feed to index {current_feed_idx} ({config.FEEDS_TO_SCAN[current_feed_idx]}).")
                        await asyncio.sleep(random.uniform(1.5, 3.5))
                        
                except Exception as e_loop:
                    logger.error(f"[TEMPORARY ERROR] Unexpected error during bot loop: {e_loop}")
                    
                    # Detect if the browser, page, or context has crashed/closed
                    err_str = str(e_loop).lower()
                    is_browser_crash = ("closed" in err_str or "crashed" in err_str or "detached" in err_str or "target page" in err_str or "context" in err_str)
                    
                    if is_browser_crash:
                        logger.warning("[RECOVERY] Browser session crashed/closed. Re-initializing...")
                        try:
                            await page.close()
                            await context.close()
                        except Exception:
                            pass
                        
                        logger.info("Re-initializing stealth browser context...")
                        await asyncio.sleep(random.uniform(8, 15))
                        try:
                            context = await browser.get_browser_context(p)
                            page = await context.new_page()
                            await page.goto(config.FEEDS_TO_SCAN[current_feed_idx])
                            await asyncio.sleep(random.uniform(4, 7))
                            logger.info("Browser session successfully re-initialized.")
                            continue
                        except Exception as e_reinit:
                            logger.critical(f"Failed to re-initialize browser session: {e_reinit}")
                            await asyncio.sleep(30)
                            continue
                            
                    # Standard temporary error
                    current_feed_idx = (current_feed_idx + 1) % len(config.FEEDS_TO_SCAN)
                    logger.info(f"Switching to feed index {current_feed_idx} ({config.FEEDS_TO_SCAN[current_feed_idx]}) after error.")
                    await asyncio.sleep(random.uniform(20, 40))
                    
        except replier.LLMException as eq:
            logger.critical(f"LLM CRITICAL ERROR: {eq}")
            notifier.send_error_email(f"LLM Error: {eq}")
            logger.info("Closing browser and terminating...")
            try:
                await context.close()
            except Exception as e_close:
                logger.error(f"Failed to close context during shutdown: {e_close}")
            logger.info("Bot ended gracefully.")
            sys.exit(0)
        except Exception as e:
            logger.critical(f"An unexpected critical bot error occurred: {e}")
            notifier.send_error_email(f"Catastrophic Unexpected Bot Error: {e}")
            await asyncio.sleep(60)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="X (Twitter) Automation Bot — Stealth Edition")
    parser.add_argument("--dry-run", action="store_true", help="Run the bot in dry-run mode (does not post replies)")
    args = parser.parse_args()
    
    try:
        asyncio.run(run_bot(dry_run=args.dry_run))
    except KeyboardInterrupt:
        logger.info("Bot manually terminated. Goodbye!")
        sys.exit(0)
