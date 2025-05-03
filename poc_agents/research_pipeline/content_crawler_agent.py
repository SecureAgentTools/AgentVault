import logging
import asyncio
import json
import traceback
from typing import Dict, Any, Union, List, Optional, Tuple
import random
import datetime
import time
import re
import uuid
from pathlib import Path
from urllib.parse import urlparse, urljoin

# Scraping Imports
try:
    import httpx
    from bs4 import BeautifulSoup
    _scraper_available = True
except ImportError:
    logging.getLogger(__name__).warning("httpx or beautifulsoup4 not found. Install with 'pip install httpx beautifulsoup4 lxml'. Web scraping will be disabled.")
    _scraper_available = False

# Import base class and SDK components
from base_agent import ResearchAgent
from agentvault_server_sdk.state import TaskState, TaskContext
from agentvault_server_sdk.exceptions import AgentProcessingError, ConfigurationError

# Import core library models with fallback
try:
    from agentvault.models import Message, TextPart, Artifact
    _MODELS_AVAILABLE = True
except ImportError:
    logging.getLogger(__name__).warning("Core agentvault models not found in content_crawler_agent.py. Using placeholders.")
    class Message: pass # type: ignore
    class TextPart: pass # type: ignore
    class Artifact: pass # type: ignore
    TaskState = ResearchAgent.task_store.TaskState # Use state from base if possible
    _MODELS_AVAILABLE = False

logger = logging.getLogger(__name__)

AGENT_ID = "content-crawler-agent"

# --- Constants (Enhanced Retries) ---
MAX_URLS_PER_QUERY = 5
MAX_TOTAL_URLS = 20
SCRAPE_TIMEOUT = 25.0 # Slightly increased timeout
REQUEST_DELAY_MIN = 2.0 # Increased min delay
REQUEST_DELAY_MAX = 5.0 # Increased max delay
MAX_CONTENT_LENGTH = 25000 # Increased max content length
MAX_RETRIES = 5 # Increased retries
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (X11; Linux i686; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.2420.65",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
]
CONTENT_SELECTORS = [ 'article', 'main', '#main', '#content', '.content', '.post-content', '.entry-content', '.main-content', '#main-content', '.article-content', '.story-content', '.story', '.post', '.article-body', '.article__body', '.article__content', '.post__content', '.blog-post', '.blog-content', '.news-article', '.container' ]
NOISE_SELECTORS = [ 'header', 'footer', 'nav', '.nav', '#nav', '.navigation', '#navigation', '.menu', '#menu', '.sidebar', '#sidebar', 'aside', '.aside', '.ad', '.ads', '.advertisement', '.advertisements', '.banner', '.banners', '.cookie', '.cookies', '.cookie-banner', '.cookie-notice', '.popup', '.modal', '.subscribe', '.subscription', '.newsletter', '.comments', '#comments', '.comment-section', '.related-posts', '.social', '.social-share', '.social-links', '.share-buttons', 'script', 'style', 'noscript', 'iframe', 'svg' ]
SEARCH_ENGINES = [ {"name": "DuckDuckGo Lite", "url": "https://lite.duckduckgo.com/lite/", "method": "POST", "params": {"q": "QUERY_PLACEHOLDER"}, "result_selector": "a.result-link", "parser": "duck_duck_go_parser"}, {"name": "Ecosia", "url": "https://www.ecosia.org/search", "method": "GET", "params": {"q": "QUERY_PLACEHOLDER"}, "result_selector": ".result a.js-result-url", "parser": "ecosia_parser"}, {"name": "Mojeek", "url": "https://www.mojeek.com/search", "method": "GET", "params": {"q": "QUERY_PLACEHOLDER"}, "result_selector": ".results-standard .title a", "parser": "mojeek_parser"} ]
# --- End Constants ---

# --- Helper Functions (Unchanged from previous version) ---
def get_random_delay():
    return random.uniform(REQUEST_DELAY_MIN, REQUEST_DELAY_MAX)

def is_valid_url(url):
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except Exception:
        return False

def clean_content(content):
    content = re.sub(r'\s+', ' ', content).strip()
    content = re.sub(r'\S+@\S+\.\S+', '[EMAIL]', content)
    content = re.sub(r'\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}', '[PHONE]', content)
    content = re.sub(r'[^\w\s]{3,}', '...', content)
    return content

