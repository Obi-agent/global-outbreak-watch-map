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
from collections import defaultdict
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "gow_data.geojson"
SOURCES_OUT = ROOT / "gow_sources.json"
WINDOW_DAYS = int(os.environ.get("GOW_SIGNAL_WINDOW_DAYS", "210"))
MAX_ITEMS = int(os.environ.get("GOW_MAX_ITEMS_PER_SOURCE", "45"))
UA = "Mozilla/5.0 (compatible; GlobalOutbreakWatch/2.0; +https://github.com/Obi-agent/global-outbreak-watch-map)"
DETAIL_CACHE = {}
SEVERITY_RANK = {"Critical": 4, "High": 3, "Moderate": 2, "Low": 1}

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
DISEASES = [(r"west nile","West Nile virus"),(r"swine influenza|h1n1v","Swine influenza A(H1N1)v"),(r"plague|yersinia pestis","Plague"),(r"h5n1|bird flu","Avian influenza A(H5N1)"),(r"h7n9","Avian influenza A(H7N9)"),(r"h9n2","Avian influenza A(H9N2)"),(r"avian influenza","Avian influenza"),(r"cholera","Cholera"),(r"mpox|monkeypox","Mpox"),(r"measles","Measles"),(r"dengue","Dengue"),(r"yellow fever","Yellow fever"),(r"hantavirus","Hantavirus"),(r"marburg","Marburg virus disease"),(r"ebola|sudan virus disease","Ebola virus disease"),(r"nipah","Nipah virus"),(r"polio|poliovirus","Poliovirus"),(r"middle east respiratory syndrome|\bmers\b","MERS"),(r"crimean-congo|cchf","Crimean-Congo haemorrhagic fever"),(r"lassa fever","Lassa fever"),(r"rift valley fever","Rift Valley fever"),(r"chikungunya","Chikungunya"),(r"oropouche","Oropouche virus disease"),(r"pertussis|whooping cough","Pertussis"),(r"seasonal influenza","Seasonal influenza"),(r"covid-19|sars-cov-2","COVID-19"),(r"listeria","Listeriosis"),(r"salmonella","Salmonellosis"),(r"botulism","Botulism"),(r"diphtheria","Diphtheria")]
RELEVANT = re.compile(r"outbreak|epidemiolog|alert|update|disease|infection|virus|fever|cholera|mpox|measles|dengue|influenza|marburg|ebola|hantavirus|polio|pertussis|salmonella|listeria|botulism|chikungunya|oropouche|nipah|mers|cchf", re.I)
EXCLUDE = re.compile(r"glp-1|methanol|chemical|radionuclear|heatwave|heat wave|poisoning", re.I)
NOISE = re.compile(r"loading\s*=|stroke-width|aria-hidden|data-ga4-link|govuk-link|views-field|tabindex=|data-module=|href=|<a\b|<div\b|</d\b|M\d+,\d+H\d+|h\d+v-?\d", re.I)
NON_SIGNAL_TITLE = re.compile(
    r"\bpagination\b|heat[- ]health|eligibility criteria|antibiotic use|"
    r"food hygiene|terms and conditions|privacy notice",
    re.I,
)
DATE_LABEL = re.compile(r"^\d{1,2}\s+[A-Z][a-z]{2,8}\s+\d{4}$")

def strip_markup(value):
    value = html.unescape(str(value or ""))
    value = re.sub(r"<!--.*?-->", " ", value, flags=re.S)
    value = re.sub(r"<script\b.*?</script>|<style\b.*?</style>|<svg\b.*?</svg>|<noscript\b.*?</noscript>", " ", value, flags=re.I|re.S)
    value = re.sub(r"<img\b[^>]*>", " ", value, flags=re.I)
    return value

def clean(value):
    value = strip_markup(value)
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"<[^>]*", " ", value)
    return re.sub(r"\s+", " ", value).strip()

def looks_noisy(value):
    text = clean(value)
    return bool(text and NOISE.search(text))

