#!/usr/bin/env python
"""
COMPLETE REPLACEMENT for direct_scraper.py with fallbacks disabled
"""
import asyncio
import httpx
from bs4 import BeautifulSoup
import json
import os
import logging
import random
import datetime
import re
import time
import sys
from pathlib import Path
from urllib.parse import urlparse, urljoin

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Constants for scraping
MAX_URLS_PER_QUERY = 5
MAX_TOTAL_URLS = 20
SCRAPE_TIMEOUT = 20.0
REQUEST_DELAY_MIN = 1.0
REQUEST_DELAY_MAX = 3.0
MAX_CONTENT_LENGTH = 20000
MAX_RETRIES = 3

# IMPORTANT: Fallbacks are DISABLED by default
USE_FALLBACK_URLS = False
ADD_FALLBACK_RESULTS = False

# If configuration file is provided, load it directly
def load_config(config_path):
    """Load configuration from a JSON file."""
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config_data = json.load(f)
            logger.info(f"Loaded configuration from {config_path}")
            
            # Extract search settings
            global USE_FALLBACK_URLS, ADD_FALLBACK_RESULTS
            if 'search' in config_data:
                search_config = config_data.get('search', {})
                USE_FALLBACK_URLS = search_config.get('use_fallback_urls', False)
                ADD_FALLBACK_RESULTS = search_config.get('add_fallback_results', False)
                logger.info(f"Config fallback settings: USE_FALLBACK_URLS={USE_FALLBACK_URLS}, ADD_FALLBACK_RESULTS={ADD_FALLBACK_RESULTS}")
            
            # Extract other scraper settings
            global MAX_URLS_PER_QUERY, MAX_TOTAL_URLS, SCRAPE_TIMEOUT, REQUEST_DELAY_MIN, REQUEST_DELAY_MAX, MAX_CONTENT_LENGTH, MAX_RETRIES
            if 'scraper' in config_data:
                scraper_config = config_data.get('scraper', {})
                MAX_URLS_PER_QUERY = scraper_config.get('max_urls_per_query', MAX_URLS_PER_QUERY)
                MAX_TOTAL_URLS = scraper_config.get('max_total_urls', MAX_TOTAL_URLS)
                SCRAPE_TIMEOUT = scraper_config.get('scrape_timeout', SCRAPE_TIMEOUT)
                REQUEST_DELAY_MIN = scraper_config.get('request_delay_min', REQUEST_DELAY_MIN)
                REQUEST_DELAY_MAX = scraper_config.get('request_delay_max', REQUEST_DELAY_MAX)
                MAX_CONTENT_LENGTH = scraper_config.get('max_content_length', MAX_CONTENT_LENGTH)
                MAX_RETRIES = scraper_config.get('max_retries', MAX_RETRIES)
                
            return config_data
    except Exception as e:
        logger.error(f"Error loading configuration from {config_path}: {e}")
        return None

# Robust list of user agents to avoid detection
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/117.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
]

# Common content selectors across different websites
CONTENT_SELECTORS = [
    'article', 'main', '#main', '#content', '.content', 
    '.post-content', '.entry-content', '.main-content', 
    '#main-content', '.article-content', '.story-content',
]

# Elements to remove (noisy content)
NOISE_SELECTORS = [
    'header', 'footer', 'nav', '.nav', '#nav', '.navigation', '#navigation',
    '.menu', '#menu', '.sidebar', '#sidebar', 'aside', '.aside', 
]

# List of common search engines for basic queries
SEARCH_ENGINES = [
    {
        "name": "DuckDuckGo Lite",
        "url": "https://lite.duckduckgo.com/lite/",
        "method": "POST",
        "params": {"q": "QUERY_PLACEHOLDER"},
        "result_selector": "a.result-link",
        "parser": "duck_duck_go_parser"
    },
    {
        "name": "Ecosia",
        "url": "https://www.ecosia.org/search",
        "method": "GET",
        "params": {"q": "QUERY_PLACEHOLDER"},
        "result_selector": ".result a.js-result-url",
        "parser": "ecosia_parser"
    },
    {
        "name": "Mojeek",
        "url": "https://www.mojeek.com/search",
        "method": "GET",
        "params": {"q": "QUERY_PLACEHOLDER"},
        "result_selector": ".results-standard .title a",
        "parser": "mojeek_parser"
    }
]

