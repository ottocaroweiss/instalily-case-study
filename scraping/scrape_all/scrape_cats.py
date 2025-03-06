import os
import time
import logging
import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from tqdm import tqdm
import xml.etree.ElementTree as ET

from scraping.PartScraper import PartScraper
from scraping.PartScraper import AbstractScraper
from scraping.database import DatabaseHandler
import re
import sqlite3

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)


def process_part( link: str) -> str:
    """
    Worker function to process an individual part page.
    Initializes a new PartScraper instance and calls .scrape_all().
    Returns a status message.
    """
    try:
        # Set up a new DB handler and ensure row_factory is set.
        db = DatabaseHandler()
        scraper = PartScraper(db=db)
        # We pass the URL; manufacturer_id can be extracted by the scraper.
        scraper.new(url=link, manufacturer_id=None)
        scraper.scrape_all()
        db.close()
        logger.info(f"Successfully scraped part: {link}")
        return f"Success: {link}"
    except Exception as e:
        logger.error(f"Error scraping {link}: {e}")
        return f"Error: {link} -> {e}"
        

def extract_refrigerator_dishwasher_links(xml_path: str):
    """
    1) Parse the XML (sitemap or category structure).
    2) For each <url><loc> element, check if it contains 'refrigerator' or 'dishwasher' (ignoring case).
    3) Save matching URLs as a list in JSON.
    """
    # Regex to match case-insensitive "refrigerator" or "dishwasher"
    pattern = re.compile(r"(refrigerator|dishwasher)", re.IGNORECASE)

    # Parse XML
    tree = ET.parse(xml_path)
    root = tree.getroot()

    # We'll store matching links here
    filtered_links = []

    # Because there's a default namespace, we'll do findall with a wildcard
    for url_elem in root.findall('.//{*}url'):
        loc_elem = url_elem.find('{*}loc')
        if loc_elem is not None:
            link = loc_elem.text.strip()
            # Check if it contains the words
            if pattern.search(link):
                filtered_links.append(link)

    return filtered_links


class CategoryScraper(AbstractScraper):
    """
    Scrapes a category page (with pagination) to extract part URLs.
    It requests pages using a URL pattern (e.g., "CategoryParts.htm?start=1") 
    and stops when a page returns no part links.
    """
    def __init__(self, url: str):
        self.url_f = f"{url}/?start={{}}"
        self.url = url

    def get_page_links(self, page_number: int) -> list:
        """
        Fetches a category page and extracts part links using a CSS selector.
        Returns a list of URLs.
        """
        super().__init__()
        self.conn = sqlite3.connect("scraper_data.sqlite", check_same_thread=True)
        url = self.url
        if page_number > 1:
            url = self.url_f.format(page_number)
        logger.info(f"Fetching category page: {url}")
        # Adjust the CSS selector to match the part links on the page
        elements = self.get_items("a.nf__part__detail__title", url)
        links = []
        for el in elements:
            href = el.get("href")
            if href:
                full_url = href if href.startswith("http") else "https://www.partselect.com" + href
                links.append(full_url)
        logger.info(f"Page {page_number}: Found {len(links)} part link(s).")
        return links

    def scrape_category_links(self) -> list:
        """
        Iterates over paginated category pages until a page returns no part links.
        Returns a list of all part URLs found.
        """
        page_number = 1
        all_links = []
        while True:
            links = self.get_page_links(page_number)
            if not links:
                logger.info(f"No links found on page {page_number}; stopping pagination.")
                break
            all_links.extend(links)
            page_number += 1
            time.sleep(1)  # delay to be polite to the server
        logger.info(f"Total part links scraped: {len(all_links)}")
        return all_links

def main():
    # LOAD THE CATEGORY URLS FROM XML
    xml_path = "scraping/PartSelect.com_Sitemap_CategoryPages.xml"
    category_urls = extract_refrigerator_dishwasher_links(xml_path)
    if not category_urls:
        logger.error("No category URLs found in the XML.")
        return
    for category in category_urls:
        logger.info(f"Processing category: {category}")
        cat_scraper = CategoryScraper(url=category)
        
        part_links = cat_scraper.scrape_category_links()
        if not part_links:
            logger.error("No part links found in the category.")
            return

        # Process each part link with a process pool executor
        logger.info("Starting detailed scraping of individual part pages...")
        results = []
        with ProcessPoolExecutor(max_workers=os.cpu_count() - 1) as executor:
            futures = {executor.submit(process_part, link): link for link in part_links}
            for future in tqdm(as_completed(futures), total=len(futures), desc="Scraping Parts"):
                result = future.result()
                results.append(result)
                logger.info(result)