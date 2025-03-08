### To run frontend development server:
<pre><code>npm start</code></pre>

### To run backend:
<pre><code>uvicorn agents:app --reload</code></pre>

### To run individual files:
<pre><code>python -m [agents or scraping].[file].py </code></pre>

#### My goal was to maximize relevant context retrieval for DeepSeekChat while minimizing response time.
#### The asynchronous agent implementation seemed the best approach, but, after some debugging, I found FastApi's streaming endpoint is too slow and unreliable. I could be wrong though.

#### I was hoping to build out and refine it a bit more, as I think the setup and approach is very scalable and structured.

<pre><code>
├── agents/                                  (Holds agent-related code & config)
│   ├── __init__.py                          (Initializes the backend agents API with FastAPI)
│   ├── .env                                 (Environment variables/config; gitignored)
│   ├── main_agent.py                        (Primary agent code handling chat logic & tool usage)
│   ├── my_tools.py                          (Collection of “tool” functions used by the agent)
│   └── validation_agent.py                  (Utility/agent for verifying response accuracy - might need to be updated)
│
├── chroma_db/                               (Local storage for Chroma-based vector indexes, converted from SQL data)
│
├── frontend/                                (React front-end application, mostly the same)
│   ├── node_modules/                        
│   ├── public/                              
│   ├── src/
│   │   ├── api/                             (Front-end API call)
│   │   ├── components/                      (ChatWindow.js and ChatWindow.css)
│   │   ├── App.css                          (Global CSS)
│   │   ├── App.js                           (Main React component)
│   │   └── index.js                         (App entry point rendering to the DOM)
│   ├── package-lock.json
│   └── package.json
│
├── scraping/                               (Core scraping logic and RAG DB utilities)
│   ├── scrape_all/
│   │   └── scrapy/                          (Scrapy project, slower than Selenium approach)
│   │       └── ...                         (Additional spider files, feeds)
│   ├── PartSelect.com_Sitemap_CategoryPage… (Category sitemap)
│   ├── scrape_cats.py                      (Script to scrape category or item pages)
│   ├── __init__.py                         (Makes 'scraping' a Python package)
│   ├── AbstractScraper.py                  (Base Selenium scraping class)
│   ├── database_utils.py                   (Generates SQL from dataclasses)
│   ├── database.py                         (DatabaseHandler for creating/upserting data in SQLite)
│   ├── itemclasses.py                      (Dataclasses for Part, Model, Review, etc.)
│   ├── ModelScraper.py                     (Scraper for model pages on PartSelect)
│   ├── PartScraper.py                      (Scraper for individual part pages & data)
│   └── SymptomScraper.py                   (Scraper for “symptom” pages suggesting parts)
│
├── README.md                               (Project documentation)
├── requirements.txt                        (Python dependencies)
└── scraper_data.sqlite                     (SQLite DB containing scraped data, used for Chroma db)
</code></pre>