# Default fallback search queries for climate change adaptation
DEFAULT_SEARCH_QUERIES = [
    "climate change adaptation strategies",
    "climate resilience urban planning",
    "water management climate change",
    "agricultural adaptation climate change",
]

# Fallback directory of manually curated URLs DISABLED
FALLBACK_URLS = []  # COMPLETELY EMPTY - NO FALLBACKS

def get_random_delay():
    """Get a random delay between min and max delay time."""
    return random.uniform(REQUEST_DELAY_MIN, REQUEST_DELAY_MAX)

def is_valid_url(url):
    """Check if a URL is valid."""
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except Exception:
        return False

def extract_urls_from_search_response(response_text, engine):
    """Extract URLs from a search engine response."""
    urls = []
    try:
        soup = BeautifulSoup(response_text, 'lxml')
        
        # Get the parser function
        parser_name = engine.get("parser", "default_parser")
        if parser_name == "duck_duck_go_parser":
            urls = duck_duck_go_parser(soup)
        elif parser_name == "ecosia_parser":
            urls = ecosia_parser(soup)
        elif parser_name == "mojeek_parser":
            urls = mojeek_parser(soup)
        else:
            # Default parser uses the provided selector
            result_selector = engine.get("result_selector")
            if result_selector:
                for link in soup.select(result_selector):
                    href = link.get('href')
                    if href and is_valid_url(href):
                        urls.append(href)
    except Exception as e:
        logger.error(f"Error extracting URLs from {engine['name']} response: {e}")
    
    return urls

def duck_duck_go_parser(soup):
    """Parse URLs from DuckDuckGo Lite search results."""
    urls = []
    try:
        for link in soup.select('a.result-link'):
            href = link.get('href')
            if href and '/lite/?' not in href and is_valid_url(href):
                urls.append(href)
    except Exception as e:
        logger.error(f"Error in DuckDuckGo parser: {e}")
    return urls

def ecosia_parser(soup):
    """Parse URLs from Ecosia search results."""
    urls = []
    try:
        for link in soup.select('.result a.js-result-url, .result-url'):
            href = link.get('href')
            if href and is_valid_url(href):
                if href.startswith('/url?'):
                    # Extract the actual URL from Ecosia's redirect format
                    url_match = re.search(r'url=([^&]+)', href)
                    if url_match:
                        href = url_match.group(1)
                urls.append(href)
    except Exception as e:
        logger.error(f"Error in Ecosia parser: {e}")
    return urls

def mojeek_parser(soup):
    """Parse URLs from Mojeek search results."""
    urls = []
    try:
        for link in soup.select('.results-standard .title a'):
            href = link.get('href')
            if href and href.startswith('http') and is_valid_url(href):
                urls.append(href)
    except Exception as e:
        logger.error(f"Error in Mojeek parser: {e}")
    return urls

def clean_content(content):
    """Clean up the extracted content."""
    # Remove extra whitespace
    content = re.sub(r'\s+', ' ', content).strip()
    # Remove common email patterns
    content = re.sub(r'\S+@\S+\.\S+', '[EMAIL]', content)
    # Remove phone numbers
    content = re.sub(r'\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}', '[PHONE]', content)
    # Limit consecutive non-alphanumeric characters
    content = re.sub(r'[^\w\s]{3,}', '...', content)
    return content

def uuid4():
    """Generate a uuid4."""
    import uuid
    return uuid.uuid4()

async def search_and_get_urls(query, client):
    """Search for a query and get relevant URLs."""
    urls = []
    
    # Try each search engine until we get some URLs
    for engine in SEARCH_ENGINES:
        if len(urls) >= MAX_URLS_PER_QUERY:
            break
            
        engine_name = engine["name"]
        search_url = engine["url"]
        method = engine["method"]
        params = {k: (v.replace("QUERY_PLACEHOLDER", query) if isinstance(v, str) else v) 
                 for k, v in engine.get("params", {}).items()}
        
        logger.info(f"Searching with {engine_name} for: {query}")
        
        try:
            # Random delay to avoid detection
            await asyncio.sleep(get_random_delay())
            
            # Update User-Agent for each request
            client.headers['User-Agent'] = random.choice(USER_AGENTS)
            
            # Make the request based on the method
            if method.upper() == "POST":
                response = await client.post(search_url, data=params, follow_redirects=True)
            else:
                response = await client.get(search_url, params=params, follow_redirects=True)
                
            response.raise_for_status()
            
            # Extract URLs from the search results
            search_urls = extract_urls_from_search_response(response.text, engine)
            
            # Add new unique URLs
            for url in search_urls:
                if url not in urls and is_valid_url(url):
                    urls.append(url)
                    if len(urls) >= MAX_URLS_PER_QUERY:
                        break
                        
            if urls:
                logger.info(f"Found {len(urls)} URLs from {engine_name} for query: {query}")
                break
        
        except httpx.TimeoutException:
            logger.warning(f"Timeout searching with {engine_name} for query: {query}")
        except httpx.RequestError as e:
            logger.warning(f"Request error with {engine_name} for query: {query}: {e}")
        except Exception as e:
            logger.error(f"Error searching with {engine_name} for query: {query}: {e}")
    
    return urls[:MAX_URLS_PER_QUERY]  # Limit to max URLs per query

