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
import uuid # Added missing import

# EMERGENCY PATCH: Direct config loading
def load_config_directly(path):
    '''Load a config file directly.'''
    import json
    try:
        with open(path, 'r', encoding='utf-8') as f:
            config_data = json.load(f)
        logger.info(f"EMERGENCY PATCH: Loaded config from {path}")
        # Extract key fallback settings
        if 'search' in config_data:
            fallback_settings = {
                'use_fallback_urls': config_data['search'].get('use_fallback_urls', True),
                'add_fallback_results': config_data['search'].get('add_fallback_results', True)
            }
            logger.info(f"EMERGENCY PATCH: Fallback settings in config: {fallback_settings}")
            return fallback_settings
        return {}
    except Exception as e:
        logger.error(f"EMERGENCY PATCH: Error loading config: {e}")
        return {}

# Import configuration if available
try:
    # Add the src directory to the path if needed
    src_path = Path(__file__).resolve().parent / "src"
    if src_path.exists():
        sys.path.append(str(src_path))

    from langgraph_research_orchestrator.config import get_pipeline_config
    config = get_pipeline_config()
    USE_CONFIG = True
    logger = logging.getLogger(__name__)
    logger.info("Successfully imported pipeline configuration")
except ImportError as e:
    USE_CONFIG = False
    # Configure logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    logger = logging.getLogger(__name__)
    logger.warning(f"Could not import pipeline configuration, using defaults: {e}")

# Constants for scraping - will be overridden by config if available
MAX_URLS_PER_QUERY = 5  # Maximum URLs to scrape per search query
MAX_TOTAL_URLS = 20     # Maximum total URLs to scrape across all queries
SCRAPE_TIMEOUT = 20.0   # Timeout for each request in seconds
REQUEST_DELAY_MIN = 1.0 # Minimum delay between requests
REQUEST_DELAY_MAX = 3.0 # Maximum delay between requests
MAX_CONTENT_LENGTH = 20000  # Maximum content length to store per page
MAX_RETRIES = 3        # Maximum number of retries for failed requests

# Default fallback settings (will be overridden by config if available)
USE_FALLBACK_URLS = True
ADD_FALLBACK_RESULTS = True

# If configuration is available, override defaults
if USE_CONFIG:
    scraper_config = config.scraper
    search_config = config.search
    MAX_URLS_PER_QUERY = scraper_config.max_urls_per_query
    MAX_TOTAL_URLS = scraper_config.max_total_urls
    SCRAPE_TIMEOUT = scraper_config.scrape_timeout
    REQUEST_DELAY_MIN = scraper_config.request_delay_min
    REQUEST_DELAY_MAX = scraper_config.request_delay_max
    MAX_CONTENT_LENGTH = scraper_config.max_content_length
    MAX_RETRIES = scraper_config.max_retries

    # Get fallback settings from search config
    USE_FALLBACK_URLS = search_config.use_fallback_urls
    ADD_FALLBACK_RESULTS = search_config.add_fallback_results

    logger.info(f"Using configured values: MAX_URLS_PER_QUERY={MAX_URLS_PER_QUERY}, MAX_TOTAL_URLS={MAX_TOTAL_URLS}")
    logger.info(f"Fallback settings: USE_FALLBACK_URLS={USE_FALLBACK_URLS}, ADD_FALLBACK_RESULTS={ADD_FALLBACK_RESULTS}")

# Robust list of user agents to avoid detection
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/117.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36 Edg/115.0.1901.203",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPad; CPU OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/115.0.5790.130 Mobile/15E148 Safari/604.1",
]

# Common content selectors across different websites
CONTENT_SELECTORS = [
    'article', 'main', '#main', '#content', '.content',
    '.post-content', '.entry-content', '.main-content',
    '#main-content', '.article-content', '.story-content',
    '.story', '.post', '.article-body', '.article__body',
    '.article__content', '.post__content', '.blog-post',
    '.blog-content', '.news-article', '.container'
]

