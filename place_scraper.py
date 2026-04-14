import os, requests, webbrowser, time, csv, io
from urllib.parse import urlparse
from dotenv import load_dotenv

# Load the API key from your .env file
load_dotenv()

def clean_url(url):
    """Strips tracking parameters (?utm...) from the website URL."""
    if not url: return ""
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

def get_root_domain(url):
    """Extracts the root domain from a URL (e.g. https://sub.example.com.au/path -> example.com.au)."""
    if not url: return ""
    try:
        parsed = urlparse(url)
        hostname = parsed.netloc.lower()
        # Remove www. prefix
        if hostname.startswith("www."):
            hostname = hostname[4:]
        return hostname
    except:
        return ""

def parse_address(formatted_address):
    """
    Splits a Google formatted address into: address_line, city, state.
    Google typically returns: 'Street, Suburb VIC POSTCODE, Australia'
    """
    if not formatted_address:
        return "", "", ""
    
    parts = [p.strip() for p in formatted_address.split(",")]
    
    # Last part is usually 'Australia'
    # Second to last is usually 'Suburb STATE POSTCODE' or 'STATE POSTCODE'
    # First part is street address
    
    state = ""
    city = ""
    address_line = ""
    
    au_states = ["VIC", "NSW", "QLD", "SA", "WA", "TAS", "NT", "ACT"]
    
    # Find the part containing the state code
    state_part_idx = None
    for i, part in enumerate(parts):
        for s in au_states:
            if f" {s} " in f" {part} " or part.strip().upper().startswith(s + " "):
                state = s
                state_part_idx = i
                # The city is whatever comes before the state code in this segment
                city_candidate = part.replace(s, "").strip()
                # Remove postcode (trailing digits)
                city_tokens = city_candidate.split()
                city = " ".join(t for t in city_tokens if not t.isdigit()).strip()
                break
        if state_part_idx is not None:
            break
    
    # Address line = everything before the state part
    if state_part_idx is not None and state_part_idx > 0:
        address_line = ", ".join(parts[:state_part_idx])
    elif state_part_idx == 0:
        address_line = ""
    else:
        address_line = formatted_address  # Fallback

    return address_line, city, state

def clean_business_name(raw_name):
    """Strips common suffixes/noise from business names."""
    if not raw_name:
        return ""
    name = raw_name.strip()
    # Remove trailing - Victoria, - VIC, - Melbourne etc.
    noise = [" - Victoria", " - VIC", " – Victoria", " – VIC", " | Victoria"]
    for n in noise:
        if name.endswith(n):
            name = name[: -len(n)].strip()
    return name

def extract_places_victorian_wide(category, limit=1000):
    api_key = os.getenv("GOOGLE_PLACES_API_KEY")
    url = "https://places.googleapis.com/v1/places:searchText"
    
    cities = [
        "Melbourne", "Geelong", "Ballarat", "Bendigo", "Shepparton", "Mildura",
        "Wodonga", "Warrnambool", "Traralgon", "Wangaratta", "Sunbury", "Werribee",
        "Dandenong", "Frankston", "Melton", "Ararat", "Bairnsdale", "Benalla",
        "Colac", "Echuca", "Hamilton", "Horsham", "Maryborough", "Portland",
        "Sale", "Swan Hill", "Wonthaggi", "Bacchus Marsh", "Healesville",
        "Lakes Entrance", "Morwell", "Moe", "Seymour", "Warragul", "Yarrawonga",
        "Castlemaine", "Epping", "Craigieburn", "Pakenham", "Cranbourne"
    ]
    
    all_results = []
    seen_ids = set()

    for city in cities:
        if len(all_results) >= limit:
            break
        print(f"🏙️ Searching in {city}... Total unique with websites: {len(all_results)}")
        
        next_token = None
        for page in range(3):
            headers = {
                "Content-Type": "application/json",
                "X-Goog-Api-Key": api_key,
                "X-Goog-FieldMask": "places.id,places.displayName,places.formattedAddress,places.websiteUri,nextPageToken"
            }
            data = {"textQuery": f"{category} in {city}, Victoria", "maxResultCount": 20}
            if next_token:
                data["pageToken"] = next_token

            try:
                response = requests.post(url, headers=headers, json=data)
                response.raise_for_status()
                res_json = response.json()
                places = res_json.get("places", [])

                for p in places:
                    address = p.get("formattedAddress", "")

                    # ✅ Filter: only Victorian, Australia results
                    if "VIC" not in address or "Australia" not in address:
                        continue

                    if p.get("id") not in seen_ids and "websiteUri" in p:
                        raw_name = p.get("displayName", {}).get("text", "")
                        clean_website = clean_url(p["websiteUri"])
                        address_line, city_parsed, state_parsed = parse_address(address)
                        root_domain = get_root_domain(clean_website)

                        p["_name"]         = clean_business_name(raw_name)
                        p["_address_line"] = address_line
                        p["_city"]         = city_parsed
                        p["_state"]        = state_parsed
                        p["_website"]      = clean_website
                        p["_root_domain"]  = root_domain

                        all_results.append(p)
                        seen_ids.add(p["id"])

                next_token = res_json.get("nextPageToken")
                if not next_token or len(all_results) >= limit:
                    break
                time.sleep(1.5)
            except Exception as e:
                print(f"❌ Error in {city}: {e}")
                break

    print(f"\n✅ Finished! Found {len(all_results)} unique Victorian results.")
    return all_results

