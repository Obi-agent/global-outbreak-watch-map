#!/usr/bin/env python3
import email.utils
import hashlib
import html
import json
import os
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "gow_data.geojson"
SOURCES_OUT = ROOT / "gow_sources.json"
WINDOW_DAYS = int(os.environ.get("GOW_SIGNAL_WINDOW_DAYS", "210"))
MAX_ITEMS = int(os.environ.get("GOW_MAX_ITEMS_PER_SOURCE", "45"))
UA = "GlobalOutbreakWatch/1.0 public-source disease signal monitor"

SOURCES = [
    {"id":"who-don","name":"WHO Disease Outbreak News","type":"Global authority","adapter":"who","url":"https://cms.who.int/api/hubs/diseaseoutbreaknews?%24top=100&%24orderby=PublicationDateAndTime%20desc"},
    {"id":"cdc-travel","name":"CDC Travel Health Notices","type":"National authority","adapter":"rss","url":"https://wwwnc.cdc.gov/travel/rss/notices.xml"},
    {"id":"cdc-us-outbreaks","name":"CDC U.S. Outbreak List","type":"National authority","adapter":"html","url":"https://www.cdc.gov/outbreaks/rss/us-outbreaks.html","default":"United States"},
    {"id":"cdc-int-outbreaks","name":"CDC International Outbreak List","type":"National authority","adapter":"html","url":"https://www.cdc.gov/outbreaks/rss/int-outbreaks.html"},
    {"id":"ecdc-cdtr","name":"ECDC Communicable Disease Threats Report","type":"Regional authority","adapter":"rss","url":"https://www.ecdc.europa.eu/en/taxonomy/term/1505/feed","default":"EU/EEA"},
    {"id":"paho-alerts","name":"PAHO Epidemiological Alerts","type":"Regional authority","adapter":"html","url":"https://www.paho.org/en/epidemiological-alerts-and-updates","default":"Americas Region","must":"/en/documents/"},
    {"id":"ukhsa-news","name":"UKHSA News and Communications","type":"National authority","adapter":"rss","url":"https://www.gov.uk/search/news-and-communications.atom?organisations%5B%5D=uk-health-security-agency","default":"United Kingdom"},
    {"id":"ukhsa-monitoring","name":"UKHSA Outbreaks Under Monitoring","type":"National authority","adapter":"html","url":"https://www.gov.uk/government/publications/outbreaks-under-monitoring-in-2026","must":"/government/publications/outbreaks-under-monitoring-in-2026/"},
]

