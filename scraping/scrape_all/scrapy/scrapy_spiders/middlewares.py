import random
import ua_generator
from scrapy import signals
from scrapy.downloadermiddlewares.retry import get_retry_request
from .items import FailedURLItem
PROXY_URL = "http://kZmKX6jcpYGR:MTDvU0uxCYZj@superproxy.zenrows.com:1337"

class RotateUserAgentAndProxyMiddleware:
    """ Middleware to dynamically rotate User-Agents and use ZenRows proxies. """

    def __init__(self):
        self.user_agents = self.generate_user_agents(30)  # Start with 30 user agents

    def generate_user_agents(self, count=30):
        """ Generate a list of user agents with correct Sec-CH-UA headers. """
        return [
            {
                "User-Agent": ua_generator.generate(device="desktop").text,
                "sec-ch-ua": ua_generator.generate(device="desktop").ch.brands,
                "sec-ch-ua-platform": ua_generator.generate(device="desktop").ch.platform.replace("\"", "")
            }
            for _ in range(count)
        ]


    def process_request(self, request, spider):
        """ Assigns a random User-Agent and ZenRows proxy to each request. """
        if len(self.user_agents) < 10:
            self.user_agents = self.user_agents.extend(self.generate_user_agents(10))  # Refill when empty
        """        if "proxy" not in request.meta:
            request.meta["proxy"] = PROXY_URL"""
        # Assign a random User-Agent
        user_agent = random.choice(self.user_agents)
        request.headers["User-Agent"] = user_agent["User-Agent"]
        request.headers["sec-ch-ua"] = user_agent["sec-ch-ua"]
        request.headers["sec-ch-ua-platform"] = user_agent["sec-ch-ua-platform"]

        # Set standard headers if missing
        request.headers["Accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        request.headers["Accept-Language"] = "en-US,en;q=0.9"
        request.headers["Accept-Encoding"] = "gzip, deflate, br"
        request.headers["Connection"] = "keep-alive"
        request.headers["Upgrade-Insecure-Requests"] = "1"
        request.headers["Referer"] = "https://www.partselect.com"

    def process_response(self, request, response, spider):
        """ Retry request if blocked (403, 429). """
        if response.status in [403, 429]:  # Blocked or rate-limited
            blocked_user_agent = request.headers.get("User-Agent").decode('utf-8')
            self.user_agents = [agent for agent in self.user_agents if agent["User-Agent"] != blocked_user_agent]  # Remove blocked 
            new_request = get_retry_request(request, reason=f"Blocked: {response.status}", spider=spider)
            if new_request:
                return new_request
        return response  # Continue processing normally

    
    @classmethod
    def from_crawler(cls, crawler):
        """ Connects middleware to Scrapy signals. """
        middleware = cls()
        crawler.signals.connect(middleware.spider_opened, signal=signals.spider_opened)
        return middleware

    def spider_opened(self, spider):
        spider.logger.info("User-Agent & ZenRows Proxy Middleware initialized.")