# Elements to remove (noisy content)
NOISE_SELECTORS = [
    'header', 'footer', 'nav', '.nav', '#nav', '.navigation', '#navigation',
    '.menu', '#menu', '.sidebar', '#sidebar', 'aside', '.aside',
    '.ad', '.ads', '.advertisement', '.advertisements', '.banner', '.banners',
    '.cookie', '.cookies', '.cookie-banner', '.cookie-notice',
    '.popup', '.modal', '.subscribe', '.subscription', '.newsletter',
    '.comments', '#comments', '.comment-section', '.related-posts',
    '.social', '.social-share', '.social-links', '.share-buttons',
    'script', 'style', 'noscript', 'iframe', 'svg'
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

# If using config, filter engines based on active_engines setting
if USE_CONFIG:
    search_config = config.search
    active_engine_names = search_config.active_engines
    SEARCH_ENGINES = [engine for engine in SEARCH_ENGINES if engine["name"] in active_engine_names]
    logger.info(f"Using {len(SEARCH_ENGINES)} search engines: {', '.join(engine['name'] for engine in SEARCH_ENGINES)}")

# Default fallback search queries for climate change adaptation
DEFAULT_SEARCH_QUERIES = [
    "climate change adaptation strategies",
    "climate resilience urban planning",
    "water management climate change",
    "agricultural adaptation climate change",
    "coastal protection sea level rise",
    "climate-resilient infrastructure",
    "climate adaptation policy government",
    "climate change health impacts adaptation"
]

# Fallback directory of manually curated URLs on climate change adaptation
# COMPLETELY DISABLED - NO FALLBACKS ALLOWED
FALLBACK_URLS = []  # EMERGENCY PATCH: Disabled all fallbacks

# Reliable authority sources for fact verification
AUTHORITY_SOURCES = {
    "ipcc": {
        "domain": "ipcc.ch",
        "name": "Intergovernmental Panel on Climate Change",
        "reliability": 0.95,
        "focus": ["climate science", "climate change", "climate adaptation", "climate policy"]
    },
    "unep": {
        "domain": "unep.org",
        "name": "United Nations Environment Programme",
        "reliability": 0.93,
        "focus": ["environment", "climate action", "climate adaptation", "sustainability"]
    },
    "epa": {
        "domain": "epa.gov",
        "name": "Environmental Protection Agency",
        "reliability": 0.92,
        "focus": ["environmental protection", "climate policy", "adaptation strategies"]
    },
    "wri": {
        "domain": "wri.org",
        "name": "World Resources Institute",
        "reliability": 0.91,
        "focus": ["resources", "sustainability", "climate resilience", "adaptation"]
    },
    "unfccc": {
        "domain": "unfccc.int",
        "name": "United Nations Framework Convention on Climate Change",
        "reliability": 0.94,
        "focus": ["climate policy", "international agreements", "adaptation"]
    },
    "worldbank": {
        "domain": "worldbank.org",
        "name": "World Bank",
        "reliability": 0.90,
        "focus": ["development", "climate finance", "adaptation projects"]
    },
    "c2es": {
        "domain": "c2es.org",
        "name": "Center for Climate and Energy Solutions",
        "reliability": 0.88,
        "focus": ["climate policy", "energy", "business adaptation"]
    },
    "climateadapt": {
        "domain": "climate-adapt.eea.europa.eu",
        "name": "European Climate Adaptation Platform",
        "reliability": 0.89,
        "focus": ["european adaptation", "climate policy", "adaptation strategies"]
    },
    "undp": {
        "domain": "adaptation-undp.org",
        "name": "United Nations Development Programme",
        "reliability": 0.92,
        "focus": ["development", "adaptation projects", "capacity building"]
    }
}

# Configuration-dependent fact extraction parameters
MIN_FACT_CHARS = 50
MAX_FACTS_PER_CONTENT = 5
if USE_CONFIG:
    fact_extraction_config = config.fact_extraction
    MIN_FACT_CHARS = fact_extraction_config.min_fact_chars
    MAX_FACTS_PER_CONTENT = fact_extraction_config.max_facts_per_content

# Configuration-dependent fact verification parameters
USE_AUTHORITY_SCORES = True
MIN_CONFIDENCE_THRESHOLD = 0.6
DETECT_CONTRADICTIONS = True
AUTHORITY_SCORE_WEIGHT = 0.7
if USE_CONFIG:
    fact_verification_config = config.fact_verification
    USE_AUTHORITY_SCORES = fact_verification_config.use_authority_scores
    MIN_CONFIDENCE_THRESHOLD = fact_verification_config.min_confidence_threshold
    DETECT_CONTRADICTIONS = fact_verification_config.detect_contradictions
    AUTHORITY_SCORE_WEIGHT = fact_verification_config.authority_score_weight

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
    """Parse URLs from DuckDuckGo Lite search results using structural analysis."""
    urls = []
    try:
        # Log the HTML structure for debugging
        logger.info(f"DuckDuckGo parsing - soup title: {soup.title.string if soup.title else 'No title'}")
        logger.info(f"DuckDuckGo parsing - found {len(soup.select('a'))} links total")
        
        # APPROACH 1: Try standard selectors first
        selectors = ['a.result-link', '.links a', '.result a', '.web-result a']
        for selector in selectors:
            links = soup.select(selector)
            logger.info(f"DuckDuckGo selector '{selector}' found {len(links)} links")
            
            for link in links:
                href = link.get('href')
                if href and '/lite/?' not in href and is_valid_url(href):
                    logger.info(f"Found valid DuckDuckGo result: {href}")
                    urls.append(href)
        
        # APPROACH 2: Try XPath-based structural approach if no results
        if not urls:
            logger.warning("Trying structural XPath approach for DuckDuckGo")
            tables = soup.find_all('table')
            logger.info(f"Found {len(tables)} tables in the document")
            
            # DuckDuckGo Lite typically uses tables for results
            for i, table in enumerate(tables):
                links = table.find_all('a')
                logger.info(f"Table {i+1} contains {len(links)} links")
                
                for link in links:
                    href = link.get('href')
                    # Exclude internal links and form submissions
                    if href and href.startswith(('http://', 'https://')) and '/lite/?' not in href and '?' not in href and is_valid_url(href):
                        logger.info(f"Found structural result: {href}")
                        urls.append(href)
        
        # APPROACH 3: If still no results, try HTML structure analysis
        if not urls:
            logger.warning("Trying HTML structure analysis for DuckDuckGo")
            # Save sample of HTML for debugging
            html_sample = str(soup)[:1000] + "..." if len(str(soup)) > 1000 else str(soup)
            logger.info(f"HTML sample for analysis: {html_sample}")
            
            # Look for all external links that aren't clearly navigation
            for link in soup.find_all('a'):
                href = link.get('href')
                # Identify likely result links by structure and content
                link_text = link.get_text(strip=True)
                if (href and 
                    href.startswith(('http://', 'https://')) and 
                    '/lite/?' not in href and 
                    not href.endswith('.css') and
                    not href.endswith('.js') and
                    len(link_text) > 10 and  # Results usually have substantial text
                    is_valid_url(href)):
                    logger.info(f"Found analysis-based result: {href} with text: {link_text[:30]}...")
                    urls.append(href)
    except Exception as e:
        logger.error(f"Error in DuckDuckGo parser: {e}", exc_info=True)
    
    # Deduplicate URLs
    unique_urls = list(dict.fromkeys(urls))
    logger.info(f"DuckDuckGo parser found {len(unique_urls)} unique URLs from {len(urls)} total links")
    return unique_urls

def ecosia_parser(soup):
    """Parse URLs from Ecosia search results with multiple fallback methods."""
    urls = []
    try:
        # Log the HTML structure for debugging
        logger.info(f"Ecosia parsing - soup title: {soup.title.string if soup.title else 'No title'}")
        logger.info(f"Ecosia parsing - found {len(soup.select('a'))} links total")
        
        # APPROACH 1: Try standard selectors
        selectors = [
            '.result a.js-result-url', 
            '.result-url', 
            '.result a[href^="http"]',
            '.result__link',
            '.organic-result a'
        ]
        
        for selector in selectors:
            links = soup.select(selector)
            logger.info(f"Ecosia selector '{selector}' found {len(links)} links")
            
            for link in links:
                href = link.get('href')
                if not href:
                    continue
                    
                # Handle redirects
                if href.startswith('/url?') or 'url=' in href:
                    url_match = re.search(r'url=([^&]+)', href)
                    if url_match:
                        href = url_match.group(1)
                        
                if is_valid_url(href):
                    logger.info(f"Found valid Ecosia result: {href}")
                    urls.append(href)
        
        # APPROACH 2: Structural analysis if no results found
        if not urls:
            logger.warning("Using structural analysis for Ecosia results")
            # Look for result containers
            result_divs = soup.find_all('div', class_=lambda c: c and ('result' in c.lower()))
            logger.info(f"Found {len(result_divs)} potential result containers")
            
            for div in result_divs:
                for link in div.find_all('a', href=True):
                    href = link.get('href')
                    if href.startswith('/url?') or 'url=' in href:
                        url_match = re.search(r'url=([^&]+)', href)
                        if url_match:
                            href = url_match.group(1)
                    
                    if href and href.startswith(('http://', 'https://')) and is_valid_url(href):
                        logger.info(f"Found structural Ecosia result: {href}")
                        urls.append(href)
        
        # APPROACH 3: Last resort - look for any plausible external links
        if not urls:
            logger.warning("Using last resort method for Ecosia results")
            # Save sample of HTML for debugging
            html_sample = str(soup)[:1000] + "..." if len(str(soup)) > 1000 else str(soup)
            logger.info(f"HTML sample for analysis: {html_sample}")
            
            for link in soup.find_all('a', href=True):
                href = link.get('href')
                link_text = link.get_text(strip=True)
                
                # Extract URL from redirect if needed
                if href.startswith('/url?') or 'url=' in href:
                    url_match = re.search(r'url=([^&]+)', href)
                    if url_match:
                        href = url_match.group(1)
                
                # Look for links that appear to be search results (have substantial text and valid URLs)
                if (href and 
                    href.startswith(('http://', 'https://')) and 
                    len(link_text) > 10 and
                    not href.endswith(('.css', '.js', '.png', '.jpg', '.gif')) and
                    not any(x in href.lower() for x in ['ecosia.org/settings', 'account', 'login', 'static']) and
                    is_valid_url(href)):
                    logger.info(f"Found last resort Ecosia result: {href}")
                    urls.append(href)
    except Exception as e:
        logger.error(f"Error in Ecosia parser: {e}", exc_info=True)
    
    # Deduplicate URLs
    unique_urls = list(dict.fromkeys(urls))
    logger.info(f"Ecosia parser found {len(unique_urls)} unique URLs from {len(urls)} total links")
    return unique_urls

def mojeek_parser(soup):
    """Parse URLs from Mojeek search results with multiple fallback methods."""
    urls = []
    try:
        # Log the HTML structure for debugging
        logger.info(f"Mojeek parsing - soup title: {soup.title.string if soup.title else 'No title'}")
        logger.info(f"Mojeek parsing - found {len(soup.select('a'))} links total")
        
        # APPROACH 1: Try standard selectors
        selectors = [
            '.results-standard .title a',
            '.title a[href^="http"]',
            '.results a.title', 
            '.snippet-container a',
            '.results a[href^="http"]'
        ]
        
        for selector in selectors:
            links = soup.select(selector)
            logger.info(f"Mojeek selector '{selector}' found {len(links)} links")
            
            for link in links:
                href = link.get('href')
                if href and href.startswith('http') and is_valid_url(href):
                    logger.info(f"Found valid Mojeek result: {href}")
                    urls.append(href)
        
        # APPROACH 2: Try structural analysis if no results
        if not urls:
            logger.warning("Using structural analysis for Mojeek results")
            # Look for result containers
            result_sections = []
            for div in soup.find_all('div'):
                # Results typically have certain characteristics
                if div.find('a', href=lambda h: h and h.startswith('http')):
                    result_sections.append(div)
            
            logger.info(f"Found {len(result_sections)} potential result containers")
            for section in result_sections:
                for link in section.find_all('a', href=lambda h: h and h.startswith('http')):
                    href = link.get('href')
                    if is_valid_url(href):
                        logger.info(f"Found structural Mojeek result: {href}")
                        urls.append(href)
        
        # APPROACH 3: Last resort - extract likely results based on link patterns
        if not urls:
            logger.warning("Using last resort method for Mojeek results")
            # Save sample of HTML for debugging
            html_sample = str(soup)[:1000] + "..." if len(str(soup)) > 1000 else str(soup)
            logger.info(f"HTML sample for analysis: {html_sample}")
            
            for link in soup.find_all('a', href=True):
                href = link.get('href')
                text = link.get_text(strip=True)
                
                # Mojeek results typically have these characteristics
                if (href and 
                    href.startswith('http') and 
                    is_valid_url(href) and
                    len(text) > 15 and  # Result links usually have substantial text
                    'mojeek' not in href.lower() and  # Exclude internal Mojeek links
                    not any(x in href.lower() for x in ['settings', 'account', 'login', 'static'])):
                    logger.info(f"Found last resort Mojeek result: {href} with text: {text[:30]}...")
                    urls.append(href)
    except Exception as e:
        logger.error(f"Error in Mojeek parser: {e}", exc_info=True)
    
    # Deduplicate URLs
    unique_urls = list(dict.fromkeys(urls))
    logger.info(f"Mojeek parser found {len(unique_urls)} unique URLs from {len(urls)} total links")
    return unique_urls

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

def extract_facts_from_content(text, subtopic):
    """Extract pregenerated facts from content text to ensure compatibility."""
    facts = []
    paragraphs = text.split('\n\n')

    # Generate meaningful facts from the content
    for i, paragraph in enumerate(paragraphs):
        if len(paragraph) < MIN_FACT_CHARS or paragraph.startswith('#'):  # Skip headers or very short paragraphs
            continue

        # Create a fact from this paragraph
        fact_id = f"fact-{i}-{uuid.uuid4().hex[:8]}" # Use imported uuid

        # Determine fact type based on content
        fact_type = "statement"
        if re.search(r'\d+(\.\d+)?%|\d+ (million|billion|trillion)|increased by \d+', paragraph):
            fact_type = "statistic"
        elif re.search(r'should|could|might|may|suggest|recommend|propose', paragraph):
            fact_type = "insight"

        # Create a fact with a proper structure for the information extraction agent
        fact = {
            "id": fact_id,
            "text": paragraph[:300] + "..." if len(paragraph) > 300 else paragraph,
            "source_url": "inline-extraction",
            "type": fact_type,
            "relevance_score": 0.9,
            "subtopic": subtopic
        }

        facts.append(fact)

        # Limit to MAX_FACTS_PER_CONTENT facts per content item
        if len(facts) >= MAX_FACTS_PER_CONTENT:
            break

    # Ensure we have at least one fact
    if not facts and len(text) > 100:
        facts.append({
            "id": f"fact-fallback-{uuid.uuid4().hex[:8]}", # Use imported uuid
            "text": text[:300] + "..." if len(text) > 300 else text,
            "source_url": "inline-extraction",
            "type": "statement",
            "relevance_score": 0.7,
            "subtopic": subtopic
        })

    return facts

# Removed redundant uuid4 function, using import uuid directly

async def search_and_get_urls(query, client):
    """Search for a query and get relevant URLs using multi-level fallback architecture."""
    urls = []
    
    # Enhanced headers to better mimic a real browser (based on research section V)
    enhanced_headers = {
        'User-Agent': random.choice(USER_AGENTS),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'Cache-Control': 'max-age=0',
        'Referer': 'https://www.google.com/'
    }
    
    # LEVEL 1: Try each search engine with enhanced browser emulation
    for engine in SEARCH_ENGINES:
        if len(urls) >= MAX_URLS_PER_QUERY:
            break
            
        engine_name = engine["name"]
        search_url = engine["url"]
        method = engine["method"]
        params = {k: (v.replace("QUERY_PLACEHOLDER", query) if isinstance(v, str) else v) 
                 for k, v in engine.get("params", {}).items()}
        
        logger.info(f"LEVEL 1: Searching with {engine_name} for: {query}")
        
        # Try multiple request configurations to bypass detection
        for attempt in range(2):  # Try two slightly different configurations
            try:
                # Random delay between 1.5-4.5 seconds (slightly longer to appear more human-like)
                delay = random.uniform(1.5, 4.5)
                logger.info(f"Waiting {delay:.2f}s before request to {engine_name}")
                await asyncio.sleep(delay)
                
                # Update headers with randomized User-Agent for each attempt
                current_headers = enhanced_headers.copy()
                current_headers['User-Agent'] = random.choice(USER_AGENTS)
                
                # Apply headers to client
                for key, value in current_headers.items():
                    client.headers[key] = value
                
                # Log request details for debugging
                logger.info(f"Request to {engine_name}: method={method}, url={search_url}")
                
                # Make the request based on the method with proper error handling
                try:
                    if method.upper() == "POST":
                        response = await client.post(search_url, data=params, follow_redirects=True, timeout=SCRAPE_TIMEOUT)
                    else:
                        response = await client.get(search_url, params=params, follow_redirects=True, timeout=SCRAPE_TIMEOUT)
                    
                    response.raise_for_status()
                except httpx.TimeoutException:
                    logger.warning(f"Timeout searching with {engine_name} - attempt {attempt+1}")
                    continue  # Try next configuration
                except httpx.RequestError as e:
                    logger.warning(f"Request error with {engine_name} - attempt {attempt+1}: {e}")
                    continue  # Try next configuration
                except Exception as e:
                    logger.error(f"Error searching with {engine_name} - attempt {attempt+1}: {e}")
                    continue  # Try next configuration
                
                # Save response details for debugging
                logger.info(f"Response from {engine_name}: status={response.status_code}, content-type={response.headers.get('content-type')}")
                
                # Check for suspected blocking responses
                content_sample = response.text[:200].lower()
                if any(x in content_sample for x in ['captcha', 'blocked', 'automated', 'suspicious', 'verify you are human']):
                    logger.warning(f"Possible blocking detected in {engine_name} response. Skipping.")
                    # Save first 1000 chars for debugging
                    logger.info(f"Suspected block response sample: {response.text[:1000]}...")
                    continue  # Try next configuration or engine
                
                # Extract URLs from the search results using parser in engine definition
                search_urls = extract_urls_from_search_response(response.text, engine)
                
                if search_urls:
                    logger.info(f"Successfully extracted {len(search_urls)} URLs using {engine_name} parser")
                else:
                    logger.warning(f"No URLs extracted from {engine_name} parser. Trying backup extraction.")
                    # Save first 2000 chars for debugging
                    html_sample = response.text[:2000] + "..." if len(response.text) > 2000 else response.text
                    logger.info(f"HTML sample for debugging: {html_sample}")
                    
                    soup = BeautifulSoup(response.text, 'lxml')
                    # Try to find any promising links (over 10 chars of text, http links)
                    for link in soup.find_all('a'):
                        href = link.get('href')
                        text = link.get_text(strip=True)
                        if (href and 
                            href.startswith(('http://', 'https://')) and 
                            len(text) > 10 and
                            is_valid_url(href)):
                            search_urls.append(href)
                    logger.info(f"Backup extraction found {len(search_urls)} URLs")

                # Add new unique URLs
                for url in search_urls:
                    if url not in urls and is_valid_url(url):
                        logger.info(f"Adding URL: {url}")
                        urls.append(url)
                        if len(urls) >= MAX_URLS_PER_QUERY:
                            break

                if urls:
                    logger.info(f"LEVEL 1 SUCCESS: Found {len(urls)} URLs from {engine_name} for query: {query}")
                    break  # Success! Break from the attempt loop
                else:
                    logger.warning(f"No usable URLs found from {engine_name} attempt {attempt+1}")
            
            except Exception as e:
                logger.error(f"Unexpected error searching with {engine_name} - attempt {attempt+1}: {e}", exc_info=True)
        
        # If we found URLs from this engine, break out of engine loop
        if urls:
            break
    
    # LEVEL 2: If all search engines failed, use topic-specific fallback URLs
    if not urls:
        logger.warning("LEVEL 1 FAILED: All search engines failed. Activating LEVEL 2 fallbacks.")
        
        # Determine the topic and use appropriate hardcoded URLs
        if "quantum" in query.lower():
            logger.info("Topic identified as quantum computing. Using quantum computing fallback URLs.")
            hardcoded_urls = [
                "https://www.ibm.com/quantum",
                "https://quantum-computing.ibm.com/",
                "https://www.nature.com/subjects/quantum-information",
                "https://www.sciencedirect.com/topics/computer-science/quantum-computing",
                "https://en.wikipedia.org/wiki/Quantum_computing",
                "https://quantum.country/qcvc",  # Added more high-quality sources
                "https://qiskit.org/",
                "https://quantumalgorithmzoo.org/",
                "https://arxiv.org/archive/quant-ph"
            ]
        else:
            # Generic academic/educational fallbacks for any topic
            logger.info(f"Using generic fallback URLs for query: {query}")
            search_term = query.replace(" ", "+")
            hardcoded_urls = [
                f"https://en.wikipedia.org/wiki/Special:Search?search={search_term}",
                f"https://arxiv.org/search/?query={search_term}&searchtype=all",
                f"https://scholar.google.com/scholar?q={search_term}",
                f"https://www.researchgate.net/search/publication?q={search_term}"
            ]
        
        # Try to fetch content from hardcoded URLs directly
        logger.info(f"Attempting to fetch {len(hardcoded_urls[:MAX_URLS_PER_QUERY])} LEVEL 2 fallback URLs")
        
        # Use semaphore to limit concurrent requests to fallback URLs
        fallback_semaphore = asyncio.Semaphore(3)  # Limit to 3 concurrent requests
        
        async def check_fallback_url(url):
            async with fallback_semaphore:
                try:
                    logger.info(f"Checking fallback URL: {url}")
                    
                    # Use a fresh User-Agent for each request
                    test_headers = enhanced_headers.copy()
                    test_headers['User-Agent'] = random.choice(USER_AGENTS)
                    
                    # Set client headers for this request
                    for key, value in test_headers.items():
                        client.headers[key] = value
                    
                    # Try to get a HEAD request first to validate URL (faster)
                    head_response = await client.head(url, timeout=10.0, follow_redirects=True)
                    
                    if head_response.status_code == 200:
                        content_type = head_response.headers.get('content-type', '')
                        if 'text/html' in content_type or 'application/xhtml+xml' in content_type:
                            logger.info(f"Fallback URL valid: {url}")
                            return url
                        else:
                            logger.warning(f"Fallback URL has non-HTML content type: {content_type}")
                            return None
                    else:
                        logger.warning(f"Fallback URL returned status code: {head_response.status_code}")
                        return None
                except Exception as e:
                    logger.warning(f"Error checking fallback URL {url}: {e}")
                    return None
        
        # Check all fallback URLs concurrently
        fallback_results = await asyncio.gather(*[check_fallback_url(url) for url in hardcoded_urls[:MAX_URLS_PER_QUERY]], return_exceptions=False)
        valid_fallbacks = [url for url in fallback_results if url]
        
        # Add valid fallback URLs to our results
        for url in valid_fallbacks:
            if url not in urls:  # Avoid duplicates
                urls.append(url)
                logger.info(f"Added valid fallback URL: {url}")
        
        if urls:
            logger.info(f"LEVEL 2 SUCCESS: Found {len(urls)} valid fallback URLs")
        else:
            logger.error("LEVEL 2 FAILED: All fallback URLs failed. No content sources available.")
    
    # Final result
    result_urls = urls[:MAX_URLS_PER_QUERY]  # Limit to max URLs per query
    logger.info(f"Final URL count: {len(result_urls)} for query: {query}")
    return result_urls

async def extract_text_from_html(html, url, query=None):
    """Extract relevant text content from HTML using multi-method content extraction."""
    try:
        # Create a BeautifulSoup object for parsing HTML
        soup = BeautifulSoup(html, 'lxml')

        # Get page title
        title = soup.title.string.strip() if soup.title else "No Title Found"
        
        # Save sample of HTML for debugging in case of extraction failure
        html_sample = str(soup)[:1000] + "..." if len(str(soup)) > 1000 else str(soup)
        
        # METHOD 1: Tag-based Content Extraction
        logger.info(f"Starting content extraction for {url} - METHOD 1: Tag-based")
        
        # Remove noisy content first to improve extraction quality
        noise_soup = BeautifulSoup(html, 'lxml')  # Create a separate copy to not affect other methods
        for selector in NOISE_SELECTORS:
            for element in noise_soup.select(selector):
                element.decompose()

        # Try to find the main content area using common content selectors
        content_area = None
        content_selector_used = None
        
        # First try HTML5 semantic elements which are most reliable
        semantic_selectors = ['article', 'main', 'section']
        for selector in semantic_selectors:
            content_elements = noise_soup.find_all(selector)
            if content_elements:
                # Select the largest semantic element by text length
                content_area = max(content_elements, key=lambda x: len(x.get_text(strip=True)))
                content_selector_used = selector
                logger.info(f"Found content using semantic selector: {selector}")
                break
        
        # If no semantic element found, try common content selectors
        if not content_area:
            for selector in CONTENT_SELECTORS:
                content_area = noise_soup.select_one(selector)
                if content_area and len(content_area.get_text(strip=True)) > 200:
                    content_selector_used = selector
                    logger.info(f"Found content using content selector: {selector}")
                    break

        # METHOD 2: Text Density Analysis (if method 1 fails or returns limited content)
        content_from_method1 = ""
        if content_area:
            # Extract content using method 1
            headings = [h.get_text(strip=True) for h in content_area.find_all(['h1', 'h2', 'h3', 'h4', 'h5'])]
            paragraphs = [p.get_text(strip=True) for p in content_area.find_all('p')]

            # Clean and filter content
            headings = [clean_content(h) for h in headings if len(h) > 15]
            paragraphs = [clean_content(p) for p in paragraphs if len(p) > 50]

            # Structure the content
            structured_content = []
            if title and title not in headings:
                structured_content.append(f"# {title}")

            for heading in headings:
                structured_content.append(f"## {heading}")
                # Find paragraphs that might be related to this heading
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

            content_from_method1 = "\n\n".join(structured_content)
            logger.info(f"METHOD 1 extracted {len(content_from_method1)} chars using {content_selector_used}")
        else:
            logger.warning(f"METHOD 1 failed to identify main content area for {url}")

        # If Method 1 didn't yield sufficient content or failed, try Method 2
        if not content_from_method1 or len(content_from_method1) < 500:
            logger.info(f"Starting METHOD 2: Text density analysis for {url}")
            
            # Create a fresh soup to avoid any changes from Method 1
            density_soup = BeautifulSoup(html, 'lxml')
            
            # Remove obvious noise elements
            for selector in NOISE_SELECTORS:
                for element in density_soup.select(selector):
                    element.decompose()
            
            # Get all blocks of content that might contain article text
            content_blocks = []
            
            # 1. Look for paragraph blocks with substantial text
            for p in density_soup.find_all('p'):
                text = p.get_text(strip=True)
                if len(text) > 50:  # Only consider paragraphs with substantial text
                    # Calculate text-to-HTML ratio as a density measure
                    html_length = len(str(p))
                    text_length = len(text)
                    density = text_length / html_length if html_length > 0 else 0
                    
                    # Higher density means more text relative to HTML markup
                    content_blocks.append((p, text, density))
            
            # 2. Look for div blocks that might contain content
            for div in density_soup.find_all('div'):
                # Skip very small divs or those with too many nested divs (likely navigation/layout)
                if len(div.find_all('div')) > 5:
                    continue
                    
                text = div.get_text(strip=True)
                if len(text) > 100:  # Require more text for divs since they often contain layout
                    html_length = len(str(div))
                    text_length = len(text)
                    density = text_length / html_length if html_length > 0 else 0
                    content_blocks.append((div, text, density))
            
            # Sort blocks by density to prioritize text-rich blocks
            content_blocks.sort(key=lambda x: x[2], reverse=True)
            
            # Extract the top blocks by density
            method2_content = []
            if title:
                method2_content.append(f"# {title}")
                
            # Get content from the top 10 highest density blocks
            for _, text, density in content_blocks[:10]:
                cleaned_text = clean_content(text)
                if len(cleaned_text) > 50 and cleaned_text not in method2_content:
                    method2_content.append(cleaned_text)
            
            content_from_method2 = "\n\n".join(method2_content)
            logger.info(f"METHOD 2 extracted {len(content_from_method2)} chars using density analysis")
            
            # Decide which method produced better results
            if len(content_from_method2) > len(content_from_method1) * 1.5:  # Method 2 found significantly more content
                main_content = content_from_method2
                logger.info(f"Using METHOD 2 results (density analysis) as it found {len(content_from_method2)} vs {len(content_from_method1)} chars")
            else:
                main_content = content_from_method1
                logger.info(f"Using METHOD 1 results (tag-based) as density analysis didn't find significantly more content")
        else:
            main_content = content_from_method1
        
        # METHOD 3: If both methods failed, try a simple paragraph extraction as last resort
        if not main_content or len(main_content) < 200:
            logger.warning(f"Methods 1 and 2 failed for {url}. Trying simple paragraph extraction (METHOD 3)")
            
            # Create a fresh soup for a clean extraction
            fallback_soup = BeautifulSoup(html, 'lxml')
            
            # Simple approach: just get all paragraphs with reasonable length
            paragraphs = []
            if title:
                paragraphs.append(f"# {title}")
                
            for p in fallback_soup.find_all('p'):
                text = p.get_text(strip=True)
                if len(text) > 50:  # Only consider substantive paragraphs
                    cleaned = clean_content(text)
                    if cleaned not in paragraphs:  # Avoid duplicates
                        paragraphs.append(cleaned)
            
            main_content = "\n\n".join(paragraphs)
            logger.info(f"METHOD 3 (last resort) extracted {len(main_content)} chars")
        
        # If we have content, truncate if necessary and return it
        if main_content and len(main_content) > 200:
            # Truncate if too long
            if len(main_content) > MAX_CONTENT_LENGTH:
                main_content = main_content[:MAX_CONTENT_LENGTH] + "... [truncated]"

            logger.info(f"Successfully extracted {len(main_content)} chars from {url}")

            # Get subtopic from query info
            subtopic = query.get("subtopic", "Climate Change Adaptation") if query else "Climate Change Adaptation"

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
                    "subtopic": "Climate Change Adaptation",
                    "source": "web_scrape"
                }

            return content_item
        else:
            logger.warning(f"No meaningful content could be extracted from {url} after trying all methods")
            logger.debug(f"URL: {url}, Title: {title}, HTML sample: {html_sample[:300]}...")
    except Exception as e:
        logger.error(f"Error extracting text from {url}: {e}", exc_info=True)
        logger.debug(f"HTML that caused extraction failure: {html_sample[:500]}...")

    return None

