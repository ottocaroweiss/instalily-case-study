# my_tools.py

import os
import time
import logging
import sqlite3
import atexit
from typing import Dict
from concurrent.futures import ProcessPoolExecutor, as_completed
# Load environment variables from .env
from dotenv import load_dotenv
load_dotenv()
# External libraries
from langchain_community.tools import tool
from langchain_community.docstore.document import Document
from langchain_community.embeddings import OpenAIEmbeddings
from langchain_community.vectorstores.chroma import Chroma

# Local imports
from scraping.database import DatabaseHandler
from scraping.PartScraper import PartScraper
from scraping.ModelScraper import ModelScraper
from scraping.SymptomScraper import SymptomScraper

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Global DB for the session
DB = DatabaseHandler()
DB.conn.row_factory = sqlite3.Row
atexit.register(DB.close)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

###############################################################################
# Instantiating scrapers
###############################################################################
def get_model_scraper():
    return ModelScraper(db=DB)

def get_part_scraper():
    return PartScraper(db=DB)

def get_symptom_scraper():
    return SymptomScraper(db=DB)

PART_SCRAPER = get_part_scraper
MODEL_SCRAPER = get_model_scraper
SYMPTOM_SCRAPER = get_symptom_scraper

###############################################################################
# Global paths and vector store references
###############################################################################
CHROMA_MAIN_DIR = "chroma_db"
ALL_PARTS_DIR = os.path.join(CHROMA_MAIN_DIR, "all_parts")

all_parts_index = None
PART_USER_TEXT_INDEXES: Dict[str, Chroma] = {}

###############################################################################
# 1) Build & Access the 'all_parts' Vector Store
###############################################################################
def _build_all_parts_index():
    """
    Builds and persists the vectorstore for 'all_parts' from the DB.
    Embeds name, description, fixes fields, plus rating & price in metadata.
    """
    global all_parts_index
    logger.info("Building vector index for all_parts...")

    selected_columns = ["manufacturer_id", "part_select_id", "name", "description", "fixes"]
    col_list = ", ".join(selected_columns)

    db = DatabaseHandler()
    db.conn.row_factory = sqlite3.Row
    c = db.conn.cursor()
    query = f"SELECT {col_list} FROM parts"
    c.execute(query)
    rows = c.fetchall()
    db.conn.close()

    docs = []
    for idx, row in enumerate(rows):
        manufacturer_id = row["manufacturer_id"]
        part_select_id = row["part_select_id"]

        # name
        name_str = (row["name"] or "").strip()
        if name_str:
            docs.append(
                Document(
                    page_content=name_str,
                    metadata={
                        "manufacturer_id": manufacturer_id,
                        "part_select_id": part_select_id,
                        "field": "name",
                    }
                )
            )

        # description
        desc_str = (row["description"] or "").strip()
        if desc_str:
            docs.append(
                Document(
                    page_content=desc_str,
                    metadata={
                        "manufacturer_id": manufacturer_id,
                        "part_select_id": part_select_id,
                        "field": "description",
                    }
                )
            )

        # fixes
        fixes_str = (row["fixes"] or "").strip()
        if fixes_str:
            docs.append(
                Document(
                    page_content=fixes_str,
                    metadata={
                        "manufacturer_id": manufacturer_id,
                        "part_select_id": part_select_id,
                        "field": "fixes",
                    }
                )
            )

    logger.info(f"Building Chroma store from {len(docs)} doc(s).")
    all_parts_index = Chroma.from_documents(
        docs,
        embedding=OpenAIEmbeddings(api_key=OPENAI_API_KEY),
        collection_name="all_parts_collection",
        persist_directory=ALL_PARTS_DIR,
    )
    logger.info(f"[AllPartsIndex] Built with {len(docs)} docs at {ALL_PARTS_DIR}")


def _get_all_parts_index() -> Chroma:
    global all_parts_index
    if all_parts_index:
        return all_parts_index

    if os.path.exists(ALL_PARTS_DIR) and os.listdir(ALL_PARTS_DIR):
        logger.info(f"[AllPartsIndex] Loading existing index from {ALL_PARTS_DIR}")
        all_parts_index = Chroma(
            persist_directory=ALL_PARTS_DIR,
            collection_name="all_parts_collection",
            embedding_function=OpenAIEmbeddings(api_key=OPENAI_API_KEY),
        )
    else:
        logger.info("No existing all_parts index found. Building fresh index.")
        _build_all_parts_index()

    return all_parts_index

