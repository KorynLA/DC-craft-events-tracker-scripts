import requests
from bs4 import BeautifulSoup
from datetime import datetime
import re
import json
import time
import base64
import traceback
import logging

logging.basicConfig(level=logging.NOTSET)
logging.getLogger('chardet.charsetprober').setLevel(logging.INFO)
logging.getLogger("bs4.dammit").setLevel(logging.ERROR)
log = logging.getLogger("dc_library_scraper")

library_location_codes = {
    "Anacostia Neighborhood Library": "2305",
    "Arthur Capper TechExpress": "3915",
    "Bellevue (William O. Lockridge) Neighborhood Library": "2306",
    "Benning (Dorothy I. Height) Neighborhood Library": "2304",
    "Capitol View Neighborhood Library": "2307",
    "Chevy Chase Neighborhood Library": "2308",
    "Cleveland Park Neighborhood Library": "2309",
    "Deanwood Neighborhood Library": "2310",
    "Francis A. Gregory Neighborhood Library": "2312",
    "Georgetown Neighborhood Library": "2313",
    "Lamond-Riggs Neighborhood Library": "2314",
    "Martin Luther King Jr. Memorial Library - Central Library": "2316",
    "Mt. Pleasant Neighborhood Library": "2317",
    "Northeast Neighborhood Library": "2318",
    "Northwest One Neighborhood Library": "2330",
    "Palisades Neighborhood Library": "2331",
    "Parklands-Turner Neighborhood Library": "2319",
    "Petworth Neighborhood Library": "2320",
    "Rosedale Neighborhood Library": "2321",
    "Shaw (Watha T. Daniel) Neighborhood Library": "2322",
    "Shepherd Park (Juanita E. Thornton) Neighborhood Library": "2323",
    "Southwest Neighborhood Library": "2943",
    "Takoma Park Neighborhood Library": "2326",
    "Tenley-Friendship Neighborhood Library": "2327",
    "Virtual": "3098",
    "West End Neighborhood Library": "2328",
    "Woodridge Neighborhood Library": "2329",
}

def encode_rss_filter(location_id, kids=False, types=None, term="", days=1):
    if kids:
        ages = ["Birth - 5", "5 - 12 Years Old", "13 - 19 Years Old (Teens)"]
    else:
        ages = ["Adults", "Seniors"]
    
    filter_data = {
        "feedType": "rss",
        "filters": {
            "location": [location_id],
            "ages": ages,
            "types": ["Arts & Crafts", "Makers & DIY Program", "Writing"],
            "tags": [],
            "term": "",
            "days": 1
        }
    }

    json_str = json.dumps(filter_data, separators=(',', ':'))
    encoded = base64.b64encode(json_str.encode('utf-8')).decode('utf-8')
    return encoded


def parse_date(date_text):
    if not date_text:
        return None
    
    date_text = re.sub(r'<[^>]+>', '', str(date_text))
    date_text = re.sub(r'\s+', ' ', date_text).strip()
    
    date_patterns = [
        r'(\w+\s+\d{1,2},?\s+\d{4})',
        r'(\d{1,2}/\d{1,2}/\d{2,4})',
        r'(\d{1,2}-\d{1,2}-\d{2,4})',
        r'(\d{4}-\d{1,2}-\d{1,2})'
    ]
    
    for pattern in date_patterns:
        matches = re.findall(pattern, date_text, re.IGNORECASE)
        for match in matches:
            date_str = match.strip()
            
            formats = [
                '%B %d, %Y',
                '%b %d, %Y',
                '%B %d %Y',
                '%b %d %Y',
                '%m/%d/%Y',
                '%m/%d/%y',
                '%m-%d-%Y',
                '%m-%d-%y',
                '%Y-%m-%d',
                '%d.%m.%Y',
                '%d.%m.%y',
            ]
            
            for fmt in formats:
                try:
                    parsed_date = datetime.strptime(date_str, fmt)
                    if parsed_date.year < 1970:
                        parsed_date = parsed_date.replace(year=parsed_date.year + 100)
                    return parsed_date.date() if parsed_date else ""
                except ValueError:
                    continue
    
    return None

def parse_time(text):
    time_patterns = [
        r'(\d{1,2}:\d{2}\s*(?:am|pm|AM|PM))',
        r'(\d{1,2}\s*(?:am|pm|AM|PM))',
        r'(\d{1,2}:\d{2})',
        r'at\s+(\d{1,2}:\d{2}\s*(?:am|pm|AM|PM))',
        r'at\s+(\d{1,2}\s*(?:am|pm|AM|PM))',
    ]
    time_part = ""
    for pattern in time_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            time_part = match.group(1).strip()
            break
    time_formats = [
        "%I:%M %p",
        "%I:%M%p",
        "%I %p",
        "%I%p"
    ]
    
    start_time = None
    for fmt in time_formats:
        try:
            start_time = datetime.strptime(time_part, fmt)
            return start_time.time()
        except ValueError:
            continue
    return None

