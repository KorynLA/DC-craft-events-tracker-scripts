import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import re
import xml.etree.ElementTree as ET
from dateutil import parser as date_parser
import time
from urllib.parse import urljoin, urlparse
from datetime import datetime

# Smithsonian museum names and locations
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
        print(f"Error extracting date: {e}")
    
    return None

    """
    Cleans up an event description pulled from the Smithsonian Events RSS feed.
    - Removes leading date/time and all valuues after the description
    - Removes everything from <b>Sponsor</b> onward
    - Strips HTML tags
    - Decodes HTML entities
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
    Cleans up an event description pulled from the Smithsonian Events RSS feed.
    - Removes leading date/time and all valuues after the description
    - Removes everything from <b>Sponsor</b> onward
    - Strips HTML tags
    - Decodes HTML entities
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
        # Just grab the first line before <br/> or newline
        first_line = description.split("<br")[0]
        text = BeautifulSoup(first_line, "html.parser").get_text(" ", strip=True)

        # Regex: capture start/end times with optional am/pm on each
        # Examples: "10 am – 3 pm", "1 – 2:15 pm", "10:30 am – 11:45 am"
        time_match = re.search(
            r"(\d{1,2}(?::\d{2})?)\s*(am|pm)?\s*[–-]\s*(\d{1,2}(?::\d{2})?)\s*(am|pm)",
            text,
            re.I
        )

        if not time_match:
            return None, None

        start_raw, start_meridiem, end_raw, end_meridiem = time_match.groups()

        # If start_meridiem missing, inherit from end
        if not start_meridiem:
            start_meridiem = end_meridiem

        # Normalize
        start_time_str = f"{start_raw} {start_meridiem.lower()}"
        end_time_str = f"{end_raw} {end_meridiem.lower()}"

        # Parse into datetime objects
        start_dt = datetime.strptime(start_time_str, "%I:%M %p") if ":" in start_raw else datetime.strptime(start_time_str, "%I %p")
        end_dt = datetime.strptime(end_time_str, "%I:%M %p") if ":" in end_raw else datetime.strptime(end_time_str, "%I %p")

        # Format as SQL-compatible time
        start_sql = start_dt.strftime("%H:%M:%S")
        end_sql = end_dt.strftime("%H:%M:%S")

        return start_sql, end_sql

    except Exception as e:
        print(f"Error extracting event times: {e}")
        return None, None

    except Exception as e:
        print(f"Error extracting event times: {e}")
        return None, None

def extract_price_link_from_description(description):
    """Extract Smithsonian Associates pricing link from RSS description"""
    if not description:
        return ""
    
    # Look for the specific pricing link pattern in the RSS
    price_link_pattern = r'<a\s+href="(https://smithsonianassociates\.org/ticketing/tickets/[^"]+)"[^>]*>Click here to view prices</a>'
    match = re.search(price_link_pattern, description, re.I)
    
    if match:
        return match.group(1)
    
    # Fallback: look for any smithsonianassociates.org/ticketing link
    fallback_pattern = r'href="(https://smithsonianassociates\.org/ticketing/[^"]+)"'
    match = re.search(fallback_pattern, description, re.I)
    
    if match:
        return match.group(1)
    
    return ""

def scrape_smithsonian_associates_price(url):
    """Scrape Smithsonian Associates ticketing page for General Admission price"""
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
        
        # Look for Gen. Admission pricing specifically first
        # This pattern looks for "$150\nGen. Admission" or similar layouts
        gen_admission_patterns = [
            # Price followed by "Gen. Admission" (most common layout)
            r'\$(\d+(?:\.\d{2})?)\s*(?:\n|\s)+gen\.?\s*admission',
            # "Gen. Admission" followed by price
            r'gen\.?\s*admission\s*(?:\n|\s)*\$(\d+(?:\.\d{2})?)',
            # "General Admission" variations
            r'\$(\d+(?:\.\d{2})?)\s*(?:\n|\s)+general\s*admission',
            r'general\s*admission\s*(?:\n|\s)*\$(\d+(?:\.\d{2})?)',
            # With colons or other separators
            r'gen\.?\s*admission[:\s]*\$(\d+(?:\.\d{2})?)',
            r'general\s*admission[:\s]*\$(\d+(?:\.\d{2})?)',
        ]
        
        # First, specifically look for General Admission pricing
        for pattern in gen_admission_patterns:
            match = re.search(pattern, page_text, re.I)
            if match:
                price = f"${match.group(1)}"
                print(f"    💰 Found General Admission price: {price}")
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
                
                print(f"    💰 Found Smithsonian Associates price: {price}")
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
                print(f"    💰 Found potential Smithsonian Associates price: {price}")
                return price
        
        print(f"    ❌ No price found on Smithsonian Associates page")
        return ""
        
    except requests.exceptions.RequestException as e:
        print(f"    ❌ Error fetching Smithsonian Associates page: {e}")
        return ""
    except Exception as e:
        print(f"    ❌ Error parsing Smithsonian Associates page: {e}")
        return ""
    finally:
        time.sleep(1.5)

def scrape_website_for_price(url):
    """Scrape a website to find price information"""
    if not url or 'eventbrite' in url.lower():
        return ""
    
    # If it's a Smithsonian Associates ticketing page, use specialized scraper
    if 'smithsonianassociates.org/ticketing' in url:
        return scrape_smithsonian_associates_price(url)
    
    try:
        print(f"Checking website for price: {url[:60]}...")
        
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
        
        # Check HTML elements first
        for selector in price_selectors:
            elements = soup.select(selector)
            for element in elements:
                element_text = element.get_text(strip=True)
                if '$' in element_text or 'free' in element_text.lower():
                    # Extract price from element
                    dollar_match = re.search(r'\$(\d+(?:\.\d{2})?)', element_text)
                    if dollar_match:
                        price = f"${dollar_match.group(1)}"
                        print(f"    💰 Found price in HTML element: {price}")
                        return price
                    elif 'free' in element_text.lower():
                        print(f"    💰 Found free event in HTML element")
                        return "Free"
        
        # Enhanced price detection patterns - prioritize General Admission
        # First, look specifically for General Admission pricing
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
        
        # Check for General Admission pricing first
        for pattern in gen_admission_patterns:
            match = re.search(pattern, page_text_lower, re.I)
            if match:
                price = f"${match.group(1)}"
                print(f"    💰 Found General Admission price: {price}")
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
                
                print(f"    💰 Found price: {price}")
                return price
        
        # Look for standalone dollar amounts as fallback
        dollar_matches = re.findall(r'\$(\d+(?:\.\d{2})?)', page_text)
        if dollar_matches:
            # Get the most common price or the first reasonable one
            reasonable_prices = [float(p) for p in dollar_matches if 5 <= float(p) <= 100]
            if reasonable_prices:
                price = f"${reasonable_prices[0]:.0f}" if reasonable_prices[0] == int(reasonable_prices[0]) else f"${reasonable_prices[0]}"
                print(f"    💰 Found potential price: {price}")
                return price
        
        print(f"    ❌ No price found on website")
        return ""
        
    except requests.exceptions.RequestException as e:
        print(f"    ❌ Error fetching website: {e}")
        return ""
    except Exception as e:
        print(f"    ❌ Error parsing website: {e}")
        return ""
    finally:
        # Add small delay to be respectful
        time.sleep(1.5)

def extract_venue_and_location_from_rss(description):
    """
    Extract only Venue and Event Location from the Smithsonian RSS description HTML.
    Returns a combined string like "Anacostia Community Museum, 1901 Fort Place SE"
    """
    if not description:
        return ""

    try:
        soup = BeautifulSoup(description, "html.parser")
        text = soup.get_text(" ", strip=True)
                # Sponsor (preferred)
        sponsor_match = re.search(r"Sponsor\s*:\s*([^\n\r]+?)(?=\s*(Event Location|Cost|Categories|$))", text, re.I)
        sponsor = sponsor_match.group(1).strip() if sponsor_match else ""
        # Strict regex: stop at "Cost", "Categories", or end of line
        venue_match = re.search(r"Venue\s*:\s*([^\n\r]+?)(?=\s*(Event Location|Cost|Categories|$))", text, re.I)
        loc_match = re.search(r"Event Location\s*:\s*([^\n\r]+?)(?=\s*(Venue|Cost|Categories|$))", text, re.I)

        venue = venue_match.group(1).strip() if venue_match else ""
        event_location = loc_match.group(1).strip() if loc_match else ""
        print(event_location)
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
        print(f" Error extracting venue/location: {e}")
        return ""

def is_virtual(text, title=""):
    """Extract location information from Smithsonian event text"""
    if not text:
        return ""
    
    combined_text = f"{title} {text}".lower()
    
    # Check for virtual event indicators first
    virtual_indicators = [
        'virtual', 'online', 'zoom', 'webinar', 'livestream', 'live stream',
        'digital', 'remote', 'via zoom', 'online event', 'virtual event',
        'from home', 'participate online', 'join online', 'web-based'
    ]
    
    for indicator in virtual_indicators:
        if indicator in combined_text:
            return "Virtual"
    
    # Check for specific Smithsonian locations
    for location in smithsonian_locations:
        if location in combined_text:
            return location.title()
    
    # General location patterns
    location_patterns = [
        r'\b(washington\s*dc|washington|dc)\b',
        r'\b(\d+\s+\w+\s+(?:street|st|avenue|ave|road|rd|drive|dr|place|pl|way|blvd|boulevard))\b',
        r'location:?\s*([^\n,.]+)',
        r'address:?\s*([^\n,.]+)',
        r'at\s+the\s+([^\n,.]+(?:museum|gallery|center|building))',
        r'held\s+at\s+([^\n,.]+)',
        r'venue:?\s*([^\n,.]+)'
    ]
    
    for pattern in location_patterns:
        match = re.search(pattern, combined_text, re.I)
        if match:
            location = match.group(1).strip()
            location = re.sub(r'\s+', ' ', location)
            return location
    
    return ""


def is_kid_friendly(text, title):
    """Determine if event is kid-friendly based on content"""
    if not text and not title:
        return ""
    
    combined_text = f"{title} {text}".lower()
    
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

def scrape_smithsonian_rss():
    """Scrape the Smithsonian RSS feed for future events"""
    rss_url = "https://www.trumba.com/calendars/smithsonian-events.rss?filter1=_16658_&filterfield1=11153"
    scraped_at = datetime.now().isoformat()
    workshops = []
    
    try:
        print(f"Fetching Smithsonian RSS feed...")
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/rss+xml, application/xml, text/xml, */*'
        }
        
        response = requests.get(rss_url, headers=headers, timeout=20)
        response.raise_for_status()
        
        print(f"RSS feed fetched successfully: {len(response.content)} bytes")

        try:
            soup = BeautifulSoup(response.content, 'xml')
            items = soup.find_all('item')
            print(f"Parsed with BeautifulSoup XML parser")
        except Exception as e:
            print(f"BeautifulSoup XML parsing failed: {e}")
            try:
                # Fallback to ElementTree
                root = ET.fromstring(response.content)
                items = root.findall('.//item')
                print(f"Parsed with ElementTree")
            except ET.ParseError as e:
                print(f"ElementTree parsing failed: {e}")
                soup = BeautifulSoup(response.content, 'html.parser')
                items = soup.find_all('item')
                print(f"Parsed with BeautifulSoup HTML parser")
        
        print(f"Found {len(items)} items in RSS feed")
        
        current_date = datetime.now()

        for i, item in enumerate(items, 10):
            try:
                print(f"\nProcessing item {i}/{len(items)}...")
                # Extract basic information - handle both BeautifulSoup and ElementTree
                if hasattr(item, 'find') and hasattr(item.find('title'), 'get_text'):
                    # BeautifulSoup object
                    title = item.find('title').get_text() if item.find('title') else ""
                    description = item.find('description').get_text() if item.find('description') else ""
                    link = item.find('link').get_text() if item.find('link') else ""
                    pub_date = item.find('pubDate').get_text() if item.find('pubDate') else ""
                    category = item.find('category').get_text() if item.find('category') else ""
                else:
                    # ElementTree object
                    title = item.find('title').text if item.find('title') is not None else ""
                    description = item.find('description').text if item.find('description') is not None else ""
                    link = item.find('link').text if item.find('link') is not None else ""
                    pub_date = item.find('pubDate').text if item.find('pubDate') is not None else ""
                    category = item.find('category').text if item.find('category') is not None else ""
                
                print(f"Title: {title[:60]}...")
                # Store original description for price link extraction
                original_description = description
                event_date = extract_event_date(category, original_description)
                test_time = extract_event_times(original_description)
                found_price  = get_cost(original_description)

                cleaned_description = clean_event_description(original_description)

                # Clean up HTML from description
                if description:
                    desc_soup = BeautifulSoup(description, 'html.parser')
                    description = desc_soup.get_text(separator=' ', strip=True)

                location = extract_venue_and_location_from_rss(description)
                
                
                # Check if event is in the future
                if event_date:
                    if event_date < datetime.today():
                        print(f"Skipping past event: {event_date.date()}")
                        continue
                else:
                    print(f"Could not parse date, including anyway")
                
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
                        print(f"  🎫 Found Smithsonian Associates pricing link")
                        scraped_price = scrape_smithsonian_associates_price(pricing_link)
                        if scraped_price:
                            price = scraped_price
                        elif not price:
                            price = "Check website"
                    # If price is still empty or says "check website", try scraping the main event website
                    elif not price or "check website" in price.lower():
                        event_url = link.strip() if link else ""
                        if event_url and 'eventbrite' not in event_url.lower():
                            print(f"  🌐 Attempting to scrape price from: {event_url[:50]}...")
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
                    'kidfriendly': kid_friendly
                }
                
                if title and len(title.strip()) > 5:
                    workshops.append(workshop_data)
                    print(f"Added workshop: {title[:50]}...")
                else:
                    print(f"Skipped item with insufficient data")
                
            except Exception as e:
                print(f"Error processing item {i}: {e}")
                continue
        
        print(f"Extracted {len(workshops)} future workshops from Smithsonian RSS")
        
    except requests.exceptions.RequestException as e:
        print(f"Error fetching RSS feed: {e}")
    except Exception as e:
        print(f"Error parsing RSS feed: {e}")
        import traceback
        traceback.print_exc()
    
    return workshops

def format_workshop_data(workshop):
    
    return (
        workshop["title"],
        workshop["price"],
        workshop["description"],
        workshop["url"],
        workshop["location"], 
        workshop["date"],
        workshop["time"],
        "Smithsonian",
        "YES",
        "scraper"
    )

def save_to_json(workshops, filename="smithsonian_workshops.json"):
    """Save workshops data to JSON file"""
    import json
    
    # Format workshops for JSON output
    formatted_workshops = []
    for workshop in workshops:
        formatted_data = format_workshop_data(workshop)
        
        # Convert tuple to dictionary for JSON
        workshop_dict = {
            "title": formatted_data[0],
            "price": formatted_data[1],
            "description": formatted_data[2],
            "url": formatted_data[3],
            "location": formatted_data[4],
            "event_date": formatted_data[5],
            "event_time": formatted_data[6],
            "business": formatted_data[7],
            "kidfriendly": formatted_data[8],
            "submittedBy": formatted_data[9],
            "scraped_at": workshop["scraped_at"]
        }
        formatted_workshops.append(workshop_dict)
    
    # Save to JSON file
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(formatted_workshops, f, indent=2, ensure_ascii=False)
        print(f"\n💾 Saved {len(formatted_workshops)} workshops to {filename}")
        return True
    except Exception as e:
        print(f"Error saving to JSON: {e}")
        return False

def main():
    """Main function to run the Smithsonian RSS scraper"""
    
    workshops = scrape_smithsonian_rss()
    
    if workshops:
        print(f"Found {len(workshops)} future workshops:")
        
        # Save to JSON file
        save_to_json(workshops)
        
        # Summary statistics
        print(f"\n📊 Summary:")
        print(f"Total events: {len(workshops)}")
        
        # Kid-friendly breakdown
        kid_friendly_count = sum(1 for w in workshops if w['kidfriendly'] == 'Yes')
        adult_only_count = sum(1 for w in workshops if w['kidfriendly'] == 'No')
        unknown_count = len(workshops) - kid_friendly_count - adult_only_count
        
        print(f"Kid-friendly: {kid_friendly_count}")
        print(f"Adult-only: {adult_only_count}")
        print(f"Unknown: {unknown_count}")
        
        # Other stats
        with_location = sum(1 for w in workshops if w['location'])
        print(f"With location info: {with_location}")
        
        with_datetime = sum(1 for w in workshops if w['date'])
        with_datetime = sum(1 for w in workshops if w['time'])
        print(f"With date/time info: {with_datetime}")
        
        free_events = sum(1 for w in workshops if 'free' in w['price'].lower())
        print(f"Free events: {free_events}")
        
    else:
        print("\n❌ No workshops found.")
        print("\nPossible reasons:")
        print("• RSS feed is empty or has no future events")
        print("• RSS feed format has changed")
        print("• Network connectivity issues")
        print("• Filter parameters in URL exclude all events")
        print("• All events are in the past")
    
    return workshops

if __name__ == "__main__":
    workshops = main()