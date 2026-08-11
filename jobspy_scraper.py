"""
JobSpy-based scraper - replaces the old HTML scraper with a more reliable library.
Supports LinkedIn, Indeed, Glassdoor, Google, ZipRecruiter.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from jobspy import scrape_jobs as jobspy_scrape


def scrape_with_jobspy(keyword, location, sites=None, max_results=50):
    """
    Scrape jobs using JobSpy library.
    Returns jobs in the same format as the old scraper.
    """
    if sites is None:
        sites = ["indeed", "linkedin"]

    try:
        results = jobspy_scrape(
            site_name=sites,
            search_term=keyword,
            location=location,
            results_wanted=max_results,
            country_indeed="Malaysia",
            verbose=0,
        )

        jobs = []
        if results is not None and hasattr(results, 'iterrows'):
            for _, row in results.iterrows():
                job = {
                    "id": str(row.get("job_url", hash(keyword))),
                    "title": str(row.get("title", "")),
                    "company": str(row.get("company", "")),
                    "location": _format_location(row),
                    "url": str(row.get("job_url", "")),
                    "platform": str(row.get("site", "unknown")),
                    "snippet": _clean_description(str(row.get("description", ""))),
                    "salary": _parse_salary(row),
                }
                if job["title"] and job["url"]:
                    jobs.append(job)

        print(f"JobSpy found {len(jobs)} jobs for '{keyword}' in '{location}'")
        return jobs

    except Exception as e:
        print(f"JobSpy error: {e}")
        return []


def _format_location(row):
    """Format location from JobSpy row."""
    parts = []
    city = str(row.get("city", "")).strip()
    state = str(row.get("state", "")).strip()
    country = str(row.get("country", "")).strip()

    if city and city != "None":
        parts.append(city)
    if state and state != "None":
        parts.append(state)
    if country and country != "None":
        parts.append(country)

    return ", ".join(parts) if parts else str(row.get("location", ""))


def _clean_description(desc):
    """Clean and truncate description."""
    if not desc or desc == "None":
        return ""
    # Remove excessive whitespace
    import re
    desc = re.sub(r'\s+', ' ', desc).strip()
    # Truncate to 2000 chars
    if len(desc) > 2000:
        desc = desc[:2000] + "..."
    return desc


def _parse_salary(row):
    """Parse salary from JobSpy row."""
    min_amt = row.get("min_amount")
    max_amt = row.get("max_amount")

    if min_amt and max_amt:
        try:
            return (float(min_amt) + float(max_amt)) / 2
        except (ValueError, TypeError):
            pass
    elif min_amt:
        try:
            return float(min_amt)
        except (ValueError, TypeError):
            pass
    return None


def get_all_jobs(keywords, locations, platforms=None):
    """
    Aggregate jobs from multiple keywords and locations.
    Compatible with the old scraper's interface.
    """
    all_jobs = []
    seen_urls = set()

    if platforms is None:
        platforms = ["indeed", "linkedin", "jobstreet"]

    # Map platform names to JobSpy names (JobSpy doesn't support jobstreet)
    site_map = {
        "indeed": "indeed",
        "linkedin": "linkedin",
        "glassdoor": "glassdoor",
        "google": "google",
        "ziprecruiter": "ziprecruiter",
    }
    sites = [site_map.get(p, p) for p in platforms if p in site_map]

    for keyword in keywords:
        for location in locations:
            try:
                jobs = scrape_with_jobspy(keyword, location, sites=sites)
                for job in jobs:
                    if job["url"] not in seen_urls:
                        seen_urls.add(job["url"])
                        all_jobs.append(job)
            except Exception as e:
                print(f"Error scanning '{keyword}' in '{location}': {e}")

    return all_jobs


# Keep backward compatibility
def scrape_indeed(keyword, location):
    return scrape_with_jobspy(keyword, location, sites=["indeed"])

def scrape_jobstreet(keyword, location):
    # JobSpy doesn't support jobstreet - use Indeed as fallback
    return scrape_with_jobspy(keyword, location, sites=["indeed"])

def scrape_linkedin(keyword, location):
    return scrape_with_jobspy(keyword, location, sites=["linkedin"])


if __name__ == "__main__":
    jobs = scrape_with_jobspy("Junior RPA Developer", "Penang, Malaysia")
    print(f"\nFound {len(jobs)} jobs")
    for j in jobs[:5]:
        print(f"  {j['title']} @ {j['company']} ({j['location']})")
