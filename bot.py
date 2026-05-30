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

# Setup Rich and Premium Logger configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("bot.log", encoding="utf-8")
    ]
)
logger = logging.getLogger("bot.main")

def is_in_time_window() -> bool:
    """Checks if current time in IST is within 12:00 AM (0) and 5:00 AM (5)."""
    if config.BYPASS_WINDOW_FOR_TESTING:
        logger.info("[TIME CHECK] Bypassing time window check for testing.")
        return True
        
    # Get current UTC time and convert to IST (UTC + 5:30)
    utc_now = datetime.datetime.now(datetime.timezone.utc)
    ist_tz = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    ist_now = utc_now.astimezone(ist_tz)
    
    current_hour = ist_now.hour
    
    # 12:00 AM IST to 5:00 AM IST
    # 0 <= hour < 5
    in_window = config.WINDOW_START_HOUR <= current_hour < config.WINDOW_END_HOUR
    logger.info(f"[TIME CHECK] Current IST time: {ist_now.strftime('%I:%M %p')}. In target window: {in_window}")
    return in_window

def get_seconds_until_window() -> int:
    """Returns number of seconds to sleep until the window starts (12:00 AM IST)."""
    utc_now = datetime.datetime.now(datetime.timezone.utc)
    ist_tz = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    ist_now = utc_now.astimezone(ist_tz)
    
    # Target is today or tomorrow at 12:00 AM
    target = ist_now.replace(hour=config.WINDOW_START_HOUR, minute=0, second=0, microsecond=0)
    if ist_now >= target:
        # Move target to tomorrow
        target += datetime.timedelta(days=1)
        
    delta = target - ist_now
    return int(delta.total_seconds())

