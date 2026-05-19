import pandas as pd
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import re
import random

def extract_number(text):
    if not text:
        return None
    
    text = text.strip().replace(",", "").replace("$", "").lower()
    
    multiplier = 1
    if text.endswith("k"):
        multiplier = 1_000
        text = text[:-1]
    elif text.endswith("m"):
        multiplier = 1_000_000
        text = text[:-1]
    elif text.endswith("b"):
        multiplier = 1_000_000_000
        text = text[:-1]
    
    match = re.search(r"-?\d+(\.\d+)?", text)
    if match:
        return float(match.group()) * multiplier
    return None

INPUT_EXCEL = "data/wefunder_links.xlsx"
OUTPUT_EXCEL = "output/wefunder_uniform_metrics.xlsx"
UNIFORM_METRICS = [
    "Company Name", 
    "Campaign URL", 
    "Funding Platform",
    "Annual Revenue", 
    "Net Profit/Loss", 
    "Total Funding Raised",
    "Current Cash", 
    "Short-Term Debt", 
    "Net Margin", 
    "Gross Margin",
    "Form C Link",
    "Funding Goal Met", 
    "Pct_Goal_Achieved" 
]

options = Options()
options.add_argument("--headless=new")
options.add_argument("--disable-blink-features=AutomationControlled")
options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
service = Service(ChromeDriverManager().install())
browser = webdriver.Chrome(service=service, options=options)

try:
    campaign_urls = pd.read_excel(INPUT_EXCEL).iloc[:, 0].unique().tolist()
    if not campaign_urls:
        raise ValueError("No URLs found in input file")
except Exception as e:
    print(f"Failed to load URLs: {str(e)}")
    campaign_urls = []
    
campaign_urls_with_details = [url + '/details' for url in campaign_urls]

results = []
if campaign_urls_with_details:
    print(f"Analyzing {len(campaign_urls)} campaigns...")

    for i, url in enumerate(campaign_urls_with_details, 1):
        metrics = {key: None for key in UNIFORM_METRICS}
        metrics.update({
            "Campaign URL": url,
            "Funding Platform": "WeFunder",
            "Form C Link": None  
        })
        print("Analyzing campaign " + str(i))
        
        browser.quit() 
        
        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
        service = Service(ChromeDriverManager().install())
        browser = webdriver.Chrome(service=service, options=options)

        try:
            browser.get(url)
            
            try:
                
                percent_element = WebDriverWait(browser, 5).until(
                    EC.presence_of_element_located((By.XPATH, "//div[contains(@class, 'progress')]//span | //div[contains(@class, 'percentage')] | //span[contains(@class, 'percent')]"))
                )
                percent_text = percent_element.text
      
                metrics["Pct_Goal_Achieved"] = extract_number(percent_text)
                print(f"Scraped Goal Achievement: {metrics['Pct_Goal_Achieved']}%")
            except Exception as e:
                print(f"Could not find percentage element: {e}")
                metrics["Pct_Goal_Achieved"] = None

            
            try:
                sec_link_el = WebDriverWait(browser, 8).until(
                    EC.presence_of_element_located((By.XPATH, "//a[contains(@href, 'sec.gov/Archives')]"))
                )
                metrics["Form C Link"] = sec_link_el.get_attribute("href")
            except:
                metrics["Form C Link"] = None

            time.sleep(2.5)

            soup = BeautifulSoup(browser.page_source, "html.parser")

            metrics["Funding Goal Met"] = "Yes" if soup.find("div", class_=lambda x: x and "fully-funded" in (x or "")) else "No"

            try:
                title = soup.find("title")
                metrics["Company Name"] = title.text.split("|")[0].strip() if title else url.split("/")[-1]
            except:
                metrics["Company Name"] = url.split("/")[-1]


            for card in soup.find_all("div", class_=lambda x: x and "pr-2 pb-4 text-center" in str(x)):
                try:
                    text = card.get_text().lower()
                    print(text)
                    value_div = card.find("div", class_=lambda x: x and "text-sm mt-4 mb-2 justify-center flex" in str(x))
                    raw_value = value_div.get_text() if value_div else ""
                    
                    cleaned_value = extract_number(raw_value) if raw_value else None

                    if "net margin" in text or "net profit margin" in text:
                        metrics["Net Margin"] = cleaned_value / 100 if cleaned_value is not None else None
                    elif "gross margin" in text or "gross profit margin" in text:
                        metrics["Gross Margin"] = cleaned_value / 100 if cleaned_value is not None else None
                    elif "revenue" in text:
                        metrics["Annual Revenue"] = cleaned_value
                    elif "net income" in text or "net profit" in text:
                        metrics["Net Profit/Loss"] = cleaned_value
                    elif "net loss" in text:
                        metrics["Net Profit/Loss"] = -abs(cleaned_value) if cleaned_value else None
                    elif "raised" in text and "investors" not in text:
                        metrics["Total Funding Raised"] = cleaned_value
                    elif "cash" in text and ("balance" in text or "hand" in text):
                        metrics["Current Cash"] = cleaned_value
                    elif "short-term debt" in text or "short term debt" in text: 
                        metrics["Short-Term Debt"] = cleaned_value

                except Exception as e:
                    print(f"Error parsing card: {e}")
                    continue

        except Exception as e:
            print(f"SCRAPE FAILED FOR {url}: {str(e)}")

        results.append(metrics)

        if i % 5 == 0:
            pd.DataFrame(results).to_excel(OUTPUT_EXCEL, index=False)

        time.sleep(max(1.5, min(4, random.random() * 3)))

browser.quit()
df_final = pd.DataFrame(results)
df_final.to_excel(OUTPUT_EXCEL, index=False)
print(f"Saved {len([r for r in results if any(r.values())])}/{len(campaign_urls)} campaigns to {OUTPUT_EXCEL}")
