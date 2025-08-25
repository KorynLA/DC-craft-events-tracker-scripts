import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import re
import xml.etree.ElementTree as ET
import json

dc_library_branches = [
    'martin luther king jr memorial library',
    'martin luther king jr. memorial library', 
    'central library',
    'anacostia neighborhood library',
    'benning neighborhood library',
    'capitol view neighborhood library',
    'chevy chase neighborhood library',
    'cleveland park neighborhood library',
    'deanwood neighborhood library',
    'francis a gregory neighborhood library',
    'lamond-riggs neighborhood library',
    'mount pleasant neighborhood library',
    'northeast neighborhood library',
    'northwest one neighborhood library', 
    'palisades neighborhood library',
    'parklands-turner neighborhood library',
    'petworth neighborhood library',
    'pocahontas neighborhood library',
    'popular point neighborhood library',
    'seattle neighborhood library',
    'southeast neighborhood library',
    'southwest neighborhood library',
    'tenley-friendship neighborhood library',
    'washington highlands neighborhood library',
    'wesley neighborhood library',
    'woodridge neighborhood library'
]

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

def extract_location_from_text(text):
    """Extract location information from text"""
    if not text:
        return ""
    
    # Clean HTML tags
    clean_text = re.sub(r'<[^>]+>', ' ', str(text))
    clean_text = re.sub(r'\s+', ' ', clean_text).strip()
    
    # First, check for full library names (most specific)
    for branch in dc_library_branches:
        if branch in clean_text.lower():
            # Format nicely for display
            formatted_branch = ' '.join(word.capitalize() for word in branch.split())
            return formatted_branch
    
    # Location extraction patterns
    location_patterns = [
        # Specific format: **Location Name**
        r'\*\*([^*]+(?:library|branch|center)[^*]*)\*\*',
        # Location: format
        r'location:?\s*([^\n,.;]+)',
        # Address format
        r'address:?\s*([^\n,.;]+)',
        # At location format
        r'at\s+([^\n,.;]+(?:library|branch|center))',
        # Held at format
        r'held\s+at\s+([^\n,.;]+)',
        # Visit format
        r'visit\s+([^\n,.;]+(?:library|branch))',
        # Street address
        r'(\d+\s+\w+\s+(?:street|st|avenue|ave|road|rd|drive|dr|place|pl|way|blvd|boulevard))',
        # Simple branch name patterns
        r'\b(northeast|northwest|southeast|southwest|central|anacostia|benning|capitol view|chevy chase|cleveland park|deanwood|francis a gregory|lamond-riggs|martin luther king|mount pleasant|palisades|parklands-turner|petworth|pocahontas|popular point|seattle|tenley-friendship|washington highlands|wesley|woodridge)\s*(?:neighborhood\s*)?(?:library|branch)?\b',
    ]
    
    for pattern in location_patterns:
        match = re.search(pattern, clean_text, re.IGNORECASE)
        if match:
            location = match.group(1).strip()
            # Clean up the location
            location = re.sub(r'\s+', ' ', location)
            location = location.rstrip('.,;')
            location = location.strip('*')  # Remove markdown formatting
            
            # Format properly
            if 'library' in location.lower() or 'branch' in location.lower():
                # Capitalize each word for library names
                location = ' '.join(word.capitalize() for word in location.split())
            
            if len(location) > 3:  # Avoid very short matches
                return location
    
    return ""

def extract_price_from_text(text):
    """Extract price information from text"""
    if not text:
        return "Free"  # DC Library events are typically free
    
    clean_text = re.sub(r'<[^>]+>', ' ', str(text))
    
    # Look for free indicators first
    if re.search(r'\b(free|no cost|no charge|complimentary|admission free)\b', clean_text, re.I):
        return "Free"
    
    # Look for price patterns
    price_match = re.search(r'\$(\d+(?:\.\d{2})?)', clean_text)
    if price_match:
        return f"${price_match.group(1)}"
    
    return "Free"  # Default for DC Library