async def extract_text_from_html(html, url, query=None):
    """Extract relevant text content from HTML."""
    try:
        soup = BeautifulSoup(html, 'lxml')
        
        # Get page title
        title = soup.title.string.strip() if soup.title else "No Title Found"
        
        # Remove noisy content first
        for selector in NOISE_SELECTORS:
            for element in soup.select(selector):
                element.decompose()
        
        # Try to find the main content area
        content_area = None
        
        # First try common content selectors
        for selector in CONTENT_SELECTORS:
            content_area = soup.select_one(selector)
            if content_area and len(content_area.get_text(strip=True)) > 200:
                break
        
        # If no content area found, fallback to body
        if not content_area or len(content_area.get_text(strip=True)) < 200:
            content_area = soup.body
        
        if content_area:
            # Get all paragraphs and headings
            headings = [h.get_text(strip=True) for h in content_area.find_all(['h1', 'h2', 'h3', 'h4', 'h5'])]
            paragraphs = [p.get_text(strip=True) for p in content_area.find_all('p')]
            
            # Clean and filter content
            headings = [clean_content(h) for h in headings if len(h) > 15]
            paragraphs = [clean_content(p) for p in paragraphs if len(p) > 50]
            
            # Combine content with structure
            structured_content = []
            
            # Add title as a heading
            if title and title not in headings:
                structured_content.append(f"# {title}")
                
            # Add headings and paragraphs
            for heading in headings:
                structured_content.append(f"## {heading}")
                for p in paragraphs[:]:
                    if len(p) > 50:
                        structured_content.append(p)
                        try:
                            paragraphs.remove(p)
                        except ValueError:
                            pass
            
            # Add any remaining paragraphs
            for p in paragraphs:
                if p not in structured_content and len(p) > 50:
                    structured_content.append(p)
            
            main_content = "\n\n".join(structured_content)
            
            # Truncate if too long
            if len(main_content) > MAX_CONTENT_LENGTH:
                main_content = main_content[:MAX_CONTENT_LENGTH] + "... [truncated]"
            
            if main_content and len(main_content) > 200:
                logger.info(f"Successfully extracted {len(main_content)} chars from {url}")
                
                # Get subtopic from query info
                subtopic = query.get("subtopic", "Topic Research") if query else "Topic Research"
                
                # Create the content item with query information
                content_item = {
                    "url": url,
                    "title": title,
                    "content": main_content,
                    "timestamp": datetime.datetime.now().isoformat()
                }
                
                # Add query info for downstream compatibility
                if query:
                    content_item["query_source"] = {
                        "subtopic": subtopic,
                        "query": query.get("query", ""),
                        "source": "web_scrape"
                    }
                else:
                    content_item["query_source"] = {
                        "subtopic": subtopic, 
                        "source": "web_scrape"
                    }
                
                return content_item
        
        logger.warning(f"Could not extract meaningful content from {url}")
    except Exception as e:
        logger.error(f"Error extracting text from {url}: {e}")
    
    return None

