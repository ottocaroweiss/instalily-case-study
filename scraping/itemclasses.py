# /Users/ottoweiss/Desktop/instalily-case-study/scraping/itemclasses.py

from dataclasses import dataclass
from typing import Optional, List


@dataclass
class PartReplacementItem:
    """
    Represents an *individual* replacement part reference.
    E.g. "AP6030094", "8579307", etc.
    """
    replacement_id: int
    manufacturer_id: str
    replacement_text: str


@dataclass
class PartReviewItem:
    """
    Represents a single review for a part.
    review_id is an autoincrement PK.
    manufacturer_id is the part_select_num or "PSXXXXX".
    """
    review_id: int = None
    manufacturer_id: str = None
    header: Optional[str] = None
    text: Optional[str] = None

@dataclass
class PartReviewStoryItem:
    """
    Represents a single repair story for a part.
    story_id is an autoincrement PK.
    manufacturer_id is the part_select_num or "PSXXXXX".
    """
    story_id: int = None
    manufacturer_id: Optional[str] = None
    title: Optional[str] = None
    text: Optional[str] = None



@dataclass
class PartQnAItem:
    """
    Represents a single Q&A entry for a part.
    qna_id is an autoincrement PK.
    manufacturer_id is e.g. "PS11759673"
    question, model_number, answer are scraped from the Q&A section
    """
    qna_id: int = None
    manufacturer_id: Optional[str] = None
    question: Optional[str] = None
    model_number: Optional[str] = None
    answer: Optional[str] = None

@dataclass
class PartItem:
    """
    Represents a part with only scalar fields (no lists).
    """
    manufacturer_id: str = None
    part_select_id: Optional[str] = None
    name: Optional[str] = None
    url: Optional[str] = None
    availability: Optional[bool] = True
    #category: Optional[str] = None

    price: Optional[float] = None
    difficulty: Optional[str] = None
    time: Optional[str] = None
    rating: Optional[float] = None
    description: Optional[str] = None
    fixes: Optional[str]= None
    part_replacements: Optional[str]= None
    products: Optional[str] = None
    related_parts: Optional[str] = None

@dataclass
class ModelItem:
    """
    Represents a model with only scalar fields for the model.
    """
    id: str
    name: Optional[str] = None
    description: Optional[str] = None
    parts: Optional[str] = None
    symptoms: Optional[str] = None