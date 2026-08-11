import re
import urllib.parse
import xml.etree.ElementTree as ET

import requests
from bs4 import BeautifulSoup

# Standard headers to mimic a real browser request
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
}

def get_jobstreet_domain(location):
    """Determines the appropriate JobStreet/SEEK domain based on location."""
    loc_lower = location.lower()
    if "malaysia" in loc_lower:
        return "https://my.jobstreet.com"
    elif "philippines" in loc_lower:
        return "https://ph.jobstreet.com"
    elif "indonesia" in loc_lower:
        return "https://id.jobstreet.com"
    # Default to Singapore
    return "https://sg.jobstreet.com"

def fetch_job_description(url, platform):
    """Fetches the full job description from the given URL."""
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        if response.status_code != 200:
            return ""

        soup = BeautifulSoup(response.text, "html.parser")
        
        if platform == "linkedin":
            # LinkedIn guest job page JD selectors
            jd_elem = soup.select_one(".show-more-less-html__markup") or soup.select_one(".description__text")
            if jd_elem:
                return jd_elem.get_text(separator="\n").strip()
                
        elif platform == "indeed":
            # Indeed JD selector
            jd_elem = soup.find(id="jobDescriptionText")
            if jd_elem:
                return jd_elem.get_text(separator="\n").strip()
                
        elif platform == "jobstreet":
            # JobStreet (SEEK) JD selectors
            jd_elem = (
            soup.select_one('[data-automation="jobDescription"]')
            or soup.select_one('[data-automation="jobAdDetails"]')
        )
            if jd_elem:
                return jd_elem.get_text(separator="\n").strip()
                
        # Generic fallback
        body_text = soup.body.get_text(separator="\n") if soup.body else ""
        return body_text[:2000] # Return snippet if selectors fail
    except Exception as e:
        print(f"Error fetching description from {url}: {e}")
        return ""

def scrape_linkedin(keyword, location):
    """Scrapes LinkedIn guest jobs API."""
    jobs = []
    try:
        keyword_enc = urllib.parse.quote(keyword)
        location_enc = urllib.parse.quote(location)
        # LinkedIn guest jobs search endpoint
        url = f"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords={keyword_enc}&location={location_enc}&start=0"
        
        response = requests.get(url, headers=HEADERS, timeout=15)
        if response.status_code != 200:
            print(f"LinkedIn search returned status code {response.status_code}")
            return jobs

        soup = BeautifulSoup(response.text, "html.parser")
        job_cards = soup.select("li")
        
        for card in job_cards:
            title_elem = card.select_one(".base-search-card__title")
            company_elem = (
            card.select_one(".base-search-card__subtitle a")
            or card.select_one(".base-search-card__subtitle")
        )
            link_elem = card.select_one(".base-card__full-link")
            loc_elem = card.select_one(".job-search-card__location")
            
            if not title_elem or not link_elem:
                continue
                
            title = title_elem.get_text().strip()
            company = company_elem.get_text().strip() if company_elem else "Unknown Company"
            link = link_elem.get("href", "").split("?")[0] # Clean query params
            job_location = loc_elem.get_text().strip() if loc_elem else location
            
            # Extract LinkedIn Job ID from link (guest URLs end with -<digits>)
            job_id_match = re.search(r"-(\d+)$", link)
            job_id = f"linkedin_{job_id_match.group(1)}" if job_id_match else f"linkedin_{hash(link)}"
            
            # LinkedIn doesn't show snippet in search - will be fetched by main.py
            jobs.append({
                "id": job_id,
                "title": title,
                "company": company,
                "location": job_location,
                "url": link,
                "platform": "linkedin",
                "snippet": ""
            })
    except Exception as e:
        print(f"Error scraping LinkedIn: {e}")
    return jobs

