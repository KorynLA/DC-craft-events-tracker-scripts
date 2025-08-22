import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import re
import xml.etree.ElementTree as ET
from dateutil import parser as date_parser
import time
from urllib.parse import urljoin, urlparse
from datetime import datetime
import logging
import json

logging.basicConfig(level=logging.NOTSET)
logging.getLogger('chardet.charsetprober').setLevel(logging.INFO)
log = logging.getLogger("smithsonian_sraper")

smithsonian_locations = [
    'national air and space museum',
    'national museum of natural history',        
    'national museum of american history',
    'hirshhorn museum',
    'arts and industries building',
    'freer and sackler galleries',
    'national portrait gallery',
    'smithsonian american art museum',
    'anacostia community museum',
    'national postal museum',
    'renwick gallery',
    'cooper hewitt',
    'national zoo',
    'national museum of african american history',
    'national museum of the american indian',
    'smithsonian castle',
    'enid a haupt garden',
    's dillon ripley center'
]

# Kid-friendly indicators
kid_friendly_keywords = [
    'kids', 'children', 'child', 'family', 'families', 'toddler', 'preschool',
    'elementary', 'youth', 'teen', 'teenager', 'ages', 'grade', 'young',
    'workshop for kids', 'family program', 'baby', 'babies',
    'story', 'puppet', 'discovery', 'exploration', 'junior', 'mini'
]

# Adult-only indicators
adult_keywords = [
    'adult only', 'adults only', '18+', '21+', 'mature', 'senior', 'seniors',
    'professional development', 'business', 'career', 'academic', 'scholarly',
    'research', 'graduate', 'university level', 'advanced study',
    'wine', 'alcohol', 'cocktail', 'beer', 'happy hour', 'evening reception'
]
gen_admission_patterns = [
    # Price followed by "Gen. Admission" or "General Admission"
    r'\$(\d+(?:\.\d{2})?)\s*(?:\n|\s)+gen\.?\s*admission',
    r'\$(\d+(?:\.\d{2})?)\s*(?:\n|\s)+general\s*admission',
    # "Gen. Admission" followed by price
    r'gen\.?\s*admission\s*(?:\n|\s)*\$(\d+(?:\.\d{2})?)',
    r'general\s*admission\s*(?:\n|\s)*\$(\d+(?:\.\d{2})?)',
    # With separators
    r'gen\.?\s*admission[:\s]*\$(\d+(?:\.\d{2})?)',
    r'general\s*admission[:\s]*\$(\d+(?:\.\d{2})?)',
]

location_patterns = [
    r'\b(washington\s*dc|washington|dc)\b',
    r'\b(\d+\s+\w+\s+(?:street|st|avenue|ave|road|rd|drive|dr|place|pl|way|blvd|boulevard))\b',
    r'location:?\s*([^\n,.]+)',
    r'address:?\s*([^\n,.]+)',
    r'at\s+the\s+([^\n,.]+(?:museum|gallery|center|building))',
    r'held\s+at\s+([^\n,.]+)',
    r'venue:?\s*([^\n,.]+)'
]

