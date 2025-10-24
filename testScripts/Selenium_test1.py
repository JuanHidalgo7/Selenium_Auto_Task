# Python program to demonstrate Selenium with Chrome

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# Optional: Configure Chrome options (e.g., headless mode)
options = webdriver.ChromeOptions()
# options.add_argument("--headless")  # Uncomment for headless mode

# Create the Chrome driver
service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=options)

try:
    # Open Google
    driver.get("https://www.google.com/")
    print("Page title:", driver.title)
finally:
    # Close the browser
    driver.quit()
