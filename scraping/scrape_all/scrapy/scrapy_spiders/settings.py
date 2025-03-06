# Scrapy settings for scrapy_project project
#
# For simplicity, this file contains only settings considered important or
# commonly used. You can find more settings consulting the documentation:
#
#     https://docs.scrapy.org/en/latest/topics/settings.html
#     https://docs.scrapy.org/en/latest/topics/downloader-middleware.html
#     https://docs.scrapy.org/en/latest/topics/spider-middleware.html

BOT_NAME = "scrapy_spiders"
ITEM_PIPELINES = {
    'scrapy_spiders.pipelines.SQLStorePipeline': 300,
}

SPIDER_MODULES = ["scrapy_spiders.spiders"]
NEWSPIDER_MODULE = "scrapy_spiders.spiders"
# scrapy_project/settings.py

# Disable cookies (enabled by default)
COOKIES_ENABLED = False

# Set to False if you don’t want to obey robots.txt (be sure to check legal/ethical implications)
ROBOTSTXT_OBEY = False


# Increase concurrent requests if needed
CONCURRENT_REQUESTS = 16

# Default request headers – note the added Accept header and corrected client hints.
DEFAULT_REQUEST_HEADERS = {
    'User-Agent': "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/133.0.0.0 Safari/537.36",
    'Accept': "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Cache-Control': 'no-cache',
    'Pragma': 'no-cache',
    "sec-ch-ua": '"Not.A/Brand";v="99", "Google Chrome";v="133", "Chromium";v="133"',
    "sec-ch-ua-platform": "macOS",
    "upgrade-insecure-requests": "1"
}

# Enable the custom downloader middleware for rotating proxies and user agents.
DOWNLOADER_MIDDLEWARES = {
    "scrapy_spiders.middlewares.RotateUserAgentAndProxyMiddleware": 350,
    "scrapy.downloadermiddlewares.useragent.UserAgentMiddleware": None,  # Disable default
}


# If you use AutoThrottle, adjust as needed.
AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 1
AUTOTHROTTLE_MAX_DELAY = 10

# Use asyncio-based reactor for better async performance.
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"



# Crawl responsibly by identifying yourself (and your website) on the user-agent
#USER_AGENT = "scrapy_project (+http://www.yourdomain.com)"

# Obey robots.txt rules
#ROBOTSTXT_OBEY = True

# Configure maximum concurrent requests performed by Scrapy (default: 16)

# Configure a delay for requests for the same website (default: 0)
# See https://docs.scrapy.org/en/latest/topics/settings.html#download-delay
# See also autothrottle settings and docs
#DOWNLOAD_DELAY = 3
# The download delay setting will honor only one of:
#CONCURRENT_REQUESTS_PER_DOMAIN = 16
#CONCURRENT_REQUESTS_PER_IP = 16

# Disable Telnet Console (enabled by default)
TELNETCONSOLE_ENABLED = False


# Enable or disable spider middlewares
# See https://docs.scrapy.org/en/latest/topics/spider-middleware.html
#SPIDER_MIDDLEWARES = {
#    "scrapy_project.middlewares.ScrapyProjectSpiderMiddleware": 543,
#}

# Enable or disable downloader middlewares
# See https://docs.scrapy.org/en/latest/topics/downloader-middleware.html
#DOWNLOADER_MIDDLEWARES = {
#    "scrapy_project.middlewares.ScrapyProjectDownloaderMiddleware": 543,
#}

# Enable or disable extensions
# See https://docs.scrapy.org/en/latest/topics/extensions.html
#EXTENSIONS = {
#    "scrapy.extensions.telnet.TelnetConsole": None,
#}

# Configure item pipelines
# See https://docs.scrapy.org/en/latest/topics/item-pipeline.html
#ITEM_PIPELINES = {
#    "scrapy_project.pipelines.ScrapyProjectPipeline": 300,
#}

# Enable and configure the AutoThrottle extension (disabled by default)
# See https://docs.scrapy.org/en/latest/topics/autothrottle.html
#AUTOTHROTTLE_ENABLED = True
# The initial download delay
#AUTOTHROTTLE_START_DELAY = 5
# The maximum download delay to be set in case of high latencies
#AUTOTHROTTLE_MAX_DELAY = 60
# The average number of requests Scrapy should be sending in parallel to
# each remote server
#AUTOTHROTTLE_TARGET_CONCURRENCY = 1.0
# Enable showing throttling stats for every response received:
#AUTOTHROTTLE_DEBUG = False

#LOG_LEVEL = 'CRITICAL'

# Enable and configure HTTP caching (disabled by default)
# See https://docs.scrapy.org/en/latest/topics/downloader-middleware.html#httpcache-middleware-settings
HTTPCACHE_ENABLED = False
HTTPCACHE_EXPIRATION_SECS = 0
HTTPCACHE_DIR = "httpcache"
HTTPCACHE_IGNORE_HTTP_CODES = []
HTTPCACHE_STORAGE = "scrapy.extensions.httpcache.FilesystemCacheStorage"


