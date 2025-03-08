import logging
import time
from typing import Optional

from scraping.AbstractScraper import AbstractScraper
from scraping.itemclasses import ModelItem, PartItem
from scraping.database import DatabaseHandler
PARTS_URL = "https://www.partselect.com/Models/{}/Parts/"
MODEL_URL = "https://www.partselect.com/Models/{}"
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class ModelScraper(AbstractScraper):
    """
    Scraper that loads a model page, retrieves data, populates a ModelItem.
    We also upsert each PartItem into the 'parts' table,
    and store a comma-separated list of part_select_ids in self.model.parts.
    """
    def __init__(self, db: Optional[DatabaseHandler] = None):
        """
        Passes `db` to parent constructor. 
        The instance is 'uninitialized' until you call .new(model_id).
        """
        logger.info("ModelScraper.__init__() called with db=%s", db)
        start_time = time.time()
        try:
            super().__init__(db=db)
            self.model_id: Optional[str] = None
            self.model_url: Optional[str] = None
            self.parts_url: Optional[str] = None
            self.model: Optional[ModelItem] = None
        finally:
            elapsed = time.time() - start_time
            logger.info("ModelScraper.__init__() completed in %.4f seconds", elapsed)

    def new(self, model_id: str):
        """
        Initialize or re-initialize the scraper for a new model_id.
        This method loads the model page, sets up the ModelItem, and calls scrape_all().
        """
        logger.info("ModelScraper.new() called with model_id='%s'", model_id)
        start_time = time.time()
        try:
            if not model_id:
                raise ValueError("You must provide a model ID.")

            self.model_id = model_id
            self.model_url = MODEL_URL.format(model_id)
            self.parts_url = PARTS_URL.format(model_id)

            # Navigate to the model page
            logger.debug("Navigating to %s", self.model_url)
            self.driver.get(self.model_url)
            # Create a new ModelItem

            # Scrape everything
            self.scrape_all()

        finally:
            elapsed = time.time() - start_time
            logger.info("ModelScraper.new() completed in %.4f seconds", elapsed)

    def scrape_all(self) -> ModelItem:
        """
        Ensures all fields are populated (name, description, symptoms, etc.), 
        and returns the fully-populated ModelItem.
        """
        logger.info("ModelScraper.scrape_all() called for id='%s'", self.model_id)
        start_time = time.time()
        try:
            self.model = self.db.get_model(self.model_id)
            if not self.model:
                self.model = ModelItem(id=self.model_id)
                self.model.name = self.name
                self.model.description = self.description
                self.model.symptoms = self.symptoms
                self.db.save_model(self.model)
            return self.model
        finally:
            elapsed = time.time() - start_time
            logger.info("ModelScraper.scrape_all() completed in %.4f seconds", elapsed)

    @property
    def name(self) -> str:
        """
        If self.model.name is missing, call _scrape_name(), store it, 
        and possibly update DB. Returns a string or "" if none.
        """
        if not self.model.name:
            logger.info("ModelScraper.name property triggered for model_id='%s'", self.model_id)
            self.model.name = self._scrape_name()
        return self.model.name or ""

    @property
    def description(self) -> str:
        if not self.model.description:
            logger.info("ModelScraper.description property triggered for model_id='%s'", self.model_id)
            self.model.description = self._scrape_description()
        return self.model.description or ""

    @property
    def parts(self) -> str:
        """
        If `model.parts` is missing, we call _scrape_parts_and_store() 
        and populate it. Returns a comma-separated string of part_select_ids.
        """
        if not self.model.parts:
            logger.info("ModelScraper.parts property triggered for model_id='%s'", self.model_id)
            self.model.parts = self._scrape_part_ids()
        return self.model.parts or ""

    @property
    def symptoms(self) -> str:
        """
        If `model.symptoms` is missing, call _scrape_symptoms().
        Return it or "" if none.
        """
        if not getattr(self.model, 'symptoms', None):
            logger.info("ModelScraper.symptoms property triggered for model_id='%s'", self.model_id)
            self.model.symptoms = self._scrape_symptoms()
        return self.model.symptoms or ""

    # -------------------------------------------------
    # PRIVATE SCRAPE METHODS
    # -------------------------------------------------
    def _scrape_name(self) -> str:
        logger.debug("ModelScraper._scrape_name() for model_id='%s'", self.model_id)
        return self.get_item(
            css_path="h1.title-main",
            url=self.model_url,
            parser=lambda el: el.text.strip()
        ) or ""

    def _scrape_description(self) -> str:
        logger.debug("ModelScraper._scrape_description() for model_id='%s'", self.model_id)
        return self.get_item(
            css_path=".description",
            url=self.model_url,
            parser=lambda el: el.text.strip()
        ) or ""

    def _scrape_part_ids(self, query=None) -> list[str]:
        """
        1) Scrape the part blocks from self.parts_url
        2) Convert each block to PartItem
        3) Return a comma-separated list of part_select_ids
        """
        logger.info("ModelScraper._scrape_parts_and_store() for model_id='%s'", self.model_id)
        start_time = time.time()
        page = 1
        if query:
            part_url = f"{self.parts_url}/?SearchTerm={query.replace(' ', '%20')}"
        else:
            part_url = f"{self.parts_url}/?start={{}}"
        logger.info("Scraping parts from URL=%s", part_url)
        all_ids = set()
        popup_clicked = False
        while True:
            if query:
                page_url = part_url
            elif page > 1:
                page_url = part_url.format(page)
            else:
                page_url = self.parts_url
            try:
                parts: PartItem = self.get_items("div.mega-m__part", page_url, parser=self._parse_part_block)
                
                if not parts and page == 1:
                    logger.warning("No parts found for model_id='%s' at URL=%s", self.model_id, self.parts_url)
                    return ""
                ids = [p.part_select_id for p in parts if p.part_select_id]
                ids_unique = set(ids)

                current_count = len(all_ids)
                all_ids.update(ids_unique)
                if not ids or len(ids) == current_count:
                    if popup_clicked:
                        break
                    self.click_popup()
                    popup_clicked = True
                if query:
                    break
                logger.info("Found %d parts: %s", len(ids), ids)
                page += 1
                logger.info(f"ModelScraper._scrape_parts() scraped page {page}.")
            except:
                logger.exception("Error scraping parts for model_id='%s' at URL=%s", self.model_id, self.parts_url)
                break
        elapsed = time.time() - start_time
        logger.info("ModelScraper._scrape_parts_and_store() completed in %.4f seconds", elapsed)
        if query:
            return "\n".join([str(part) for part in parts])
        return list(all_ids)

    def search_parts(self, query: str) -> list[str]:
        """
        Search for parts by name. 
        """
        return self._scrape_part_ids(query)

    def _parse_part_block(self, part_div) -> PartItem:
        """
        Create a PartItem from a single <div class="mega-m__part"> block 
        on the parts page. 
        """
        logger.debug("ModelScraper._parse_part_block() called for model_id='%s'", self.model_id)
        availability = "No Longer Available" not in part_div.text

        ps_el = part_div.find("span", string="PartSelect #:")
        part_select_id = ps_el.next_sibling.strip() if ps_el else None

        mn_el = part_div.find("span", string="Manufacturer #:")
        manufacturer_id = mn_el.next_sibling.strip() if mn_el else None

        part_name_el = part_div.select_one("a.mega-m__part__name")
        part_name = part_name_el.text.strip() if part_name_el else None

        anchor = part_div.find("a")
        if anchor and anchor.get("href"):
            part_url = self.base_url + anchor["href"].lstrip("/")
        else:
            part_url = None

        item = PartItem(
            part_select_id=part_select_id,
            manufacturer_id=manufacturer_id,
            name=part_name,
            url=part_url,
            availability=availability,
        )
        return item

    def _scrape_symptoms(self) -> str:
        """
        Return them as a single big string. 
        Example: each 'a.symptoms' => we gather URL + description
        """
        logger.info("ModelScraper._scrape_symptoms() for model_id='%s'", self.model_id)
        start_time = time.time()
        try:
            symptom_elements = self.get_items('a.symptoms', self.model_url)
            if not symptom_elements:
                logger.warning("No symptoms found for model_id='%s' at URL=%s", self.model_id, self.model_url)
                return ""

            lines = []
            for i, sym_el in enumerate(symptom_elements, 1): # limit to ten
                symptom_url = "https://www.partselect.com" + sym_el.get("href", "")
                desc_el = sym_el.select_one('.symptoms__descr')
                symptom_description = desc_el.text.strip() if desc_el else ""
                lines.append(f"{i}. {symptom_url}\n{symptom_description}\n")

            return "(links below provide lists of symptoms, you may call get_symptom_parts on them to get corresponding parts)" + "\n".join(lines)
        finally:
            elapsed = time.time() - start_time
            logger.info("ModelScraper._scrape_symptoms() completed in %.4f seconds", elapsed)

    def __str__(self):
        """
        Summarize relevant info about the model for debugging or printing.
        """
        return (
            f"model_id: {self.model_id}\n"
            f"model url: {self.model_url}\n"
            f"name: {self.name}\n"
            f"description: {self.none_string_handler(self.description)}\n"
            f"symptoms: {self.none_string_handler(self.symptoms)}\n"
            f"link for all parts: {self.none_string_handler(self.parts_url)} [hidden too long]"
        )