###############################################################################
# 2) Build & Access Part-Specific User Text Vector Stores
###############################################################################
def _build_part_user_text_index(manufacturer_id: str, force_rebuild: bool = False) -> None:
    global PART_USER_TEXT_INDEXES

    persist_dir = os.path.join(CHROMA_MAIN_DIR, f"user_text_{manufacturer_id}")
    if not force_rebuild and os.path.exists(persist_dir) and os.listdir(persist_dir):
        logger.info(f"[PartUserTextIndex] Loading existing index for {manufacturer_id}")
        PART_USER_TEXT_INDEXES[manufacturer_id] = Chroma(
            persist_directory=persist_dir,
            collection_name=f"user_text_{manufacturer_id}",
            embedding_function=OpenAIEmbeddings(api_key=OPENAI_API_KEY),
        )
        return

    logger.info(f"[PartUserTextIndex] Building fresh index for {manufacturer_id} ...")

    part_scraper = PART_SCRAPER()
    try:
        part_scraper.new(manufacturer_id=manufacturer_id)
        part_scraper.scrape_all()
        part_reviews = part_scraper.reviews
        part_stories = part_scraper.stories
        part_qnas = part_scraper.questions
    except:
        logger.warning(f"Part Scraper failed to scrape for manufacturer-id={manufacturer_id}.")
        return "FAILURE: Are you sure you provided the part id and not the model id?"

    docs = []
    for rv in part_reviews:
        text = f"[ReviewHeader]: {rv.header or ''}\n[ReviewText]: {rv.text or ''}"
        meta = {"type": "review", "review_id": rv.review_id}
        docs.append(Document(page_content=text, metadata=meta))

    for st in part_stories:
        text = f"[StoryTitle]: {st.title or ''}\n[StoryText]: {st.text or ''}"
        meta = {"type": "story", "story_id": st.story_id}
        docs.append(Document(page_content=text, metadata=meta))

    for qq in part_qnas:
        text = f"[Question]: {qq.question or ''}\n[Answer]: {qq.answer or ''}"
        meta = {"type": "qna", "qna_id": qq.qna_id}
        docs.append(Document(page_content=text, metadata=meta))

    os.makedirs(persist_dir, exist_ok=True)

    if docs:
        index = Chroma.from_documents(
            docs,
            embedding=OpenAIEmbeddings(api_key=OPENAI_API_KEY),
            collection_name=f"user_text_{manufacturer_id}",
            persist_directory=persist_dir
        )
        PART_USER_TEXT_INDEXES[manufacturer_id] = index
        logger.info(f"[PartUserTextIndex] Built user-text index with {len(docs)} docs for part {manufacturer_id}")
    else:
        empty_index = Chroma.from_texts(
            texts=["(empty)"],
            embedding=OpenAIEmbeddings(api_key=OPENAI_API_KEY),
            collection_name=f"user_text_{manufacturer_id}",
            persist_directory=persist_dir
        )
        PART_USER_TEXT_INDEXES[manufacturer_id] = empty_index
        logger.info(f"[PartUserTextIndex] No user docs for {manufacturer_id}; created empty index.")

###############################################################################
# 3) Search Tools
###############################################################################


@tool(description="Given an appliance model id (fridge or dishwasher), word match search query on matching part titles. Args: appliance_id(str), query(str). Returns detailed text on any matching parts. Limit length of query to between one and three words.")
def search_parts_of_an_appliance(appliance_id: str, query: str) -> str:
    start_time = time.time()
    logger.info(f"Tool search_parts_by_appliance_id called with appliance_id='{appliance_id}'")
    try:
        model_scraper = MODEL_SCRAPER()
        model_scraper.new(manufacturer_id=appliance_id)
        return model_scraper.search_parts(query=query)
    finally:
        elapsed = time.time() - start_time
        logger.info(f"Tool scrape_model_symptoms completed in {elapsed:.4f} sec")




@tool(description="Semantically search reviews, stories, and customer support text on a specific part id (commonly starts with PS). Make sure to use the id of the part and not the model. Please make your query at least 4 words long. Args: manufacturer_id and a query. Returns string or 'NO SEARCH'.")
def search_all_customer_text_on_individual_part_tool(manufacturer_id: str, query: str) -> str:
    start_time = time.time()
    logger.info(f"Tool search_all_customer_text_on_individual_part_tool called with manufacturer_id='{manufacturer_id}', query='{query}'")
    if not manufacturer_id:
        return "FAILURE: You did not provide a manufacturer id."
    query = query.strip()
    if not query:
        return "FAILURE: You did not provide a query."
    top_k = 5

    if manufacturer_id not in PART_USER_TEXT_INDEXES:
        _build_part_user_text_index(manufacturer_id, force_rebuild=True)
    
    index = PART_USER_TEXT_INDEXES[manufacturer_id]
    results = index.similarity_search(query, k=top_k)
    if not results:
        return "NO SEARCH"

    lines = []
    for i, doc in enumerate(results):
        typ = doc.metadata.get("type", "?")
        lines.append(f"{i} - {typ}:\n{doc.page_content}")
    return "\n".join(lines)