# Check for virtual event indicators first
virtual_indicators = [
    'virtual', 'online', 'zoom', 'webinar', 'livestream', 'live stream',
    'digital', 'remote', 'via zoom', 'online event', 'virtual event',
    'from home', 'participate online', 'join online', 'web-based'
]
price_patterns = [
    (r'\b(free admission|free entry|no admission fee|admission is free|entry is free|free of charge)\b', 'Free'),
    (r'\b(free\s+event|this\s+event\s+is\s+free|no\s+charge)\b', 'Free'),
    (r'\b(complimentary|free)\b(?![a-z])', 'Free'),
    (r'non[\-\s]*member[s]?[:\s]*\$(\d+(?:\.\d{2})?)', lambda m: f"${m.group(1)}"),
    (r'registration[\s\-]*gen\.?\s*admission[:\s]*\$(\d+(?:\.\d{2})?)', lambda m: f"${m.group(1)}"),
    (r'museum\s+admission[:\s]*\$(\d+(?:\.\d{2})?)', lambda m: f"${m.group(1)}"),
    (r'adults?[:\s]*\$(\d+(?:\.\d{2})?)', lambda m: f"${m.group(1)}"),
    (r'admission[:\s]*\$(\d+(?:\.\d{2})?)', lambda m: f"${m.group(1)}"),
    (r'cost[:\s]*\$(\d+(?:\.\d{2})?)', lambda m: f"${m.group(1)}"),
    (r'price[:\s]*\$(\d+(?:\.\d{2})?)', lambda m: f"${m.group(1)}"),
    (r'fee[:\s]*\$(\d+(?:\.\d{2})?)', lambda m: f"${m.group(1)}"),
    (r'ticket[s]?[:\s]*\$(\d+(?:\.\d{2})?)', lambda m: f"${m.group(1)}"),
    (r'(?:admission|cost|price|fee|ticket).*?\$(\d+(?:\.\d{2})?)', lambda m: f"${m.group(1)}"),
    (r'\$(\d+(?:\.\d{2})?).*?(?:admission|cost|price|fee|ticket)', lambda m: f"${m.group(1)}"),
    (r'admission.*?\$(\d+(?:\.\d{2})?)', lambda m: f"${m.group(1)}"),
    (r'\$(\d+(?:\.\d{2})?).*?admission', lambda m: f"${m.group(1)}"),
    (r'included\s+with\s+museum\s+admission', 'Included with museum admission'),
    (r'included\s+with\s+admission', 'Included with museum admission'),
    (r'with\s+paid\s+museum\s+admission', 'Included with museum admission'),
    (r'no\s+additional\s+cost', 'Included with museum admission'),
    (r'\$(\d+(?:\.\d{2})?)\s*(?:per\s+person|each|adult)', lambda m: f"${m.group(1)}"),
    (r'member[s]?[:\s]*\$(\d+(?:\.\d{2})?)', lambda m: f"${m.group(1)}"),
]


"""
Extracts event date from <category> or <description>.
Returns a SQL-compatible DATE string: YYYY-MM-DD
"""
def extract_event_date(item_category, description):
    try:
        if item_category:
            match = re.search(r"(\d{4})/(\d{2})/(\d{2})", item_category)
            if match:
                year, month, day = match.groups()
                return datetime(int(year), int(month), int(day)) 

        if description:
            first_line = description.split("<br")[0]
            text = BeautifulSoup(first_line, "html.parser").get_text(" ", strip=True)

            date_match = re.search(
                r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}",
                text
            )
            if date_match:
                date_str = date_match.group(0)
                dt = datetime(date_str, "%B %d, %Y")
                return dt

    except Exception as e:
        log.warning(f"Error extracting date: {e}")
    
    return None

"""
Cleans up an event description pulled from the Smithsonian Events RSS feed.
- Removes leading date/time and all valuues after the description
- Removes everything from <b>Sponsor</b> onward
- Strips HTML tags
"""
def clean_event_description(description):
    parts = re.split(r"<br/><br/>", description)

    if len(parts) >= 2:
        desc = parts[1]
    else:
        desc = parts[0]

    soup = BeautifulSoup(desc, "html.parser")
    desc = soup.get_text(" ", strip=True)
    return desc

"""
Extracts event date from <category> or <description>.
Returns a SQL-compatible DATE string: YYYY-MM-DD
"""
def get_cost(description):
    pattern = r'<b>Cost</b>:&nbsp;([^<]+)'
    match = re.search(pattern, description)
    if match:
        cost_split = re.split(r'[|;,./]', match[0])
        if len(cost_split)> 2:
            cost = cost_split[2]
            return cost

    return None


