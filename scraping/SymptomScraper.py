from dataclasses import asdict
from scraping.AbstractScraper import AbstractScraper
from scraping.itemclasses import ModelItem, PartItem
from scraping.database import DatabaseHandler
from typing import Optional
PARTS_URL = "https://www.partselect.com/Models/{}/Parts/"
MODEL_URL = "https://www.partselect.com/Models/{}"
SYMPTOM_URL = "https://www.partselect.com/Models/{}/Symptoms/{}"

class SymptomScraper(AbstractScraper):
    """
    Scraper that loads a model page, retrieves data,
    and populates a ModelItem. 
    We also upsert each PartItem into the 'parts' table,
    and store a comma-separated list of part_select_nums in self.model.parts.
    """
    def __init__(self, url: str, model_id: str= None, symptom_name: str= None):
        if not url:
            if not model_id or not symptom_name:
                raise ValueError("You must either a url or a model ID and symptom name.")
            self.url = SYMPTOM_URL.format(model_id, symptom_name)
        else:
            self.url = url
        super().__init__(start_url=url)
        self.model_id = model_id
        self.symptoms = {}
        self.click(url, 'div.bold.text-link[data-collapse-trigger=show-more]')
        self.symptom_divs = self.soup.select('div.symptoms')
        self.symptoms_string, self.symptoms = self.set_symptoms()
    
    def __init__(self, db: Optional[DatabaseHandler] = None):
        super().__init__(db=db)

    def new(self, url):
        if not url:
            raise ValueError("You must provide a URL.")
        self.url = url
        self.driver.get(self.url)
        self.symptoms = {}
        self.click(url, 'div.bold.text-link[data-collapse-trigger=show-more]')
        self.symptom_divs = self.soup.select('div.symptoms')
        self.symptoms_string, self.symptoms = self.set_symptoms()
    
    def set_symptoms(self):
        self.symptoms = {}
        self.symptoms_string = ""
        for num, symptom_el in enumerate(self.symptom_divs, 1):
            symptom_percent = symptom_el.select_one('div.symptoms__percent').text.strip()
            item = symptom_el.select_one('div.flex-grow-1 div.flex-grow-1')
            link_a = item.select_one('a')
            link = link_a['href']
            part_title = link_a.text.strip()
            part_model_number = item.select_one('div a').text.strip()
            part_price = symptom_el.select_one('div.symptoms__buy-part div.mega-m__part__price').text.strip()
            self.symptoms[part_model_number] = {
                "title": part_title,
                "percent": symptom_percent,
                "link": link,
                "price": part_price
            }
            self.symptoms_string += f"{num}. {part_title} ({part_model_number}) - {symptom_percent} - {part_price}\n"
        return self.symptoms_string, self.symptoms
    
    def __str__(self):
        return self.symptoms_string