@tool(description="Semantic search in customer support only for a single part. Use this for sepecific or general questions that are not about the product. Args: manufacturer_id, question, k(opt).  Please make your query at least 4 words long. Returns snippet or 'NO SEARCH'.")
def search_customer_support_on_individual_part_tool(manufacturer_id: str, question: str, k: str = "3") -> str:
    start_time = time.time()
    logger.info(f"Tool search_customer_support_on_individual_part_tool called with manufacturer_id='{manufacturer_id}', question='{question}', k='{k}'")
    try:
        question = question.strip()
        if not question:
            return "NO SEARCH"
        top_k = int(k) if k else 3

        if manufacturer_id not in PART_USER_TEXT_INDEXES:
            _build_part_user_text_index(manufacturer_id, force_rebuild=True)

        index = PART_USER_TEXT_INDEXES[manufacturer_id]
        results = index.similarity_search(question, k=top_k)
        if not results:
            return "NO SEARCH"

        filtered = [r for r in results if r.metadata.get("type") == "qna"]
        if not filtered:
            return "NO SEARCH"

        lines = []
        for doc in filtered:
            snippet = doc.page_content[:100].replace("\n", " ")
            lines.append(f"QnA => {snippet}...")
        return "\n".join(lines)
    finally:
        elapsed = time.time() - start_time
        logger.info(f"Tool search_customer_support_on_individual_part_tool completed in {elapsed:.4f} sec")

###############################################################################
# 4) Database Tools
###############################################################################
@tool(description="Retrieve all details on a specific part by the id. Returns a string or 'INVALID PART ID'. Arg is manufacturer_id.")
def get_part_by_id(manufacturer_id: str) -> str:
    start_time = time.time()
    logger.info(f"Tool get_part_by_id called with manufacturer_id='{manufacturer_id}'")
    try:
        part_scraper = PART_SCRAPER()
        part_scraper.new(manufacturer_id=manufacturer_id)
        return str(part_scraper)
    except Exception as e:
        try:
            model_scraper = MODEL_SCRAPER()
            model_scraper.new(manufacturer_id=manufacturer_id)
            return str(model_scraper)
        except:
            logger.error(f"Error in get_part_by_id: {e}")
            return "INVALID PART ID"
    finally:
        elapsed = time.time() - start_time
        logger.info(f"Tool get_part_by_id completed in {elapsed:.4f} sec")


@tool(description="Given a dishwasher or refrigerator id, Rrtrieve details about the specific appliance (dishwasher or refrigerator). Returns a string or 'INVALID APPLIANCE ID'.")
def get_appliance_by_id(manufacturer_id: str) -> str:
    start_time = time.time()
    logger.info(f"Tool get_appliance_by_id called with model_id='{manufacturer_id}'")
    try:
        model_scraper = MODEL_SCRAPER()
        model_scraper.new(manufacturer_id=manufacturer_id)
        return str(model_scraper)
    except Exception as e:
        """        try:
            part_scraper = PART_SCRAPER()
            part_scraper.new(manufacturer_id=manufacturer_id)
            return str(part_scraper)
        except:
            logger.error(f"Error in get_part_by_id: {e}")
            return "INVALID APPLIANCE ID"""
        logger.error(f"E{e}")
        return "INVALID APPLIANCE ID"
    finally:
        elapsed = time.time() - start_time
        logger.info(f"Tool get_appliance_by_id completed in {elapsed:.4f} sec")


@tool(description="Check if a part and model are compatible. Must provide both fields. Returns 'true' or 'false'.")
def check_model_part_compatibility(part_id: str, appliance_id: str) -> str:
    start_time = time.time()
    logger.info(f"Tool check_compatibility called with part_select_id='{part_id}', model_id='{appliance_id}'")
    try:
        is_compatible = PartScraper.checkCompatibility(part_id, appliance_id)
        return "true" if is_compatible else "false"
    finally:
        elapsed = time.time() - start_time
        logger.info(f"Tool check_compatibility completed in {elapsed:.4f} sec")