"""
Extracts event time from <description>.
Returns a tuple with the SQL-compatible start time and end time
"""
def extract_event_times(description):
    if not description:
        return None, None

    try:
        first_line = description.split("<br")[0]
        text = BeautifulSoup(first_line, "html.parser").get_text(" ", strip=True)

        time_match = re.search(
            r"(\d{1,2}(?::\d{2})?)\s*(am|pm)?\s*[–-]\s*(\d{1,2}(?::\d{2})?)\s*(am|pm)",
            text,
            re.I
        )

        if not time_match:
            return None, None

        start_raw, start_meridiem, end_raw, end_meridiem = time_match.groups()
        if not start_meridiem:
            start_meridiem = end_meridiem
        start_time_str = f"{start_raw} {start_meridiem.lower()}"
        end_time_str = f"{end_raw} {end_meridiem.lower()}"

        start_dt = datetime.strptime(start_time_str, "%I:%M %p") if ":" in start_raw else datetime.strptime(start_time_str, "%I %p")
        end_dt = datetime.strptime(end_time_str, "%I:%M %p") if ":" in end_raw else datetime.strptime(end_time_str, "%I %p")

        start_sql = start_dt.strftime("%H:%M:%S")
        end_sql = end_dt.strftime("%H:%M:%S")

        return start_sql, end_sql

    except Exception as e:
        log.warning(f"Error extracting event times: {e}")
        return None, None

    except Exception as e:
        log.warning(f"Error extracting event times: {e}")
        return None, None

"""
Extracts event price link from <description>.
Returns the URL as a string
"""
def extract_price_link_from_description(description):
    if not description:
        return ""
    
    price_link_pattern = r'<a\s+href="(https://smithsonianassociates\.org/ticketing/tickets/[^"]+)"[^>]*>Click here to view prices</a>'
    match = re.search(price_link_pattern, description, re.I)
    if match:
        return match.group(1)
    
    fallback_pattern = r'href="(https://smithsonianassociates\.org/ticketing/[^"]+)"'
    match = re.search(fallback_pattern, description, re.I)
    if match:
        return match.group(1)
    return ""

"""
Extracts event price link from <description>.
Returns the URL as a string
"""
def scrape_smithsonian_associates_price(url):
    if not url or 'smithsonianassociates.org/ticketing' not in url:
        return ""
    
    try:
        print(f"Scraping Smithsonian Associates price: {url[:60]}...")
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br'
        }
        
        response = requests.get(url, headers=headers, timeout=20, allow_redirects=True)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, 'html.parser')
        page_text = soup.get_text(separator=' ', strip=True).lower()
        
        for pattern in gen_admission_patterns:
            match = re.search(pattern, page_text, re.I)
            if match:
                price = f"${match.group(1)}"
                log.info(f"Found General Admission price: {price}")
                return price
        
        # Fallback patterns if Gen. Admission not found explicitly
        price_patterns = [
            # Free event indicators (check first)
            (r'\b(free|no\s*charge|complimentary)\b', 'Free'),
            
            # Non-member pricing (preferred over member pricing)
            (r'non[\-\s]*member[s]?[:\s]*\$(\d+(?:\.\d{2})?)', lambda m: f"${m.group(1)}"),
            
            # Registration patterns
            (r'registration[\s\-]*gen\.?\s*admission[:\s]*\$(\d+(?:\.\d{2})?)', lambda m: f"${m.group(1)}"),
            
            # Look for price in table or list context with "admission"
            (r'admission.*?\$(\d+(?:\.\d{2})?)', lambda m: f"${m.group(1)}"),
            (r'\$(\d+(?:\.\d{2})?).*?admission', lambda m: f"${m.group(1)}"),
            
            # General price patterns for ticketing pages
            (r'price[:\s]*\$(\d+(?:\.\d{2})?)', lambda m: f"${m.group(1)}"),
            (r'cost[:\s]*\$(\d+(?:\.\d{2})?)', lambda m: f"${m.group(1)}"),
            (r'fee[:\s]*\$(\d+(?:\.\d{2})?)', lambda m: f"${m.group(1)}"),
            
            # Member pricing (lower priority - only if nothing else found)
            (r'member[s]?[:\s]*\$(\d+(?:\.\d{2})?)', lambda m: f"${m.group(1)}"),
        ]
        
        for pattern, result in price_patterns:
            match = re.search(pattern, page_text, re.I)
            if match:
                if callable(result):
                    price = result(match)
                else:
                    price = result
                
                log.info(f"Found Smithsonian Associates price: {price}")
                return price
        
        # Fallback: look for any dollar amounts on the page
        dollar_matches = re.findall(r'\$(\d+(?:\.\d{2})?)', page_text)
        if dollar_matches:
            # Filter reasonable event prices
            reasonable_prices = [float(p) for p in dollar_matches if 5 <= float(p) <= 200]
            if reasonable_prices:
                # Take the first reasonable price found
                price_val = reasonable_prices[0]
                price = f"${price_val:.0f}" if price_val == int(price_val) else f"${price_val}"
                log.info(f'Found potential Smithsonian Associates price:{price}')
                return price
        
        log.info(f"No price found on Smithsonian Associates page")
        return ""
        
    except requests.exceptions.RequestException as e:
        log.warning(f"Error fetching Smithsonian Associates page: {e}")
        return ""
    except Exception as e:
        log.warning(f"Error parsing Smithsonian Associates page: {e}")
        return ""
    finally:
        time.sleep(1.5)