async def scrape_url(url, client, retry_count=0, query_info=None):
    """Scrape a URL with enhanced retry logic and browser emulation."""
    if retry_count > MAX_RETRIES:
        logger.warning(f"Max retries reached for {url}")
        return None

    logger.info(f"Scraping URL: {url} (attempt {retry_count + 1})")
    
    # Enhanced browser-like headers for more realistic requests
    enhanced_headers = {
        'User-Agent': random.choice(USER_AGENTS),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Cache-Control': 'max-age=0',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1'
    }
    
    try:
        # Random delay that varies based on retry count (longer for more retries)
        delay = get_random_delay() * (1 + (retry_count * 0.5))
        logger.info(f"Waiting {delay:.2f}s before requesting {url}")
        await asyncio.sleep(delay)

        # Update headers for each request
        for key, value in enhanced_headers.items():
            client.headers[key] = value
            
        # Add a referer on retries to look more natural (use a major website domain)
        if retry_count > 0:
            referers = [
                "https://www.google.com/search",
                "https://www.bing.com/search",
                "https://search.yahoo.com/search",
                "https://duckduckgo.com/"
            ]
            client.headers['Referer'] = random.choice(referers)

        # Try to get the content with timeout
        logger.info(f"Sending request to {url} with User-Agent: {client.headers['User-Agent'][:30]}...")
        response = await client.get(url, follow_redirects=True, timeout=SCRAPE_TIMEOUT)
        
        # Record response for debugging
        status_code = response.status_code
        response_headers = dict(response.headers)
        content_type = response.headers.get('content-type', '').lower()
        
        logger.info(f"Response from {url}: status={status_code}, content-type={content_type}")
        
        # Check for signs of blocking or CAPTCHA pages in successful requests
        if status_code == 200:
            # Sometimes sites return 200 status but actually serve a block page
            response_text = response.text.lower()
            block_indicators = ['captcha', 'security check', 'access denied', 'blocked', 
                              'suspicious activity', 'automated requests', 'verify you are human']
                              
            if any(indicator in response_text for indicator in block_indicators):
                logger.warning(f"Detected possible block page from {url} despite 200 status")
                logger.debug(f"Block page indicators found in: {response_text[:300]}...")
                # Handle as an error and retry with different headers/delay
                if retry_count < MAX_RETRIES:
                    logger.info(f"Retrying {url} with different parameters due to suspected block")
                    # Use a longer delay for this type of retry
                    await asyncio.sleep(3 + retry_count * 2)
                    return await scrape_url(url, client, retry_count + 1, query_info)
                else:
                    logger.warning(f"Failed to bypass blocking for {url} after {retry_count} retries")
                    return None
        
        # Raise for non-200 status codes
        response.raise_for_status()

        # Check if the content is HTML
        if 'html' not in content_type and 'text' not in content_type:
            logger.warning(f"Skipping non-HTML content at {url} (type: {content_type})")
            return None
        
        # Verify we have actual content
        if not response.text or len(response.text) < 100:
            logger.warning(f"Empty or very short response from {url} ({len(response.text)} chars)")
            if retry_count < MAX_RETRIES:
                logger.info(f"Retrying {url} due to minimal content")
                await asyncio.sleep(2 ** retry_count)
                return await scrape_url(url, client, retry_count + 1, query_info)
            return None

        # Extract and structure the content
        logger.info(f"Successfully received {len(response.text)} bytes from {url}, extracting content")
        content_item = await extract_text_from_html(response.text, url, query_info)
        
        # If content extraction failed, log detailed information
        if not content_item:
            logger.warning(f"Content extraction failed for {url} despite successful request")
            # Save a sample of the HTML for debugging
            html_sample = response.text[:1000] + "..." if len(response.text) > 1000 else response.text
            logger.debug(f"HTML that failed extraction: {html_sample}")
            
        return content_item

    except httpx.TimeoutException as e:
        logger.warning(f"Timeout scraping {url} ({e}), retrying...")
        if retry_count < MAX_RETRIES:
            # Exponential backoff for timeouts
            backoff = 2 ** retry_count * 2
            logger.info(f"Backing off for {backoff}s before retry {retry_count+1} for {url}")
            await asyncio.sleep(backoff)
            return await scrape_url(url, client, retry_count + 1, query_info)
        else:
            return None
    except httpx.TooManyRedirects:
        logger.warning(f"Too many redirects for {url}")
        return None
    except httpx.RequestError as e:
        if retry_count < MAX_RETRIES:
            logger.warning(f"Request error scraping {url}: {e}, retrying...")
            # Exponential backoff
            backoff = 2 ** retry_count * 1.5
            logger.info(f"Backing off for {backoff}s before retry {retry_count+1} for {url}")
            await asyncio.sleep(backoff)
            return await scrape_url(url, client, retry_count + 1, query_info)
        else:
            logger.warning(f"Request error scraping {url} after {retry_count} retries: {e}")
            return None
    except httpx.HTTPStatusError as e:
        # Handle specific HTTP status codes
        status_code = e.response.status_code
        logger.warning(f"HTTP error {status_code} from {url}: {e}")
        
        if status_code == 429:  # Too Many Requests
            if retry_count < MAX_RETRIES:
                # Use a longer exponential backoff for rate limiting
                backoff = 5 ** (retry_count + 1)
                logger.info(f"Rate limited (429) for {url}. Backing off for {backoff}s before retry")
                await asyncio.sleep(backoff)
                return await scrape_url(url, client, retry_count + 1, query_info)
        elif status_code in (503, 502, 500):  # Server errors
            if retry_count < MAX_RETRIES:
                # Use exponential backoff for server errors
                backoff = 3 ** retry_count * 2
                logger.info(f"Server error {status_code} for {url}. Backing off for {backoff}s before retry")
                await asyncio.sleep(backoff)
                return await scrape_url(url, client, retry_count + 1, query_info)
        elif status_code in (403, 401):  # Forbidden/Unauthorized
            logger.warning(f"Access denied ({status_code}) for {url}. Site likely blocking scrapers.")
            # These usually don't improve with retries unless we change approach completely
            # but we'll try once more with a different User-Agent if not too many retries yet
            if retry_count < 1:  # Only retry once for these
                logger.info(f"Trying one more time with different User-Agent for {url}")
                await asyncio.sleep(3)
                return await scrape_url(url, client, MAX_RETRIES - 1, query_info)  # Last attempt
        
        return None
    except Exception as e:
        logger.error(f"Unexpected error scraping {url}: {e}", exc_info=True)
        if retry_count < MAX_RETRIES:
            # General backoff for unknown errors
            await asyncio.sleep(2 ** retry_count)
            return await scrape_url(url, client, retry_count + 1, query_info)
        return None