def tidy_summary(value, fallback=""):
    text = clean(value)
    text = re.sub(r"^\d+\s*\"?\s*loading\s*=\s*\"lazy\"\s*/?>?\s*", "", text, flags=re.I)
    text = re.sub(r"\b(?:HTML|Details)\b\s+.*$", "", text, flags=re.I)
    text = re.sub(r"\b(?:target|tabindex|aria-hidden|data-ga4-link|data-module)\s*=.*$", "", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip(" -|,;:")
    if not text or text.lower() in {"html", "details"} or looks_noisy(text):
        return clean(fallback)
    return text

def meta_content(text, names):
    for name in names:
        pattern = rf'<meta[^>]+(?:name|property)=["\']{re.escape(name)}["\'][^>]+content=["\'](.*?)["\']'
        match = re.search(pattern, text, re.I | re.S)
        if match:
            value = clean(match.group(1))
            if value:
                return value
    return ""

def linked_context(source, title, url):
    key = (source["id"], url)
    if key in DETAIL_CACHE:
        return DETAIL_CACHE[key]
    try:
        page = fetch(url)
    except Exception:
        DETAIL_CACHE[key] = title
        return title

    if source["id"] == "paho-alerts":
        summary = meta_content(page, ["description", "og:description", "twitter:description"])
        DETAIL_CACHE[key] = tidy_summary(summary, fallback=title)
        return DETAIL_CACHE[key]

    if source["id"] == "ukhsa-monitoring":
        scripts = re.findall(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', page, re.I | re.S)
        for script in scripts:
            try:
                payload = json.loads(script.strip())
            except Exception:
                continue
            article_body = payload.get("articleBody", "") if isinstance(payload, dict) else ""
            if article_body:
                disease_match = re.search(r"Disease or pathogen</(?:th|td)>\s*<(?:th|td)[^>]*>(.*?)</(?:th|td)>", article_body, re.I | re.S)
                summary_match = re.search(r"Summary</(?:td|th)>\s*<(?:td|th)[^>]*>(.*?)</(?:td|th)>", article_body, re.I | re.S)
                disease_name = clean(disease_match.group(1)) if disease_match else ""
                summary_text = clean(summary_match.group(1).replace("<br>", " ").replace("<br/>", " ").replace("<br />", " ")) if summary_match else ""
                if disease_name or summary_text:
                    combined = f"{disease_name}. {summary_text}".strip(". ").strip()
                    DETAIL_CACHE[key] = tidy_summary(combined, fallback=title)
                    return DETAIL_CACHE[key]
            entities = payload.get("mainEntity", [])
            if isinstance(entities, dict):
                entities = [entities]
            for entity in entities:
                answer = entity.get("acceptedAnswer", {}).get("text", "")
                if not answer:
                    continue
                disease_match = re.search(r"Disease or pathogen.*?<strong>(.*?)</strong>", answer, re.I | re.S)
                summary_match = re.search(r"Summary</td>\s*<td>(.*?)</td>", answer, re.I | re.S)
                disease_name = clean(disease_match.group(1)) if disease_match else ""
                summary_text = clean(summary_match.group(1).replace("<br>", " ").replace("<br/>", " ").replace("<br />", " ")) if summary_match else ""
                if disease_name or summary_text:
                    combined = f"{disease_name}. {summary_text}".strip(". ").strip()
                    DETAIL_CACHE[key] = tidy_summary(combined, fallback=title)
                    return DETAIL_CACHE[key]
        body_match = re.search(r'<main\b.*?</main>', page, re.I | re.S)
        body = body_match.group(0) if body_match else page
        disease_match = re.search(r"Disease or pathogen</(?:strong|b)>\s*</(?:td|th)>\s*<(?:td|th)[^>]*>\s*<(?:strong|b)>(.*?)</(?:strong|b)>", body, re.I | re.S)
        if not disease_match:
            disease_match = re.search(r"Disease or pathogen</(?:td|th)>\s*<(?:td|th)[^>]*>(.*?)</(?:td|th)>", body, re.I | re.S)
        summary_match = re.search(r"Summary</(?:td|th)>\s*<(?:td|th)[^>]*>(.*?)</(?:td|th)>", body, re.I | re.S)
        disease_name = clean(disease_match.group(1)) if disease_match else ""
        summary_text = clean(summary_match.group(1).replace("<br>", " ").replace("<br/>", " ").replace("<br />", " ")) if summary_match else ""
        if disease_name or summary_text:
            combined = f"{disease_name}. {summary_text}".strip(". ").strip()
            DETAIL_CACHE[key] = tidy_summary(combined, fallback=title)
            return DETAIL_CACHE[key]

    summary = meta_content(page, ["description", "og:description", "twitter:description"])
    DETAIL_CACHE[key] = tidy_summary(summary, fallback=title)
    return DETAIL_CACHE[key]

def fetch(url):
    last_exc = None
    for attempt in range(3):
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": UA,
                "Accept": "application/json, application/atom+xml, application/rss+xml, text/html;q=0.9, */*;q=0.8",
                "Accept-Language": "en-GB,en;q=0.9",
                "Cache-Control": "no-cache",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=24) as res:
                return res.read().decode(res.headers.get_content_charset() or "utf-8", errors="replace")
        except Exception as exc:
            last_exc = exc
            if attempt == 2:
                raise
            time.sleep(1.5 * (attempt + 1))
    raise last_exc

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
        link_node = entry.find("a:link[@href]", ns)
        if link_node is None:
            link_node = entry.find("a:link", ns)
        link = urllib.parse.urljoin(source["url"], link_node.get("href")) if link_node is not None and link_node.get("href") else source["url"]
        out.append((title, summary, link, dt(entry.findtext("a:updated", namespaces=ns) or entry.findtext("a:published", namespaces=ns))))
    return [x for x in out if x[0]]

def html_items(source, text):
    text = strip_markup(text)
    out = []
    for m in re.finditer(r"<a\s[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", text, re.I|re.S):
        href, body = m.groups(); title = clean(body)
        url = urllib.parse.urljoin(source["url"], html.unescape(href or ""))
        if len(title) < 8 or not RELEVANT.search(title) or looks_noisy(title):
            continue
        if source.get("must") and source["must"].lower() not in url.lower():
            continue
        context_raw = text[m.end():min(len(text), m.end() + 900)]
        context = tidy_summary(context_raw, fallback=title)
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
        flags = 0 if alias.isupper() and len(alias) <= 3 else re.I
        if re.search(rf"(?<![A-Za-z]){re.escape(alias)}(?![A-Za-z])", hay, flags):
            found.append(canonical)
    for country in COORDS:
        if re.search(rf"(?<![A-Za-z]){re.escape(country)}(?![A-Za-z])", hay, re.I):
            found.append(country)
    if not found:
        for region, pat in (("Americas Region",r"americas|latin america|caribbean"),("Africa Region",r"africa|african region"),("EU/EEA",r"\beu/eea\b|european union|\beu\b"),("European Region",r"european region|europe"),("Eastern Mediterranean Region",r"eastern mediterranean"),("South-East Asia Region",r"south-east asia|southeast asia"),("Western Pacific Region",r"western pacific"),("Global",r"global|multi-country|multicountry|worldwide")):
            if re.search(pat, hay, re.I): found.append(region); break
    if not found and default: found.append(default)
    if not found: found.append("Global")
    if "Democratic Republic of the Congo" in found:
        found = [place for place in found if place != "Congo"]
    return list(dict.fromkeys(found))[:6]

def signal_places(source, title, summary):
    title_places = [place for place in places(title) if place != "Global"]
    generic_title = re.search(r"outbreaks under monitoring|communicable disease threats report|weekly|week\s+\d+|situation report", title, re.I)
    if source["id"] == "ukhsa-news" and re.search(r"deploy|support team|response team", title, re.I):
        summary_places = places(summary, source.get("default"))
        if len(summary_places) > 1 and source.get("default") in summary_places:
            summary_places.remove(source["default"])
        return summary_places
    if title_places and not generic_title:
        return title_places
    location_context = summary[:420] if generic_title else f"{title} {summary}"
    return places(location_context, source.get("default"))

def known_disease(name):
    return any(canonical == name for _, canonical in DISEASES)

def label_is_suspicious(title):
    title = clean(title)
    return (
        len(title) < 8
        or len(title) > 180
        or bool(DATE_LABEL.fullmatch(title))
        or bool(NON_SIGNAL_TITLE.search(title))
        or looks_noisy(title)
    )

def severity_assessment(name, text):
    low = text.lower()
    if re.search(r"public health emergency of international concern|\bpheic\b|sustained human-to-human", low):
        return "Critical", ["Authority language indicates an international emergency or sustained human transmission."]
    if re.search(r"marburg|ebola|nipah|cchf|crimean-congo|h5n1|cholera|lassa", name, re.I):
        return "High", [f"{name} is treated as a high-consequence pathogen in this screening model."]
    if re.search(r"death|fatal|haemorrhagic|hemorrhagic|hospitali[sz]ed", low):
        return "High", ["The source text reports severe outcomes such as death, haemorrhage, or hospitalisation."]
    if re.search(r"mpox|measles|dengue|yellow fever|hantavirus|polio|mers|chikungunya|oropouche|pertussis|salmonella|listeria|botulism", name, re.I):
        return "Moderate", [f"{name} is on the monitored outbreak-priority list."]
    return "Low", ["No critical or high-severity trigger was detected in the published text."]

def confidence_assessment(source, name, place, summary, when):
    score = 58
    reasons = [f"Published by {source['name']}, a {source['type'].lower()} source."]
    if known_disease(name):
        score += 15; reasons.append("The disease name matched the controlled outbreak vocabulary.")
    else:
        reasons.append("The disease label was inferred from the source headline.")
    if place in COORDS:
        score += 12; reasons.append("The signal names a country in the geographic index.")
    elif place in REGIONS and place != "Global":
        score += 7; reasons.append("The signal is located at regional precision.")
    else:
        reasons.append("The signal could only be located globally.")
    if len(summary) >= 120:
        score += 8; reasons.append("The source supplied enough context for a meaningful synopsis.")
    if when:
        score += 6; reasons.append("A publication date was parsed from the source.")
    score = min(score, 99)
    level = "High" if score >= 85 else "Moderate" if score >= 70 else "Low"
    return score, level, reasons

def quality_assessment(title, summary, name, place, when):
    score = 100; notes = []
    if not known_disease(name):
        score -= 18; notes.append("Disease label inferred rather than vocabulary-matched.")
    if place == "Global":
        score -= 16; notes.append("No country or region was identified.")
    elif place in REGIONS:
        score -= 8; notes.append("Location is regional rather than country-level.")
    if summary == title or len(summary) < 80:
        score -= 15; notes.append("Limited source synopsis.")
    if not when:
        score -= 12; notes.append("Publication date unavailable; refresh time used.")
    if label_is_suspicious(title):
        score -= 60; notes.append("Headline resembles navigation, markup, or a non-signal label.")
    score = max(0, score)
    label = "Verified" if score >= 85 else "Review" if score >= 65 else "Quarantined"
    return score, label, notes or ["No automated quality concerns detected."]

def status(title, summary):
    low = f"{title} {summary}".lower()
    if re.search(r"\bclosed\b|declared an end|declared over|end of the outbreak|resolved", low): return "Closed"
    if re.search(r"monitor|update|situation report|surveillance|weekly", low): return "Monitoring"
    return "Open"

def coord(place):
    place = ALIASES.get(place, place)
    return COORDS.get(place) or REGIONS.get(place) or REGIONS["Global"]

def feature(source, title, summary, url, when, place, offset, now):
    summary = tidy_summary(summary, fallback=title)
    name_source = summary if summary and summary != title else title
    text = title if summary == title else f"{summary} {title}"; name = disease(name_source); lon, lat = coord(place)
    h = hashlib.sha1(f"{source['id']}|{url}|{place}|{name}".encode()).hexdigest()[:10]
    published_when = when
    effective_when = when or now
    snap = tidy_summary(summary or title, fallback=title)
    if len(snap) > 540: snap = snap[:540].rsplit(" ",1)[0] + "..."
    severity, severity_reasons = severity_assessment(name, text)
    confidence_score, confidence_level, confidence_reasons = confidence_assessment(source, name, place, snap, published_when)
    quality_score, quality_status, quality_notes = quality_assessment(title, snap, name, place, published_when)
    precision = "Country" if place in COORDS else "Region" if place in REGIONS and place != "Global" else "Global"
    return {
        "type":"Feature",
        "properties":{
            "Outbreak_ID":f"{iso(effective_when)}-{source['id']}-{h}","Threat":name,"Disease":name,
            "Country":place,"Location_Label":place,"Geographic_Precision":precision,
            "Status":status(title, summary),"Signal_Status":status(title, summary),
            "Severity":severity,"Severity_Rationale":severity_reasons,
            "Date_First_Noted":iso(effective_when),"Date_Last_Updated":iso(effective_when),
            "Source_ID":source["id"],"Source_Name":source["name"],"Source_Type":source["type"],"Source_URL":url,
            "Confidence":f"{confidence_level} ({confidence_score}/100)","Confidence_Level":confidence_level,
            "Confidence_Score":confidence_score,"Confidence_Rationale":confidence_reasons,
            "Quality_Score":quality_score,"Quality_Status":quality_status,"Quality_Notes":quality_notes,
            "Situation_Snapshot":snap,
            "Travel_Health_Takeaways":"Verify case counts, local restrictions and clinical guidance with the linked authority before operational use.",
            "Title":title,"Generated_At":now.isoformat(),"Is_Stale":False,"Data_State":"Current"
        },
        "geometry":{"type":"Point","coordinates":[lon + offset*0.12, lat + offset*0.08]}
    }

def parse_iso_date(value):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None

def load_previous_payload():
    if not OUT.exists():
        return {"features": [], "metadata": {}}
    try:
        return json.loads(OUT.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"features": [], "metadata": {}}

def feature_source_id(feature):
    props = feature.get("properties", {})
    if props.get("Source_ID"):
        return props["Source_ID"]
    outbreak_id = props.get("Outbreak_ID", "")
    for source in SOURCES:
        if f"-{source['id']}-" in outbreak_id:
            return source["id"]
    return ""

def carry_forward_features(previous, source, now, seen):
    carried = []
    for old in previous.get("features", []):
        if feature_source_id(old) != source["id"]:
            continue
        props = old.get("properties", {})
        noted = parse_iso_date(props.get("Date_Last_Updated"))
        if noted and (now - noted).days > WINDOW_DAYS:
            continue
        copied = deepcopy(old)
        copied_props = copied.setdefault("properties", {})
        copied_props["Source_ID"] = source["id"]
        copied_props["Is_Stale"] = True
        copied_props["Data_State"] = "Last known good"
        copied_props["Quality_Status"] = "Review"
        notes = list(copied_props.get("Quality_Notes") or [])
        notes.append("Source refresh failed; retained from the last successful dataset.")
        copied_props["Quality_Notes"] = list(dict.fromkeys(notes))
        copied_props["Quality_Score"] = max(0, int(copied_props.get("Quality_Score", 75)) - 10)
        key = (copied_props.get("Disease", "").lower(), copied_props.get("Country", "").lower(), copied_props.get("Source_URL", "").lower())
        if key in seen:
            continue
        seen.add(key); carried.append(copied)
    return carried

def trend_assessment(properties, incident_status, now):
    latest = sorted(properties, key=lambda item: item.get("Date_Last_Updated", ""), reverse=True)[:8]
    text = " ".join(f"{item.get('Title', '')} {item.get('Situation_Snapshot', '')}" for item in latest).lower()
    if incident_status == "Closed" or re.search(r"no new cases|zero new cases|declin|decreas|contained|under control|declared over|end of (?:the )?outbreak|\bresolved\b", text):
        return "Improving", "The latest linked authority language reports no new cases, decline, containment, or closure."
    if re.search(r"increase(?:d|s)?\s+(?:of|by|from|in)\b|\bsurge\b|\brising\b|escalat|rapid spread|cross-border|new (?:areas|regions|countries|deaths)|public health emergency|\bpheic\b", text):
        return "Worsening", "Recent authority language indicates rising burden, wider spread, escalation, or emergency status."
    if re.search(r"\bnew cases\b|additional cases|continued transmission|outbreak (?:was )?declared|confirmed cases|case count", text):
        return "Increasing", "Recent authority language reports new or additional cases, continued transmission, or a newly declared outbreak."
    last_updated = max((item.get("Date_Last_Updated", "") for item in properties), default="")
    parsed = parse_iso_date(last_updated)
    age = (now - parsed).days if parsed else WINDOW_DAYS
    return "Stable", f"No directional change language was detected in linked authority updates; the latest signal is {age} days old."

def build_incidents(features, now):
    if not features:
        return []
    parent = list(range(len(features)))
    def find(index):
        while parent[index] != index:
            parent[index] = parent[parent[index]]; index = parent[index]
        return index
    def union(left, right):
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[right_root] = left_root
    disease_country = {}; disease_url = {}
    for index, item in enumerate(features):
        props = item["properties"]
        disease_key = props.get("Disease", "").lower()
        country_key = props.get("Country", "").lower()
        url_key = props.get("Source_URL", "").lower()
        for collection, key in (
            (disease_country, (disease_key, country_key)),
            (disease_url, (disease_key, url_key)),
        ):
            if not all(key):
                continue
            if key in collection:
                union(index, collection[key])
            else:
                collection[key] = index
    groups = defaultdict(list)
    for index, item in enumerate(features):
        groups[find(index)].append(item)
    incidents = []
    for items in groups.values():
        props = [item["properties"] for item in items]
        disease_name = props[0].get("Disease", "Disease signal")
        countries = sorted(dict.fromkeys(p.get("Country", "Global") for p in props))
        sources = sorted(dict.fromkeys(p.get("Source_Name", "Unknown source") for p in props))
        severest = max((p.get("Severity", "Low") for p in props), key=lambda value: SEVERITY_RANK.get(value, 0))
        status_values = [p.get("Status", "Monitoring") for p in props]
        incident_status = "Open" if "Open" in status_values else "Monitoring" if "Monitoring" in status_values else "Closed"
        first_noted = min((p.get("Date_First_Noted", "") for p in props if p.get("Date_First_Noted")), default="")
        last_updated = max((p.get("Date_Last_Updated", "") for p in props if p.get("Date_Last_Updated")), default="")
        trend, trend_reason = trend_assessment(props, incident_status, now)
        confidence_score = round(sum(int(p.get("Confidence_Score", 65)) for p in props) / len(props))
        confidence_level = "High" if confidence_score >= 85 else "Moderate" if confidence_score >= 70 else "Low"
        quality_score = round(sum(int(p.get("Quality_Score", 70)) for p in props) / len(props))
        precision_values = {p.get("Geographic_Precision", "Global") for p in props}
        geographic_precision = "Country centroid" if precision_values == {"Country"} else "Regional centroid" if "Region" in precision_values else "Global"
        coordinates = [item.get("geometry", {}).get("coordinates", REGIONS["Global"]) for item in items]
        lon = round(sum(point[0] for point in coordinates) / len(coordinates), 4)
        lat = round(sum(point[1] for point in coordinates) / len(coordinates), 4)
        identity = f"{disease_name.lower()}|{'|'.join(country.lower() for country in countries)}"
        incident_id = "INC-" + hashlib.sha1(identity.encode()).hexdigest()[:10].upper()
        evidence = []
        for item in sorted(items, key=lambda row: row["properties"].get("Date_Last_Updated", ""), reverse=True):
            p = item["properties"]
            evidence.append({
                "Signal_ID":p.get("Outbreak_ID"),"Title":p.get("Title"),"Date":p.get("Date_Last_Updated"),
                "Source_Name":p.get("Source_Name"),"Source_Type":p.get("Source_Type"),"Source_URL":p.get("Source_URL"),
                "Snapshot":p.get("Situation_Snapshot"),"Country":p.get("Country"),"Is_Stale":bool(p.get("Is_Stale")),
                "Confidence_Score":p.get("Confidence_Score"),"Quality_Score":p.get("Quality_Score")
            })
        location_label = ", ".join(countries[:3]) + (f" +{len(countries)-3}" if len(countries) > 3 else "")
        incidents.append({
            "Incident_ID":incident_id,"Title":f"{disease_name} - {location_label}","Disease":disease_name,
            "Countries":countries,"Location_Label":location_label,"Coordinates":[lon,lat],
            "Geographic_Precision":geographic_precision,
            "Severity":severest,"Status":incident_status,"Trend":trend,"Trend_Rationale":trend_reason,
            "Confidence_Level":confidence_level,"Confidence_Score":confidence_score,
            "Quality_Score":quality_score,"Source_Count":len(sources),"Update_Count":len(items),
            "Sources":sources,"Date_First_Noted":first_noted,"Date_Last_Updated":last_updated,
            "Has_Stale_Evidence":any(p.get("Is_Stale") for p in props),
            "Severity_Rationale":list(dict.fromkeys(reason for p in props for reason in p.get("Severity_Rationale", []))),
            "Confidence_Rationale":list(dict.fromkeys(reason for p in props for reason in p.get("Confidence_Rationale", []))),
            "Evidence":evidence
        })
    incidents.sort(key=lambda item: (SEVERITY_RANK.get(item["Severity"], 0), item["Date_Last_Updated"]), reverse=True)
    return incidents

def build_quality_summary(features, incidents, statuses):
    source_ok = sum(1 for row in statuses if row["status"] == "ok")
    source_lkg = sum(1 for row in statuses if row["status"] == "using_last_known_good")
    source_error = len(statuses) - source_ok - source_lkg
    feature_score = round(sum(int(item["properties"].get("Quality_Score", 0)) for item in features) / len(features)) if features else 0
    source_score = round(100 * (source_ok + source_lkg * 0.55) / len(statuses)) if statuses else 0
    overall = round(feature_score * 0.45 + source_score * 0.55)
    health = "Healthy" if overall >= 85 else "Degraded" if overall >= 65 else "Attention"
    return {
        "status":health,"score":overall,"feature_quality_score":feature_score,"source_health_score":source_score,
        "sources_ok":source_ok,"sources_last_known_good":source_lkg,"sources_error":source_error,
        "signals_current":sum(1 for item in features if not item["properties"].get("Is_Stale")),
        "signals_last_known_good":sum(1 for item in features if item["properties"].get("Is_Stale")),
        "signals_quarantined":sum(int(row.get("skipped_quarantined", 0)) for row in statuses),
        "signals_rejected_noisy":sum(int(row.get("skipped_noisy", 0)) for row in statuses),
        "incidents":len(incidents)
    }

def main():
    now = datetime.now(timezone.utc); previous = load_previous_payload(); feats = []; seen = set(); statuses = []
    for source in SOURCES:
        start = time.time(); st = {"id":source["id"],"name":source["name"],"type":source["type"],"url":source["url"],"status":"ok","items_seen":0,"features_added":0,"features_carried_forward":0,"skipped_noisy":0,"skipped_quarantined":0,"elapsed_seconds":0.0,"last_success_at":""}
        try:
            text = fetch(source["url"])
            items = who_items(source, text) if source["adapter"] == "who" else rss_items(source, text) if source["adapter"] == "rss" else html_items(source, text)
            if not items:
                raise ValueError("No source items were parsed; the upstream format may have changed")
            st["items_seen"] = len(items); accepted = 0
            for title, summary, url, when in items:
                if accepted >= MAX_ITEMS: break
                summary = tidy_summary(summary, fallback=title)
                if source["adapter"] == "html" and summary == title:
                    summary = linked_context(source, title, url)
                alltext = f"{title} {summary}"
                if label_is_suspicious(title):
                    st["skipped_noisy"] += 1
                    continue
                if EXCLUDE.search(alltext) or not RELEVANT.search(alltext): continue
                if when and (now - when).days > WINDOW_DAYS: continue
                for offset, place in enumerate(signal_places(source, title, summary)):
                    f = feature(source, title, summary, url, when, place, offset, now)
                    if f["properties"]["Quality_Status"] == "Quarantined":
                        st["skipped_quarantined"] += 1
                        continue
                    key = (f["properties"]["Threat"].lower(), f["properties"]["Country"].lower(), f["properties"]["Source_URL"].lower())
                    if key in seen: continue
                    seen.add(key); feats.append(f); st["features_added"] += 1
                accepted += 1
            st["last_success_at"] = now.isoformat()
        except Exception as exc:
            carried = carry_forward_features(previous, source, now, seen)
            feats.extend(carried)
            st["features_carried_forward"] = len(carried)
            st["status"] = "using_last_known_good" if carried else "error"
            st["error"] = str(exc)[:220]
            prior_statuses = previous.get("metadata", {}).get("source_status", [])
            prior = next((row for row in prior_statuses if row.get("id") == source["id"]), {})
            st["last_success_at"] = prior.get("last_success_at", "")
        st["elapsed_seconds"] = round(time.time() - start, 2); statuses.append(st)
    if not feats:
        raise SystemExit("No features generated; refusing to overwrite data")
    feats.sort(key=lambda f: (SEVERITY_RANK.get(f["properties"]["Severity"],0), f["properties"]["Date_Last_Updated"]), reverse=True)
    incidents = build_incidents(feats, now)
    quality = build_quality_summary(feats, incidents, statuses)
    history = list(previous.get("metadata", {}).get("quality_history", []))
    history = [entry for entry in history if entry.get("date") != iso(now)][-13:]
    history.append({"date":iso(now),"score":quality["score"],"status":quality["status"],"incidents":len(incidents),"signals":len(feats),"sources_ok":quality["sources_ok"]})
    meta = {
        "generated_at":now.isoformat(),"generated_by":"scripts/update_outbreak_data.py","schema_version":"2.0",
        "feature_count":len(feats),"incident_count":len(incidents),"signals_merged":len(feats)-len(incidents),
        "source_count":len(SOURCES),"signal_window_days":WINDOW_DAYS,
        "methodology":"Automated daily scan of official public-health feeds. Signals are quality-screened, geocoded, and grouped into explainable incidents. Linked authority evidence remains the source of truth.",
        "quality":quality,"quality_history":history,"source_status":statuses
    }
    payload = {"type":"FeatureCollection","metadata":meta,"incidents":incidents,"features":feats}
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    SOURCES_OUT.write_text(json.dumps({"generated_at":meta["generated_at"],"feature_count":len(feats),"incident_count":len(incidents),"source_count":len(SOURCES),"quality":quality,"quality_history":history,"source_status":statuses}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(incidents)} incidents from {len(feats)} signals across {len(SOURCES)} sources ({quality['status']} {quality['score']}/100)")

if __name__ == "__main__":
    main()
