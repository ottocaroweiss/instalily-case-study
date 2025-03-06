# Define here the models for your scraped items
#
# See documentation in:
# https://docs.scrapy.org/en/latest/topics/items.html

import scrapy


class GatherItem(scrapy.Item):
    type = scrapy.Field()  # e.g. "part"
    name = scrapy.Field()
    url = scrapy.Field()

class ModelProcessorItem(scrapy.Item):
    model_id = scrapy.Field()
    model_name = scrapy.Field()
    model_url = scrapy.Field()
    rating = scrapy.Field()
    description = scrapy.Field()
    symptoms = scrapy.Field()
    parts = scrapy.Field()

class PartProcessorItem(scrapy.Item):
    part_name = scrapy.Field()
    part_url = scrapy.Field()
    partselect_num = scrapy.Field()
    manufacturer_num = scrapy.Field()
    price = scrapy.Field()
    difficulty = scrapy.Field()
    time = scrapy.Field()
    rating = scrapy.Field()
    description = scrapy.Field()

class FailedURLItem(scrapy.Item):
    """
    A special item used purely for logging permanently-failed requests
    into the 'failed_urls' table by the pipeline.
    """
    spider_name = scrapy.Field()
    url = scrapy.Field()
    remove = scrapy.Field() # If True, remove the URL from the table