"""
Extracts event price link from <description>.
Returns the URL as a string
"""
def scrape_website_for_price(url):
    if not url or 'eventbrite' in url.lower():
        return ""
    
    if 'smithsonianassociates.org/ticketing' in url:
        return scrape_smithsonian_associates_price(url)
    
    try:
        log.info(f'Checking website for price: url[:60]...')
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br'
        }
        
        response = requests.get(url, headers=headers, timeout=20, allow_redirects=True)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Get all text content
        page_text = soup.get_text(separator=' ', strip=True)
        page_text_lower = page_text.lower()
        
        # Also check for structured data or specific HTML elements
        price_selectors = [
            '.price', '.cost', '.admission', '.fee', '.ticket-price',
            '[class*="price"]', '[class*="cost"]', '[class*="admission"]',
            '[data-price]', '[data-cost]'
        ]
        
        # Check for General Admission pricing first
        for pattern in gen_admission_patterns:
            match = re.search(pattern, page_text_lower, re.I)
            if match:
                price = f"${match.group(1)}"
                log.info(f'   Found General Admission price: {price}')
                return price
        
        price_patterns = [
            # Free indicators (most specific first)
            (r'\b(free admission|free entry|no admission fee|admission is free|entry is free|free of charge)\b', 'Free'),
            (r'\b(free\s+event|this\s+event\s+is\s+free|no\s+charge)\b', 'Free'),
            (r'\b(complimentary|free)\b(?![a-z])', 'Free'),
            
            # Non-member pricing (preferred over member pricing)
            (r'non[\-\s]*member[s]?[:\s]*\$(\d+(?:\.\d{2})?)', lambda m: f"${m.group(1)}"),
            
            # Museum admission patterns
            (r'museum\s+admission[:\s]*\$(\d+(?:\.\d{2})?)', lambda m: f"${m.group(1)}"),
            (r'adults?[:\s]*\$(\d+(?:\.\d{2})?)', lambda m: f"${m.group(1)}"),
            
            # Standard price patterns
            (r'admission[:\s]*\$(\d+(?:\.\d{2})?)', lambda m: f"${m.group(1)}"),
            (r'cost[:\s]*\$(\d+(?:\.\d{2})?)', lambda m: f"${m.group(1)}"),
            (r'price[:\s]*\$(\d+(?:\.\d{2})?)', lambda m: f"${m.group(1)}"),
            (r'fee[:\s]*\$(\d+(?:\.\d{2})?)', lambda m: f"${m.group(1)}"),
            (r'ticket[s]?[:\s]*\$(\d+(?:\.\d{2})?)', lambda m: f"${m.group(1)}"),
            
            # Price with context
            (r'(?:admission|cost|price|fee|ticket).*?\$(\d+(?:\.\d{2})?)', lambda m: f"${m.group(1)}"),
            (r'\$(\d+(?:\.\d{2})?).*?(?:admission|cost|price|fee|ticket)', lambda m: f"${m.group(1)}"),
            
            # Museum admission patterns
            (r'included\s+with\s+museum\s+admission', 'Included with museum admission'),
            (r'included\s+with\s+admission', 'Included with museum admission'),
            (r'with\s+paid\s+museum\s+admission', 'Included with museum admission'),
            (r'no\s+additional\s+cost', 'Included with museum admission'),
            
            # Member pricing (lowest priority)
            (r'member[s]?[:\s]*\$(\d+(?:\.\d{2})?)', lambda m: f"${m.group(1)}"),
            
            # Broader dollar amount patterns
            (r'\$(\d+(?:\.\d{2})?)\s*(?:per\s+person|each|adult)', lambda m: f"${m.group(1)}"),
        ]
        
        for pattern, result in price_patterns:
            match = re.search(pattern, page_text_lower, re.I)
            if match:
                if callable(result):
                    price = result(match)
                else:
                    price = result
                
                print(f"   Found price: {price}")
                return price
        
        # Look for standalone dollar amounts as fallback
        dollar_matches = re.findall(r'\$(\d+(?:\.\d{2})?)', page_text)
        if dollar_matches:
            # Get the most common price or the first reasonable one
            reasonable_prices = [float(p) for p in dollar_matches if 5 <= float(p) <= 100]
            if reasonable_prices:
                price = f"${reasonable_prices[0]:.0f}" if reasonable_prices[0] == int(reasonable_prices[0]) else f"${reasonable_prices[0]}"
                log.info(f"Found potential price: ", price)
                return price
        
        log.info(f"No price found on website")
        return ""
        
    except requests.exceptions.RequestException as e:
        log.warning(f"Error fetching website: {e}")
        return ""
    except Exception as e:
        log.warning(f"Error parsing website: {e}")
        return ""
    finally:
        time.sleep(1.5)