async def scrape_url(url, client, retry_count=0, query_info=None):
    """Scrape a URL with retry logic."""
    if retry_count > MAX_RETRIES:
        logger.warning(f"Max retries reached for {url}")
        return None
    
    logger.info(f"Scraping URL: {url} (attempt {retry_count + 1})")
    
    try:
        # Random delay between requests
        await asyncio.sleep(get_random_delay())
        
        # Update User-Agent for each request
        client.headers['User-Agent'] = random.choice(USER_AGENTS)
        
        # Try to get the content
        response = await client.get(url, follow_redirects=True)
        response.raise_for_status()
        
        # Check if the content is HTML
        content_type = response.headers.get('content-type', '').lower()
        if 'html' not in content_type:
            logger.warning(f"Skipping non-HTML content at {url} (type: {content_type})")
            return None
        
        # Extract and structure the content
        return await extract_text_from_html(response.text, url, query_info)
    
    except httpx.TimeoutException:
        logger.warning(f"Timeout scraping {url}, retrying...")
        return await scrape_url(url, client, retry_count + 1, query_info)
    except httpx.TooManyRedirects:
        logger.warning(f"Too many redirects for {url}")
        return None
    except httpx.RequestError as e:
        if retry_count < MAX_RETRIES:
            logger.warning(f"Request error scraping {url}: {e}, retrying...")
            # Exponential backoff
            await asyncio.sleep(2 ** retry_count * 1.5)
            return await scrape_url(url, client, retry_count + 1, query_info)
        else:
            logger.warning(f"Request error scraping {url} after {retry_count} retries: {e}")
            return None
    except Exception as e:
        logger.error(f"Error scraping {url}: {e}")
        if retry_count < MAX_RETRIES:
            await asyncio.sleep(2 ** retry_count)
            return await scrape_url(url, client, retry_count + 1, query_info)
        return None

async def load_search_queries(project_id, base_dir):
    """Load search queries from the project state."""
    try:
        topic_research_dir = base_dir / project_id / "topic_research"
        if topic_research_dir.exists():
            potential_files = list(topic_research_dir.glob("*.json"))
            for file_path in potential_files:
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        if isinstance(data, dict) and "search_queries" in data:
                            queries = data["search_queries"]
                            if isinstance(queries, list) and queries:
                                logger.info(f"Loaded {len(queries)} search queries from {file_path}")
                                return queries
                except Exception as e:
                    logger.warning(f"Could not process file {file_path}: {e}")
    except Exception as e:
        logger.error(f"Error loading search queries: {e}")
    
    # If fallbacks are disabled, return empty list instead of default queries
    if not USE_FALLBACK_URLS:
        logger.warning("Could not load search queries and fallbacks are disabled. Will return empty query list.")
        return []
    
    # Fallback to default queries only if allowed
    logger.warning("Using default search queries")
    return [{"subtopic": "Topic Research", "query": q} for q in DEFAULT_SEARCH_QUERIES]

