import scrapy
import sqlite3
from ..items import GatherItem, FailedURLItem

class ModelGathererSpider(scrapy.Spider):
    name = "model_gatherer"
    allowed_domains = ["partselect.com"]

    custom_settings = {
        "DOWNLOAD_DELAY": 1,
        "AUTOTHROTTLE_ENABLED": True,
        "AUTOTHROTTLE_START_DELAY": 1,
        "AUTOTHROTTLE_MAX_DELAY": 10,
        "RETRY_TIMES": 7
    }

    def __init__(self, category="Dishwasher", start_page=1, end_page=1, was_missed="False", *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.category = category
        self.start_page = int(start_page)
        self.end_page = int(end_page)
        self.was_missed = (was_missed.lower() == "true")
        self.base_url = f"https://www.partselect.com/{self.category}-Models.htm"

    def start_requests(self):
        if self.was_missed:
            conn = sqlite3.connect("scraped_data.sqlite")
            cur = conn.cursor()
            cur.execute("SELECT url FROM failed_urls WHERE spider=?", (self.name,))
            rows = cur.fetchall()
            conn.close()

            if not rows:
                self.logger.info("No missed model URLs found for re-run.")
                return

            for (url,) in rows:
                yield scrapy.Request(url, callback=self.parse, errback=self.errback_failure)
        else:
            for page in range(self.start_page, self.end_page + 1):
                url = f"{self.base_url}?start={page}"
                yield scrapy.Request(url, callback=self.parse, errback=self.errback_failure)

    def parse(self, response):
        if self.was_missed:
            yield FailedURLItem(spider_name=self.name, url=response.url, remove=True)

        models = response.css("ul.nf__links li a")
        self.logger.info(f"Found {len(models)} models at {response.url}")

        for m in models:
            item = GatherItem()
            item["type"] = "model"
            item["name"] = m.css("::text").get(default="").strip()
            item["url"] = response.urljoin(m.attrib.get("href", ""))
            yield item

    def errback_failure(self, failure):
        url = failure.request.url
        self.logger.warning(f"{self.name} permanently failed: {url}")
        yield FailedURLItem(spider_name=self.name, url=url, remove=False)