"""
Extract only Venue and Event Location from the Smithsonian RSS description HTML.
Returns a combined string like "Anacostia Community Museum, 1901 Fort Place SE"
"""
def extract_venue_and_location_from_rss(description):
    if not description:
        return ""

    try:
        soup = BeautifulSoup(description, "html.parser")
        text = soup.get_text(" ", strip=True)

        sponsor_match = re.search(r"Sponsor\s*:\s*([^\n\r]+?)(?=\s*(Event Location|Cost|Categories|$))", text, re.I)
        sponsor = sponsor_match.group(1).strip() if sponsor_match else ""
        # Strict regex: stop at "Cost", "Categories", or end of line
        venue_match = re.search(r"Venue\s*:\s*([^\n\r]+?)(?=\s*(Event Location|Cost|Categories|$))", text, re.I)
        loc_match = re.search(r"Event Location\s*:\s*([^\n\r]+?)(?=\s*(Venue|Cost|Categories|$))", text, re.I)

        venue = venue_match.group(1).strip() if venue_match else ""
        event_location = loc_match.group(1).strip() if loc_match else ""

        if sponsor and "Smithsonian Associates" not in sponsor:
            return sponsor 
        elif venue and event_location:
            return f"{venue}, {event_location}"
        elif venue:
            return venue
        elif event_location:
            return event_location
        else:
            return ""

    except Exception as e:
        log.warning(f"Error extracting venue/location: {e}")
        return ""