@tool(description="Scrape an appliance's symptoms page (via url) and return a detailed list of parts for a symptom. "
"DO NOT USE UNLESS YOU HAVE ALREADY SCRAPED THE APPLICATION MODEL PAGE. Args: url(str). Returns a string.")
def scrape_model_symptoms(url: str) -> str:
    start_time = time.time()
    logger.info(f"Tool scrape_model_symptoms called with url='{url}'")
    try:
        sym_scraper = SYMPTOM_SCRAPER()
        sym_scraper.new(url=url)
        return sym_scraper.symptoms_string
    finally:
        elapsed = time.time() - start_time
        logger.info(f"Tool scrape_model_symptoms completed in {elapsed:.4f} sec")

###############################################################################
# NOT CURRENTLY USED: Tools/Functions for reference
###############################################################################

@tool(description=(
    "Fallback semantic search across parted-out fields (name, description, fixes). "
    "Args: name(str, optional), description(str, optional), symptoms(str, optional),"
    " k(str, int, optional). "
    "Returns top hits or 'NO SEARCH'."
))
def search_all_parts_tool(
    name: str = "",
    description: str = "",
    symptoms: str = "",
    k: str = "5"
) -> str:
    start_time = time.time()
    logger.info(
        "Tool search_all_parts_tool called with "
        f"name='{name}', description='{description}', symptoms='{symptoms}', k='{k}'"
    )

    try:
        # If no textual queries are provided, there's nothing to search
        if not (name.strip() or description.strip() or symptoms.strip()):
            return "NO SEARCH"

        top_k = int(k) if k else 5
        index = _get_all_parts_index()

        combined_results = []
        
        # 1) Search 'name' field if provided
        if name.strip():
            name_results = index.similarity_search(
                name.strip(),
                k=1000,
                filter={"field": "name"}
            )
            combined_results.extend(name_results)
        
        # 2) Search 'description' field if provided
        if description.strip():
            desc_results = index.similarity_search(
                description.strip(),
                k=1000,
                filter={"field": "description"}
            )
            combined_results.extend(desc_results)
        
        # 3) Search 'fixes' field if user passed 'symptoms'
        if symptoms.strip():
            fix_results = index.similarity_search(
                symptoms.strip(),
                k=1000,
                filter={"field": "fixes"}
            )
            combined_results.extend(fix_results)

        if not combined_results:
            return "NO SEARCH"

        # Deduplicate by manufacturer_id
        unique_docs = {}
        for doc in combined_results:
            mid = doc.metadata.get("manufacturer_id", "")
            if mid not in unique_docs:
                unique_docs[mid] = doc
        
        filtered = list(unique_docs.values())
        if not filtered:
            return "NO RESULTS"

        final_docs = filtered[:top_k]
        lines = []
        for doc in final_docs:
            snippet = doc.page_content.replace("\n", " ")
            mid = doc.metadata.get("manufacturer_id", "")
            field_label = doc.metadata.get("field", "")
            lines.append(f"[{field_label}] Part {mid} => {snippet}")

        return "\n".join(lines)
    finally:
        elapsed = time.time() - start_time
        logger.info(f"Tool search_all_parts_tool completed in {elapsed:.4f} sec")

MAIN_DB_FILE = "scraper_data.sqlite"

def _scrape_new_data_into_main_db(manufacturer_id: str):
    """
    1) Uses your PartScraper with 'MAIN_DB_FILE'.
    2) For the given appliance_id, it inserts new row(s) into the 'parts' table.
    """
    logger.info(f"Scraping new data for appliance_id={manufacturer_id} into {MAIN_DB_FILE}.")
    
    # 1) Set up DatabaseHandler for your main DB
    main_db = DatabaseHandler(db_path=MAIN_DB_FILE, thread_protected=True)
    main_db.conn.row_factory = sqlite3.Row

    # 2) Scrape
    ps = PartScraper(manufacturer_id=manufacturer_id, db=main_db)
    ps.scrape_all()
    ps.close()

    logger.info("Scraping done. Rows inserted into the main DB.")
    return manufacturer_id, ps

#@tool(description=(
    "Find a specified part for a given appliance id. Performs semantic search across fields (name, description, fixes) for parts scraped from a specific appliance model. "
    "Args: appliance_id(str), name(str, optional), description(str, optional), "
    "symptoms(str, optional), price(str, optional), rating(str, optional), k(str, int, optional). "
#    "Returns top hits or 'NO SEARCH'.")