def duck_duck_go_parser(soup):
    urls = []
    try:
        logger.debug(f"DuckDuckGo parsing - found {len(soup.select('a'))} links total")
        selectors = ['a.result-link', '.links a', '.result a', '.web-result a']
        for selector in selectors:
            links = soup.select(selector)
            logger.debug(f"DuckDuckGo selector '{selector}' found {len(links)} links")
            for link in links:
                href = link.get('href')
                if href and '/lite/?' not in href and is_valid_url(href):
                    logger.debug(f"Found valid DuckDuckGo result: {href}")
                    urls.append(href)
        if not urls:
            logger.warning("Trying structural XPath approach for DuckDuckGo")
            tables = soup.find_all('table')
            logger.debug(f"Found {len(tables)} tables in the document")
            for i, table in enumerate(tables):
                links = table.find_all('a')
                logger.debug(f"Table {i+1} contains {len(links)} links")
                for link in links:
                    href = link.get('href')
                    if href and href.startswith(('http://', 'https://')) and '/lite/?' not in href and '?' not in href and is_valid_url(href):
                        logger.debug(f"Found structural result: {href}")
                        urls.append(href)
        if not urls:
            logger.warning("Trying HTML structure analysis for DuckDuckGo")
            for link in soup.find_all('a'):
                href = link.get('href')
                link_text = link.get_text(strip=True)
                if (href and
                    href.startswith(('http://', 'https://')) and
                    '/lite/?' not in href and
                    not href.endswith(('.css', '.js')) and
                    len(link_text) > 10 and
                    is_valid_url(href)):
                    logger.debug(f"Found analysis-based result: {href}")
                    urls.append(href)
    except Exception as e:
        logger.error(f"Error in DuckDuckGo parser: {e}", exc_info=True)
    unique_urls = list(dict.fromkeys(urls)) # Remove duplicates while preserving order
    logger.debug(f"DuckDuckGo parser found {len(unique_urls)} unique URLs")
    return unique_urls

def ecosia_parser(soup):
    urls = []
    try:
        logger.debug(f"Ecosia parsing - found {len(soup.select('a'))} links total")
        selectors = ['.result a.js-result-url', '.result-url', '.result a[href^="http"]', '.result__link', '.organic-result a']
        for selector in selectors:
            links = soup.select(selector)
            logger.debug(f"Ecosia selector '{selector}' found {len(links)} links")
            for link in links:
                href = link.get('href')
                if not href: continue
                if href.startswith('/url?') or 'url=' in href:
                    url_match = re.search(r'url=([^&]+)', href)
                    if url_match: href = url_match.group(1)
                if is_valid_url(href):
                    logger.debug(f"Found valid Ecosia result: {href}")
                    urls.append(href)
        if not urls:
            logger.warning("Using structural analysis for Ecosia results")
            result_divs = soup.find_all('div', class_=lambda c: c and ('result' in c.lower()))
            logger.debug(f"Found {len(result_divs)} potential result containers")
            for div in result_divs:
                for link in div.find_all('a', href=True):
                    href = link.get('href')
                    if href.startswith('/url?') or 'url=' in href:
                        url_match = re.search(r'url=([^&]+)', href)
                        if url_match: href = url_match.group(1)
                    if href and href.startswith(('http://', 'https://')) and is_valid_url(href):
                        logger.debug(f"Found structural Ecosia result: {href}")
                        urls.append(href)
        if not urls:
            logger.warning("Using last resort method for Ecosia results")
            for link in soup.find_all('a', href=True):
                href = link.get('href')
                link_text = link.get_text(strip=True)
                if href.startswith('/url?') or 'url=' in href:
                    url_match = re.search(r'url=([^&]+)', href)
                    if url_match: href = url_match.group(1)
                if (href and
                    href.startswith(('http://', 'https://')) and
                    len(link_text) > 10 and
                    not href.endswith(('.css', '.js', '.png', '.jpg', '.gif')) and
                    not any(x in href.lower() for x in ['ecosia.org/settings', 'account', 'login', 'static']) and
                    is_valid_url(href)):
                    logger.debug(f"Found last resort Ecosia result: {href}")
                    urls.append(href)
    except Exception as e:
        logger.error(f"Error in Ecosia parser: {e}", exc_info=True)
    unique_urls = list(dict.fromkeys(urls))
    logger.debug(f"Ecosia parser found {len(unique_urls)} unique URLs")
    return unique_urls

