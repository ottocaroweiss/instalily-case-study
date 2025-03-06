# database.py

import sqlite3
from typing import Optional, List

from scraping.itemclasses import *
from scraping.database_utils import (
    generate_create_table_sql,
    generate_upsert_sql
)

DATABASE_PATH = "scraper_data.sqlite"

class DatabaseHandler:
    def __init__(self, db_path: str = DATABASE_PATH, thread_protected: bool = False):
        self.conn = sqlite3.connect(db_path, check_same_thread=thread_protected)
        self.cursor = self.conn.cursor()
        self.conn.row_factory = sqlite3.Row
        # Turn on Foreign Keys if desired
        self.cursor.execute("PRAGMA foreign_keys=ON;")
        self._create_tables()

    def _create_tables(self):
        """
        Creates necessary tables if they don't exist using dynamic SQL generation.
        """

        # ============== PARTS TABLE ==============
        create_parts_sql = generate_create_table_sql(
            cls=PartItem,
            table_name="parts",
            primary_key="manufacturer_id",
            auto_increment_pk=False  # we want part_select_num as text PK, not autoincrement
        )
        self.cursor.execute(create_parts_sql)

        self.upsert_parts_sql = generate_upsert_sql(
            cls=PartItem,
            table_name="parts",
            primary_key="manufacturer_id"
        )

        # ============== MODELS TABLE ==============
        create_models_sql = generate_create_table_sql(
            cls=ModelItem,
            table_name="models",
            primary_key="id",
            auto_increment_pk=False
        )
        self.cursor.execute(create_models_sql)

        self.upsert_models_sql = generate_upsert_sql(
            cls=ModelItem,
            table_name="models",
            primary_key="id"
        )

        # ============== PART_REPLACEMENTS TABLE ==============
        # If you want an autoincrement integer PK for replacement_id
        create_replacements_sql = generate_create_table_sql(
            cls=PartReplacementItem,
            table_name="part_replacements",
            primary_key="replacement_id",
            auto_increment_pk=True
        )
        
        self.cursor.execute(create_replacements_sql)

        self.upsert_replacements_sql = generate_upsert_sql(
            cls=PartReplacementItem,
            table_name="part_replacements",
            primary_key="replacement_id",
        )
        
        create_reviews_sql = generate_create_table_sql(
            cls=PartReviewItem,
            table_name="part_reviews",
            primary_key="review_id",
            auto_increment_pk=True
        )
        self.cursor.execute(create_reviews_sql)
        
        self.upsert_reviews_sql = generate_upsert_sql(
            cls=PartReviewItem,
            table_name="part_reviews",
            primary_key="review_id"
        )

        

        self.conn.commit()

        create_stories_sql = generate_create_table_sql(
            cls=PartReviewStoryItem,
            table_name="part_review_stories",
            primary_key="story_id",
            auto_increment_pk=True
        )
        self.cursor.execute(create_stories_sql)

        self.upsert_stories_sql = generate_upsert_sql(
            cls=PartReviewStoryItem,
            table_name="part_review_stories",
            primary_key="story_id"
        )

        self.conn.commit()

        create_qna_sql = generate_create_table_sql(
            cls=PartQnAItem,
            table_name="part_qna",
            primary_key="qna_id",
            auto_increment_pk=True
        )
        self.cursor.execute(create_qna_sql)

        self.upsert_qna_sql = generate_upsert_sql(
            cls=PartQnAItem,
            table_name="part_qna",
            primary_key="qna_id"
        )

        self.conn.commit()

    # ----------------------------------------------------------------
    # PARTS
    # ----------------------------------------------------------------
    def get_part(self, manufacturer_id: str) -> Optional[PartItem]:
        col_names = list(PartItem.__dataclass_fields__.keys())  # e.g. ["part_select_num","manufacture_num",...]
        col_list = ", ".join(col_names)
        sql = f"SELECT {col_list} FROM parts WHERE manufacturer_id=?"
        self.cursor.execute(sql, (manufacturer_id,))
        row = self.cursor.fetchone()
        if not row:
            return None
        
        data_dict = {}
        for idx, name in enumerate(col_names):
            data_dict[name] = row[idx]
        return PartItem(**data_dict)

    def save_part(self, part: PartItem):
        # Gather field values in the correct order
        col_names = list(PartItem.__dataclass_fields__.keys())
        values = [getattr(part, c) for c in col_names]

        # Use the upsert statement
        self.cursor.execute(self.upsert_parts_sql, values)
        self.conn.commit()

    # ----------------------------------------------------------------
    # MODELS
    # ----------------------------------------------------------------
    def get_model(self, model_id: str) -> Optional[ModelItem]:
        try:
            col_names = list(ModelItem.__dataclass_fields__.keys())
            col_list = ", ".join(col_names)
            print(col_list)
            print(model_id)
            sql = f"SELECT * FROM models WHERE id=?"
            self.cursor.execute(sql, (model_id,))
            row = self.cursor.fetchone()
            if not row:
                return None
            
            data_dict = {}
            for idx, name in enumerate(col_names):
                data_dict[name] = row[idx]
            return ModelItem(**data_dict)
        except Exception as e:
            print("Error in get_model:", e)
            return None

    def save_model(self, model: ModelItem):
        col_names = list(ModelItem.__dataclass_fields__.keys())
        values = [getattr(model, c) for c in col_names]

        self.cursor.execute(self.upsert_models_sql, values)
        self.conn.commit()

    # ----------------------------------------------------------------
    # PART_REPLACEMENTS
    # ----------------------------------------------------------------
    def get_part_replacements(self, part_select_num: str) -> List[PartReplacementItem]:
        """
        Example: If you want to fetch all replacements for a given part_select_num.
        But note, we have a PK on replacement_id, so we do a normal SELECT * approach.
        """
        # We'll do a big SELECT because we want them all
        col_names = list(PartReplacementItem.__dataclass_fields__.keys())
        col_list = ", ".join(col_names)
        sql = f"SELECT {col_list} FROM part_replacements WHERE part_select_id=?"
        self.cursor.execute(sql, (part_select_num,))
        rows = self.cursor.fetchall()
        items = []
        for row in rows:
            data_dict = {}
            for idx, name in enumerate(col_names):
                data_dict[name] = row[idx]
            items.append(PartReplacementItem(**data_dict))
        return items

    def save_part_replacement(self, rep: PartReplacementItem):
        """
        Upsert a single replacement item. If 'replacement_id' is None, it means
        we can't do an ON CONFLICT(...) unless we define some unique constraint
        on (part_select_num, replacement_text). For demonstration, let's do it anyway.
        """
        col_names = list(PartReplacementItem.__dataclass_fields__.keys())
        values = [getattr(rep, c) for c in col_names]

        # This will do ON CONFLICT(replacement_id) if you pass a non-None ID.
        # If replacement_id is None, it will just do a normal insert
        # If there's a collision on replacement_id=some_value, it does partial update.
        self.cursor.execute(self.upsert_replacements_sql, values)
        self.conn.commit()

    def save_part_replacements(self, replacements: List[PartReplacementItem]):
        """
        If you want to batch-upsert multiple PartReplacementItem in one go.
        """
        if not replacements:
            return
        for rep in replacements:
            self.save_part_replacement(rep)
    

    # ------------------------------------------------
    # PART REVIEWS
    # ------------------------------------------------
    def get_part_reviews(self, manufacturer_id: str) -> List[PartReviewItem]:
        """
        Return all reviews for the given 'manufacturer_id' (i.e. part_select_num).
        """
        col_names = list(PartReviewItem.__dataclass_fields__.keys())
        col_list = ", ".join(col_names)
        sql = f"SELECT {col_list} FROM part_reviews WHERE manufacturer_id=?"
        self.cursor.execute(sql, (manufacturer_id,))
        rows = self.cursor.fetchall()

        items = []
        for row in rows:
            data_dict = {}
            for idx, name in enumerate(col_names):
                data_dict[name] = row[idx]
            items.append(PartReviewItem(**data_dict))
        return items

    def save_part_review(self, review: PartReviewItem):
        """
        Inserts or upserts a single review. If 'review_id' is None, we do a normal insert.
        If 'review_id' is set and collides, we partially update (with COALESCE).
        """
        col_names = list(PartReviewItem.__dataclass_fields__.keys())
        values = [getattr(review, c) for c in col_names]

        self.cursor.execute(self.upsert_reviews_sql, values)
        self.conn.commit()

    def save_part_reviews(self, reviews: List[PartReviewItem]):
        """
        Convenience method to insert multiple reviews.
        """
        for r in reviews:
            self.save_part_review(r)

    def get_part_review_stories(self, manufacturer_id: str) -> List[PartReviewStoryItem]:
        """
        Return all 'repair stories' for the given 'manufacturer_id'.
        """
        col_names = list(PartReviewStoryItem.__dataclass_fields__.keys())
        col_list = ", ".join(col_names)
        sql = f"SELECT {col_list} FROM part_review_stories WHERE manufacturer_id=?"
        self.cursor.execute(sql, (manufacturer_id,))
        rows = self.cursor.fetchall()

        items = []
        for row in rows:
            data_dict = {}
            for idx, name in enumerate(col_names):
                data_dict[name] = row[idx]
            items.append(PartReviewStoryItem(**data_dict))
        return items

    def save_part_review_story(self, story: PartReviewStoryItem):
        col_names = list(PartReviewStoryItem.__dataclass_fields__.keys())
        values = [getattr(story, c) for c in col_names]
        self.cursor.execute(self.upsert_stories_sql, values)
        self.conn.commit()

    def save_part_review_stories(self, stories: List[PartReviewStoryItem]):
        for st in stories:
            self.save_part_review_story(st)



    def get_part_qnas(self, manufacturer_id: str) -> List[PartQnAItem]:
        """
        Return all Q&A items for the given 'manufacturer_id'.
        """
        col_names = list(PartQnAItem.__dataclass_fields__.keys())
        col_list = ", ".join(col_names)
        sql = f"SELECT {col_list} FROM part_qna WHERE manufacturer_id=?"
        self.cursor.execute(sql, (manufacturer_id,))
        rows = self.cursor.fetchall()

        items = []
        for row in rows:
            data_dict = {}
            for idx, name in enumerate(col_names):
                data_dict[name] = row[idx]
            items.append(PartQnAItem(**data_dict))
        return items

    def save_part_qnas(self, qnas: List[PartQnAItem]):
        """
        Upsert multiple Q&A rows in a single executemany call.
        Uses the COALESCE-based upsert, so if qna_id is None, we do an INSERT,
        if qna_id conflicts, we do partial updates.
        """
        if not qnas:
            return

        # Build the value list for each row
        col_names = list(PartQnAItem.__dataclass_fields__.keys())
        # e.g. ["qna_id", "manufacturer_id", "question", "model_number", "answer"]
        all_values = []
        for qna in qnas:
            row_vals = [getattr(qna, c) for c in col_names]
            all_values.append(row_vals)
        print(all_values)
        self.cursor.executemany(self.upsert_qna_sql, all_values)
        self.conn.commit()


    def close(self):
        self.conn.close()