def search_parts_by_appliance_id(
    appliance_id: str,
    name: str = "",
    description: str = "",
    symptoms: str = "",
    k: str = "5"
) -> str:
    """
    1) Use ModelScraper to get part_select_ids from the provided model id.
    2) For each field (name, description, fixes), do similarity_search with a filter
       limiting results to those part_select_ids.
    3) Union results, deduplicate, and return top k.
    """
    start_time = time.time()
    logger.info(
        f"search_parts_by_appliance_id called with appliance_id='{appliance_id}', "
        f"name='{name}', description='{description}', symptoms='{symptoms}', k='{k}'"
    )

    # 0) If no textual queries are provided, there's nothing to search
    if not (name.strip() or description.strip() or symptoms.strip()):
        logger.debug("No search terms provided (name/description/symptoms all empty).")
        return "NO SEARCH"

    # 1) Scrape part_select_ids from the model's page
    logger.info(f"Invoking MODEL_SCRAPER for appliance_id='{appliance_id}'.")
    model_scraper = MODEL_SCRAPER()
    model_scraper.new(model_id=appliance_id)
    scraped_ids  =  model_scraper._scrape_part_ids()
    from tqdm import tqdm
    with ProcessPoolExecutor(max_workers=os.cpu_count() - 2) as executor:
        futures = {executor.submit(_scrape_new_data_into_main_db, part_id): part_id for part_id in scraped_ids}
        with tqdm(total=len(scraped_ids), desc="Processing gather_items") as pbar:
            for fut in as_completed(futures):
                result = fut.result()
                logger.info(f"Scraped part_id: {result}")
                pbar.update(1)
    
    logger.info(f"Scraped part_ids: {scraped_ids}")

    if not scraped_ids:
        logger.info(f"No parts found for {appliance_id}.")
        return "No parts found for that model/appliance."

    # Convert to numeric if provided
    top_k = int(k) if k else 5
    # 3) Build ephemeral index from those part IDs
    """    ephemeral_index = _build_all_parts_index(MAIN_DB_FILE, scraped_ids)
        if ephemeral_index is None:
            logger.info("Ephemeral index is empty => no docs => returning 'NO SEARCH'.")
            return "NO SEARCH"
    """
    # 4) For each text input, do a similarity search with filter= { field AND p_id in ... }
    top_k = int(k) if k else 5
    combined_results = []

    def make_filter(field_val: str):
        return {
            "$and": [
                {"field": field_val},
                {"part_select_id": {"$in": scraped_ids}}
            ]
        }

    # name
    if name.strip():
        logger.info(f"Similarity searching 'name' with text='{name}' ...")
        f = make_filter("name")
        name_results = all_parts_index.similarity_search(
            name.strip(),
            k=len(scraped_ids),  # or top_k, or something else
            filter=f
        )
        logger.debug(f"name => {len(name_results)} result(s).")
        combined_results.extend(name_results)

    # description
    if description.strip():
        logger.info(f"Similarity searching 'description' with text='{description}' ...")
        f = make_filter("description")
        desc_results = all_parts_index.similarity_search(
            description.strip(),
            k=len(scraped_ids),
            filter=f
        )
        logger.debug(f"description => {len(desc_results)} result(s).")
        combined_results.extend(desc_results)

    # fixes
    if symptoms.strip():
        logger.info(f"Similarity searching 'fixes' with text='{symptoms}' ...")
        f = make_filter("fixes")
        fix_results = all_parts_index.similarity_search(
            symptoms.strip(),
            k=len(scraped_ids),
            filter=f
        )
        logger.debug(f"fixes => {len(fix_results)} result(s).")
        combined_results.extend(fix_results)

    if not combined_results:
        logger.info("No doc(s) returned from ephemeral search => 'NO SEARCH'.")
        return "NO SEARCH"

    # 5) Deduplicate
    unique_docs = {}
    for d in combined_results:
        mid = d.metadata.get("manufacturer_id", "")
        if mid not in unique_docs:
            unique_docs[mid] = d

    final_list = list(unique_docs.values())
    if not final_list:
        return "NO RESULTS"

    final_docs = final_list[:top_k]
    lines = []
    for doc in final_docs:
        snippet = doc.page_content[:80].replace("\n", " ")
        mid = doc.metadata.get("manufacturer_id", "")
        field_label = doc.metadata.get("field", "")
        psid = doc.metadata.get("part_select_id", "")
        lines.append(f"[{field_label}] PartSelectID={psid}, ManufacturerID={mid} => {snippet}...")

    elapsed = time.time() - start_time
    logger.info(f"search_parts_by_appliance_id finished in {elapsed:.2f}s")

    return "\n".join(lines)