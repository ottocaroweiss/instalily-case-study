import logging
import time
import json
from abc import abstractmethod
from dataclasses import fields
from typing import Optional

from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    ElementClickInterceptedException, 
    NoSuchElementException,
    StaleElementReferenceException,
    ElementNotInteractableException,
    NoSuchWindowException
)
from selenium.webdriver.remote.webelement import WebElement

from seleniumbase import Driver
from scraping.database import DatabaseHandler  # your own DB handler

# Set up module-level logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

SEARCH_URL = "https://www.partselect.com/api/search/?searchterm="

class AbstractScraper:
    """
    Abstract base class for scrapers on PartSelect.com.

    Responsibilities:
      1) Manages Selenium driver lifecycle (via `seleniumbase.Driver`).
      2) Optionally connects to a DatabaseHandler (DB) for storing/fetching data.
      3) Provides utility methods to find elements, click, and parse HTML (via BeautifulSoup).
      4) Defines abstract methods `scrape_all()` and `new()` that child classes must implement.
    """

    base_url = "https://www.partselect.com/"

    def __init__(
        self, 
        start_url: Optional[str] = None,
        manufacturer_id: Optional[str] = None,
        db: Optional[DatabaseHandler] = None,
        driver: Optional[Driver] = None
    ):
        """
        Initializes the scraper:
          - If 'db' is None, creates a new DatabaseHandler.
          - Creates a new SeleniumBase Driver (headless by default).
          - If 'start_url' is provided, we navigate there.
            Otherwise, if 'manufacturer_id' is provided, we do a search query with it.
            Otherwise, we just go to the base URL.

        Args:
            start_url (str, optional): A direct URL to load initially.
            manufacturer_id (str, optional): If set, we attempt a search with that ID.
            db (DatabaseHandler, optional): If provided, we use it. Otherwise, create a new DB.
            driver (Driver, optional): If you'd like to pass an existing driver, not typically used here.
        """
        self.db_given = bool(db)
        # Create or reuse a Selenium driver
        # (We ignore a passed-in 'driver' for simplicity, using our own)
        self.driver: Driver = Driver(uc=True, headless=True, chromium_arg='--ignore-certificate-errors')
        logger.info("Initialized SeleniumBase Driver with headless=True.")

        # Set up DB
        if db:
            self.db = db
            logger.info("Reusing provided DatabaseHandler.")
        else:
            self.db = DatabaseHandler()
            logger.info("Created new DatabaseHandler instance.")

        # Decide what URL or action to take
        self.wait = WebDriverWait(self.driver, 10)
        if start_url:
            logger.info(f"Navigating to start_url: {start_url}")
            self.driver.get(start_url)
        elif manufacturer_id:
            search_url = SEARCH_URL + manufacturer_id
            logger.info(f"Performing search with manufacturer_id={manufacturer_id}, url={search_url}")
            try:
                self.driver.get(search_url)
            except NoSuchWindowException:
                # If the window was closed or lost, attempt to recover
                logger.warning("Driver window was unexpectedly closed. Re-initializing.")
                time.sleep(10)
                self.driver.quit()
                self.driver = Driver(uc=True, headless=True, chromium_arg='--ignore-certificate-errors')
                self.driver.get(search_url)
                self.driver.implicitly_wait(5)
        else:
            # Default to the base PartSelect homepage
            logger.info(f"No start_url or manufacturer_id provided, going to base_url: {self.base_url}")
            self.driver.get(self.base_url)

        # Record the actual URL we ended up on
        self.start_url = self.driver.current_url
        # Parse the initial page
        self.soup = self.set_soup(self.start_url)

    def checkCompatibility(self, model_id: str, part_select_id: str) -> bool:
        """
        Checks if a part is compatible with a given model by sending a query to PartSelect's
        PartCompatibilityCheck endpoint.

        Args:
            model_id (str): The user’s or the scraped model number.
            part_select_id (str): Typically "PSXXXXX". If it starts with 'PS', we remove 'PS'.

        Returns:
            bool: True if 'MODEL_PARTSKU_MATCH', meaning the part is confirmed compatible,
                  otherwise False.

        Raises:
            ValueError: If part_select_id doesn't start with 'PS'.
        """
        logger.info(f"checkCompatibility called with model_id={model_id}, part_select_id={part_select_id}")
        if part_select_id.startswith("PS"):
            part_select_id = part_select_id[2:]
        else:
            raise ValueError("Invalid part_select_id for checking compatibility (must start with 'PS').")

        prev_url = self.driver.current_url
        url = (
            f"https://www.partselect.com/api/Part/PartCompatibilityCheck"
            f"?modelnumber={model_id}&inventoryid={part_select_id}&partdescription=undefined"
        )

        logger.debug(f"Navigating to compatibility check URL: {url}")
        self.driver.get(url)
        self.wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))

        content = self.driver.find_element(By.TAG_NAME, "body").text
        data = json.loads(content)
        compatibility_result = data.get("compatibilityCheckResult")

        # Return to previous page
        self.driver.get(prev_url)

        is_match = (compatibility_result == "MODEL_PARTSKU_MATCH")
        logger.info(f"Compatibility check result => {compatibility_result}, returning {is_match}")
        return is_match

    @abstractmethod
    def scrape_all(self):
        """
        Child classes must implement a method to scrape all relevant fields for the item.
        Typically sets multiple properties, then saves them to DB.
        """
        pass

    @abstractmethod
    def new(self, *args):
        """
        Child classes should implement a method to 'reset' or create a new item context
        (e.g., going to a new URL, storing a new manufacturer_id, etc.).
        """
        pass

    def set_soup(self, url: str) -> BeautifulSoup:
        """
        Navigates to 'url' if not already there, then parses the current page source
        into BeautifulSoup, storing it in self.soup.

        Returns:
            BeautifulSoup: The newly parsed soup object.
        """
        if self.driver.current_url != url:
            logger.debug(f"set_soup => driver.get({url})")
            self.driver.get(url)
        self.soup = BeautifulSoup(self.driver.page_source, 'html.parser')
        return self.soup

    def wait_for(self, css_path: str, clickable: bool = False):
        """
        Waits for one element matching `css_path`. If `clickable=True`, waits until it's clickable.
        Returns the corresponding BeautifulSoup element or None if timed out.
        """
        logger.debug(f"wait_for => css_path={css_path}, clickable={clickable}")
        try:
            if clickable:
                self.wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, css_path)))
            else:
                self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, css_path)))
            return self.soup.select_one(css_path)
        except TimeoutException:
            logger.warning(f"Timeout waiting for element: {css_path}")
            return None

    def wait_for_all(self, css_path: str, clickable: bool = False):
        """
        Waits for all elements matching `css_path`. If `clickable=True`, waits until at least
        one is clickable. Returns a list of BeautifulSoup elements (possibly empty).
        """
        logger.debug(f"wait_for_all => css_path={css_path}, clickable={clickable}")
        try:
            if clickable:
                self.wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, css_path)))
            else:
                self.wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, css_path)))
            return self.soup.select(css_path)
        except TimeoutException:
            logger.warning(f"Timeout waiting for elements: {css_path}")
            return []

    def get_item(self, css_path: str, url: str, parser=None):
        """
        1) Navigates/sets soup to `url`.
        2) Waits for a single element matching `css_path`.
        3) If found, returns parser(element) or the raw element.

        Returns:
            Any: The parsed result or the raw element, or None if not found.
        """
        logger.debug(f"get_item => url={url}, css_path={css_path}")
        self.set_soup(url)
        item = self.wait_for(css_path)
        if not item:
            logger.debug("get_item => No element found, returning None.")
            return None
        logger.debug("get_item => Element found, parsing if parser is provided.")
        return parser(item) if parser else item

    def get_items(self, css_path: str, url: str, parser=None):
        """
        1) Navigates/sets soup to `url`.
        2) Waits for any elements matching `css_path`.
        3) Returns a list of results (parsed if parser given, otherwise raw).

        Returns:
            List[Any]: Possibly empty list if no matches or timed out.
        """
        logger.debug(f"get_items => url={url}, css_path={css_path}")
        self.set_soup(url)
        elements = self.wait_for_all(css_path)
        if not elements:
            logger.debug("get_items => No elements found, returning [].")
            return []
        logger.debug(f"get_items => Found {len(elements)} elements, applying parser if given.")
        if parser:
            return [parser(el) for el in elements]
        return elements
    
    def click(self, url: str, css_path: str, reset_soup: bool = True, condition=None) -> bool:
        """
        Attempts to click the first element matching `css_path`. If `condition` is provided,
        the element must satisfy it. If successful, returns True, else False.

        Args:
            url (str): The page to operate on. We do `driver.get(url)` if reset_soup is True.
            css_path (str): The CSS selector for the clickable element.
            reset_soup (bool): If True, re-fetch the page and re-parse soup first.
            condition (callable): Optional. A function that takes a WebElement and returns bool.

        Returns:
            bool: True if the click was successful, otherwise False.
        """
        logger.info(f"click => url={url}, css_path={css_path}, reset_soup={reset_soup}")
        if reset_soup:
            self.set_soup(url)

        try:
            next_btn: WebElement = self.driver.find_element(By.CSS_SELECTOR, css_path)
        except (NoSuchElementException, TimeoutException):
            logger.debug("click => Element not found.")
            return False

        if not next_btn or (condition and not condition(next_btn)):
            logger.debug("click => Condition not met or no element.")
            return False
        
        try:
            self.driver.execute_script("arguments[0].scrollIntoView(true);", next_btn)
            self.wait_for(css_path, clickable=True)
            next_btn.click()
            logger.info(f"click => Clicked element at '{css_path}' successfully.")
            return True
        except (ElementClickInterceptedException, ElementNotInteractableException):
            logger.warning("click => Element was intercepted or not interactable, attempting popup close.")
            try:
                self.click_popup()
                self.wait_for(css_path, clickable=True)
                next_btn.click()
                logger.info("click => Successfully clicked after closing popup.")
                return True
            except:
                logger.exception("click => Failed to click element after popup attempt.")
                return False
        except StaleElementReferenceException:
            logger.warning("click => StaleElementReferenceException encountered.")
            return False

    def click_popup(self):
        """
        Sometimes a popup overlay must be closed before we can click other elements.
        This method tries to find and click that close button.
        """
        logger.debug("click_popup => Attempting to close any open popup.")
        self.wait_for(".bx-button[data-click='close']", clickable=True)
        try:
            popup = self.driver.find_element(By.CSS_SELECTOR, ".bx-button[data-click='close']")
            popup.click()
            logger.info("click_popup => Popup closed successfully.")
        except Exception as e:
            logger.warning(f"click_popup => Popup not found or not closable. {e}")
    

    def click_all(self, url: str, css_path: str, condition=None):
        """
        Repeatedly finds elements matching `css_path` on the page, clicks the first match,
        then re-parses soup. Continues until no clickable elements remain or condition fails.

        This is useful for 'show more' style pagination.
        """
        logger.info(f"click_all => url={url}, css_path={css_path}")
        if self.driver.current_url != url:
            self.driver.get(url)
            self.soup = BeautifulSoup(self.driver.page_source, "html.parser")

        while True:
            try:
                elements = self.driver.find_elements(By.CSS_SELECTOR, css_path)
            except TimeoutException:
                logger.debug("click_all => No matching elements found at all, stopping.")
                break

            if not elements:
                logger.debug("click_all => No more elements to click, done.")
                break

            # If condition is provided, filter
            if condition:
                elements = [el for el in elements if condition(el)]
                if not elements:
                    logger.debug("click_all => Condition not met for any elements, stopping.")
                    break

            # Click the first match
            elements[0].click()
            logger.info("click_all => Clicked one matching element. Re-parsing page.")
            time.sleep(0.5)  # let the page update
            self.soup = BeautifulSoup(self.driver.page_source, "html.parser")


    def _get_or_scrape_field(self, item_id: str, local_item, field_name: str, db_fetch_method, scrape_all_method):
        """
        Helper for child classes:
          1) Attempt to fetch a fresh copy from DB using db_fetch_method(item_id).
          2) If that copy has a non-None field 'field_name', copy its fields to local_item, return the field.
          3) Otherwise, call scrape_all_method() to populate local_item from the site.
          4) Return local_item's updated field.

        This avoids code duplication for properties that might be either in DB or need scraping.
        """
        logger.debug(f"_get_or_scrape_field => item_id={item_id}, field_name={field_name}")
        refreshed = db_fetch_method(item_id)
        if refreshed:
            value = getattr(refreshed, field_name)
            if value is not None:
                # Update local_item with all fields from DB version
                for f in fields(local_item):
                    setattr(local_item, f.name, getattr(refreshed, f.name))
                logger.debug(f"_get_or_scrape_field => Found non-None '{field_name}' in DB, returning it.")
                return value

        # If DB didn't have it, or was None => call scrape_all
        logger.debug(f"_get_or_scrape_field => Field '{field_name}' not found in DB. Scraping all.")
        scrape_all_method()
        return getattr(local_item, field_name)
    
    @staticmethod
    def none_string_handler(string: Optional[str]) -> str:
        """
        Utility that returns a string or a fallback if the value is None/empty.
        """
        return string if string else " Not provided on page"

    def close(self):
        """
        Closes the Selenium driver. If we created the DB internally, closes it too.
        """
        if not self.db_given:
            logger.info("close => Closing internal DatabaseHandler.")
            self.db.close()
        logger.info("close => Quitting Selenium driver.")
        self.driver.quit()