def mojeek_parser(soup):
    urls = []
    try:
        logger.debug(f"Mojeek parsing - found {len(soup.select('a'))} links total")
        selectors = ['.results-standard .title a', '.title a[href^="http"]', '.results a.title', '.snippet-container a', '.results a[href^="http"]']
        for selector in selectors:
            links = soup.select(selector)
            logger.debug(f"Mojeek selector '{selector}' found {len(links)} links")
            for link in links:
                href = link.get('href')
                if href and href.startswith('http') and is_valid_url(href):
                    logger.debug(f"Found valid Mojeek result: {href}")
                    urls.append(href)
        if not urls:
            logger.warning("Using structural analysis for Mojeek results")
            result_sections = []
            for div in soup.find_all('div'):
                if div.find('a', href=lambda h: h and h.startswith('http')):
                    result_sections.append(div)
            logger.debug(f"Found {len(result_sections)} potential result containers")
            for section in result_sections:
                for link in section.find_all('a', href=lambda h: h and h.startswith('http')):
                    href = link.get('href')
                    if is_valid_url(href):
                        logger.debug(f"Found structural Mojeek result: {href}")
                        urls.append(href)
        if not urls:
            logger.warning("Using last resort method for Mojeek results")
            for link in soup.find_all('a', href=True):
                href = link.get('href')
                text = link.get_text(strip=True)
                if (href and
                    href.startswith('http') and
                    is_valid_url(href) and
                    len(text) > 15 and
                    'mojeek' not in href.lower() and
                    not any(x in href.lower() for x in ['settings', 'account', 'login', 'static'])):
                    logger.debug(f"Found last resort Mojeek result: {href}")
                    urls.append(href)
    except Exception as e:
        logger.error(f"Error in Mojeek parser: {e}", exc_info=True)
    unique_urls = list(dict.fromkeys(urls))
    logger.debug(f"Mojeek parser found {len(unique_urls)} unique URLs")
    return unique_urls

def extract_urls_from_search_response(response_text, engine):
    """Extract URLs from a search engine response using specific parsers."""
    urls = []
    try:
        soup = BeautifulSoup(response_text, 'lxml')
        parser_name = engine.get("parser", "default_parser")
        parser_func = globals().get(parser_name) # Get parser function from global scope
        if parser_func:
            urls = parser_func(soup)
        else: # Fallback if no specific parser defined
            result_selector = engine.get("result_selector")
            if result_selector:
                for link in soup.select(result_selector):
                    href = link.get('href')
                    if href and is_valid_url(href):
                        urls.append(href)
    except Exception as e:
        logger.error(f"Error extracting URLs from {engine['name']} response: {e}")
    return urls

async def search_and_get_urls(query, client):
    """Search for a query and get relevant URLs, continuing if one engine fails."""
    urls = []
    enhanced_headers = { 'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8', 'Accept-Language': 'en-US,en;q=0.9', 'Accept-Encoding': 'gzip, deflate', 'DNT': '1', 'Connection': 'keep-alive', 'Upgrade-Insecure-Requests': '1', 'Sec-Fetch-Dest': 'document', 'Sec-Fetch-Mode': 'navigate', 'Sec-Fetch-Site': 'none', 'Sec-Fetch-User': '?1', 'Cache-Control': 'max-age=0', 'Referer': 'https://www.google.com/' }
    logger.debug(f"--- Starting search for query: '{query}' ---") # Log query start

    for engine in SEARCH_ENGINES:
        if len(urls) >= MAX_URLS_PER_QUERY: break
        engine_name = engine["name"]; search_url = engine["url"]; method = engine["method"]
        params = {k: (v.replace("QUERY_PLACEHOLDER", query) if isinstance(v, str) else v) for k, v in engine.get("params", {}).items()}
        logger.info(f"Searching with {engine_name} for: {query}")

        for attempt in range(MAX_RETRIES): # Use MAX_RETRIES for search attempts
            try:
                delay = get_random_delay(); logger.debug(f"Engine '{engine_name}', Query '{query}', Attempt {attempt+1}: Waiting {delay:.2f}s") # Log delay
                await asyncio.sleep(delay)
                logger.debug(f"Engine '{engine_name}', Query '{query}', Attempt {attempt+1}: Delay finished, attempting request...") # Log after delay
                current_headers = enhanced_headers.copy(); current_headers['User-Agent'] = random.choice(USER_AGENTS)
                client.headers.update(current_headers)
                logger.debug(f"Engine '{engine_name}', Query '{query}', Attempt {attempt+1}: Requesting {method} {search_url}")
                if method.upper() == "POST": response = await client.post(search_url, data=params, follow_redirects=True, timeout=SCRAPE_TIMEOUT)
                else: response = await client.get(search_url, params=params, follow_redirects=True, timeout=SCRAPE_TIMEOUT)
                logger.debug(f"Engine '{engine_name}', Query '{query}', Attempt {attempt+1}: Received status {response.status_code}") # Log status code

                content_sample = response.text[:200].lower()
                if response.status_code == 200 and any(x in content_sample for x in ['captcha', 'blocked', 'automated', 'suspicious', 'verify you are human']):
                    logger.warning(f"Engine '{engine_name}', Query '{query}', Attempt {attempt+1}: Possible blocking detected. Skipping.")
                    continue # Try next attempt/engine

                if 400 <= response.status_code < 500:
                    logger.warning(f"Engine '{engine_name}', Query '{query}', Attempt {attempt+1}: Client error {response.status_code}. Skipping engine.") # Log 4xx skip
                    break # Break inner attempt loop, go to next engine

                response.raise_for_status()
                search_urls = extract_urls_from_search_response(response.text, engine)
                new_urls_count = 0
                for url in search_urls:
                    if url not in urls and is_valid_url(url): urls.append(url); new_urls_count += 1;
                    if len(urls) >= MAX_URLS_PER_QUERY: break
                if new_urls_count > 0: logger.info(f"Engine '{engine_name}', Query '{query}', Attempt {attempt+1}: Found {new_urls_count} new URLs.")
                if urls: break # Break attempt loop if URLs found

            except httpx.TimeoutException: logger.warning(f"Engine '{engine_name}', Query '{query}', Attempt {attempt+1}: Timeout. Trying next attempt/engine."); continue
            except httpx.RequestError as e: logger.warning(f"Engine '{engine_name}', Query '{query}', Attempt {attempt+1}: Request error: {e}. Trying next attempt/engine."); continue
            except Exception as e: logger.error(f"Engine '{engine_name}', Query '{query}', Attempt {attempt+1}: Unexpected error: {e}. Trying next attempt/engine.", exc_info=True); continue # Log traceback for unexpected

        if len(urls) >= MAX_URLS_PER_QUERY: break # Break engine loop if max URLs reached

    logger.debug(f"--- Finished search for query: '{query}'. Found {len(urls)} total URLs. ---") # Log query end
    return urls[:MAX_URLS_PER_QUERY]

