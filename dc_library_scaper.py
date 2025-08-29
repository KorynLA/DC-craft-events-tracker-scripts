import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import re
import xml.etree.ElementTree as ET
import json
import time
import base64

# Your library location codes hashmap
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
    "Virtual Program": "3098",
    "West End Neighborhood Library": "2328",
    "Woodridge Neighborhood Library": "2329",
}

def encode_rss_filter(location_id, ages=None, types=None, tags=None, term="", days=1):
    if ages == "kids":
        ages = ["Birth - 5", "5 - 12 Years Old", "13 - 19 Years Old (Teens)"]
    else:
        ages = adult_ages = ["Adults", "Seniors"]

    if tags is None:
        tags = []
    
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


def parse_date_from_text(date_text):
    """Parse various date formats and return datetime object"""
    if not date_text:
        return None
    
    # Clean the text first
    date_text = re.sub(r'<[^>]+>', '', str(date_text))  # Remove HTML tags
    date_text = re.sub(r'\s+', ' ', date_text).strip()  # Normalize whitespace
    
    # Common date patterns - more comprehensive
    date_patterns = [
        r'(\w+\s+\d{1,2},?\s+\d{4})',  # January 15, 2024
        r'(\d{1,2}/\d{1,2}/\d{2,4})',  # 1/15/24 or 1/15/2024
        r'(\d{1,2}-\d{1,2}-\d{2,4})',  # 1-15-24 or 1-15-2024
        r'(\d{4}-\d{1,2}-\d{1,2})',    # 2024-01-15 (ISO format)
        r'(\d{1,2}\.\d{1,2}\.\d{2,4})', # 15.1.2024 (European format)
    ]
    
    for pattern in date_patterns:
        matches = re.findall(pattern, date_text, re.IGNORECASE)
        for match in matches:
            date_str = match.strip()
            
            # Try different datetime parsing formats
            formats = [
                '%B %d, %Y',   # January 15, 2024
                '%b %d, %Y',   # Jan 15, 2024
                '%B %d %Y',    # January 15 2024
                '%b %d %Y',    # Jan 15 2024
                '%m/%d/%Y',    # 1/15/2024
                '%m/%d/%y',    # 1/15/24
                '%m-%d-%Y',    # 1-15-2024
                '%m-%d-%y',    # 1-15-24
                '%Y-%m-%d',    # 2024-01-15
                '%d.%m.%Y',    # 15.1.2024
                '%d.%m.%y',    # 15.1.24
            ]
            
            for fmt in formats:
                try:
                    parsed_date = datetime.strptime(date_str, fmt)
                    # Convert 2-digit years
                    if parsed_date.year < 1970:
                        parsed_date = parsed_date.replace(year=parsed_date.year + 100)
                    return parsed_date
                except ValueError:
                    continue
    
    return None

def extract_datetime_from_text(text):
    """Extract date and time from text content"""
    if not text:
        return ""
    
    # Clean HTML tags
    clean_text = re.sub(r'<[^>]+>', ' ', str(text))
    clean_text = re.sub(r'\s+', ' ', clean_text).strip()
    
    # Look for date patterns
    date_obj = parse_date_from_text(clean_text)
    date_part = date_obj.strftime('%Y-%m-%d') if date_obj else ""
    
    # Look for time patterns - more comprehensive
    time_patterns = [
        r'(\d{1,2}:\d{2}\s*(?:am|pm|AM|PM))',
        r'(\d{1,2}\s*(?:am|pm|AM|PM))',
        r'(\d{1,2}:\d{2})',
        r'at\s+(\d{1,2}:\d{2}\s*(?:am|pm|AM|PM))',
        r'at\s+(\d{1,2}\s*(?:am|pm|AM|PM))',
    ]
    
    time_part = ""
    for pattern in time_patterns:
        match = re.search(pattern, clean_text, re.IGNORECASE)
        if match:
            time_part = match.group(1).strip()
            break
    
    # Combine date and time
    if date_part and time_part:
        return f"{date_part} {time_part}"
    elif date_part:
        return date_part
    elif time_part:
        return time_part
    else:
        return ""