def get_indeed_domain(location):
    """Determines the appropriate Indeed domain based on location."""
    loc_lower = location.lower()
    if "malaysia" in loc_lower or "penang" in loc_lower or "kl" in loc_lower or "kuala lumpur" in loc_lower:
        return "https://my.indeed.com"
    elif "singapore" in loc_lower:
        return "https://sg.indeed.com"
    elif "philippines" in loc_lower:
        return "https://ph.indeed.com"
    elif "indonesia" in loc_lower:
        return "https://id.indeed.com"
    # Default to global
    return "https://www.indeed.com"

def scrape_indeed(keyword, location):
    """Scrapes Indeed jobs using RSS feeds (more stable)."""
    jobs = []
    try:
        keyword_enc = urllib.parse.quote(keyword)
        location_enc = urllib.parse.quote(location)
        
        # Get appropriate domain based on location
        domain = get_indeed_domain(location)
        url = f"{domain}/rss?q={keyword_enc}&l={location_enc}"
        
        response = requests.get(url, headers=HEADERS, timeout=15)
        if response.status_code != 200:
            # Fallback to other domains
            fallback_domains = ["https://sg.indeed.com", "https://my.indeed.com", "https://www.indeed.com"]
            for fallback_url in fallback_domains:
                url = f"{fallback_url}/rss?q={keyword_enc}&l={location_enc}"
                response = requests.get(url, headers=HEADERS, timeout=15)
                if response.status_code == 200:
                    break
            else:
                print(f"Indeed RSS returned status code {response.status_code} for all domains")
                return jobs
                
        # Parse trusted RSS XML from Indeed domains (fixed URLs in config/list).
        root = ET.fromstring(response.content)  # nosec B314
        
        for item in root.findall(".//item"):
            title_elem = item.find("title")
            link_elem = item.find("link")
            desc_elem = item.find("description")
            guid_elem = item.find("guid")
            
            if title_elem is None or link_elem is None:
                continue
                
            full_title = title_elem.text
            # Indeed RSS title is usually "Job Title - Company - Location"
            parts = [p.strip() for p in full_title.split("-")]
            title = parts[0]
            company = parts[1] if len(parts) > 1 else "Unknown"
            job_location = parts[2] if len(parts) > 2 else location
            
            link = link_elem.text.split("?")[0] if link_elem.text else ""
            guid = guid_elem.text if guid_elem is not None else link
            job_id = f"indeed_{guid.split('/')[-1] if '/' in guid else hash(guid)}"
            
            jobs.append({
                "id": job_id,
                "title": title,
                "company": company,
                "location": job_location,
                "url": link,
                "platform": "indeed",
                "snippet": desc_elem.text if desc_elem is not None else ""
            })
    except Exception as e:
        print(f"Error scraping Indeed: {e}")
    return jobs

def scrape_jobstreet(keyword, location):
    """Scrapes JobStreet SEEK jobs."""
    jobs = []
    try:
        domain = get_jobstreet_domain(location)
        keyword_enc = urllib.parse.quote(keyword)
        
        # JobStreet search page
        url = f"{domain}/jobs?keywords={keyword_enc}"
        
        response = requests.get(url, headers=HEADERS, timeout=15)
        if response.status_code != 200:
            print(f"JobStreet search returned status code {response.status_code}")
            return jobs
            
        soup = BeautifulSoup(response.text, "html.parser")
        
        # SEEK / Jobstreet renders jobs as articles with automation attributes
        job_articles = soup.find_all("article", attrs={"data-automation": "normalJob"})
        
        for article in job_articles:
            title_elem = article.find("a", attrs={"data-automation": "jobTitle"})
            company_elem = article.find("a", attrs={"data-automation": "jobCompany"})
            loc_elem = (
            article.find("span", attrs={"data-automation": "jobLocation"})
            or article.find("a", attrs={"data-automation": "jobLocation"})
        )
            
            if not title_elem:
                continue
                
            title = title_elem.get_text().strip()
            company = company_elem.get_text().strip() if company_elem else "Unknown Company"
            link = title_elem.get("href", "")
            if not link.startswith("http"):
                link = f"{domain}{link}"
            link = link.split("?")[0]
            
            job_location = loc_elem.get_text().strip() if loc_elem else location
            
            # Extract job ID
            job_id_match = re.search(r"job/(\d+)", link)
            job_id = f"jobstreet_{job_id_match.group(1)}" if job_id_match else f"jobstreet_{hash(link)}"
            
            # Extract snippet/description from search results
            snippet_elem = (
            article.find("span", attrs={"data-automation": "jobDescription"})
            or article.find("div", class_=lambda x: x and "description" in x.lower())
        )
            snippet = snippet_elem.get_text().strip()[:500] if snippet_elem else ""
            
            jobs.append({
                "id": job_id,
                "title": title,
                "company": company,
                "location": job_location,
                "url": link,
                "platform": "jobstreet",
                "snippet": snippet
            })
    except Exception as e:
        print(f"Error scraping JobStreet: {e}")
    return jobs

