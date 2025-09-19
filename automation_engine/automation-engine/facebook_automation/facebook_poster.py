import asyncio
import json
import random
import time
from pathlib import Path
from playwright.async_api import async_playwright

class SimpleFacebookPoster:
    def __init__(self, account_name):
        self.account_name = account_name
        self.base_path = Path("C:/Crazy_poster")
        self.account_path = self.base_path / "account-instances" / account_name
        self.browser_profile_path = self.account_path / "browser-profile"
        self.context = None
        self.page = None
    
    def log(self, message):
        print(f"[{self.account_name}] {message}")
    
    async def start_browser(self):
        try:
            self.log("Starting browser...")
            
            playwright = await async_playwright().start()
            
            # Launch persistent context with user data
            self.context = await playwright.chromium.launch_persistent_context(
                user_data_dir=str(self.browser_profile_path),
                headless=False,
                viewport={'width': 1366, 'height': 768}
            )
            
            self.page = await self.context.new_page()
            self.log("Browser started successfully")
            return True
            
        except Exception as e:
            self.log(f"Browser start failed: {e}")
            return False
    
    async def goto_facebook(self):
        try:
            await self.page.goto("https://www.facebook.com")
            self.log("Navigated to Facebook")
            return True
        except Exception as e:
            self.log(f"Navigation failed: {e}")
            return False

    async def login_to_facebook(self):
        try:
            self.log("Checking Facebook login status...")
        
        # Check if already logged in by looking for profile elements
            try:
                await self.page.wait_for_selector('[data-testid="blue_bar_profile_link"]', timeout=5000)
                self.log("Already logged in to Facebook")
                return True
            except:
                self.log("Not logged in. Please login manually in the browser window.")
                self.log("After login, press Enter in this console to continue...")
                input("Press Enter after manual login...")
            
            # Verify login worked
            try:
                await self.page.wait_for_selector('[data-testid="blue_bar_profile_link"]', timeout=10000)
                self.log("Login verified successfully")
                return True
            except:
                self.log("Login verification failed")
                return False
                
        except Exception as e:
         self.log(f"Login process error: {e}")
        return False

    async def navigate_to_marketplace(self):        
        try:
            self.log("Navigating to Facebook Marketplace...")
            await self.page.goto("https://www.facebook.com/marketplace/create/vehicle")
        
            # Wait for the marketplace create page to load
            await self.page.wait_for_selector('[data-testid="marketplace-composer-title-input"]', timeout=15000)
            self.log("Marketplace create page loaded successfully")
            return True
        
        except Exception as e:
             self.log(f"Failed to navigate to Marketplace: {e}")
        return False

    async def close_browser(self):
        try:
            if self.context:
                await self.context.close()
            self.log("Browser closed")
        except Exception as e:
            self.log(f"Error closing browser: {e}")

async def test_poster():
    poster = SimpleFacebookPoster("Account_001")
    
    if await poster.start_browser():
        if await poster.goto_facebook():
            if await poster.login_to_facebook():
                if await poster.navigate_to_marketplace():
                    print("Success! Marketplace create page loaded.")
                    print("Press Enter to close browser...")
                    input()
                else:
                    print("Failed to navigate to Marketplace")
            else:
                print("Facebook login failed")
        else:
            print("Failed to navigate to Facebook")
    else:
        print("Failed to start browser")
    
    await poster.close_browser()
