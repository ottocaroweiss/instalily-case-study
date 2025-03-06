# file: pipelines.py
import sqlite3
import json as pyjson
from scrapy.exceptions import NotConfigured
from .items import (
    GatherItem, ModelProcessorItem, PartProcessorItem,
    FailedURLItem  # newly imported
)

class SQLStorePipeline:
    def open_spider(self, spider):
        self.connection = sqlite3.connect("scraper_data.sqlite")
        self.cursor = self.connection.cursor()

        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS gather_items (
                url TEXT PRIMARY KEY,
                type TEXT,
                name TEXT
            )
        """)
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS model_processor_items (
                model_url TEXT PRIMARY KEY,
                model_id TEXT,
                model_name TEXT,
                rating REAL,
                description TEXT,
                symptoms TEXT,
                parts TEXT
            )
        """)
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS part_processor_items (
                part_url TEXT PRIMARY KEY,
                part_name TEXT,
                partselect_num TEXT,
                manufacturer_num TEXT,
                price REAL,
                difficulty TEXT,
                time TEXT,
                rating REAL,
                description TEXT,
                troubleshooting TEXT
            )
        """)
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS failed_urls (
                spider TEXT,
                url TEXT,
                UNIQUE(spider, url)
            )
        """)

    def close_spider(self, spider):
        self.connection.commit()
        self.connection.close()

    def process_item(self, item, spider):
        if isinstance(item, GatherItem):
            self.save_gather_item(item)
        elif isinstance(item, ModelProcessorItem):
            self.save_model_processor_item(item)
        elif isinstance(item, PartProcessorItem):
            self.save_part_processor_item(item)
        elif isinstance(item, FailedURLItem):
            self.save_failed_url_item(item)
        return item

    def save_gather_item(self, item):
        self.cursor.execute("""
            INSERT OR REPLACE INTO gather_items (url, type, name)
            VALUES (?, ?, ?)
        """, (
            item.get("url"),
            item.get("type"),
            item.get("name")
        ))
        self.connection.commit()

    def save_model_processor_item(self, item):
        symptoms_str = None
        parts_str = None
        if item.get("symptoms"):
            symptoms_str = pyjson.dumps(item["symptoms"], ensure_ascii=False)
        if item.get("parts"):
            parts_str = pyjson.dumps(item["parts"], ensure_ascii=False)

        self.cursor.execute("""
            INSERT OR REPLACE INTO model_processor_items (
                model_url, model_id, model_name, rating, description, symptoms, parts
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            item.get("model_url"),
            item.get("model_id"),
            item.get("model_name"),
            item.get("rating"),
            item.get("description"),
            symptoms_str,
            parts_str
        ))
        self.connection.commit()

    def save_part_processor_item(self, item):
        self.cursor.execute("""
            INSERT OR REPLACE INTO part_processor_items (
                part_url, part_name, partselect_num, manufacturer_num,
                price, difficulty, time, rating, description, troubleshooting
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            item.get("part_url"),
            item.get("part_name"),
            item.get("partselect_num"),
            item.get("manufacturer_num"),
            item.get("price"),
            item.get("difficulty"),
            item.get("time"),
            item.get("rating"),
            item.get("description"),
            item.get("troubleshooting")
        ))
        self.connection.commit()

    def save_failed_url_item(self, item):
        """
        If remove=True => we delete from failed_urls
        else => insert or ignore
        """
        spider_name = item.get("spider_name")
        url = item.get("url")
        remove = item.get("remove", False)

        if remove:
            self.cursor.execute("""
                DELETE FROM failed_urls
                WHERE spider=? AND url=?
            """, (spider_name, url))
        else:
            self.cursor.execute("""
                INSERT OR IGNORE INTO failed_urls (spider, url)
                VALUES (?, ?)
            """, (spider_name, url))

        self.connection.commit()
