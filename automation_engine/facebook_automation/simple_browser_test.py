import asyncio
from playwright.async_api import async_playwright

async def test_browser():
    print("Testing browser launch...")
    
    playwright = await async_playwright().start()
    
    try:
        browser = await playwright.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        
        print("Browser launched successfully!")
        await page.goto("https://www.facebook.com")
        print("Facebook loaded!")
        
        input("Press Enter to close browser...")
        
        await browser.close()
        print("Browser closed")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_browser())
