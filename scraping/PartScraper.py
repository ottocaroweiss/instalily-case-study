import time
import logging
from typing import Optional, List, Tuple
from dataclasses import asdict
import re
import hashlib

from scraping.AbstractScraper import AbstractScraper
from scraping.itemclasses import (
    PartItem, PartReplacementItem, PartReviewItem, PartReviewStoryItem, PartQnAItem
)
from scraping.database import DatabaseHandler

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
PART_SEARCH = "https://www.partselect.com/api/search/?searchterm={}&trackSearchType=combinedsearch"
class PartScraper(AbstractScraper):
    """
    Scraper for a single part, preserving all previously scraped aspects,
    but using property-based getters so we only scrape what's needed.
    """
    def __init__(
        self,
        db: DatabaseHandler = None,
        manufacturer_id: Optional[str] = None,
        link: Optional[str] = None
    ):
        if db and isinstance(db, DatabaseHandler) and not manufacturer_id and not link:
            logging.info("Initializing PartScraper with an existing DatabaseHandler")
            super().__init__(db=db)
            return
        elif link:
            logging.info(f"Initializing PartScraper with link={link} manufacturer_id={manufacturer_id}")
            super().__init__(start_url=link)
            logging.info(f"Started driver at URL: {link}")
            self.url = link
        elif manufacturer_id:
            super().__init__(manufacturer_id=manufacturer_id)
            self.url = PART_SEARCH.format(manufacturer_id)
            logging.info(f"Started driver with manufacturer_id: {manufacturer_id}")
        else:
            raise ValueError("Must provide either link, or manufacturer_id")

        
        self.manufacturer_id = manufacturer_id

        # (from original code) If part in DB, load it; else create new PartItem
        existing_part = self.db.get_part(self.manufacturer_id)
        logging.info(f"Existing part in DB? {bool(existing_part)}")
        if existing_part:
            self.part_item = existing_part
            if not self.part_item.part_select_id:
                logging.info("No part_select_id found; scraping it.")
                self._scrape_part_select_id()
        else:
            logging.info("Part not found in DB; creating a new PartItem.")
            if link:
                self.part_item = PartItem(url=self.url)
                self._scrape_manufacturer_id()
                time.sleep(1)
            else:
                self.part_item = PartItem(
                    manufacturer_id=self.manufacturer_id,
                    url=self.url
                )
            self.scrape_all()


    def new(self, url=None, manufacturer_id=None):
        """
        A method to handle "resetting" or creating a new part scraping context,
        after __init__ is called with a db. 
        """
        logging.info(f"new() called with url={url}, manufacturer_id={manufacturer_id}")
        if url and not manufacturer_id:
            logging.info(f"Initializing PartScraper with link={url} manufacturer_id={manufacturer_id}")
            super().__init__(start_url=url)
            logging.info(f"Started driver at URL: {url}")
        elif manufacturer_id:
            super().__init__(manufacturer_id=manufacturer_id)
            self.url = PART_SEARCH.format(manufacturer_id)
            self.driver.get(self.url)
            logging.info(f"Started driver with manufacturer_id: {manufacturer_id}")
        else:
            raise ValueError("Must provide either link, or manufacturer_id")

        self.manufacturer_id = manufacturer_id
        existing_part = self.db.get_part(self.manufacturer_id)
        logging.info(f"Existing part in DB? {bool(existing_part)}")
        if existing_part:
            self.part_item = existing_part
            if not self.part_item.part_select_id:
                logging.info("No part_select_id found; scraping it.")
                self._scrape_part_select_id()
        else:
            if url:
                self.part_item = PartItem(url=self.url)
                self._scrape_manufacturer_id()
                time.sleep(1)
            else:
                self.part_item = PartItem(
                    manufacturer_id=self.manufacturer_id,
                    url=self.url
                )
            self.scrape_all()


    # ---------------------------------------------------------
    # OPTIONAL: Full scrape_all if you want to force everything
    # ---------------------------------------------------------
    def scrape_all(self, includeComments = False) -> PartItem:
        """
        Scrape ALL fields for this part, forcibly, and save to DB.
        """
        if not self.manufacturer_id:
            logging.info("manufacturer_id not set; scraping manufacturer_id first.")
            self._scrape_manufacturer_id()
        logging.info(f"Starting full scrape for {self.manufacturer_id or 'unknown'}")
        self.part_item.name = self.name
        self.part_item.part_select_id = self.part_select_id
        self.part_item.price = self.price
        self.part_item.difficulty = self.difficulty
        self.part_item.time = self.time
        self.part_item.rating = self.rating
        self.part_item.description = self.description
        self.part_item.related_parts = self.related_parts
        self.part_item.fixes = self.fixes
        self.part_item.part_replacements = self.part_replacements
        self.part_item.products = self.products
        self.part_item.url = self.url

        logging.info("Saving PartItem to DB ...")
        self.db.save_part(self.part_item)

        # Store replacements
        replacements_list = [
            PartReplacementItem(
                replacement_id=None,
                manufacturer_id=self.manufacturer_id,
                replacement_text=r.strip()
            )
            for r in self.part_replacements.split(",")
            if r.strip()
        ]
        if replacements_list:
            logging.info(f"Storing {len(replacements_list)} part replacements into DB ...")
            self.db.save_part_replacements(replacements_list)
        if includeComments:
            logging.info("Scraping reviews and stories...")
            if not self.reviews:
                reviews = self.reviews
            if not self.stories:
                stories = self.stories
            if not self.questions:
                questions = self.questions
        # Also forcibly get stories & reviews

        return self.part_item

    # ---------------------------------------------------------
    # PROPERTIES: on-demand scraping for each field
    # ---------------------------------------------------------
    @property
    def name(self) -> Optional[str]:
        if not self.part_item.name:
            logging.info("Property 'name' not found in PartItem; scraping...")
            self.part_item.name = self._scrape_name()
            self.db.save_part(self.part_item)
        return self.part_item.name

    @property
    def part_select_id(self) -> Optional[str]:
        if not self.part_item.part_select_id:
            logging.info("Property 'part_select_id' not found in PartItem; scraping...")
            self.part_item.part_select_id = self._scrape_part_select_id()
            self.db.save_part(self.part_item)
        return self.part_item.part_select_id

    @property
    def price(self) -> Optional[float]:
        if self.part_item.price is None:
            logging.info("Property 'price' not found in PartItem; scraping...")
            self.part_item.price = self._scrape_price()
            self.db.save_part(self.part_item)
        return self.part_item.price

    @property
    def difficulty(self) -> Optional[str]:
        if self.part_item.difficulty is None:
            logging.info("Property 'difficulty' not found in PartItem; scraping...")
            self.part_item.difficulty = self._scrape_difficulty()
            self.db.save_part(self.part_item)
        return self.part_item.difficulty

    @property
    def time(self) -> Optional[str]:
        if self.part_item.time is None:
            logging.info("Property 'time' not found in PartItem; scraping...")
            self.part_item.time = self._scrape_time()
            self.db.save_part(self.part_item)
        return self.part_item.time

    @property
    def rating(self) -> Optional[float]:
        if self.part_item.rating is None:
            logging.info("Property 'rating' not found in PartItem; scraping...")
            self.part_item.rating = self._scrape_rating()
            self.db.save_part(self.part_item)
        return self.part_item.rating

    @property
    def description(self) -> Optional[str]:
        if not self.part_item.description:
            logging.info("Property 'description' not found in PartItem; scraping...")
            self.part_item.description = self._scrape_description()
            self.db.save_part(self.part_item)
        return self.part_item.description

    @property
    def related_parts(self) -> Optional[str]:
        if not self.part_item.related_parts:
            logging.info("Property 'related_parts' not found; scraping...")
            val = self._scrape_related_parts()
            self.part_item.related_parts = val
        return self.part_item.related_parts

    @property
    def fixes(self) -> Optional[str]:
        if not self.part_item.fixes:
            try:
                logging.info("Property 'fixes' not found; scraping troubleshooting info...")
                f, r, p = self._scrape_troubleshooting()
                self.part_item.fixes = f
                self.part_item.part_replacements = r
                self.part_item.products = p
                self.db.save_part(self.part_item)
            except Exception as ex:
                logging.error(f"Error scraping troubleshooting info: {ex}")
        return self.part_item.fixes

    @property
    def part_replacements(self) -> Optional[str]:
        if not self.part_item.part_replacements:
            logging.info("Property 'part_replacements' not found; triggering 'fixes' property scrape...")
            _ = self.fixes
        return self.part_item.part_replacements

    @property
    def products(self) -> Optional[str]:
        if not self.part_item.products:
            logging.info("Property 'products' not found; triggering 'fixes' property scrape...")
            _ = self.fixes
        return self.part_item.products

    @property
    def availability(self) -> bool:
        if not self.part_item.availability:
            logging.info("Property 'availability' not found; scraping availability...")
            val = self._scrape_availability()
            self.part_item.availability = val
        return self.part_item.availability


    @property
    def reviews(self) -> List[PartReviewItem]:
        db_reviews = self.db.get_part_reviews(self.manufacturer_id)
        if not db_reviews:
            logging.info("Property 'reviews' not found; scraping reviews...")
            return self._scrape_reviews()
        return db_reviews

    @property
    def stories(self) -> List[PartReviewStoryItem]:
        db_stories = self.db.get_part_review_stories(self.manufacturer_id)
        if not db_stories:
            logging.info("Property 'stories' not found; scraping stories...")
            return self._scrape_stories()
        return db_stories

    @property
    def questions(self) -> List[PartQnAItem]:
        db_questions = self.db.get_part_qnas(self.manufacturer_id)
        if not db_questions:
            logging.info("Property 'reviews' not found; scraping reviews...")
            self.reviews = self._scrape_questions()
        return db_questions
    
    # -------------------------------------------------
    # PRIVATE SCRAPE METHODS
    # -------------------------------------------------
    def _scrape_name(self):
        logging.info(f"Scraping 'name' from URL: {self.url}")
        return self.get_item(
            ".title-lg.mt-1.mb-3",
            self.url,
            parser=lambda el: el.text.strip()
        )
    
    def _scrape_availability(self):
        logging.info(f"Scraping 'availability' from URL: {self.url}")
        if not self.part_item.part_select_id:
            return self.get_item('span[itemprop="availability"]', self.url,
                                 parser=lambda el: el.text.strip()) == "In Stock"
        return self.part_item.availability
    

    def _scrape_part_select_id(self):
        logging.info(f"Scraping 'part_select_id' from URL: {self.url}")
        if not self.part_item.part_select_id:
            return self.get_item('span[itemprop="productID"]', self.url, parser=lambda el: el.text.strip())
        return self.part_item.part_select_id

    def _scrape_manufacturer_id(self):
        logging.info(f"Scraping 'manufacturer_id' from URL: {self.url}")
        manufacturer_id = self.get_item('span[itemprop="mpn"]', self.url, parser=lambda el: el.text.strip())
        if not self.part_item.manufacturer_id:
            self.part_item.manufacturer_id = manufacturer_id
            self.manufacturer_id = manufacturer_id
        return manufacturer_id

    def _scrape_price(self):
        logging.info(f"Scraping 'price' from URL: {self.url}")
        return self.get_item(
            "span.js-partPrice",
            self.url,
            parser=lambda el: float(el.text.replace("$", "").strip())
        )
    
    def _scrape_difficulty(self):
        logging.info(f"Scraping 'difficulty' from URL: {self.url}")
        items = self.get_items(
            "div.pd__repair-rating__container__item p.bold",
            self.url,
            parser=lambda x: x.text.strip()
        )
        return items[0] if items else None

    def _scrape_time(self):
        logging.info(f"Scraping 'time' from URL: {self.url}")
        items = self.get_items(
            "div.pd__repair-rating__container__item p.bold",
            self.url,
            parser=lambda x: x.text.strip()
        )
        return items[1] if items and len(items) > 1 else None

    def _scrape_related_parts(self) -> str:
        logging.info(f"Scraping 'related_parts' from URL: {self.url}")
        blocks = self.soup.select("div.pd__related-part")
        if not blocks:
            return ""
        lines = []
        for i, block in enumerate(blocks, 1):
            anchor = block.select_one("a.bold")
            if anchor:
                part_name = anchor.get_text(strip=True)
                href = anchor.get("href", "")
                full_link = self.base_url.rstrip("/") + "/" + href.lstrip("/")
                lines.append(f"{i}. {part_name} - ({full_link})")
        return "\n".join(lines)

    def _scrape_rating(self):
        logging.info(f"Scraping 'rating' from URL: {self.url}")
        el = self.get_item("div.rating__stars__upper", self.url)
        if not el:
            return None
        style = el.get("style", "")
        if "width" in style:
            pct = float(style.split("width:")[1].replace("%", "").replace(";", "").strip())
            return round(pct / 20, 2)
        return None

    def _scrape_description(self):
        logging.info(f"Scraping 'description' from URL: {self.url}")
        return self.get_item(
            'div[itemprop="description"]',
            self.url,
            parser=lambda el: el.text.strip()
        )

    def _scrape_troubleshooting(self):
        logging.info(f"Scraping 'troubleshooting' from URL: {self.url}")
        self.click_all(
            url=self.url,
            css_path=".bold.text-link.underline",
            condition=lambda w: "Show more" in w.text
        )
        raw_text = self.get_item("div#Troubleshooting + div", self.url, parser=lambda el: el.get_text("\n", True)) or ""
        data = self._parse_troubleshooting_text(raw_text)
        fixes_str = ", ".join(data["symptoms"]) if data["symptoms"] else ""
        replacements_str = ", ".join(data["replaced_parts"]) if data["replaced_parts"] else ""
        products_str = ", ".join(data["products"]) if data["products"] else ""
        return (fixes_str, replacements_str, products_str)
    
    @staticmethod
    def _parse_troubleshooting_text(text: str):
        data = {
            "symptoms": [],
            "products": [],
            "replaced_parts": [],
        }
        s = re.search(r"This part fixes the following symptoms:\s*(.*?)\s*This part works with the following products:",
                      text, re.DOTALL)
        if s:
            raw = s.group(1)
            data["symptoms"] = [x.strip() for x in raw.split("|") if x.strip()]

        pm = re.search(r"This part works with the following products:\s*(.*?)\s*Part#", text, re.DOTALL)
        if pm:
            rawp = pm.group(1)
            data["products"] = [p.strip() for p in re.split(r"[\n|]+", rawp) if p.strip()]

        rm = re.search(r"replaces these:\s*(.*?)\s*(Show less|Back to Top|$)", text, re.DOTALL)
        if rm:
            rawr = rm.group(1)
            items = []
            for r in rawr.split(","):
                c = r.strip()
                if "Show" in c:
                    c = c.split("\n")[0].strip()
                items.append(c)
            data["replaced_parts"] = items
        return data
    
    def _scrape_reviews(self):
        logging.info(f"Scraping 'reviews' for manufacturer_id={self.manufacturer_id}")
        collected = set()
        reviews = []
        while True:
            page_reviews, combined_str = self._parse_current_page_reviews()
            new_reviews = [r for r in page_reviews if combined_str not in collected]
            reviews.extend(new_reviews)
            if new_reviews:
                logging.info(f"Found {len(new_reviews)} new reviews on this page.")
                collected.update(combined_str)
            else:
                logging.info("No new reviews found on this page. Stopping scrape.")
                break
            clicked_next = self.click(
                self.url,
                css_path=".js-resultsRenderer[data-event-target='Customer Review'] li.next:not(.disabled)"
            )
            if not clicked_next:
                logging.info("No more 'next' pagination for reviews.")
                break
        if collected:
            logging.info(f"Inserting total of {len(collected)} reviews into DB.")
            self.db.save_part_reviews(reviews)
        return reviews

    def _scrape_stories(self):
        logging.info(f"Scraping 'stories' for manufacturer_id={self.manufacturer_id}")
        container_css = ".js-resultsRenderer[data-event-target='Repair Story']"
        collected = set()
        stories = []
        while True:
            items, combined_str = self._parse_current_page_stories(container_css)
            new_stories = [s for s in items if combined_str not in collected]
            stories.extend(new_stories)
            if new_stories:
                logging.info(f"Found {len(new_stories)} new stories on this page.")
                collected.update(combined_str)
            else:
                logging.info("No new stories found on this page. Stopping scrape.")
                break
            clicked_next = self.click(
                self.url,
                css_path=f"{container_css} ul.pagination.js-pagination li.next:not(.disabled)"
            )
            if not clicked_next:
                logging.info("No more 'next' pagination for stories.")
                break
        if collected:
            logging.info(f"Inserting total of {len(collected)} stories into DB.")
            self.db.save_part_review_stories(stories)
        return stories

    def _scrape_questions(self):
        logging.info(f"Scraping 'questions' (Q&A) for manufacturer_id={self.manufacturer_id}")
        container_css = "div.js-resultsRenderer[id=QuestionsAndAnswersContent]"
        collected = set()
        questions = []
        while True:
            page_items, combined_str = self._parse_qna_page(container_css)
            new_questions = [q for q in page_items if combined_str not in collected]
            questions.extend(new_questions)
            if new_questions:
                logging.info(f"Found {len(new_questions)} new Q&As on this page.")
                collected.update(combined_str)
            else:
                logging.info("No new Q&As found on this page. Stopping scrape.")
                break
            clicked_next = self.click(
                url=self.url,
                css_path=f"{container_css} ul.pagination.js-pagination li.next:not(.disabled)",
                reset_soup=False
            )
            if not clicked_next:
                logging.info("No more 'next' pagination for Q&A.")
                break
        if collected:
            logging.info(f"Inserting total of {len(collected)} Q&As into DB.")
            self.db.save_part_qnas(questions)
        return questions
    
    def _parse_qna_page(self, container_css: str) -> Tuple[List[PartQnAItem], str]:
        container = self.get_item(container_css, self.url)
        if not container:
            return [], ""
        qna_divs = container.select("div.js-dataContainer div.qna__question.js-qnaResponse")
        results = []
        combined_str = ""
        for div in qna_divs:
            try:
                q_box = div.select_one("div.js-searchKeys")
                question_text = q_box.get_text(strip=True) if q_box else ""
                model_spec = q_box.find_next_sibling("div") if q_box else None

                if model_spec:
                    model_number_text = model_spec.get_text(strip=True)
                    if "For model number " in model_number_text:
                        model_number = model_number_text.split("For model number ")[1].strip()
                    else:
                        model_number = ""
                else:
                    model_number = ""

                answer_box = div.select_one("div.qna__ps-answer__msg div.js-searchKeys")
                answer = answer_box.get_text(strip=True) if answer_box else ""

                unique_str = f"{self.manufacturer_id.upper()}{question_text}{model_number}{answer}"
                qna_id = int(hashlib.md5(unique_str.encode()).hexdigest(), 16) % (10 ** 8)  # Generate an 8-digit hash
                q_item = PartQnAItem(
                    qna_id=qna_id,
                    manufacturer_id=self.part_item.manufacturer_id.upper(),
                    question=question_text,
                    model_number=model_number.upper(),
                    answer=answer
                )
                results.append(q_item)
                combined_str += f"{question_text} {model_number} {answer} "
            except Exception as ex:
                logging.error(f"Error parsing Q&A block: {ex}")
        return results, combined_str.strip()
    
    def _parse_current_page_stories(self, container_css: str) -> Tuple[List[PartReviewStoryItem], str]:
        container = self.get_item(container_css, self.url)
        blocks = container.select("div.repair-story")
        results = []
        combined_str = ""
        for div in blocks:
            title_el = div.select_one("div.repair-story__title")
            instr_el = div.select_one("div.repair-story__instruction .js-searchKeys")
            title_str = title_el.get_text(strip=True) if title_el else ""
            text_str = instr_el.get_text(strip=True) if instr_el else ""
            unique_str = f"{self.manufacturer_id.upper()}{title_str}{text_str}"
            story_id = int(hashlib.md5(unique_str.encode()).hexdigest(), 16) % (10 ** 8)  # Generate an 8-digit hash
            st = PartReviewStoryItem(
                story_id=story_id,
                manufacturer_id=self.manufacturer_id or "",
                title=title_str,
                text=text_str
            )
            results.append(st)
            combined_str += f"{title_str} {text_str} "
        return results, combined_str.strip()
    
    def _parse_current_page_reviews(self) -> Tuple[List[PartReviewItem], str]:
        container = self.get_item(".js-resultsRenderer[data-event-target='Customer Review']", self.url)
        blocks = container.select("div.pd__cust-review__submitted-review")
        results = []
        combined_str = ""
        for div in blocks:
            header_el = div.select_one("div.bold")
            text_el = div.select_one("div.js-searchKeys")
            header = header_el.get_text(strip=True) if header_el else ""
            text = text_el.get_text(strip=True) if text_el else ""
            unique_str = f"{self.manufacturer_id.upper()}{header}{text}"
            review_id = int(hashlib.md5(unique_str.encode()).hexdigest(), 16) % (10 ** 8)  # Generate an 8-digit hash
            r_item = PartReviewItem(
                review_id=review_id,
                manufacturer_id=self.manufacturer_id.upper() or "",
                header=header,
                text=text
            )
            results.append(r_item)
            combined_str += f"{header} {text} "
        return results, combined_str.strip()

    def __str__(self):
        part_item_dict = asdict(self.part_item)
        return "\n".join(f"{key}: {value}" for key, value in part_item_dict.items())