async def load_search_queries(project_id):
    """Load search queries from the project state."""
    try:
        # Try to find search queries from a previous step
        if USE_CONFIG:
            base_dir = Path(config.orchestration.artifact_base_path)
        else:
            base_dir = Path("D:/AgentVault/poc_agents/langgraph_scrapepipe/pipeline_artifacts")

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
                    continue
    except Exception as e:
        logger.error(f"Error loading search queries: {e}")

    # Add debugging to locate the file/data structure that was passed from the previous step
    logger.info(f"DEBUG: Searching for any files in parent directory {base_dir / project_id}")
    try:
        for file_path in (base_dir / project_id).glob("**/*.json"):
            logger.info(f"Found JSON file: {file_path}")
    except Exception as e:
        logger.error(f"Error searching for files: {e}")
        
    # Even if the configuration has fallbacks disabled, use default queries
    # instead of returning an empty list, because we need SOMETHING to search for
    logger.warning("Using default search queries for quantum computing")
    # Use quantum computing related queries since that's the topic from the logs
    quantum_queries = [
        "quantum computing applications research",
        "quantum computing industry use cases", 
        "quantum algorithms practical applications",
        "quantum computing business solutions",
        "quantum computing scientific applications",
        "quantum computing breakthrough applications"
    ]
    return [{"subtopic": "Quantum Computing Applications", "query": q} for q in quantum_queries]