"""
Extracts event price link from <description>.
Returns the URL as a string
"""
def is_virtual(text, title=""):
    """Extract location information from Smithsonian event text"""
    if not text:
        return ""
    
    combined_text = f"{title} {text}".lower()
    
    for indicator in virtual_indicators:
        if indicator in combined_text:
            return "Virtual"
    
    # Check for specific Smithsonian locations
    for location in smithsonian_locations:
        if location in combined_text:
            return location.title()
    
    for pattern in location_patterns:
        match = re.search(pattern, combined_text, re.I)
        if match:
            location = match.group(1).strip()
            location = re.sub(r'\s+', ' ', location)
            return location
    
    return ""
"""
Extracts event price link from <description>.
Returns the URL as a string
"""
def is_kid_friendly(text, title):
    """Determine if event is kid-friendly based on content"""
    if not text and not title:
        return ""
    
    combined_text = f"{title} {text}".lower()
    
    # Age-specific patterns
    age_patterns = [
        r'age[s]?\s*(\d+)[-\s]*(\d+)?',
        r'(\d+)[-\s]*(\d+)?\s*years?\s*old',
        r'for\s*(\d+)[-\s]*(\d+)?\s*year\s*olds'
    ]
    
    for pattern in age_patterns:
        match = re.search(pattern, combined_text)
        if match:
            min_age = int(match.group(1))
            max_age = int(match.group(2)) if match.group(2) else None
            
            if min_age <= 12:
                return "Yes"
            elif min_age >= 18:
                return "No"
            elif max_age and max_age <= 17:
                return "Yes"
    
    # Check for explicit family/children mentions
    if any(keyword in combined_text for keyword in kid_friendly_keywords):
        return "Yes"
    elif any(keyword in combined_text for keyword in adult_keywords):
        return "No"
    
    # Smithsonian-specific: many programs are family-friendly unless specified otherwise
    if any(term in combined_text for term in ['workshop', 'program', 'demonstration', 'tour']):
        # If no explicit age restrictions and it's educational, likely family-friendly
        if not any(keyword in combined_text for keyword in adult_keywords):
            return "Yes"

    return ""