def extract_datetime_from_text(text):
    if not text:
        return ""
    
    clean_text = re.sub(r'<[^>]+>', ' ', str(text))
    clean_text = re.sub(r'\s+', ' ', clean_text).strip()
    
    date_part = parse_date(clean_text)
    time_part = parse_time(clean_text)

    if date_part and time_part:
        return (date_part, time_part)
    elif date_part:
        return (date_part, None)
    else:
        return (None, None)

def scrape_dc_library_rss(kid_friendly = False, title_set = None):
    scraped_at = datetime.now().isoformat()
    workshops = []

    for location in library_location_codes.keys():
        rss_url = "https://dclibrary.libnet.info/feeds?data="+encode_rss_filter(library_location_codes[location], kid_friendly)
        try:
            log.info(f"Fetching RSS feed: {rss_url}")
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'application/rss+xml, application/xml, text/xml, */*',
                'Accept-Language': 'en-US,en;q=0.9',
                'Cache-Control': 'no-cache'
            }
            response = requests.get(rss_url, headers=headers, timeout=30)
            response.raise_for_status()
            
            current_date = datetime.now()

            log.info("RSS feed fetched successfully")
            
            items = []
            
            try:
                soup = BeautifulSoup(response.content, 'xml')
                log.info("BeautifulSoup XML: Found {} items".format(len(items)))
            except Exception as e:
                log.warning(f"BeautifulSoup XML failed: {e}")
            
            items = soup.find_all('item')
            if len(items) <= 1:
                continue

            for item in items:
                content_encoded = item.find('content:encoded')
                if content_encoded:
                    html_content = content_encoded.get_text()
                if html_content:
                    clean_description = html_content
                
                try:
                    title = ""
                    link = ""
                    pub_date = ""
                    description = ""

                    if hasattr(item, 'find'):
                        title_elem = item.find('title')
                        desc_elem = item.find('description')
                        link_elem = item.find('link')
                        date_elem = item.find('pubDate') or item.find('pubdate')
                        desc_elem = item.find('description')

                        title = title_elem.get_text().strip() if title_elem else ""
                        description = desc_elem.get_text().strip() if desc_elem else ""
                        link = link_elem.get_text() if link_elem else ""
                        pub_date = date_elem.get_text() if date_elem else ""
                    else:
                        title_elem = item.find('title')
                        desc_elem = item.find('description') 
                        link_elem = item.find('link')
                        date_elem = item.find('pubDate')
                        
                        title = title_elem.text.strip() if title_elem is not None else ""
                        description = desc_elem.text.strip() if desc_elem is not None else ""
                        link = link_elem.text if link_elem is not None else ""
                        pub_date = date_elem.text if date_elem is not None else ""
                    
                    if not title or len(title.strip()) < 3 :
                        log.warning(f"Skipping: {title}, No meaningful title")
                        continue
                    if title_set is not None and title in title_set:
                        log.info(f"Skipping: {title}, Already added")
                        continue

                    full_text = f"{title} {description}"
                    date_time = extract_datetime_from_text(full_text)
                    event_date = date_time[0] if date_time else None

                    if event_date:
                        if event_date < current_date.date():
                            log.warning(f"Skipping past event title: {title}, {event_date}")
                            continue
                    else:
                        log.warning(f"Skipping event {title} without date")
                        continue
                    
                    workshop_data = {
                        'url': link.strip() if link else rss_url,
                        'scraped_at': scraped_at,
                        'title': title,
                        'description': clean_description.strip() if clean_description else title,
                        'date': event_date.strftime("%Y-%m-%d"), 
                        'time': date_time[1].strftime("%H:%M:%S") if date_time[1] else None,
                        'price': 0,
                        'location': location,
                        'kidfriendly': kid_friendly,
                        'submittedBy': "scraper_dc_library",
                        'business': 'DC Libaries'
                    }
                    log.info(f"Successfully extracted event: {title}")
                    workshops.append(workshop_data)
                    
                except Exception as e:
                    log.error(f"{e}")
                    continue
            
        except requests.exceptions.RequestException as e:
            log.error(f"Network error fetching RSS feed: {rss_url}")
            log.debug(f"{e}")
        except Exception as e:
            log.error(f"Error parsing RSS feed: {rss_url}")
            log.debug("Full traceback:", exc_info=True)
        
    return workshops

def main():
    log.info("Starting DC Library RSS Events Scraper")
    
    workshops = scrape_dc_library_rss(True)
    title_set = set()

    for workshop in workshops:
        title_set.add(workshop['title'])
    workshops.extend(scrape_dc_library_rss(False, title_set))
    if workshops:
        log.info("Found {} workshops: ".format(len(workshops)))
    
        try:
            filename = f"dc_library_workshops_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(workshops, f, indent=2, ensure_ascii=False)
            log.info(f"\nData saved to: {filename}")
        except Exception as e:
            log.error(f"Could not save to file {filename}: {e}")
        
    else:
        log.warning("\nNo workshops found.")
    
    return workshops

if __name__ == "__main__":
    workshops = main()