def build_csv_data(results):
    """Builds CSV content as a string for embedding in HTML."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["#", "Business Name", "Address", "City", "State", "Website URL", "Root Domain"])
    for i, p in enumerate(results, 1):
        writer.writerow([
            i,
            p.get("_name", ""),
            p.get("_address_line", ""),
            p.get("_city", ""),
            p.get("_state", ""),
            p.get("_website", ""),
            p.get("_root_domain", ""),
        ])
    return output.getvalue()

def save_and_open_results(results):
    filename = "victoria_leads.html"
    csv_data = build_csv_data(results)

    rows_html = ""
    for i, p in enumerate(results, 1):
        name        = p.get("_name", "—")
        address     = p.get("_address_line", "—")
        city        = p.get("_city", "—")
        state       = p.get("_state", "—")
        website     = p.get("_website", "")
        root_domain = p.get("_root_domain", "—")

        website_cell = (
            f"<a href='{website}' target='_blank' style='color:#1a73e8;text-decoration:none;'>{website}</a>"
            f"<button onclick=\"navigator.clipboard.writeText('{website}'); this.innerText='✅'; setTimeout(()=>this.innerText='📋',1000)\" "
            f"style='cursor:pointer;margin-left:8px;border:none;background:#e8f0fe;border-radius:4px;padding:2px 6px;font-size:11px;'>📋</button>"
        ) if website else "—"

        rows_html += f"""
        <tr>
            <td style='color:#94a3b8;font-size:12px;'>{i}</td>
            <td><strong>{name}</strong></td>
            <td style='color:#64748b;font-size:13px;'>{address}</td>
            <td>{city}</td>
            <td><span style='background:#dbeafe;color:#1d4ed8;padding:2px 7px;border-radius:99px;font-size:12px;font-weight:600;'>{state}</span></td>
            <td style='font-size:12px;'>{website_cell}</td>
            <td style='font-family:monospace;font-size:12px;color:#475569;'>{root_domain}</td>
        </tr>"""

    # Escape CSV for JS string (escape backticks and backslashes)
    csv_escaped = csv_data.replace("\\", "\\\\").replace("`", "\\`")

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Victoria Leads</title>
    <link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600&family=DM+Mono&display=swap" rel="stylesheet">
    <style>
        *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: 'DM Sans', sans-serif;
            background: #f8fafc;
            color: #0f172a;
            padding: 40px 32px;
        }}
        .header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 28px;
            flex-wrap: wrap;
            gap: 16px;
        }}
        .header h1 {{
            font-size: 22px;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        .badge {{
            background: #0f172a;
            color: #f8fafc;
            font-size: 13px;
            font-weight: 500;
            padding: 3px 10px;
            border-radius: 99px;
        }}
        .export-btn {{
            background: #0f172a;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 8px;
            font-family: 'DM Sans', sans-serif;
            font-size: 14px;
            font-weight: 500;
            cursor: pointer;
            display: flex;
            align-items: center;
            gap: 8px;
            transition: background 0.15s;
        }}
        .export-btn:hover {{ background: #1e293b; }}
        .card {{
            background: white;
            border-radius: 14px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.07), 0 4px 16px rgba(0,0,0,0.04);
            overflow: hidden;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
        }}
        thead th {{
            background: #0f172a;
            color: #94a3b8;
            font-size: 11px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.06em;
            padding: 12px 16px;
            text-align: left;
            white-space: nowrap;
        }}
        tbody tr {{
            border-bottom: 1px solid #f1f5f9;
            transition: background 0.1s;
        }}
        tbody tr:last-child {{ border-bottom: none; }}
        tbody tr:hover {{ background: #f8fafc; }}
        td {{
            padding: 12px 16px;
            font-size: 14px;
            vertical-align: middle;
        }}
        .search-bar {{
            padding: 0 0 20px 0;
        }}
        .search-bar input {{
            font-family: 'DM Sans', sans-serif;
            font-size: 14px;
            padding: 10px 16px;
            border: 1.5px solid #e2e8f0;
            border-radius: 8px;
            width: 320px;
            outline: none;
            transition: border-color 0.15s;
        }}
        .search-bar input:focus {{ border-color: #1a73e8; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>
            📍 Victoria Property Manager Leads
            <span class="badge">{len(results)} results</span>
        </h1>
        <button class="export-btn" onclick="exportCSV()">
            ⬇ Export CSV
        </button>
    </div>

    <div class="search-bar">
        <input type="text" id="searchInput" placeholder="🔍 Filter by name, city, domain..." oninput="filterTable()">
    </div>

    <div class="card">
        <table id="leadsTable">
            <thead>
                <tr>
                    <th>#</th>
                    <th>Business Name</th>
                    <th>Address</th>
                    <th>City</th>
                    <th>State</th>
                    <th>Website URL</th>
                    <th>Root Domain</th>
                </tr>
            </thead>
            <tbody id="tableBody">
                {rows_html}
            </tbody>
        </table>
    </div>

    <script>
        const csvData = `{csv_escaped}`;

        function exportCSV() {{
            const blob = new Blob([csvData], {{ type: 'text/csv;charset=utf-8;' }});
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'victoria_leads.csv';
            a.click();
            URL.revokeObjectURL(url);
        }}

        function filterTable() {{
            const query = document.getElementById('searchInput').value.toLowerCase();
            const rows = document.querySelectorAll('#tableBody tr');
            rows.forEach(row => {{
                const text = row.textContent.toLowerCase();
                row.style.display = text.includes(query) ? '' : 'none';
            }});
        }}
    </script>
</body>
</html>"""

    with open(filename, "w", encoding="utf-8") as f:
        f.write(html_content)

    file_path = os.path.abspath(filename)
    webbrowser.open("file://" + file_path)
    print(f"✅ Table opened in browser: {filename}")

if __name__ == "__main__":
    results = extract_places_victorian_wide("property manager", limit=1000)
    if results:
        save_and_open_results(results)
    else:
        print("No results found. Verify your API Key and check 'Places API (New)' settings.")