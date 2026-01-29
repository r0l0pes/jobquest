
import time
from duckduckgo_search import DDGS

import argparse

from rich.console import Console
from rich.table import Table

console = Console()

def parse_markdown_table(file_path: str):
    """Parses the markdown file to extract Company and Website."""
    with open(file_path, 'r') as f:
        content = f.read()
    
    companies = []
    lines = content.split('\n')
    for line in lines:
        if line.strip().startswith('|') and '---|---' not in line and 'Startup' not in line:
            parts = [p.strip() for p in line.split('|')]
            if len(parts) >= 8:
                name = parts[1]
                website = parts[7]
                if website and website != '—':
                    companies.append({"name": name, "url": website})
    return companies

def check_jobs_ddg(company):
    """
    Uses DuckDuckGo to find Product Manager jobs.
    """
    domain = company['url'].replace('www.', '').replace('https://', '').replace('http://', '').strip('/').split('/')[0]
    name = company['name']
    

    # Expanded list of target roles
    target_roles = [
        "product manager", "senior product manager", "growth product manager", 
        "ai product manager", "platform product manager", "technical product manager",
        "product owner" 
    ]
    
    hits = []
    
    try:
        ddgs = DDGS()
        
        # Broad Search with exclusions
        q = f'{name} "product manager" jobs -site:linkedin.com -site:glassdoor.com -site:xing.com -site:kununu.com -site:crunchbase.com'
        
        # Increased results fetch to cast a wider net
        results = list(ddgs.text(q, max_results=5))
        
        known_ats = ["greenhouse.io", "lever.co", "personio", "ashbyhq", "workable", "bamboohr", "join.com", "recruitee", "jobs"]
        
        for r in results:
            url = r['href'].lower()
            title = r['title'].lower()
            snippet = r['body'].lower()
            
            # Check for target roles in Title or Snippet
            role_match = any(role in title for role in target_roles) or any(role in snippet for role in target_roles)
            
            if not role_match:
                continue

            # Heuristic 1: URL matches company domain
            if domain in url:
                hits.append(r['href'])
                
            # Heuristic 2: URL is a known ATS and mentions company
            elif any(ats in url for ats in known_ats):
                hits.append(r['href'])
                
            # Heuristic 3: Strong Title match
            elif role_match and name.lower() in title:
                hits.append(r['href'])

        # Remove duplicates
        hits = list(set(hits))

        if hits:
            return f"Found {len(hits)} hits", hits
        
        # Unverified check
        if results:
             if any(role in results[0]['body'].lower() for role in target_roles):
                 return "Potentially Hiring (Unverified)", [results[0]['href']]
        
        return "No results", []

    except Exception as e:
        return f"Error: {str(e)[:20]}", []

def main(limit: int = 304, start: int = 0):
    """
    Checks startups for Product Manager roles using DuckDuckGo.
    """
    md_file = "germany_startups_by_city_304.md"
    companies = parse_markdown_table(md_file)
    
    target_companies = companies[start:start+limit]
    console.print(f"Checking {len(target_companies)} companies (Index {start} to {start+limit})...")
    
    results = []
    
    # Prepare output file
    with open("found_jobs.md", "w") as f:
        f.write("# Potential Product Manager Jobs\n\n| Company | Status | Link |\n|---|---|---|\n")

    for i, company in enumerate(target_companies):
        status, urls = check_jobs_ddg(company)
        results.append({**company, "status": status, "urls": urls})
        
        color = "green" if urls else "red"
        if "Unverified" in status: color = "yellow"
        
        console.print(f"[{start+i+1}/{start+limit}] {company['name']}: [{color}]{status}[/{color}]")
        
        if urls:
            # Append to file immediately so we don't lose progress
            top_url = urls[0]
            with open("found_jobs.md", "a") as f:
                f.write(f"| {company['name']} | {status} | {top_url} |\n")
            console.print(f"   -> {top_url}")
        
        time.sleep(1.5) # Slightly longer delay for safety


if __name__ == "__main__":
    print("Script started...")
    main(limit=304)