"""
Extracts event price link from <description>.
Returns the URL as a string
"""
def scrape_smithsonian_rss():
    """Scrape the Smithsonian RSS feed for future events"""
    rss_url = "https://www.trumba.com/calendars/smithsonian-events.rss?filter1=_16658_&filterfield1=11153"
    scraped_at = datetime.now().isoformat()
    workshops = []
    
    try:
        log.info(f"Fetching Smithsonian RSS feed...")
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/rss+xml, application/xml, text/xml, */*'
        }
        
        response = requests.get(rss_url, headers=headers, timeout=20)
        response.raise_for_status()
        
        log.info(f"RSS feed fetched successfully: {len(response.content)} bytes")

        try:
            soup = BeautifulSoup(response.content, 'xml')
            items = soup.find_all('item')
        except Exception as e:
            print(f"BeautifulSoup XML parsing failed: {e}")
            try:
                root = ET.fromstring(response.content)
                items = root.findall('.//item')
                print(f"Parsed with ElementTree")
            except ET.ParseError as e:
                print(f"ElementTree parsing failed: {e}")
                soup = BeautifulSoup(response.content, 'html.parser')
                items = soup.find_all('item')
        
        log.info(f"Found {len(items)} items in RSS feed")
        
        current_date = datetime.now()

        for i, item in enumerate(items, 1):
            try:
                log.info("\nProcessing item {}/{}".format(i, len(items)))
                if hasattr(item, 'find') and hasattr(item.find('title'), 'get_text'):
                    title = item.find('title').get_text() if item.find('title') else ""
                    description = item.find('description').get_text() if item.find('description') else ""
                    link = item.find('link').get_text() if item.find('link') else ""
                    pub_date = item.find('pubDate').get_text() if item.find('pubDate') else ""
                    category = item.find('category').get_text() if item.find('category') else ""
                else:
                    title = item.find('title').text if item.find('title') is not None else ""
                    description = item.find('description').text if item.find('description') is not None else ""
                    link = item.find('link').text if item.find('link') is not None else ""
                    pub_date = item.find('pubDate').text if item.find('pubDate') is not None else ""
                    category = item.find('category').text if item.find('category') is not None else ""
                
                log.info("Title: {}".format(title[:60]))
                original_description = description
                event_date = extract_event_date(category, original_description)
                if event_date:
                    if event_date < datetime.today():
                        log.info(f"Skipping past event: {event_date.date()}")
                        continue
                else:
                    print(f"Could not parse date, including anyway")

                test_time = extract_event_times(original_description)
                found_price  = get_cost(original_description)

                cleaned_description = clean_event_description(original_description)

                if description:
                    desc_soup = BeautifulSoup(description, 'html.parser')
                    description = desc_soup.get_text(separator=' ', strip=True)

                location = extract_venue_and_location_from_rss(description)
                
                
                # Combine title and cleaned description for analysis
                full_text = f"{title} {cleaned_description}"
                price = None
                if found_price is not None:
                    price = found_price
                if not price:
                    # First, try to extract Smithsonian Associates pricing link from RSS description
                    pricing_link = extract_price_link_from_description(original_description)
                    # If we found a pricing link, scrape it for actual price
                    if pricing_link:
                        log.info(f"Found Smithsonian Associates pricing link")
                        scraped_price = scrape_smithsonian_associates_price(pricing_link)
                        if scraped_price:
                            price = scraped_price
                        elif not price:
                            price = "Check website"
                    # If price is still empty or says "check website", try scraping the main event website
                    elif not price or "check website" in price.lower():
                        event_url = link.strip() if link else ""
                        if event_url and 'eventbrite' not in event_url.lower():
                            log.info("Attempting to scrape price from: {}".format(event_url[:50]))
                            scraped_price = scrape_website_for_price(event_url)
                            if scraped_price:
                                price = scraped_price
                            elif not price:
                                price = "Check website"
                        elif not price:
                            price = "Check website"
                
                kid_friendly = is_kid_friendly(full_text, title)
                
                # Use link from RSS or default to RSS URL
                event_url = link.strip() if link else rss_url
                
                # Create workshop data
                workshop_data = {
                    'url': event_url,
                    'scraped_at': scraped_at,
                    'title': title.strip(),
                    'description': cleaned_description.strip() if cleaned_description else title.strip(),
                    'date': event_date.strftime("%Y-%m-%d"),
                    'time': test_time,
                    'price': price,
                    'location': location,
                    'kidfriendly': kid_friendly,
                    'submittedBy': "scraper_smithsonian",
                    "business": "Smithsonian"
                }
                
                if title and len(title.strip()) > 5:
                    workshops.append(workshop_data)
                    log.info("Added workshop: {}".format(title[:50]))
                else:
                    log.info(f"Skipped item with insufficient data")
                
            except Exception as e:
                print(f"Error processing item {i}: {e}")
                continue
        
        log.info("Extracted {} future workshops from Smithsonian RSS".format(len(workshops)))
        
    except requests.exceptions.RequestException as e:
        log.warning(f"Error fetching RSS feed: {e}")
    except Exception as e:
        log.warning(f"Error parsing RSS feed: {e}")
        import traceback
        traceback.print_exc()
    
    return workshops

def save_to_json(workshops, filename="smithsonian_workshops.json"):
    """Save workshops data to JSON file"""
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(workshops, f, indent=2, ensure_ascii=False)
        log.info("\nSaved {} workshops to {}".format(len(workshops), filename))
        return True
    except Exception as e:
        log.warning(f"Error saving to JSON: {e}")
        return False

def main():
    
    workshops = scrape_smithsonian_rss()
    
    if workshops:
        log.info("Found {} future workshops:".format(len(workshops)))
        save_to_json(workshops)
        log.info("Total events added: {}".format(len(workshops)))   
    else:
        log.warning("No workshops found.")

if __name__ == "__main__":
    main()