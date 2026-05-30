import asyncio
import os
import sys
from playwright.async_api import async_playwright
from config import USER_DATA_DIR

async def main():
    print("=" * 60)
    print("X (Twitter) Session Login Helper")
    print("=" * 60)
    print(f"Target Session Directory: {USER_DATA_DIR}")
    print("\nStarting browser. Please sign in to your X (Twitter) account.")
    print("Make sure you are logged in, see your feed, and then close the browser window or press Ctrl+C in this terminal to save session data.")
    print("=" * 60)
    
    # Create profiles directory if not exists
    os.makedirs(USER_DATA_DIR, exist_ok=True)
    
    async with async_playwright() as p:
        try:
            # We use chromium context. Using standard Chrome system installation or Brave can be done,
            # but default chromium in a persistent context is clean and highly portable.
            # Brave/Chrome executable_path can also be configured if necessary.
            context = await p.chromium.launch_persistent_context(
                user_data_dir=USER_DATA_DIR,
                headless=False,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--start-maximized"
                ],
                no_viewport=True
            )
            
            page = await context.new_page()
            await page.goto("https://x.com")
            
            # Loop to keep script running until browser closed or process interrupted
            while True:
                await asyncio.sleep(1)
                
        except KeyboardInterrupt:
            print("\nExiting and saving session context...")
        except Exception as e:
            print(f"\nAn error occurred: {e}")
            print("Please make sure all chromium browser processes are closed before running.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nExiting login helper.")
        sys.exit(0)