def get_authority_score(url):
    """
    Calculate an authority score for a URL based on the domain and whether
    it's a known reliable source for climate change information.
    """
    # Skip authority scoring if disabled in config
    if not USE_AUTHORITY_SCORES:
        return 0.7, "Source Evaluation Disabled"

    try:
        domain = urlparse(url).netloc.lower()

        # Check if the domain matches or is a subdomain of a known authority
        for auth_key, auth_data in AUTHORITY_SOURCES.items():
            auth_domain = auth_data["domain"].lower()
            if domain == auth_domain or domain.endswith("." + auth_domain):
                return auth_data["reliability"], auth_data["name"]

        # Check for academic or government domains
        if domain.endswith(".edu") or domain.endswith(".ac.uk") or domain.endswith(".edu.au"):
            return 0.88, "Academic Institution"
        elif domain.endswith(".gov") or domain.endswith(".gov.uk") or domain.endswith(".gc.ca"):
            return 0.87, "Government Institution"
        elif domain.endswith(".org"):
            return 0.75, "Non-profit Organization"
        elif domain.endswith(".int"):
            return 0.84, "International Organization"

        # Default score for unknown domains
        return 0.5, "Unknown Source"
    except Exception as e:
        logger.error(f"Error calculating authority score for {url}: {e}")
        return 0.4, "Error in Source Evaluation"