async def extract_text_from_html(html, url):
    """Extract relevant text content from HTML using multi-method content extraction."""
    try:
        soup = BeautifulSoup(html, 'lxml')
        title = soup.title.string.strip() if soup.title else "No Title Found"
        html_sample = str(soup)[:1000] + "..." if len(str(soup)) > 1000 else str(soup) # For debugging

        # METHOD 1: Tag-based Content Extraction
        logger.debug(f"Starting content extraction for {url} - METHOD 1: Tag-based")
        noise_soup = BeautifulSoup(html, 'lxml')
        for selector in NOISE_SELECTORS:
            for element in noise_soup.select(selector): element.decompose()
        content_area = None; content_selector_used = None
        semantic_selectors = ['article', 'main', 'section']
        for selector in semantic_selectors:
            content_elements = noise_soup.find_all(selector)
            if content_elements:
                # Select the largest semantic element by text length
                content_area = max(content_elements, key=lambda x: len(x.get_text(strip=True)))
                content_selector_used = selector; logger.debug(f"Found content using semantic selector: {selector}"); break
        if not content_area:
            for selector in CONTENT_SELECTORS:
                content_area = noise_soup.select_one(selector)
                if content_area and len(content_area.get_text(strip=True)) > 200:
                    content_selector_used = selector; logger.debug(f"Found content using content selector: {selector}"); break

        # Extract content using method 1
        content_from_method1 = ""
        if content_area:
            headings = [clean_content(h.get_text(strip=True)) for h in content_area.find_all(['h1', 'h2', 'h3', 'h4', 'h5']) if len(h.get_text(strip=True)) > 15]
            paragraphs = [clean_content(p.get_text(strip=True)) for p in content_area.find_all('p') if len(p.get_text(strip=True)) > 50]
            structured_content = []
            if title and title not in headings: structured_content.append(f"# {title}")
            for heading in headings:
                structured_content.append(f"## {heading}")
                # Use a copy of paragraphs list for safe removal
                for p in paragraphs[:]:
                    if len(p) > 50:
                        structured_content.append(p)
                        try: paragraphs.remove(p)
                        except ValueError: pass
            for p in paragraphs:
                if p not in structured_content and len(p) > 50: structured_content.append(p)
            content_from_method1 = "\n\n".join(structured_content)
            logger.debug(f"METHOD 1 extracted {len(content_from_method1)} chars using {content_selector_used}")
        else:
            logger.warning(f"METHOD 1 failed to identify main content area for {url}")

        # METHOD 2: Text Density Analysis
        if not content_from_method1 or len(content_from_method1) < 500:
            logger.debug(f"Starting METHOD 2: Text density analysis for {url}")
            density_soup = BeautifulSoup(html, 'lxml')
            for selector in NOISE_SELECTORS:
                for element in density_soup.select(selector): element.decompose()
            content_blocks = []
            for p in density_soup.find_all('p'):
                text = p.get_text(strip=True); html_length = len(str(p)); text_length = len(text)
                if text_length > 50: density = text_length / html_length if html_length > 0 else 0; content_blocks.append((p, text, density))
            for div in density_soup.find_all('div'):
                if len(div.find_all('div')) > 5: continue
                text = div.get_text(strip=True); html_length = len(str(div)); text_length = len(text)
                if text_length > 100: density = text_length / html_length if html_length > 0 else 0; content_blocks.append((div, text, density))
            content_blocks.sort(key=lambda x: x[2], reverse=True)
            method2_content = []
            if title: method2_content.append(f"# {title}")
            for _, text, density in content_blocks[:10]:
                cleaned_text = clean_content(text)
                if len(cleaned_text) > 50 and cleaned_text not in method2_content: method2_content.append(cleaned_text)
            content_from_method2 = "\n\n".join(method2_content)
            logger.debug(f"METHOD 2 extracted {len(content_from_method2)} chars using density analysis")
            if len(content_from_method2) > len(content_from_method1) * 1.5:
                main_content = content_from_method2; logger.debug(f"Using METHOD 2 results for {url}")
            else:
                main_content = content_from_method1; logger.debug(f"Using METHOD 1 results for {url}")
        else:
            main_content = content_from_method1

        # METHOD 3: Simple Paragraph Extraction (Last Resort)
        if not main_content or len(main_content) < 200:
            logger.warning(f"Methods 1 and 2 failed for {url}. Trying simple paragraph extraction (METHOD 3)")
            fallback_soup = BeautifulSoup(html, 'lxml')
            paragraphs = [];
            if title: paragraphs.append(f"# {title}")
            for p in fallback_soup.find_all('p'):
                text = p.get_text(strip=True)
                if len(text) > 50:
                    cleaned = clean_content(text)
                    if cleaned not in paragraphs: paragraphs.append(cleaned)
            main_content = "\n\n".join(paragraphs)
            logger.debug(f"METHOD 3 (last resort) extracted {len(main_content)} chars")

        # Final Processing
        if main_content and len(main_content) > 200:
            if len(main_content) > MAX_CONTENT_LENGTH: main_content = main_content[:MAX_CONTENT_LENGTH] + "... [truncated]"
            logger.info(f"Successfully extracted {len(main_content)} chars from {url}")
            return {"title": title, "content": main_content, "url": url}
        else:
            logger.warning(f"No meaningful content could be extracted from {url} after trying all methods")
            logger.debug(f"URL: {url}, Title: {title}, HTML sample: {html_sample[:300]}...")
    except Exception as e:
        logger.error(f"Error extracting text from {url}: {e}", exc_info=True)
        # Avoid logging potentially large HTML in production errors
        # logger.debug(f"HTML that caused extraction failure: {html_sample[:500]}...")
    return None