async def run_bot(dry_run: bool = False):
    """Main execution loop for X automation bot."""
    logger.info("=" * 60)
    logger.info(f"X AUTOMATION BOT STARTING (Dry Run: {dry_run})")
    logger.info("=" * 60)
    
    # Initialize SQLite database
    db.init_db()
    
    # Initialize Playwright
    async with async_playwright() as p:
        logger.info("Launching browser...")
        try:
            context = await browser.get_browser_context(p)
            page = await context.new_page()
            
            # Go to X home/explore page to start
            logger.info("Navigating to initial target timeline feed...")
            initial_feed = config.FEEDS_TO_SCAN[0]
            await page.goto(initial_feed)
            await asyncio.sleep(5)
            
            # Verify if user is logged in
            # If not logged in, there is usually a login button or sign up banner
            login_needed = await page.query_selector('a[data-testid="loginButton"]')
            if login_needed:
                logger.error("User is NOT logged in! Please run 'login_helper.py' first to authenticate.")
                await context.close()
                return
                
            logger.info("Successfully loaded logged-in session.")
            
            last_post_time = None
            current_feed_idx = 0
            
            while True:
                # 1. Check time window
                if not is_in_time_window():
                    sleep_secs = get_seconds_until_window()
                    logger.info(f"Outside of IST replying window. Sleeping for {sleep_secs} seconds ({sleep_secs / 3600:.2f} hours) until 12:00 AM IST.")
                    await asyncio.sleep(sleep_secs)
                    continue
                    
                # 2. Check and initialize daily cap
                date_str = datetime.date.today().isoformat()
                daily_cap = db.get_or_create_daily_cap(date_str)
                replies_sent = db.get_replies_sent_today(date_str)
                
                logger.info(f"[DAILY STATS] Date: {date_str} | Reply Cap: {daily_cap} | Replies Sent: {replies_sent}")
                
                if replies_sent >= daily_cap:
                    logger.info("Daily reply cap reached. Sleeping until tomorrow...")
                    # Sleep for an hour and check again
                    await asyncio.sleep(3600)
                    continue
                    
                # 3. Scan main/explore timeline
                target_feed = config.FEEDS_TO_SCAN[current_feed_idx]
                if page.url != target_feed and target_feed not in page.url:
                    logger.info(f"Navigating to timeline feed: {target_feed} to scan...")
                    await page.goto(target_feed)
                    await asyncio.sleep(5) # Let the timeline load fully
                    
                if "inspiration" in target_feed:
                    await browser.setup_inspiration_feed(page)
                    
                logger.info(f"Scanning timeline feed '{target_feed}' for high-opportunity tweets...")
                await browser.human_scroll(page, scrolls=3)
                candidates = await browser.extract_tweets_from_feed(page)
                
                logger.info(f"Extracted {len(candidates)} candidates from view.")
                
                qualified_tweet = None
                target_views = 0
                max_reply_views_observed = 0
                
                for candidate in candidates:
                    tweet_id = candidate["id"]
                    tweet_url = candidate["url"]
                    tweet_views = candidate["views"]
                    
                    logger.info(f"Checking candidate: ID={tweet_id} | Views={tweet_views} | URL={tweet_url}")
                    
                    # Criteria 1: Already processed?
                    if db.has_replied(tweet_id):
                        logger.info(f"-> Already processed {tweet_id}. Skipping.")
                        continue
                        
                    # Criteria 2: Views > 700,000
                    if tweet_views < config.MIN_TWEET_VIEWS:
                        logger.info(f"-> Views ({tweet_views}) below limit ({config.MIN_TWEET_VIEWS}). Skipping.")
                        continue
                        
                    # Criteria 3: Open details, extract replies
                    logger.info(f"-> Target tweet qualifies for detailed analysis. Open in detail view.")
                    
                    # Create a new tab so we don't lose feed place
                    detail_page = await context.new_page()
                    try:
                        details = await browser.analyze_tweet_details(detail_page, tweet_url)
                        replies = details["replies"]
                        
                        logger.info(f"-> Found {len(replies)} replies on details page.")
                        
                        # Criteria 4: 
                        # 1. Average impressions must be >= MIN_AVG_REPLY_VIEWS (1.5k)
                        # 2. At least MIN_HIGH_REPLY_COUNT replies must be >= MIN_REPLY_VIEWS (5k)
                        avg_views = 0
                        high_view_replies_count = 0
                        best_reply_views = 0
                        
                        if len(replies) > 0:
                            total_reply_views = sum(rep["views"] for rep in replies)
                            avg_views = total_reply_views / len(replies)
                            
                            for rep in replies:
                                rep_views = rep["views"]
                                if rep_views >= config.MIN_REPLY_VIEWS:
                                    high_view_replies_count += 1
                                if rep_views > best_reply_views:
                                    best_reply_views = rep_views
                        
                        logger.info(f"-> Thread metrics: Avg Views={avg_views:.1f} (min={config.MIN_AVG_REPLY_VIEWS}) | High View Replies Count={high_view_replies_count} (min={config.MIN_HIGH_REPLY_COUNT})")
                        
                        qualifies = (avg_views >= config.MIN_AVG_REPLY_VIEWS) and (high_view_replies_count >= config.MIN_HIGH_REPLY_COUNT)
                        
                        if qualifies:
                            qualified_tweet = candidate
                            qualified_tweet["text"] = details["original_text"] or candidate["text"]
                            qualified_tweet["top_replies"] = replies
                            qualified_tweet["has_image"] = details.get("has_image", False)
                            target_views = tweet_views
                            max_reply_views_observed = best_reply_views
                            logger.info(f"-> SUCCESS: Qualified opportunity found! Max reply views observed = {max_reply_views_observed}")
                            await detail_page.close()
                            break
                        else:
                            logger.info("-> Opportunity did not qualify (average views too low or fewer than 4 comments exceed 5,000 views). Skipping.")
                            
                    except Exception as e:
                        logger.error(f"Error checking tweet details: {e}")
                    finally:
                        if not detail_page.is_closed():
                            await detail_page.close()
                            
                # 4. Process qualified opportunity
                if qualified_tweet:
                    # Random skip chance for human behavior simulation
                    if random.random() < config.SKIP_CHANCE:
                        logger.info(f"[HUMAN BEHAVIOR] Randomly deciding to skip this qualified opportunity: {qualified_tweet['url']}")
                        await asyncio.sleep(2)
                        continue
                        
                    logger.info(f"Processing target: {qualified_tweet['url']}")
                    
                    # Generate candidate replies via Gemini
                    image_arg = config.TEMP_IMAGE_PATH if qualified_tweet.get("has_image", False) else None
                    
                    candidates_replies = replier.generate_reply_candidates(
                        qualified_tweet["text"],
                        qualified_tweet["top_replies"][:5], # Send top 5 replies for context
                        image_path=image_arg
                    )
                    
                    logger.info(f"Generated {len(candidates_replies)} candidates:")
                    for idx, cand in enumerate(candidates_replies):
                        logger.info(f"  [{idx+1}] {cand}")
                        
                    # Select best candidate
                    best_reply = replier.select_best_reply(
                        candidates_replies,
                        qualified_tweet["text"],
                        qualified_tweet["top_replies"][:5],
                        image_path=image_arg
                    )
                    logger.info(f"Selected strongest reply: '{best_reply}'")
                    
                    # Safety check
                    if replier.safety_check(best_reply, qualified_tweet["text"]):
                        # Enforce randomized delay between comments (spacing)
                        if last_post_time:
                            elapsed = (datetime.datetime.now() - last_post_time).total_seconds()
                            target_delay = random.randint(config.MIN_DELAY_SECS, config.MAX_DELAY_SECS)
                            if elapsed < target_delay:
                                remaining = target_delay - elapsed
                                logger.info(f"[DELAY ENFORCEMENT] Target delay between comments is {target_delay}s. {elapsed:.1f}s elapsed. Sleeping for remaining {remaining:.1f}s before posting...")
                                await asyncio.sleep(remaining)
                                
                        if dry_run:
                            logger.info(f"[DRY RUN] Would post reply: '{best_reply}' on {qualified_tweet['url']}")
                            db.save_reply(
                                qualified_tweet["id"],
                                qualified_tweet["url"],
                                qualified_tweet["text"],
                                f"[DRY_RUN] {best_reply}",
                                target_views,
                                max_reply_views_observed
                            )
                            db.increment_replies_sent(date_str)
                            last_post_time = datetime.datetime.now()
                        else:
                            logger.info("Posting reply to X...")
                            success = await browser.post_reply(page, qualified_tweet["url"], best_reply)
                            if success:
                                logger.info("Reply posted successfully!")
                                db.save_reply(
                                    qualified_tweet["id"],
                                    qualified_tweet["url"],
                                    qualified_tweet["text"],
                                    best_reply,
                                    target_views,
                                    max_reply_views_observed
                                )
                                db.increment_replies_sent(date_str)
                                last_post_time = datetime.datetime.now()
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
                            
                    # No delay here! We immediately proceed to scan for the next opportunity
                    current_feed_idx = (current_feed_idx + 1) % len(config.FEEDS_TO_SCAN)
                    logger.info(f"Switching feed index to {current_feed_idx} (next: {config.FEEDS_TO_SCAN[current_feed_idx]}) for the next scan.")
                    
                else:
                    logger.info("No qualified opportunities in current view.")
                    current_feed_idx = (current_feed_idx + 1) % len(config.FEEDS_TO_SCAN)
                    logger.info(f"Switching feed index to {current_feed_idx} (next: {config.FEEDS_TO_SCAN[current_feed_idx]}) for the next scan.")
                    await asyncio.sleep(2)
                    
        except replier.GeminiQuotaExceededException as eq:
            logger.critical(f"GEMINI API FREE TIER LIMIT REACHED: {eq}")
            logger.info("Closing browser context and terminating cleanly...")
            try:
                await context.close()
            except Exception as e_close:
                logger.error(f"Failed to close context during shutdown: {e_close}")
            logger.info("Bot ended automatically and gracefully.")
            sys.exit(0)
        except Exception as e:
            logger.critical(f"An unexpected critical bot error occurred: {e}")
            await asyncio.sleep(60)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="X (Twitter) Automation Bot")
    parser.add_argument("--dry-run", action="store_true", help="Run the bot in dry-run mode (does not post replies)")
    args = parser.parse_args()
    
    try:
        asyncio.run(run_bot(dry_run=args.dry_run))
    except KeyboardInterrupt:
        logger.info("Bot manually terminated. Goodbye!")
        sys.exit(0)