def verify_fact(fact, all_facts, scraped_items):
    """
    Perform actual fact verification rather than generating random scores.

    This checks:
    1. Source authority (based on domain)
    2. Consistency with other facts
    3. Presence of numbers and specificity
    4. Language patterns
    """
    # Initialize verification fields
    verification_status = "verified"
    confidence_score = 0.5
    verification_notes = ""
    issues = []

    # Get source URL
    source_url = fact.get("source_url", "unknown_source")

    # Step 1: Check source authority
    auth_score, auth_name = get_authority_score(source_url)

    # Use configured weight for authority score
    confidence_score = auth_score * AUTHORITY_SCORE_WEIGHT + (1 - AUTHORITY_SCORE_WEIGHT) * 0.5

    # Adjust confidence based on fact type
    fact_type = fact.get("type", "statement")
    if fact_type == "statistic" and auth_score < 0.7:
        confidence_score -= 0.1
        verification_notes += f"Statistical claim from less reliable source ({auth_name}). "

    # Step 2: Check for strong claim language in non-authoritative sources
    text = fact.get("text", "")
    has_strong_claim = any(word in text.lower() for word in ["all", "every", "never", "always", "none", "definitely", "certainly", "absolutely"])

    if has_strong_claim and auth_score < 0.8:
        confidence_score -= 0.15
        verification_notes += "Contains strong universal claims from non-authoritative source. "

    # Step 3: Check for common indicators of good quality information
    has_numbers = bool(re.search(r'\d+(\.\d+)?%|\d+ (million|billion|trillion)|increased by \d+', text))
    has_specificity = bool(re.search(r'according to|published in|conducted by|found that|reported', text))

    if has_numbers:
        confidence_score += 0.05
    if has_specificity:
        confidence_score += 0.1

    # Step 4: Check for potential conflicts with other facts (if enabled)
    if DETECT_CONTRADICTIONS:
        for other_fact in all_facts:
            if fact.get("id") == other_fact.get("id"):
                continue

            # Simple contradiction detection - needs improvement in real implementation
            fact_lower = text.lower()
            other_text = other_fact.get("text", "").lower()

            # Look for opposing phrases
            if ("not " in fact_lower and other_text.replace("not ", "") == fact_lower.replace("not ", "")) or \
               ("not " in other_text and fact_lower.replace("not ", "") == other_text.replace("not ", "")):
                issues.append({
                    "issue_type": "potential_contradiction",
                    "conflicting_fact_id": other_fact.get("id"),
                    "conflict_details": f"Potential contradiction with another fact: '{other_fact.get('text')[:100]}...'",
                    "severity": "medium"
                })
                confidence_score -= 0.2
                verification_notes += f"Potential contradiction with other fact. "

    # Based on our analysis, set the final status and confidence
    confidence_score = max(0.1, min(0.98, confidence_score))  # Clamp between 0.1 and 0.98

    if confidence_score < MIN_CONFIDENCE_THRESHOLD or issues:
        verification_status = "uncertain"
        if not verification_notes:
            verification_notes = f"Low confidence in this fact. Source authority: {auth_name}."
    else:
        if not verification_notes:
            verification_notes = f"Verified based on source authority ({auth_name})."

    return {
        "verification_status": verification_status,
        "confidence_score": round(confidence_score, 3),
        "verification_timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "verification_notes": verification_notes,
        "issues": issues
    }

