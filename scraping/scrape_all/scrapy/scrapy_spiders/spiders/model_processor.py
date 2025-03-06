import scrapy
import sqlite3
from urllib.parse import urljoin
from ..items import ModelProcessorItem, FailedURLItem

class ModelProcessorSpider(scrapy.Spider):
    name = "model_processor"
    allowed_domains = ["partselect.com"]

    custom_settings = {
        "DOWNLOAD_DELAY": 1,
        "AUTOTHROTTLE_ENABLED": True,
        "AUTOTHROTTLE_START_DELAY": 2,
        "AUTOTHROTTLE_MAX_DELAY": 10,
        "RETRY_TIMES": 7
    }

    def __init__(self, db_offset=0, db_limit=50, was_missed="False", *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.db_offset = int(db_offset)
        self.db_limit = int(db_limit)
        self.was_missed = (was_missed.lower() == "true")

    def start_requests(self):
        conn = sqlite3.connect("scraped_data.sqlite")
        cur = conn.cursor()

        if self.was_missed:
            cur.execute("SELECT url FROM failed_urls WHERE spider=?", (self.name,))
            rows = cur.fetchall()
        else:
            query = """
                SELECT url FROM gather_items
                WHERE type='model'
                ORDER BY url
                LIMIT ? OFFSET ?
            """
            cur.execute(query, (self.db_limit, self.db_offset))
            rows = cur.fetchall()

        conn.close()

        if not rows:
            self.logger.info(f"{self.name} found no model URLs to process (was_missed={self.was_missed}).")
            return

        for (model_url,) in rows:
            yield scrapy.Request(
                model_url,
                callback=self.parse_model_main,
                errback=self.errback_failure,
                meta={"model_url": model_url}
            )

    def parse_model_main(self, response):
        if self.was_missed:
            yield FailedURLItem(spider_name=self.name, url=response.url, remove=True)

        model_url = response.meta["model_url"]
        name_el = response.css(".title-main.d-inline::text").get()
        model_name = name_el.strip() if name_el else None

        symptoms = []
        symptom_links = response.css("a.symptoms")
        for link in symptom_links:
            rel_url = link.attrib.get("href", "")
            full_url = urljoin(response.url, rel_url)
            descr = link.css(".symptoms__descr::text").get()
            symptoms.append({
                "url": full_url,
                "description": descr.strip() if descr else ""
            })

        model_id = model_url.rstrip("/").split("/")[-1]
        parts_url = f"https://www.partselect.com/Models/{model_id}/Parts/"

        partial_item = {
            "model_url": model_url,
            "model_name": model_name,
            "rating": None,
            "description": None,
            "symptoms": symptoms,
            "parts": []
        }

        yield scrapy.Request(
            url=parts_url,
            callback=self.parse_parts_page,
            meta={"partial_item": partial_item, "page_index": 1}
        )

    def parse_parts_page(self, response):
        partial_item = response.meta["partial_item"]
        page_index = response.meta["page_index"]

        part_divs = response.css("div.mega-m__part")
        for div in part_divs:
            if "No Longer Available" in div.get():
                continue
            part_name = div.css("a.mega-m__part__name::text").get("")
            part_name = part_name.strip()
            part_url = div.css("a.mega-m__part__name::attr(href)").get()

            ps_el = div.xpath(".//span[contains(text(),'PartSelect #:')]/following-sibling::text()").get()
            part_select_num = ps_el.strip() if ps_el else None

            manuf_el = div.xpath(".//span[contains(text(),'Manufacturer #:')]/following-sibling::text()").get()
            manufacture_num = manuf_el.strip() if manuf_el else None

            partial_item["parts"].append({
                "name": part_name,
                "url": part_url,
                "part_select_num": part_select_num,
                "manufacture_num": manufacture_num
            })

        page_links = response.css("ul.pagination.js-pagination li a[href]")
        page_nums = []
        for link in page_links:
            txt = link.css("::text").get("")
            if txt.isdigit():
                page_nums.append(int(txt))
        last_page = max(page_nums) if page_nums else 1

        if page_index < last_page:
            next_page_index = page_index + 1
            next_page_url = f"{response.url}?start={next_page_index}"
            yield scrapy.Request(
                url=next_page_url,
                callback=self.parse_parts_page,
                meta={
                    "partial_item": partial_item,
                    "page_index": next_page_index
                }
            )
        else:
            # final
            yield ModelProcessorItem(**partial_item)

    def errback_failure(self, failure):
        url = failure.request.url
        self.logger.warning(f"{self.name}: Request failed permanently: {url}")
        yield FailedURLItem(spider_name=self.name, url=url, remove=False)