def determine_kid_friendly(text, title):
    """Determine if event is kid-friendly based on content"""
    if not text and not title:
        return ""
    
    combined_text = f"{title} {text}".lower()
    # Clean HTML
    combined_text = re.sub(r'<[^>]+>', ' ', combined_text)
    
    # Kid-friendly indicators
    kid_friendly_keywords = [
        'kids', 'children', 'child', 'family', 'families', 'toddler', 'preschool',
        'elementary', 'youth', 'teen', 'teenager', 'teens', 'ages', 'grade', 'young',
        'story time', 'storytime', 'game', 'games', 'puppet', 'sing', 'dance', 'play', 'baby', 'babies',
        'all ages', 'for kids', 'young adult', 'young adults'
    ]
    
    # Adult-only indicators (but not if teens are mentioned)
    adult_keywords = [
        'adult only', 'adults only', '18+', '21+'
    ]
    
    # Check for DC Library age group patterns specifically
    age_group_patterns = [
        r'age\s*group:?\s*[|\s]*([^|]+)',  # AGE GROUP: | content
        r'(\d+)\s*[-–—]\s*(\d+)\s*years?\s*old',  # 13 - 19 Years Old
        r'(\d+)\s*[-–—]\s*(\d+)\s*year\s*old',   # 13-19 year old
        r'ages?\s*(\d+)[-–—\s]*(\d+)?',          # ages 13-19 or age 13
        r'for\s*(\d+)[-–—\s]*(\d+)?\s*year',     # for 13-19 year
    ]
    
    # Look for age group information
    for pattern in age_group_patterns:
        matches = re.finditer(pattern, combined_text, re.IGNORECASE)
        for match in matches:
            if len(match.groups()) >= 2 and match.group(2):  # Range like "13 - 19"
                try:
                    min_age = int(match.group(1))
                    max_age = int(match.group(2))
                    
                    # If the range includes teens (13-19), consider it kid-friendly
                    if min_age <= 19 and max_age >= 13:
                        return "Yes"
                    elif min_age >= 18 and max_age >= 18:
                        return "No"
                except (ValueError, TypeError):
                    continue
            elif match.group(1):  # Single age or age group description
                age_desc = match.group(1).lower()
                # Check if the age group description contains teen indicators
                if any(teen_word in age_desc for teen_word in ['teen', 'youth', '13', '14', '15', '16', '17', '18', '19']):
                    return "Yes"
    
    # Check for specific teen age mentions
    teen_patterns = [
        r'\b(?:1[3-9]|teen|teens|teenager|teenagers)\b',
        r'\byouth\b',
        r'\byoung\s+adult\b'
    ]
    
    teen_found = any(re.search(pattern, combined_text, re.IGNORECASE) for pattern in teen_patterns)
    
    # Check keywords
    kid_score = sum(1 for keyword in kid_friendly_keywords if keyword in combined_text)
    adult_score = sum(1 for keyword in adult_keywords if keyword in combined_text)
    
    # If teens are mentioned, lean towards kid-friendly
    if teen_found:
        return "Yes"
    elif kid_score > adult_score and kid_score > 0:
        return "Yes"
    elif adult_score > kid_score and adult_score > 0:
        return "No"
    
    return ""

def fetch_event_details(event_url):
    """Fetch additional details from individual event page"""
    if not event_url or 'dclibrary.libnet.info' not in event_url:
        return {}, ""
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
        }
        
        response = requests.get(event_url, headers=headers, timeout=15)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Extract additional text content
        # Look for the main content area
        content_areas = [
            soup.find('div', class_='event-details'),
            soup.find('div', class_='content'),
            soup.find('main'),
            soup.find('article'),
            soup.find('div', {'id': 'content'}),
        ]
        
        full_text = ""
        for area in content_areas:
            if area:
                full_text += " " + area.get_text(separator=' ', strip=True)
                break
        
        if not full_text:
            # Fallback: get all text from body
            body = soup.find('body')
            if body:
                full_text = body.get_text(separator=' ', strip=True)
        
        # Extract structured data if available
        details = {}
        
        # Look for age group info
        age_group_elem = soup.find(text=re.compile(r'AGE GROUP', re.I))
        if age_group_elem:
            # Find the parent element and get following text
            parent = age_group_elem.parent
            if parent:
                age_text = parent.get_text()
                details['age_group'] = age_text
        
        # Look for location info in structured format
        location_patterns = [
            soup.find(text=re.compile(r'location', re.I)),
            soup.find('div', class_=re.compile(r'location', re.I)),
            soup.find('span', class_=re.compile(r'location', re.I)),
        ]
        
        for elem in location_patterns:
            if elem:
                if hasattr(elem, 'parent') and elem.parent:
                    location_text = elem.parent.get_text(strip=True)
                    if len(location_text) > 5:
                        details['location_detail'] = location_text
                        break
                elif hasattr(elem, 'get_text'):
                    location_text = elem.get_text(strip=True)
                    if len(location_text) > 5:
                        details['location_detail'] = location_text
                        break
        
        return details, full_text
        
    except Exception as e:
        print(f"  Warning: Could not fetch event details from {event_url}: {e}")
        return {}, ""