async def scrape_url(url, client, retry_count=0):
    """Scrape a URL with enhanced retry logic and browser emulation."""
    if retry_count > MAX_RETRIES: logger.warning(f"Max retries ({MAX_RETRIES}) reached for {url}"); return None
    logger.info(f"Scraping URL: {url} (attempt {retry_count + 1}/{MAX_RETRIES + 1})")
    enhanced_headers = { 'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8', 'Accept-Language': 'en-US,en;q=0.9', 'Accept-Encoding': 'gzip, deflate', 'DNT': '1', 'Connection': 'keep-alive', 'Upgrade-Insecure-Requests': '1', 'Cache-Control': 'max-age=0', 'Sec-Fetch-Dest': 'document', 'Sec-Fetch-Mode': 'navigate', 'Sec-Fetch-Site': 'none', 'Sec-Fetch-User': '?1' }
    try:
        # Exponential backoff with jitter
        backoff = (2 ** retry_count) * random.uniform(0.8, 1.2)
        delay = min(get_random_delay() + backoff, 30.0) # Cap backoff delay
        logger.debug(f"Waiting {delay:.2f}s before requesting {url}")
        await asyncio.sleep(delay)

        current_headers = enhanced_headers.copy(); current_headers['User-Agent'] = random.choice(USER_AGENTS); client.headers.update(current_headers)
        if retry_count > 0: client.headers['Referer'] = random.choice(["https://www.google.com/","https://www.bing.com/","https://duckduckgo.com/"])
        logger.debug(f"Sending request to {url} with User-Agent: {client.headers['User-Agent'][:30]}...")
        response = await client.get(url, follow_redirects=True, timeout=SCRAPE_TIMEOUT); status_code = response.status_code; content_type = response.headers.get('content-type', '').lower(); logger.debug(f"Response from {url}: status={status_code}, content-type={content_type}")
        if status_code == 200:
            response_text = response.text.lower(); block_indicators = ['captcha', 'security check', 'access denied', 'blocked', 'suspicious activity', 'automated requests', 'verify you are human']
            if any(indicator in response_text for indicator in block_indicators):
                logger.warning(f"Detected possible block page from {url} despite 200 status")
                # Treat as retriable error
                raise httpx.HTTPStatusError(f"Suspected block page detected", request=response.request, response=response)
        response.raise_for_status() # Raise for 4xx/5xx errors
        if 'html' not in content_type and 'text' not in content_type: logger.warning(f"Skipping non-HTML content at {url} (type: {content_type})"); return None
        if not response.text or len(response.text) < 100:
            logger.warning(f"Empty or very short response from {url} ({len(response.text)} chars)")
            # Treat as retriable error
            raise httpx.RequestError(f"Received minimal content ({len(response.text)} chars)")
        content_item = await extract_text_from_html(response.text, url)
        if not content_item: logger.warning(f"Content extraction failed for {url} despite successful request")
        return content_item
    except (httpx.TimeoutException, httpx.RequestError, httpx.HTTPStatusError) as e:
        logger.warning(f"Scraping error for {url} (Attempt {retry_count+1}/{MAX_RETRIES+1}): {type(e).__name__} - {e}. Retrying...")
        return await scrape_url(url, client, retry_count + 1) # Recursive retry call
    except httpx.TooManyRedirects: logger.warning(f"Too many redirects for {url}"); return None
    except Exception as e:
        logger.error(f"Unexpected error scraping {url}: {e}", exc_info=True)
        # Optionally retry unexpected errors once
        if retry_count < 1:
             logger.warning("Retrying once after unexpected error...")
             return await scrape_url(url, client, retry_count + 1)
    return None