COORDS = {
    "Algeria":(1.66,28.03),"Argentina":(-63.62,-38.42),"Bangladesh":(90.36,23.69),"Bolivia":(-63.59,-16.29),"Brazil":(-51.93,-14.24),"Cambodia":(104.99,12.57),"Canada":(-106.35,56.13),"China":(104.2,35.86),"Colombia":(-74.3,4.57),"Comoros":(43.87,-11.88),"Congo":(15.83,-0.23),"Democratic Republic of the Congo":(21.76,-4.04),"Ethiopia":(40.49,9.15),"France":(2.21,46.23),"Guinea":(-9.7,9.95),"India":(78.96,20.59),"Italy":(12.57,41.87),"Madagascar":(46.87,-18.77),"Mexico":(-102.55,23.63),"Nigeria":(8.68,9.08),"Saudi Arabia":(45.08,23.89),"Senegal":(-14.45,14.5),"South Africa":(22.94,-30.56),"Spain":(-3.75,40.46),"Uganda":(32.29,1.37),"United Kingdom":(-3.44,55.38),"United States":(-98.58,39.83),"Vietnam":(108.28,14.06),"Viet Nam":(108.28,14.06)
}
REGIONS = {"Global":(15,10),"Americas Region":(-74,5),"EU/EEA":(14,50),"Africa Region":(20,2.5),"European Region":(15,50),"Eastern Mediterranean Region":(44,25),"South-East Asia Region":(89,16),"Western Pacific Region":(136,10)}
ALIASES = {"USA":"United States","U.S.":"United States","US":"United States","United States of America":"United States","UK":"United Kingdom","DRC":"Democratic Republic of the Congo","Democratic Republic of Congo":"Democratic Republic of the Congo"}
DISEASES = [(r"h5n1|bird flu","Avian influenza A(H5N1)"),(r"h7n9","Avian influenza A(H7N9)"),(r"h9n2","Avian influenza A(H9N2)"),(r"avian influenza","Avian influenza"),(r"cholera","Cholera"),(r"mpox|monkeypox","Mpox"),(r"measles","Measles"),(r"dengue","Dengue"),(r"yellow fever","Yellow fever"),(r"hantavirus","Hantavirus"),(r"marburg","Marburg virus disease"),(r"ebola|sudan virus disease","Ebola virus disease"),(r"nipah","Nipah virus"),(r"polio|poliovirus","Poliovirus"),(r"middle east respiratory syndrome|\bmers\b","MERS"),(r"crimean-congo|cchf","Crimean-Congo haemorrhagic fever"),(r"lassa fever","Lassa fever"),(r"rift valley fever","Rift Valley fever"),(r"chikungunya","Chikungunya"),(r"oropouche","Oropouche virus disease"),(r"pertussis|whooping cough","Pertussis"),(r"seasonal influenza","Seasonal influenza"),(r"covid-19|sars-cov-2","COVID-19"),(r"listeria","Listeriosis"),(r"salmonella","Salmonellosis"),(r"botulism","Botulism"),(r"diphtheria","Diphtheria")]
RELEVANT = re.compile(r"outbreak|epidemiolog|alert|update|disease|infection|virus|fever|cholera|mpox|measles|dengue|influenza|marburg|ebola|hantavirus|polio|pertussis|salmonella|listeria|botulism|chikungunya|oropouche|nipah|mers|cchf", re.I)
EXCLUDE = re.compile(r"glp-1|methanol|chemical|radionuclear|heatwave|heat wave|poisoning", re.I)

def clean(value):
    value = html.unescape(str(value or ""))
    value = re.sub(r"<script\b.*?</script>|<style\b.*?</style>", " ", value, flags=re.I|re.S)
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()

def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=24) as res:
        return res.read().decode(res.headers.get_content_charset() or "utf-8", errors="replace")