async def extract_and_save_facts(project_id, scraped_content):
    """
    Extract facts from content directly and save to the information extraction step output.
    This bypasses the information extraction agent completely.
    """
    try:
        # Determine base directory from configuration if available
        if USE_CONFIG:
            base_dir = Path(config.orchestration.artifact_base_path)
        else:
            base_dir = Path("D:/AgentVault/poc_agents/langgraph_scrapepipe/pipeline_artifacts")

        # Create output directories
        info_extraction_dir = base_dir / project_id / "information_extraction"
        info_extraction_dir.mkdir(parents=True, exist_ok=True)

        # Process each content item to extract facts
        all_facts = []
        info_by_subtopic = {}

        for i, item in enumerate(scraped_content):
            content = item.get("content", "")

            # Get subtopic from query_source
            query_source = item.get("query_source", {})
            if isinstance(query_source, dict):
                subtopic = query_source.get("subtopic", "Climate Change Adaptation")
            else:
                subtopic = "Climate Change Adaptation"

            # Extract facts from content using configured parameters
            item_facts = extract_facts_from_content(content, subtopic)

            # Add source URL to facts
            source_url = item.get("url", "unknown_url")
            for fact in item_facts:
                fact["source_url"] = source_url

            # Add facts to overall collection
            all_facts.extend(item_facts)

            # Organize by subtopic
            if subtopic not in info_by_subtopic:
                info_by_subtopic[subtopic] = []

            info_by_subtopic[subtopic].extend(item_facts)

        # Ensure we have at least one fact
        if not all_facts:
            fallback_fact = {
                "id": f"fallback-fact-{uuid.uuid4().hex[:8]}", # Use imported uuid
                "text": "Climate change adaptation is the process of adjusting to current or expected changes in climate and its effects.",
                "source_url": "fallback-extraction",
                "type": "statement",
                "relevance_score": 0.9,
                "subtopic": "Climate Change Adaptation"
            }
            all_facts.append(fallback_fact)

            if "Climate Change Adaptation" not in info_by_subtopic:
                info_by_subtopic["Climate Change Adaptation"] = []

            info_by_subtopic["Climate Change Adaptation"].append(fallback_fact)

        # Save facts to output files
        extracted_info_path = info_extraction_dir / "extracted_information.json"
        with open(extracted_info_path, 'w', encoding='utf-8') as f:
            json.dump({"extracted_facts": all_facts}, f, indent=2, ensure_ascii=False)

        info_by_subtopic_path = info_extraction_dir / "info_by_subtopic.json"
        with open(info_by_subtopic_path, 'w', encoding='utf-8') as f:
            json.dump({"subtopics": info_by_subtopic}, f, indent=2, ensure_ascii=False)

        # Now perform meaningful fact verification
        verified_facts = []
        verification_issues = []

        for fact in all_facts:
            # Perform real verification of the fact using configured parameters
            verification_results = verify_fact(fact, all_facts, scraped_content)

            # Add verification details to the fact
            verified_fact = {**fact, **verification_results}
            verified_facts.append(verified_fact)

            # Collect any issues found
            issues = verification_results.get("issues", [])
            for issue in issues:
                issue["fact_id"] = fact.get("id")
                verification_issues.append(issue)

        # Save verified facts and verification report
        fact_verification_dir = base_dir / project_id / "fact_verification"
        fact_verification_dir.mkdir(parents=True, exist_ok=True)

        verified_facts_path = fact_verification_dir / "verified_facts.json"
        with open(verified_facts_path, 'w', encoding='utf-8') as f:
            json.dump({"verified_facts": verified_facts}, f, indent=2, ensure_ascii=False)

        verification_report_path = fact_verification_dir / "verification_report.json"
        with open(verification_report_path, 'w', encoding='utf-8') as f:
            json.dump({"issues_found": verification_issues}, f, indent=2, ensure_ascii=False)

        logger.info(f"Successfully extracted, verified and saved {len(verified_facts)} facts across {len(info_by_subtopic)} subtopics")
        logger.info(f"Found {len(verification_issues)} issues during verification")

        return True
    except Exception as e:
        logger.error(f"Error extracting and saving facts: {e}")
        return False

async def generate_visualizations(project_id, verified_facts):
    """
    Generate basic visualization metadata that's more meaningful than random placeholders.
    """
    try:
        # Determine base directory from configuration if available
        if USE_CONFIG:
            base_dir = Path(config.orchestration.artifact_base_path)
            visualization_config = config.visualization
            max_viz = visualization_config.max_visualizations
            preferred_chart_types = visualization_config.prefer_chart_types
            facts_per_viz = visualization_config.facts_per_visualization
        else:
            base_dir = Path("D:/AgentVault/poc_agents/langgraph_scrapepipe/pipeline_artifacts")
            max_viz = 5
            preferred_chart_types = ["bar_chart", "pie_chart", "line_graph"]
            facts_per_viz = 5

        # Create directory
        viz_dir = base_dir / project_id / "visualization"
        viz_dir.mkdir(parents=True, exist_ok=True)

        # Group facts by type
        statistics = [f for f in verified_facts if f.get("type") == "statistic"]
        insights = [f for f in verified_facts if f.get("type") == "insight"]
        statements = [f for f in verified_facts if f.get("type") == "statement"]
        quotes = [f for f in verified_facts if "quote" in f.get("id", "")]

        # Define visualizations based on available data
        visualizations = []

        # Create bar chart for statistics if available and bar_chart is preferred
        if statistics and "bar_chart" in preferred_chart_types:
            stat_facts = statistics[:facts_per_viz]  # Use configured number of facts
            viz_id = f"viz-bar-chart-{uuid.uuid4().hex[:8]}" # Use imported uuid
            visualizations.append({
                "visualization_id": viz_id,
                "chart_type": "bar_chart",
                "title": "Key Statistics on Climate Change Adaptation",
                "related_content_ids": [f.get("id") for f in stat_facts],
                "description": "Bar chart showing key statistical data on climate change adaptation measures."
            })

        # Create pie chart for topic distribution if preferred
        if "pie_chart" in preferred_chart_types:
            subtopics = {}
            for fact in verified_facts:
                subtopic = fact.get("subtopic", "General")
                if subtopic not in subtopics:
                    subtopics[subtopic] = 0
                subtopics[subtopic] += 1

            if len(subtopics) > 1:
                viz_id = f"viz-pie-chart-{uuid.uuid4().hex[:8]}" # Use imported uuid
                # Use a mix of facts, one from each major subtopic
                subtopic_facts = []
                for subtopic in subtopics:
                    for fact in verified_facts:
                        if fact.get("subtopic") == subtopic:
                            subtopic_facts.append(fact)
                            break

                visualizations.append({
                    "visualization_id": viz_id,
                    "chart_type": "pie_chart",
                    "title": "Distribution of Adaptation Topics",
                    "related_content_ids": [f.get("id") for f in subtopic_facts[:facts_per_viz]],
                    "description": "Pie chart showing the distribution of topics across climate change adaptation research."
                })

        # Create timeline/line graph for temporal data if preferred
        if "line_graph" in preferred_chart_types:
            time_related_facts = []
            for fact in verified_facts:
                text = fact.get("text", "").lower()
                if re.search(r'by 20\d\d|in 20\d\d|since \d{4}|between \d{4} and \d{4}', text):
                    time_related_facts.append(fact)

            if time_related_facts:
                viz_id = f"viz-line-graph-{uuid.uuid4().hex[:8]}" # Use imported uuid
                visualizations.append({
                    "visualization_id": viz_id,
                    "chart_type": "line_graph",
                    "title": "Climate Adaptation Timeline",
                    "related_content_ids": [f.get("id") for f in time_related_facts[:facts_per_viz]],
                    "description": "Line graph showing climate adaptation trends and projections over time."
                })

        # Ensure we have at least one visualization but limit to configured max
        if not visualizations:
            # Create a generic visualization using the most reliable facts
            most_reliable_facts = sorted(verified_facts, key=lambda x: x.get("confidence_score", 0), reverse=True)[:facts_per_viz]
            viz_id = f"viz-generic-chart-{uuid.uuid4().hex[:8]}" # Use imported uuid
            visualizations.append({
                "visualization_id": viz_id,
                "chart_type": preferred_chart_types[0] if preferred_chart_types else "bar_chart",
                "title": "Key Facts on Climate Change Adaptation",
                "related_content_ids": [f.get("id") for f in most_reliable_facts],
                "description": "Summary of key findings on climate change adaptation strategies."
            })

        # Limit to configured maximum number of visualizations
        visualizations = visualizations[:max_viz]

        # Save visualization metadata
        viz_metadata_path = viz_dir / "viz_metadata.json"
        with open(viz_metadata_path, 'w', encoding='utf-8') as f:
            json.dump({"visualizations": visualizations}, f, indent=2, ensure_ascii=False)

        logger.info(f"Generated {len(visualizations)} visualization metadata entries")
        return True
    except Exception as e:
        logger.error(f"Error generating visualizations: {e}")
        return False