# --- End Helper Functions ---

class ContentCrawlerAgent(ResearchAgent):
    """
    Accepts a list of search queries, performs web searches, scrapes content
    using httpx and BeautifulSoup, and returns raw content.
    """
    def __init__(self):
        super().__init__(agent_id=AGENT_ID, agent_metadata={"name": "Content Crawler Agent"})
        if not _scraper_available:
            logger.critical("Scraping dependencies (httpx, beautifulsoup4, lxml) are missing!")

    async def _create_scrape_client(self):
        """Creates a new httpx client for scraping."""
        if not _scraper_available: return None
        headers = {'User-Agent': random.choice(USER_AGENTS)}
        # Increased connect timeout
        return httpx.AsyncClient(timeout=httpx.Timeout(SCRAPE_TIMEOUT + 5.0, connect=15.0), follow_redirects=True, headers=headers)

    async def process_task(self, task_id: str, content: Union[str, Dict[str, Any]]):
        """
        Processes search queries, performs searches, scrapes URLs, and returns content.
        Ensures the raw_content artifact is always notified.
        """
        await self.task_store.update_task_state(task_id, TaskState.WORKING)
        self.logger.info(f"Task {task_id}: Starting content crawling process.")
        final_state = TaskState.FAILED # Default to FAILED
        error_message = None
        scraped_content_items = [] # Initialize as empty list
        all_urls_found = set()
        query_context_map = {}
        scrape_client = None
        completion_message = "Task started..." # Default completion message

        try:
            scrape_client = await self._create_scrape_client()
            if not scrape_client:
                 raise AgentProcessingError("Scraping dependencies missing or client creation failed.")

            if not isinstance(content, dict):
                raise AgentProcessingError("Input content must be a dictionary.")

            # --- Enhanced Input Validation and Logging ---
            search_query_groups: List[Dict[str, Any]] = []
            raw_queries_input = content.get("search_queries")
            self.logger.debug(f"Task {task_id}: Received raw_queries input of type {type(raw_queries_input)}: {str(raw_queries_input)[:200]}...")

            if isinstance(raw_queries_input, dict) and "search_queries" in raw_queries_input:
                potential_list = raw_queries_input.get("search_queries")
                if isinstance(potential_list, list):
                    search_query_groups = potential_list
                    self.logger.info(f"Task {task_id}: Extracted nested list of {len(search_query_groups)} query groups.")
                else:
                    self.logger.warning(f"Task {task_id}: Expected list under nested 'search_queries', got {type(potential_list)}. Cannot process.")
            elif isinstance(raw_queries_input, list):
                search_query_groups = raw_queries_input
                self.logger.info(f"Task {task_id}: Received list of {len(search_query_groups)} query groups directly.")
            else:
                self.logger.warning(f"Task {task_id}: 'search_queries' key missing or invalid format in input: {type(raw_queries_input)}. Cannot perform searches.")
            # --- End Enhanced Input Validation ---

            if not search_query_groups:
                self.logger.warning(f"Task {task_id}: No valid search queries provided. Crawler will produce no results.")
                completion_message = "No valid search queries provided. No content scraped."
            else:
                self.logger.info(f"Task {task_id}: Processing {len(search_query_groups)} query groups.")

                # 1. Perform Searches (using the robust search_and_get_urls)
                urls_to_scrape_with_context = []
                self.logger.debug(f"Task {task_id}: Starting search loop...")
                search_tasks = []
                for query_group_index, query_group in enumerate(search_query_groups):
                    # --- Added Detailed Check ---
                    if not isinstance(query_group, dict):
                        self.logger.warning(f"Task {task_id}: Skipping invalid query group at index {query_group_index} because it's not a dictionary. Type: {type(query_group)}, Value: {str(query_group)[:100]}")
                        continue
                    # --- End Added Check ---
                    subtopic = query_group.get("subtopic", "Unknown"); queries = query_group.get("queries")
                    if not queries or not isinstance(queries, list): self.logger.warning(f"Task {task_id}: Skipping query group for subtopic '{subtopic}' due to missing/invalid queries list (type: {type(queries)})."); continue
                    for query_index, query_str in enumerate(queries):
                        if not query_str or not isinstance(query_str, str): self.logger.warning(f"Task {task_id}: Skipping invalid query string at index {query_index} for subtopic '{subtopic}'."); continue
                        if len(all_urls_found) >= MAX_TOTAL_URLS: break
                        self.logger.debug(f"Task {task_id}: Creating search task for query: '{query_str}'")
                        # Create a task for each query search
                        search_tasks.append(asyncio.create_task(search_and_get_urls(query_str, scrape_client)))
                        # Store context mapping early
                        query_context_map[query_str] = {"subtopic": subtopic, "query": query_str, "source": "web_search"}
                    if len(all_urls_found) >= MAX_TOTAL_URLS: break

                # Gather results from all search tasks concurrently
                if search_tasks:
                    self.logger.info(f"Task {task_id}: Gathering results from {len(search_tasks)} search tasks...")
                    search_results_lists = await asyncio.gather(*search_tasks, return_exceptions=True)
                    self.logger.debug(f"Task {task_id}: Finished search loop gathering.")
                else:
                    search_results_lists = []
                    self.logger.warning(f"Task {task_id}: No valid search tasks were created.")


                # Process search results
                for i, result_list in enumerate(search_results_lists):
                    # Need a reliable way to get the original query back if tasks list is used
                    # For now, we assume the order is preserved, but this is fragile.
                    # A better approach would be to return (query, urls) from search_and_get_urls
                    # or pass context through gather. Using the map as a fallback.
                    original_query = "Unknown Query" # Fallback
                    if i < len(search_tasks):
                        # Attempt to get query from task (very fragile)
                        try:
                            # This introspection is not reliable
                            qualname_parts = search_tasks[i].get_coro().__qualname__.split("'")
                            if len(qualname_parts) > 1:
                                original_query = qualname_parts[1]
                        except Exception:
                            pass # Fallback to map below

                    # Use the map as the primary way to get context
                    # Find the query info based on the results (less direct)
                    query_info = None
                    if isinstance(result_list, list) and result_list:
                         # Find context based on the first URL returned for this query
                         first_url = result_list[0]
                         for q_str, info in query_context_map.items():
                             # This assumes search_and_get_urls returns URLs for the query q_str
                             # We need a better link between the gather result and the original query
                             # For now, let's just log the issue if we can't find it
                             pass # Need a better way to link results back to query
                         # Temporary: Use index to guess query (highly unreliable)
                         if i < len(list(query_context_map.keys())):
                             original_query = list(query_context_map.keys())[i]
                             query_info = query_context_map.get(original_query)


                    if query_info is None:
                         query_info = {"subtopic": "Unknown", "query": original_query, "source": "web_search"}
                         self.logger.warning(f"Task {task_id}: Could not reliably determine original query for result set {i}. Using fallback context.")


                    if isinstance(result_list, Exception):
                        self.logger.warning(f"Task {task_id}: Search failed for query '{query_info['query']}': {result_list}")
                        continue

                    self.logger.info(f"Task {task_id}: Found {len(result_list)} URLs for query: '{query_info['query']}'")
                    for url in result_list:
                         if url not in all_urls_found and len(all_urls_found) < MAX_TOTAL_URLS:
                             all_urls_found.add(url)
                             urls_to_scrape_with_context.append({"url": url, "query_info": query_info})
                             # Update context map with final URL if redirects happened etc.
                             query_context_map[url] = query_info # Map the actual URL found
                    if len(all_urls_found) >= MAX_TOTAL_URLS:
                        self.logger.info(f"Task {task_id}: Reached MAX_TOTAL_URLS limit ({MAX_TOTAL_URLS}) during URL collection.")
                        break

                self.logger.info(f"Task {task_id}: Total unique URLs to scrape: {len(urls_to_scrape_with_context)}")

                # 2. Scrape Content (using the robust scrape_url)
                if not urls_to_scrape_with_context:
                    self.logger.warning(f"Task {task_id}: No URLs found after searching. No content scraped.")
                    completion_message = f"Crawling complete. No URLs found for the provided queries."
                else:
                    self.logger.debug(f"Task {task_id}: Starting scraping loop for {len(urls_to_scrape_with_context)} URLs...")
                    # Use a semaphore to limit concurrency
                    scrape_semaphore = asyncio.Semaphore(5) # Limit to 5 concurrent scrapes

                    async def scrape_with_semaphore(item):
                        async with scrape_semaphore:
                            # Pass the specific client instance
                            return await scrape_url(item["url"], scrape_client)

                    scrape_tasks = [scrape_with_semaphore(item) for item in urls_to_scrape_with_context]
                    results = await asyncio.gather(*scrape_tasks, return_exceptions=True)
                    self.logger.debug(f"Task {task_id}: Finished scraping loop.")
                    for i, result in enumerate(results):
                        original_url = urls_to_scrape_with_context[i]["url"]
                        # Get context using the original URL scraped
                        query_info = query_context_map.get(original_url, {"subtopic": "Unknown", "query": "Unknown", "source": "web_search"})
                        if isinstance(result, Exception): self.logger.warning(f"Task {task_id}: Error scraping {original_url}: {result}")
                        elif result and result.get("content"): scraped_content_items.append({ "url": result.get("url", original_url), "title": result.get("title", "N/A"), "content": result.get("content"), "query_source": query_info, "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()})
                        else: self.logger.warning(f"Task {task_id}: No content returned for {original_url}")
                    self.logger.info(f"Task {task_id}: Successfully scraped {len(scraped_content_items)} items.")
                    completion_message = f"Content crawling complete. Found {len(all_urls_found)} URLs, successfully scraped {len(scraped_content_items)}."

            final_state = TaskState.COMPLETED

        except Exception as e:
            self.logger.exception(f"Error processing content crawling for task {task_id}: {e}")
            error_message = f"Failed during content crawling: {e}"
            final_state = TaskState.FAILED
            completion_message = error_message

        finally:
            if _MODELS_AVAILABLE:
                try:
                    logger.info(f"Task {task_id}: Notifying raw_content artifact (containing {len(scraped_content_items)} items).")
                    result_artifact = Artifact( id=f"{task_id}-raw_content", type="raw_content", content=scraped_content_items, media_type="application/json" )
                    await self.task_store.notify_artifact_event(task_id, result_artifact)
                except Exception as notify_err:
                    logger.error(f"Task {task_id}: CRITICAL - Failed to notify raw_content artifact: {notify_err}")
                    final_state = TaskState.FAILED; error_message = error_message or f"Failed to notify artifact: {notify_err}"; completion_message = error_message
            else: logger.warning("Task {task_id}: Cannot notify artifacts: Core models not available.")

            if _MODELS_AVAILABLE:
                 try: response_msg = Message(role="assistant", parts=[TextPart(content=completion_message)]); await self.task_store.notify_message_event(task_id, response_msg)
                 except Exception as notify_err: logger.error(f"Task {task_id}: Failed to notify final message: {notify_err}")
            else: logger.info(f"Task {task_id}: Final message: {completion_message}")

            await self.task_store.update_task_state(task_id, final_state, message=error_message)
            if scrape_client: await scrape_client.aclose()
            self.logger.info(f"Task {task_id}: EXITING process_task for ContentCrawlerAgent. Final State: {final_state}")


# --- FastAPI app setup (remains the same) ---
from fastapi import FastAPI, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from agentvault_server_sdk import create_a2a_router
import os

agent = ContentCrawlerAgent()
app = FastAPI(title="ContentCrawlerAgent")
app.add_middleware( CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"],)
router = create_a2a_router( agent=agent, task_store=agent.task_store, dependencies=[Depends(lambda: BackgroundTasks())])
app.include_router(router, prefix="/a2a")

@app.get("/agent-card.json")
async def get_agent_card():
    card_path = os.getenv("AGENT_CARD_PATH", "/app/agent-card.json")
    try:
        with open(card_path, "r", encoding="utf-8") as f: return json.load(f)
    except Exception as e:
        logger.error(f"Failed to read agent card from {card_path}: {e}")
        try:
            with open("/app/agent-card.json", "r", encoding="utf-8") as f: return json.load(f)
        except Exception as e2: logger.error(f"Failed to read fallback agent card: {e2}"); return {"error": "Agent card not found"}
@app.get("/health")
async def health_check(): return {"status": "healthy"}