def scrape_dc_library_rss():
    """Scrape the DC Library RSS feed for future events"""
    scraped_at = datetime.now().isoformat()
    workshops = []

    for location in library_location_codes.keys():
        rss_url = "https://dclibrary.libnet.info/feeds?data="+encode_rss_filter(library_location_codes[location], "kids")
        try:
            print(f"Fetching RSS feed: {rss_url}")
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'application/rss+xml, application/xml, text/xml, */*',
                'Accept-Language': 'en-US,en;q=0.9',
                'Cache-Control': 'no-cache'
            }
            response = requests.get(rss_url, headers=headers, timeout=30)
            response.raise_for_status()
            
            current_date = datetime.now()

            print(f"RSS feed fetched successfully: {len(response.content)} bytes")
            
            items = []
            
            try:
                soup = BeautifulSoup(response.content, 'xml')
                print(f"BeautifulSoup XML: Found {len(items)} items")
            except Exception as e:
                print(f"BeautifulSoup XML failed: {e}")
            items = soup.find_all('item')
            if len(items) <= 1:
                continue
            for item in items:
                html_contenxt = ""
                content_encoded = item.find('content:encoded')
                if content_encoded:
                    html_content = content_encoded.get_text()
                if html_content:
                    description = html_content
                
                try:
                    title = ""
                    link = ""
                    pub_date = ""
                    
                    if hasattr(item, 'find'):
                        title_elem = item.find('title')
                        desc_elem = item.find('description')
                        link_elem = item.find('link')
                        date_elem = item.find('pubDate') or item.find('pubdate')
                        
                        title = title_elem.get_text() if title_elem else ""
                        description = description if description else desc_elem.get_text()
                        link = link_elem.get_text() if link_elem else ""
                        pub_date = date_elem.get_text() if date_elem else ""
                    else:
                        title_elem = item.find('title')
                        desc_elem = item.find('description') 
                        link_elem = item.find('link')
                        date_elem = item.find('pubDate')
                        
                        title = title_elem.text if title_elem is not None else ""
                        description = description if description else desc_elem.text
                        link = link_elem.text if link_elem is not None else ""
                        pub_date = date_elem.text if date_elem is not None else ""
                    
                    if not title or len(title.strip()) < 3:
                        print("❌ Skipping: No meaningful title")
                        continue
                    full_text = f"{title} {description}"
                    date_time = extract_datetime_from_text(full_text)
                    event_date = parse_date_from_text(date_time)
                    if event_date:
                        if event_date.date() < current_date.date():
                            print(f"❌ Skipping past event: {event_date.date()}")
                            continue
                        else:
                            print(f"✅ Future event: {event_date.date()}")
                    else:
                        print("⚠️  Could not parse date, including anyway")
                    
                    
                    event_url = link.strip() if link else ""

                    price = 0
                    kid_friendly = False
                    
                    workshop_data = {
                        'url': event_url if event_url else rss_url,
                        'scraped_at': scraped_at,
                        'title': title,
                        'description': description if description else title,
                        'date_time': date_time,
                        'price': price,
                        'location': location,
                        'kidfriendly': kid_friendly
                    }
                    print(f'%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%{workshop_data}')
                    workshops.append(workshop_data)
                    
                except Exception as e:
                    print(f"❌ {e}")
                    continue
                
                print(f"\n🎉 Successfully extracted {len(workshops)} workshops")
            
        except requests.exceptions.RequestException as e:
            print(f"❌ Network error fetching RSS feed: {e}")
        except Exception as e:
            print(f"❌ Error parsing RSS feed: {e}")
            import traceback
            traceback.print_exc()
        
    return workshops

def main():
    print("DC Library RSS Events Scraper - FIXED VERSION")
    
    workshops = scrape_dc_library_rss()
    
    if workshops:
        print(f"\n✅ Found {len(workshops)} workshops:")
        
        try:
            filename = f"dc_library_workshops_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(workshops, f, indent=2, ensure_ascii=False)
            print(f"\n💾 Data saved to: {filename}")
        except Exception as e:
            print(f"❌ Could not save to file: {e}")
        
    else:
        print("\n❌ No workshops found.")
        print("\nPossible reasons:")
        print("• RSS feed is empty or has no future events")
        print("• RSS feed format has changed")
        print("• Network connectivity issues")
        print("• All events are in the past")
        print("• The feed URL parameters might need adjustment")
    
    return workshops

if __name__ == "__main__":
    workshops = main()