def dt(value):
    raw = clean(value)
    if not raw:
        return None
    try:
        parsed = email.utils.parsedate_to_datetime(raw)
        if parsed:
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except Exception:
        pass
    for fmt in ("%m/%d/%Y %H:%M:%S","%Y-%m-%d","%d %B %Y","%d %b %Y","%B %d, %Y","%b %d, %Y","%B %Y"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    m = re.search(r"\b(\d{1,2})\s+(Jan\w*|Feb\w*|Mar\w*|Apr\w*|May|Jun\w*|Jul\w*|Aug\w*|Sep\w*|Oct\w*|Nov\w*|Dec\w*)\s+(\d{4})\b", raw, re.I)
    return dt(" ".join(m.groups())) if m else None

def iso(value):
    return value.astimezone(timezone.utc).date().isoformat() if value else ""

def rss_items(source, text):
    root = ET.fromstring(text.encode("utf-8"))
    out = []
    for item in root.findall(".//item"):
        title = clean(item.findtext("title")); summary = clean(item.findtext("description") or item.findtext("summary"))
        link = clean(item.findtext("link")) or source["url"]
        out.append((title, summary, link, dt(item.findtext("pubDate") or item.findtext("published") or item.findtext("updated"))))
    ns = {"a":"http://www.w3.org/2005/Atom"}
    for entry in root.findall(".//a:entry", ns):
        title = clean(entry.findtext("a:title", namespaces=ns)); summary = clean(entry.findtext("a:summary", namespaces=ns) or entry.findtext("a:content", namespaces=ns))
        link_node = entry.find("a:link[@href]", ns) or entry.find("a:link", ns)
        link = urllib.parse.urljoin(source["url"], link_node.get("href")) if link_node is not None and link_node.get("href") else source["url"]
        out.append((title, summary, link, dt(entry.findtext("a:updated", namespaces=ns) or entry.findtext("a:published", namespaces=ns))))
    return [x for x in out if x[0]]

def html_items(source, text):
    out = []
    for m in re.finditer(r"<a\s[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", text, re.I|re.S):
        href, body = m.groups(); title = clean(body)
        url = urllib.parse.urljoin(source["url"], html.unescape(href or ""))
        if len(title) < 8 or not RELEVANT.search(title):
            continue
        if source.get("must") and source["must"].lower() not in url.lower():
            continue
        context = clean(text[max(0,m.start()-280):min(len(text),m.end()+420)])
        out.append((title, context, url, dt(context)))
    return out

def who_items(source, text):
    data = json.loads(text); values = data.get("value", [])
    out = []
    for e in values:
        title = clean(e.get("Title") or e.get("OverrideTitle")); summary = clean(e.get("Summary") or e.get("Overview") or e.get("Assessment") or e.get("Advice"))
        path = str(e.get("ItemDefaultUrl") or "").lstrip("/")
        url = path if path.startswith("http") else urllib.parse.urljoin("https://www.who.int/emergencies/disease-outbreak-news/item/", path)
        out.append((title, summary, url, dt(e.get("PublicationDateAndTime") or e.get("PublicationDate"))))
    return sorted([x for x in out if x[0]], key=lambda x: x[3] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)

def disease(text):
    text = clean(re.sub(r"^Level\s+\d+\s*[-:]\s*", "", text, flags=re.I))
    for pat, name in DISEASES:
        if re.search(pat, text, re.I):
            return name
    guess = re.split(r"\s[-:|]\s|\bin\b", text, maxsplit=1, flags=re.I)[0]
    guess = re.sub(r"\b(epidemiological|alert|update|outbreak|disease outbreak news)\b", "", guess, flags=re.I)
    return clean(guess)[:80] or "Disease signal"

def places(text, default=None):
    hay = " " + re.sub(r"[-_/]", " ", clean(text)) + " "
    found = []
    for alias, canonical in ALIASES.items():
        if re.search(rf"(?<![A-Za-z]){re.escape(alias)}(?![A-Za-z])", hay, re.I):
            found.append(canonical)
    for country in COORDS:
        if re.search(rf"(?<![A-Za-z]){re.escape(country)}(?![A-Za-z])", hay, re.I):
            found.append(country)
    if not found:
        for region, pat in (("Americas Region",r"americas|latin america|caribbean"),("Africa Region",r"africa|african region"),("EU/EEA",r"\beu/eea\b|european union|\beu\b"),("European Region",r"european region|europe"),("Eastern Mediterranean Region",r"eastern mediterranean"),("South-East Asia Region",r"south-east asia|southeast asia"),("Western Pacific Region",r"western pacific"),("Global",r"global|multi-country|multicountry|worldwide")):
            if re.search(pat, hay, re.I): found.append(region); break
    if not found and default: found.append(default)
    if not found: found.append("Global")
    return list(dict.fromkeys(found))[:6]

def severity(name, text):
    low = text.lower()
    if re.search(r"public health emergency of international concern|\bpheic\b|sustained human-to-human", low): return "Critical"
    if re.search(r"marburg|ebola|nipah|cchf|crimean-congo|h5n1|cholera|lassa", name, re.I): return "High"
    if re.search(r"death|fatal|haemorrhagic|hemorrhagic|hospitali[sz]ed", low): return "High"
    if re.search(r"mpox|measles|dengue|yellow fever|hantavirus|polio|mers|chikungunya|oropouche|pertussis|salmonella|listeria|botulism", name, re.I): return "Moderate"
    return "Low"

def status(title, summary):
    low = f"{title} {summary}".lower()
    if re.search(r"\bclosed\b|declared an end|declared over|end of the outbreak|resolved", low): return "Closed"
    if re.search(r"monitor|update|situation report|surveillance|weekly", low): return "Monitoring"
    return "Open"

def coord(place):
    place = ALIASES.get(place, place)
    return COORDS.get(place) or REGIONS.get(place) or REGIONS["Global"]

def feature(source, title, summary, url, when, place, offset, now):
    text = f"{title} {summary}"; name = disease(text); lon, lat = coord(place)
    h = hashlib.sha1(f"{source['id']}|{url}|{place}|{name}".encode()).hexdigest()[:10]
    when = when or now
    snap = clean(summary or title)
    if len(snap) > 540: snap = snap[:540].rsplit(" ",1)[0] + "..."
    return {"type":"Feature","properties":{"Outbreak_ID":f"{iso(when)}-{source['id']}-{h}","Threat":name,"Disease":name,"Country":place,"Location_Label":place,"Status":status(title, summary),"Signal_Status":status(title, summary),"Severity":severity(name, text),"Date_First_Noted":iso(when),"Date_Last_Updated":iso(when),"Source_Name":source["name"],"Source_Type":source["type"],"Source_URL":url,"Confidence":"Automated extraction from linked public authority source","Situation_Snapshot":snap,"Travel_Health_Takeaways":"Verify case counts, local restrictions and clinical guidance with the linked authority before operational use.","Title":title,"Generated_At":now.isoformat()},"geometry":{"type":"Point","coordinates":[lon + offset*0.12, lat + offset*0.08]}}

def main():
    now = datetime.now(timezone.utc); feats = []; seen = set(); statuses = []
    for source in SOURCES:
        start = time.time(); st = {"id":source["id"],"name":source["name"],"type":source["type"],"url":source["url"],"status":"ok","items_seen":0,"features_added":0,"elapsed_seconds":0.0}
        try:
            text = fetch(source["url"])
            items = who_items(source, text) if source["adapter"] == "who" else rss_items(source, text) if source["adapter"] == "rss" else html_items(source, text)
            st["items_seen"] = len(items); accepted = 0
            for title, summary, url, when in items:
                if accepted >= MAX_ITEMS: break
                alltext = f"{title} {summary}"
                if EXCLUDE.search(alltext) or not RELEVANT.search(alltext): continue
                if when and (now - when).days > WINDOW_DAYS: continue
                for offset, place in enumerate(places(alltext, source.get("default"))):
                    f = feature(source, title, summary, url, when, place, offset, now)
                    key = (f["properties"]["Threat"].lower(), f["properties"]["Country"].lower(), f["properties"]["Source_URL"].lower())
                    if key in seen: continue
                    seen.add(key); feats.append(f); st["features_added"] += 1
                accepted += 1
        except Exception as exc:
            st["status"] = "error"; st["error"] = str(exc)[:220]
        st["elapsed_seconds"] = round(time.time() - start, 2); statuses.append(st)
    if not feats:
        raise SystemExit("No features generated; refusing to overwrite data")
    ranks = {"Critical":4,"High":3,"Moderate":2,"Low":1}
    feats.sort(key=lambda f: (ranks.get(f["properties"]["Severity"],0), f["properties"]["Date_Last_Updated"]), reverse=True)
    meta = {"generated_at":now.isoformat(),"generated_by":"scripts/update_outbreak_data.py","feature_count":len(feats),"source_count":len(SOURCES),"signal_window_days":WINDOW_DAYS,"methodology":"Automated daily scan of official and trusted public health feeds. Signals are geocoded by country or region and should be verified against linked authority sources.","source_status":statuses}
    payload = {"type":"FeatureCollection","metadata":meta,"features":feats}
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    SOURCES_OUT.write_text(json.dumps({"generated_at":meta["generated_at"],"feature_count":len(feats),"source_count":len(SOURCES),"source_status":statuses}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(feats)} features from {len(SOURCES)} sources")

if __name__ == "__main__":
    main()