async def main(project_id):
    """Main function to coordinate the scraping process."""
    try:
        # Determine base directory
        base_dir = Path("D:/AgentVault/poc_agents/langgraph_scrapepipe/pipeline_artifacts")
        
        # Report fallback settings
        logger.info(f"Starting scraping with fallback settings: USE_FALLBACK_URLS={USE_FALLBACK_URLS}, ADD_FALLBACK_RESULTS={ADD_FALLBACK_RESULTS}")
        
        # Create the storage directory structure
        storage_dir = base_dir / project_id / "content_crawler"
        storage_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize HTTP client with timeout and headers
        headers = {
            'User-Agent': random.choice(USER_AGENTS),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        
        async with httpx.AsyncClient(timeout=SCRAPE_TIMEOUT, follow_redirects=True, headers=headers) as client:
            # Load search queries for this project
            search_queries = await load_search_queries(project_id, base_dir)
            
            all_urls = []
            all_queries = []  # Store query info for each URL
            scraped_content = []
            
            # Part 1: Gather URLs from search queries
            if search_queries:
                logger.info(f"Processing {len(search_queries)} search queries")
                
                for query_info in search_queries:
                    if len(all_urls) >= MAX_TOTAL_URLS:
                        break
                    
                    # Extract the query string and subtopic from the query info
                    subtopic = None
                    query = None
                    
                    if isinstance(query_info, dict):
                        # Get subtopic if available
                        subtopic = query_info.get("subtopic", "")
                        
                        # Get query from different possible fields
                        query = query_info.get("query", "")
                        if not query and "queries" in query_info:
                            queries = query_info.get("queries", [])
                            query = queries[0] if queries else ""
                    else:
                        query = str(query_info)
                        subtopic = "Topic Research"
                    
                    if not query:
                        continue
                    
                    # Search and get URLs for this query
                    urls = await search_and_get_urls(query, client)
                    
                    # Add new URLs to our list with query info
                    for url in urls:
                        if url not in all_urls:
                            all_urls.append(url)
                            all_queries.append({"url": url, "subtopic": subtopic, "query": query})
                            if len(all_urls) >= MAX_TOTAL_URLS:
                                break
            
            # If we didn't get enough URLs from search, use fallback URLs if enabled
            if len(all_urls) < 5 and USE_FALLBACK_URLS:
                logger.info("Not enough URLs from search queries, adding fallback URLs (USE_FALLBACK_URLS=True)")
                for url in FALLBACK_URLS:
                    if url not in all_urls:
                        all_urls.append(url)
                        all_queries.append({"url": url, "subtopic": "Topic Research", "query": "fallback"})
                        if len(all_urls) >= MAX_TOTAL_URLS:
                            break
            elif len(all_urls) < 5:
                logger.warning("Not enough URLs from search queries and USE_FALLBACK_URLS=False. Proceeding with limited URLs.")
            
            # Part 2: Scrape content from the URLs
            logger.info(f"Scraping content from {len(all_urls)} URLs")
            
            # Use semaphore to limit concurrent requests
            semaphore = asyncio.Semaphore(3)  # Limit to 3 concurrent requests
            
            # Create a mapping of URL to query info
            query_map = {item["url"]: {"subtopic": item["subtopic"], "query": item["query"]} for item in all_queries}
            
            async def scrape_with_semaphore(url):
                async with semaphore:
                    # Pass the query info for this URL
                    query_info = query_map.get(url, {"subtopic": "Topic Research", "query": "unknown"})
                    return await scrape_url(url, client, query_info=query_info)
            
            # Create scraping tasks for all URLs
            scrape_tasks = [scrape_with_semaphore(url) for url in all_urls]
            
            # Wait for all tasks to complete
            results = await asyncio.gather(*scrape_tasks, return_exceptions=True)
            
            # Process results
            for result in results:
                if isinstance(result, Exception):
                    logger.error(f"Error in scrape task: {result}")
                elif result:
                    scraped_content.append(result)
            
            # If no content was scraped and fallbacks are disabled, simply return empty content
            if not scraped_content:
                if ADD_FALLBACK_RESULTS:
                    logger.warning("No content scraped but ADD_FALLBACK_RESULTS=True. Adding minimal fallback.")
                    scraped_content = [{
                        "url": "no-results",
                        "title": "No Results Found",
                        "content": "# No content was found\n\nThe scraper was unable to retrieve content from any of the URLs.",
                        "query_source": {"subtopic": "Topic Research", "query": "no-results", "source": "fallback"},
                        "timestamp": datetime.datetime.now().isoformat()
                    }]
                else:
                    logger.error("No content was scraped and ADD_FALLBACK_RESULTS=False. Returning empty content.")
                    # Return empty content to explicitly show no results were found
                    scraped_content = []
            
            # Save the content as a JSON file
            file_path = storage_dir / "raw_content.json"
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(scraped_content, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Saved {len(scraped_content)} scraped items to {file_path}")
            return file_path, scraped_content
    except Exception as e:
        logger.error(f"Unexpected error in main function: {e}", exc_info=True)
        # No fallback content - just return None to force proper failure
        logger.critical("CRITICAL ERROR: Failing without fallback content")
        return None, None

if __name__ == "__main__":
    try:
        # Configure logging
        if not logging.getLogger().handlers:
            logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
        
        # Get project ID from command line argument
        if len(sys.argv) > 1:
            project_id = sys.argv[1]
        else:
            project_id = f"proj_direct_{random.randint(10000, 99999)}"
        
        # Load config from command line if provided
        if len(sys.argv) > 2:
            config_path = sys.argv[2]
            if os.path.exists(config_path):
                logger.info(f"Loading configuration from: {config_path}")
                config = load_config(config_path)
        
        # Run the main function
        logger.info(f"Starting direct scraper for project: {project_id}")
        result = asyncio.run(main(project_id))
        
        # Print the output path
        if result and result[0]:
            print(f"DIRECT_SCRAPE_RESULT:{result[0]}")
            
            # Print a sample of the content
            if result[1] and len(result[1]) > 0:
                print("\nSample content from first scraped page:")
                print(f"Title: {result[1][0]['title']}")
                content = result[1][0]['content']
                print(f"Content (first 500 chars): {content[:500]}...")
            else:
                print("\nNo content was scraped.")
        else:
            logger.critical("No result returned from main function.")
            sys.exit(1)
    except Exception as e:
        logger.critical(f"Critical error in script execution: {e}", exc_info=True)
        print("DIRECT_SCRAPER_CRITICAL_ERROR: Failing with no fallback")
        sys.exit(1)