def scrape_dc_library_rss():
    """Scrape the DC Library RSS feed for future events"""
    rss_url = "https://dclibrary.libnet.info/feeds?data=eyJmZWVkVHlwZSI6InJzcyIsImZpbHRlcnMiOnsibG9jYXRpb24iOlsiYWxsIl0sImFnZXMiOlsiYWxsIl0sInR5cGVzIjpbIkFydHMgJiBDcmFmdHMiLCJNYWtlcnMgJiBESVkgUHJvZ3JhbSIsIldyaXRpbmciXSwidGFncyI6W10sInRlcm0iOiIiLCJkYXlzIjoxfX0="
    scraped_at = datetime.now().isoformat()
    workshops = []
    
    try:
        print(f"Fetching RSS feed: {rss_url}")
        
        # Decode the parameters to understand what we're fetching
        #encoded_params = rss_url.split('data=')[1]
        #params = decode_rss_params(encoded_params)
        #if params:
        #    print(f"RSS Parameters: {json.dumps(params, indent=2)}")
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/rss+xml, application/xml, text/xml, */*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Cache-Control': 'no-cache'
        }
        
        response = requests.get(rss_url, headers=headers, timeout=30)
        response.raise_for_status()
        
        print(f"RSS feed fetched successfully: {len(response.content)} bytes")
        print(f"Content type: {response.headers.get('content-type', 'unknown')}")
        
        # Debug: Show first 500 characters
        content_preview = response.text[:500] if hasattr(response, 'text') else str(response.content[:500])
        print(f"Content preview: {content_preview}")
        
        # Try multiple parsing methods
        items = []
        
        # Method 1: Try BeautifulSoup with XML parser
        try:
            soup = BeautifulSoup(response.content, 'xml')
            items = soup.find_all('item')
            print(f"BeautifulSoup XML: Found {len(items)} items")
        except Exception as e:
            print(f"BeautifulSoup XML failed: {e}")
        
        # Method 2: If no items, try HTML parser
        if not items:
            try:
                soup = BeautifulSoup(response.content, 'html.parser')
                items = soup.find_all('item')
                print(f"BeautifulSoup HTML: Found {len(items)} items")
            except Exception as e:
                print(f"BeautifulSoup HTML failed: {e}")
        
        # Method 3: Try ElementTree
        if not items:
            try:
                root = ET.fromstring(response.content)
                items = root.findall('.//item')
                print(f"ElementTree: Found {len(items)} items")
            except Exception as e:
                print(f"ElementTree failed: {e}")
        
        # Method 4: Manual parsing if XML parsers fail
        if not items:
            print("Trying manual parsing...")
            # Look for item patterns in the raw content
            content_str = response.text if hasattr(response, 'text') else response.content.decode('utf-8', errors='ignore')
            item_pattern = r'<item.*?</item>'
            item_matches = re.findall(item_pattern, content_str, re.DOTALL | re.IGNORECASE)
            print(f"Manual parsing: Found {len(item_matches)} potential items")
            
            # Parse each match with BeautifulSoup
            for item_str in item_matches:
                try:
                    item_soup = BeautifulSoup(item_str, 'html.parser')
                    items.append(item_soup.find('item') or item_soup)
                except:
                    continue
        
        if not items:
            print("❌ No items found in RSS feed. The feed might be empty or have a different structure.")
            return []
        
        print(f"Processing {len(items)} items...")
        current_date = datetime.now()
        
        for i, item in enumerate(items):
            try:
                print(f"\n--- Processing item {i+1}/{len(items)} ---")
                
                # Extract basic information - handle both BeautifulSoup and ElementTree objects
                title = ""
                description = ""
                link = ""
                pub_date = ""
                
                if hasattr(item, 'find'):  # BeautifulSoup object
                    print("                                        beautifulsoup                                         ")
                    title_elem = item.find('title')
                    desc_elem = item.find('description')
                    link_elem = item.find('link')
                    date_elem = item.find('pubDate') or item.find('pubdate')
                    
                    title = title_elem.get_text() if title_elem else ""
                    description = desc_elem.get_text() if desc_elem else ""
                    link = link_elem.get_text() if link_elem else ""
                    pub_date = date_elem.get_text() if date_elem else ""
                else:  # ElementTree object
                    title_elem = item.find('title')
                    desc_elem = item.find('description') 
                    link_elem = item.find('link')
                    date_elem = item.find('pubDate')
                    
                    title = title_elem.text if title_elem is not None else ""
                    description = desc_elem.text if desc_elem is not None else ""
                    link = link_elem.text if link_elem is not None else ""
                    pub_date = date_elem.text if date_elem is not None else ""
                
                print(f"Title: {title[:100]}...")
                print(f"Description length: {len(description)}")
                
                # Skip if no meaningful content
                if not title or len(title.strip()) < 3:
                    print("❌ Skipping: No meaningful title")
                    continue
                
                # Clean up title and description
                title = re.sub(r'<[^>]+>', '', title).strip()
                if description:
                    description = re.sub(r'<[^>]+>', ' ', description)
                    description = re.sub(r'\s+', ' ', description).strip()
                
                # Combine title and description for analysis
                full_text = f"{title} {description}"
                
                # Extract date and time
                date_time = extract_datetime_from_text(full_text)
                print(f"Extracted date_time: {date_time}")
                
                # Check if event is in the future (if we can parse the date)
                event_date = parse_date_from_text(date_time)
                if event_date:
                    if event_date.date() < current_date.date():
                        print(f"❌ Skipping past event: {event_date.date()}")
                        continue
                    else:
                        print(f"✅ Future event: {event_date.date()}")
                else:
                    print("⚠️  Could not parse date, including anyway")
                
                # Extract other information
                price = extract_price_from_text(full_text)
                location = extract_location_from_text(full_text)
                kid_friendly = determine_kid_friendly(full_text, title)
                
                # Use link from RSS or construct from RSS URL
                event_url = link.strip() if link else ""
                
                # Fetch additional details from event page if we have a valid URL
                event_details = {}
                additional_text = ""
                if event_url and 'dclibrary.libnet.info' in event_url:
                    print(f"  Fetching details from: {event_url}")
                    event_details, additional_text = fetch_event_details(event_url)
                    if additional_text:
                        full_text += " " + additional_text
                        print(f"  Added {len(additional_text)} chars from event page")
                
                # Re-extract information with enhanced text
                if additional_text:
                    enhanced_date_time = extract_datetime_from_text(full_text)
                    enhanced_location = extract_location_from_text(full_text)
                    enhanced_kid_friendly = determine_kid_friendly(full_text, title)
                    
                    # Use enhanced data if it's better than what we had
                    if enhanced_date_time and not date_time:
                        date_time = enhanced_date_time
                    if enhanced_location and not location:
                        location = enhanced_location
                    if enhanced_kid_friendly and not kid_friendly:
                        kid_friendly = enhanced_kid_friendly
                
                # Use structured data from event details if available
                if 'age_group' in event_details:
                    age_group_text = event_details['age_group']
                    enhanced_kid_friendly = determine_kid_friendly(age_group_text, title)
                    if enhanced_kid_friendly:
                        kid_friendly = enhanced_kid_friendly
                        print(f"  Updated kid_friendly from age_group: {kid_friendly}")
                
                if 'location_detail' in event_details:
                    location_detail = event_details['location_detail']
                    enhanced_location = extract_location_from_text(location_detail)
                    if enhanced_location and not location:
                        location = enhanced_location
                        print(f"  Updated location from detail: {location}")
                
                print(f"Final - Price: {price}")
                print(f"Final - Location: {location}")
                print(f"Final - Kid-friendly: {kid_friendly}")
                print(f"Final - Date/time: {date_time}")
                
                # Create workshop data
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
                
                workshops.append(workshop_data)
                print(f"✅ Added workshop: {title[:50]}...")
                
            except Exception as e:
                print(f"❌ Error processing item {i+1}: {e}")
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
        
        for i, workshop in enumerate(workshops, 1):
            print(f"\nWorkshop {i}:")
            for key, value in workshop.items():
                # Format the output nicely
                display_value = value if value else "Not specified"
                if key == 'description' and len(display_value) > 100:
                    display_value = display_value[:100] + "..."
                print(f"  {key:12}: {display_value}")
        
        # Summary statistics
        print(f"\n📊 Summary:")
        print(f"Total events: {len(workshops)}")
        
        kid_friendly_count = sum(1 for w in workshops if w['kidfriendly'] == 'Yes')
        adult_only_count = sum(1 for w in workshops if w['kidfriendly'] == 'No')
        unknown_count = len(workshops) - kid_friendly_count - adult_only_count
        
        print(f"Kid-friendly: {kid_friendly_count}")
        print(f"Adult-only: {adult_only_count}")
        print(f"Unknown: {unknown_count}")
        
        with_location = sum(1 for w in workshops if w['location'])
        print(f"With location info: {with_location}")
        
        with_datetime = sum(1 for w in workshops if w['date_time'])
        print(f"With date/time info: {with_datetime}")
        
        # Save to JSON file
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