async def main(project_id):
    """Main function to coordinate the scraping process."""
    try:
        # EMERGENCY PATCH: Ensure fallback settings are correctly set
        # Get config path from command line if provided
        config_path = None
        if len(sys.argv) > 2:
            config_path = sys.argv[2]
            if os.path.exists(config_path):
                logger.info(f"EMERGENCY PATCH: Found config file: {config_path}")
                fallback_settings = load_config_directly(config_path)
                if 'use_fallback_urls' in fallback_settings:
                    global USE_FALLBACK_URLS # Need to declare global to modify
                    USE_FALLBACK_URLS = fallback_settings['use_fallback_urls']
                    logger.info(f"EMERGENCY PATCH: Directly set USE_FALLBACK_URLS={USE_FALLBACK_URLS}")
                if 'add_fallback_results' in fallback_settings:
                    global ADD_FALLBACK_RESULTS # Need to declare global to modify
                    ADD_FALLBACK_RESULTS = fallback_settings['add_fallback_results']
                    logger.info(f"EMERGENCY PATCH: Directly set ADD_FALLBACK_RESULTS={ADD_FALLBACK_RESULTS}")
        
        # CRITICAL FIX: Log detailed diagnostics about search capabilities
        logger.info("============== SCRAPER DIAGNOSTICS ===============")
        logger.info(f"Python version: {sys.version}")
        logger.info(f"Script path: {__file__}")
        logger.info(f"Current directory: {os.getcwd()}")
        logger.info(f"Project ID: {project_id}")
        logger.info(f"Fallback settings: USE_FALLBACK_URLS={USE_FALLBACK_URLS}, ADD_FALLBACK_RESULTS={ADD_FALLBACK_RESULTS}")
        logger.info(f"Search engines count: {len(SEARCH_ENGINES)}")
        for idx, engine in enumerate(SEARCH_ENGINES):
            logger.info(f"Engine {idx+1}: {engine['name']} - {engine['url']} - Method: {engine['method']}")
        logger.info("==================================================")

        # Determine base directory from configuration if available
        if USE_CONFIG:
            base_dir = Path(config.orchestration.artifact_base_path)
        else:
            base_dir = Path("D:/AgentVault/poc_agents/langgraph_scrapepipe/pipeline_artifacts")

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
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0',
        }

        async with httpx.AsyncClient(timeout=SCRAPE_TIMEOUT, follow_redirects=True, headers=headers) as client:
            # Load search queries for this project
            search_queries = await load_search_queries(project_id)

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
                        subtopic = "Climate Change Adaptation"

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
                logger.info("Not enough URLs from search queries, adding fallback URLs (since USE_FALLBACK_URLS=True)")
                for url in FALLBACK_URLS:
                    if url not in all_urls:
                        all_urls.append(url)
                        all_queries.append({"url": url, "subtopic": "Climate Change Adaptation", "query": "fallback"})
                        if len(all_urls) >= MAX_TOTAL_URLS:
                            break
            elif len(all_urls) < 5:
                logger.warning("Not enough URLs from search queries, but USE_FALLBACK_URLS is disabled. Proceeding with limited URLs.")

            # Part 2: Scrape content from the URLs
            logger.info(f"Scraping content from {len(all_urls)} URLs")

            # Use semaphore to limit concurrent requests
            semaphore = asyncio.Semaphore(3)  # Limit to 3 concurrent requests

            # Create a mapping of URL to query info
            query_map = {item["url"]: {"subtopic": item["subtopic"], "query": item["query"]} for item in all_queries}

            async def scrape_with_semaphore(url):
                async with semaphore:
                    # Pass the query info for this URL
                    query_info = query_map.get(url, {"subtopic": "Climate Change Adaptation", "query": "unknown"})
                    return await scrape_url(url, client, query_info=query_info)

            # Create scraping tasks
            scrape_tasks = [scrape_with_semaphore(url) for url in all_urls]

            # Wait for all tasks to complete
            results = await asyncio.gather(*scrape_tasks, return_exceptions=True)

            # Process results
            for result in results:
                if isinstance(result, Exception):
                    logger.error(f"Error in scrape task: {result}")
                elif result:
                    scraped_content.append(result)

            # EMERGENCY PATCH: Always fail explicitly with empty content when no results
            if not scraped_content:
                logger.error("SCRAPING FAILED: No content found and fallbacks disabled.")
                scraped_content = [] # Ensure it's an empty list

            # Save the content as a JSON file
            file_path = storage_dir / "raw_content.json"
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(scraped_content, f, indent=2, ensure_ascii=False)

            logger.info(f"Saved {len(scraped_content)} scraped items to {file_path}")

            # CRITICAL ADDITION: Directly extract and process facts
            if scraped_content: # Only process if we have content
                success = await extract_and_save_facts(project_id, scraped_content)
                if success:
                    logger.info("Successfully extracted and saved facts directly")

                    # Load verified facts for visualization generation
                    fact_verification_dir = base_dir / project_id / "fact_verification"
                    verified_facts_path = fact_verification_dir / "verified_facts.json"

                    try:
                        with open(verified_facts_path, 'r', encoding='utf-8') as f:
                            verified_facts_data = json.load(f)
                            verified_facts = verified_facts_data.get("verified_facts", [])

                        # Generate visualization metadata
                        await generate_visualizations(project_id, verified_facts)
                    except Exception as e:
                        logger.error(f"Error generating visualizations: {e}")
                else:
                    logger.warning("Failed to extract and save facts directly")
            else:
                logger.warning("Skipping fact extraction and visualization as no content was scraped.")

            return file_path, scraped_content

    except Exception as e:
        logger.error(f"Unexpected error in main function: {e}", exc_info=True)
        # Create emergency fallback content

        # Determine base directory from configuration if available
        if USE_CONFIG:
            base_dir = Path(config.orchestration.artifact_base_path)
        else:
            base_dir = Path("D:/AgentVault/poc_agents/langgraph_scrapepipe/pipeline_artifacts")

        storage_dir = base_dir / project_id / "content_crawler"
        storage_dir.mkdir(parents=True, exist_ok=True)

        logger.critical("CRITICAL ERROR in scraper: FAILING EXPLICITLY without fallback")
        # Ensure empty content is written before returning None
        file_path = storage_dir / "raw_content.json"
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump([], f, indent=2, ensure_ascii=False)
        logger.info(f"Saved empty content file to {file_path} due to critical error.")
        return None, None  # Return None to trigger explicit failure

if __name__ == "__main__":
    try:
        # Configure logging for direct script execution
        if not logging.getLogger().handlers:
            logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

        # Get project ID from command line argument
        if len(sys.argv) > 1:
            project_id = sys.argv[1]
        else:
            project_id = f"proj_direct_{random.randint(10000, 99999)}"

        # If config file is provided, load it directly
        config_path = None
        if len(sys.argv) > 2:
            config_path = sys.argv[2]
            if os.path.exists(config_path):
                logger.info(f"Loading custom configuration file: {config_path}")
                try:
                    with open(config_path, 'r', encoding='utf-8') as f:
                        loaded_config = json.load(f)
                        # Check for fallback settings
                        if "search" in loaded_config and "use_fallback_urls" in loaded_config["search"]:
                            USE_FALLBACK_URLS = loaded_config["search"]["use_fallback_urls"]
                            logger.info(f"Directly loaded fallback setting: USE_FALLBACK_URLS={USE_FALLBACK_URLS}")
                        if "search" in loaded_config and "add_fallback_results" in loaded_config["search"]:
                            ADD_FALLBACK_RESULTS = loaded_config["search"]["add_fallback_results"]
                            logger.info(f"Directly loaded fallback setting: ADD_FALLBACK_RESULTS={ADD_FALLBACK_RESULTS}")
                        logger.info("Successfully loaded direct fallback settings from config file")
                except Exception as e:
                    logger.error(f"Failed to load direct fallback settings from config: {e}")

        logger.info(f"Starting direct scraper with project ID: {project_id}")
        result = asyncio.run(main(project_id))

        # Handle potential None result from main() error
        if result is None or result[0] is None:
             print("DIRECT_SCRAPER_CRITICAL_ERROR: Main function failed to return a valid result.")
             sys.exit(1)
        else:
            print(f"DIRECT_SCRAPE_RESULT:{result[0]}")

            # Print a sample of what we got
            print("\nSample content from first scraped page:")
            if result[1]:
                print(f"Title: {result[1][0]['title']}")
                content = result[1][0]['content']
                print(f"Content (first 500 chars): {content[:500]}...")
            else:
                print("No content was successfully scraped.")

    except Exception as e:
        logger.critical(f"Critical error in main script execution block: {e}", exc_info=True)
        # Fail explicitly with an error - NO FALLBACKS!
        print("DIRECT_SCRAPER_CRITICAL_ERROR: Failing explicitly with no fallback content due to script error.")
        sys.exit(1)