def get_all_jobs(keywords, locations, platforms=None):
    """Aggregates scraping jobs from enabled platforms concurrently."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    import config
    
    all_jobs = []
    seen_urls = set()
    
    # Get platform settings from config if not provided
    if platforms is None:
        settings = config.load_settings()
        platforms = settings.get("search", {}).get("platforms", {
            "indeed": True,
            "linkedin": True,
            "jobstreet": True
        })
    
    tasks = []
    for loc in locations:
        for kw in keywords:
            tasks.append((kw, loc))
            
    def run_scrapers(kw, loc):
        """Run all platform scrapers for a keyword/location combo in parallel."""
        from concurrent.futures import ThreadPoolExecutor as InnerPool
        from concurrent.futures import as_completed as inner_completed
        
        platform_jobs = []
        platform_tasks = []
        
        if platforms.get("indeed", True):
            platform_tasks.append(("indeed", lambda: scrape_indeed(kw, loc)))
        if platforms.get("jobstreet", True):
            platform_tasks.append(("jobstreet", lambda: scrape_jobstreet(kw, loc)))
        if platforms.get("linkedin", True):
            platform_tasks.append(("linkedin", lambda: scrape_linkedin(kw, loc)))
        
        with InnerPool(max_workers=len(platform_tasks)) as inner_executor:
            inner_futures = {inner_executor.submit(fn): name for name, fn in platform_tasks}
            for inner_future in inner_completed(inner_futures):
                name = inner_futures[inner_future]
                try:
                    platform_jobs.extend(inner_future.result())
                except Exception as e:
                    print(f"  Error scraping {name} for '{kw}' in '{loc}': {e}")
        
        return platform_jobs

    print(f"Starting concurrent search scan for {len(tasks)} combinations (up to 8 parallel workers)...")
    print(f"Enabled platforms: {[k for k, v in platforms.items() if v]}")
    
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(run_scrapers, kw, loc): (kw, loc) for kw, loc in tasks}
        for future in as_completed(futures):
            kw, loc = futures[future]
            try:
                results = future.result()
                all_jobs.extend(results)
                print(f"Completed scan for '{kw}' in '{loc}': found {len(results)} jobs.")
            except Exception as e:
                print(f"Error scanning '{kw}' in '{loc}': {e}")
            
    # Remove in-memory duplicate URLs
    unique_jobs = []
    for job in all_jobs:
        if job["url"] not in seen_urls:
            seen_urls.add(job["url"])
            unique_jobs.append(job)
            
    return unique_jobs

if __name__ == "__main__":
    # Test Run
    test_jobs = get_all_jobs(["Python Developer"], ["Singapore"])
    print(f"Total Unique Jobs Found: {len(test_jobs)}")
    for j in test_jobs[:3]:
        print(f"- {j['title']} at {j['company']} ({j['platform']}): {j['url']}")
