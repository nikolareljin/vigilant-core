"""Curated sources and RSS discovery helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional
from urllib.parse import parse_qs, quote_plus, unquote, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup


@dataclass(frozen=True)
class Source:
    name: str
    url: str


DEFAULT_SOURCES: List[Source] = [
    # United States
    Source("AP News", "https://apnews.com"),
    Source("Reuters", "https://www.reuters.com"),
    Source("Bloomberg", "https://www.bloomberg.com"),
    Source("The Wall Street Journal", "https://www.wsj.com"),
    Source("The New York Times", "https://www.nytimes.com"),
    Source("The Washington Post", "https://www.washingtonpost.com"),
    Source("USA Today", "https://www.usatoday.com"),
    Source("NPR", "https://www.npr.org/sections/news/"),
    Source("PBS NewsHour", "https://www.pbs.org/newshour/"),
    Source("CNN", "https://www.cnn.com"),
    Source("NBC News", "https://www.nbcnews.com"),
    Source("CBS News", "https://www.cbsnews.com"),
    Source("ABC News (US)", "https://abcnews.go.com"),
    Source("Fox News", "https://www.foxnews.com"),
    Source("Politico", "https://www.politico.com"),
    Source("Axios", "https://www.axios.com"),
    Source("The Hill", "https://thehill.com"),
    Source("Time", "https://time.com"),
    Source("Newsweek", "https://www.newsweek.com"),
    Source("U.S. News", "https://www.usnews.com"),
    Source("The Atlantic", "https://www.theatlantic.com"),
    Source("CNBC", "https://www.cnbc.com"),
    Source("Yahoo News", "https://news.yahoo.com"),
    Source("ProPublica", "https://www.propublica.org"),
    Source("Vox", "https://www.vox.com"),
    Source("The Verge", "https://www.theverge.com"),
    Source("CNET", "https://www.cnet.com"),
    Source("Weather.gov", "https://www.weather.gov"),
    Source("NOAA", "https://www.noaa.gov"),
    Source("NWS Alerts", "https://alerts.weather.gov"),
    Source("Los Angeles Times", "https://www.latimes.com"),
    Source("Chicago Tribune", "https://www.chicagotribune.com"),
    Source("Miami Herald", "https://www.miamiherald.com"),
    Source("Houston Chronicle", "https://www.houstonchronicle.com"),
    Source("Dallas Morning News", "https://www.dallasnews.com"),
    Source("San Francisco Chronicle", "https://www.sfchronicle.com"),
    Source("Boston Globe", "https://www.bostonglobe.com"),
    Source("Philadelphia Inquirer", "https://www.inquirer.com"),
    Source("Seattle Times", "https://www.seattletimes.com"),
    Source("Star Tribune", "https://www.startribune.com"),
    Source("Detroit Free Press", "https://www.freep.com"),
    Source("Tampa Bay Times", "https://www.tampabay.com"),
    Source("Cleveland Plain Dealer", "https://www.cleveland.com"),
    Source("Denver Post", "https://www.denverpost.com"),
    Source("Arizona Republic", "https://www.azcentral.com"),
    Source("The Oregonian", "https://www.oregonlive.com"),
    Source("The Sacramento Bee", "https://www.sacbee.com"),
    Source("The Kansas City Star", "https://www.kansascity.com"),
    Source("The Indianapolis Star", "https://www.indystar.com"),
    Source("The Baltimore Sun", "https://www.baltimoresun.com"),
    Source("The Charlotte Observer", "https://www.charlotteobserver.com"),
    Source("The Buffalo News", "https://buffalonews.com"),
    Source("The Columbus Dispatch", "https://www.dispatch.com"),
    Source("The Tennessean", "https://www.tennessean.com"),
    Source("The Courier-Journal", "https://www.courier-journal.com"),
    Source("The Virginian-Pilot", "https://www.pilotonline.com"),
    Source("The Times-Picayune", "https://www.nola.com"),
    # Europe
    Source("BBC News", "https://www.bbc.com/news"),
    Source("The Guardian", "https://www.theguardian.com"),
    Source("Financial Times", "https://www.ft.com"),
    Source("The Economist", "https://www.economist.com"),
    Source("Euronews", "https://www.euronews.com"),
    Source("DW", "https://www.dw.com"),
    Source("France 24", "https://www.france24.com"),
    Source("Le Monde", "https://www.lemonde.fr"),
    Source("Le Figaro", "https://www.lefigaro.fr"),
    Source("Liberation", "https://www.liberation.fr"),
    Source("El Pais", "https://elpais.com"),
    Source("El Mundo", "https://www.elmundo.es"),
    Source("La Vanguardia", "https://www.lavanguardia.com"),
    Source("Corriere della Sera", "https://www.corriere.it"),
    Source("La Repubblica", "https://www.repubblica.it"),
    Source("Il Sole 24 Ore", "https://www.ilsole24ore.com"),
    Source("Der Spiegel", "https://www.spiegel.de"),
    Source("Die Zeit", "https://www.zeit.de"),
    Source("Frankfurter Allgemeine", "https://www.faz.net"),
    Source("Sueddeutsche Zeitung", "https://www.sueddeutsche.de"),
    Source("Sky News", "https://news.sky.com"),
    Source("ITV News", "https://www.itv.com/news"),
    Source("The Independent", "https://www.independent.co.uk"),
    Source("The Times (UK)", "https://www.thetimes.co.uk"),
    Source("The Telegraph", "https://www.telegraph.co.uk"),
    Source("The Irish Times", "https://www.irishtimes.com"),
    Source("RTÉ News", "https://www.rte.ie/news/"),
    Source("The Local", "https://www.thelocal.com"),
    # Australia / Oceania
    Source("ABC News (AU)", "https://www.abc.net.au/news"),
    Source("SBS News", "https://www.sbs.com.au/news"),
    Source("Sydney Morning Herald", "https://www.smh.com.au"),
    Source("The Age", "https://www.theage.com.au"),
    Source("The Australian", "https://www.theaustralian.com.au"),
    Source("The Guardian Australia", "https://www.theguardian.com/australia-news"),
    Source("7NEWS", "https://7news.com.au"),
    Source("9News", "https://www.9news.com.au"),
    Source("The West Australian", "https://thewest.com.au"),
    Source("The Canberra Times", "https://www.canberratimes.com.au"),
    Source("The Advertiser", "https://www.adelaidenow.com.au"),
    Source("The Courier-Mail", "https://www.couriermail.com.au"),
    Source("The Herald Sun", "https://www.heraldsun.com.au"),
    Source("NZ Herald", "https://www.nzherald.co.nz"),
    Source("Stuff NZ", "https://www.stuff.co.nz"),
    # South America
    Source("Folha de S.Paulo", "https://www.folha.uol.com.br"),
    Source("O Globo", "https://oglobo.globo.com"),
    Source("Estadao", "https://www.estadao.com.br"),
    Source("G1", "https://g1.globo.com"),
    Source("UOL", "https://www.uol.com.br"),
    Source("La Nacion", "https://www.lanacion.com.ar"),
    Source("Clarín", "https://www.clarin.com"),
    Source("Pagina/12", "https://www.pagina12.com.ar"),
    Source("El Tiempo", "https://www.eltiempo.com"),
    Source("El Espectador", "https://www.elespectador.com"),
    Source("Semana", "https://www.semana.com"),
    Source("El Comercio (PE)", "https://elcomercio.pe"),
    Source("La Republica (PE)", "https://larepublica.pe"),
    Source("El Mercurio", "https://www.elmercurio.com"),
    Source("La Tercera", "https://www.latercera.com"),
    Source("El Universal (MX)", "https://www.eluniversal.com.mx"),
    Source("Milenio", "https://www.milenio.com"),
    Source("Reforma", "https://www.reforma.com"),
    Source("Excelsior", "https://www.excelsior.com.mx"),
    # East Europe
    Source("The Kyiv Independent", "https://kyivindependent.com"),
    Source("Kyiv Post", "https://www.kyivpost.com"),
    Source("RFE/RL", "https://www.rferl.org"),
    Source("Polskie Radio", "https://www.polskieradio.pl"),
    Source("TVP Info", "https://www.tvp.info"),
    Source("B92", "https://www.b92.net"),
    Source("Dnevnik", "https://www.dnevnik.bg"),
    Source("Helsinki Times", "https://www.helsinkitimes.fi"),
    Source("ERT News", "https://www.ertnews.gr"),
    Source("Kathimerini", "https://www.ekathimerini.com"),
    Source("Protothema", "https://www.protothema.gr"),
    Source("Ta Nea", "https://www.tanea.gr"),
    Source("Blic", "https://www.blic.rs"),
    Source("Kurir", "https://www.kurir.rs"),
    Source("N1 (Serbia)", "https://n1info.rs"),
    Source("RTS", "https://www.rts.rs"),
    Source("Danas", "https://www.danas.rs"),
    Source("Vecernji list", "https://www.vecernji.hr"),
    Source("Jutarnji list", "https://www.jutarnji.hr"),
    Source("Index.hr", "https://www.index.hr"),
    Source("HRT News", "https://www.hrt.hr"),
    Source("24sata", "https://www.24sata.hr"),
    Source("Tanjug", "https://www.tanjug.rs"),
    Source("FENA", "https://www.fena.ba"),
    Source("Klix", "https://www.klix.ba"),
    Source("Dnevni Avaz", "https://avaz.ba"),
    Source("Vijesti (ME)", "https://www.vijesti.me"),
    Source("RTCG", "https://rtcg.me"),
    Source("Telegrafi (XK)", "https://telegrafi.com"),
    Source("Koha", "https://www.koha.net"),
    Source("Alsat M", "https://alsat.mk"),
    Source("A1on", "https://a1on.mk"),
    Source("BTA", "https://www.bta.bg/en"),
    # China / East Asia
    Source("Xinhua", "https://www.xinhuanet.com/english/"),
    Source("China Daily", "https://www.chinadaily.com.cn"),
    Source("South China Morning Post", "https://www.scmp.com"),
    Source("CGTN", "https://www.cgtn.com"),
    Source("Caixin Global", "https://www.caixinglobal.com"),
    Source("Global Times", "https://www.globaltimes.cn"),
    Source("China.org.cn", "http://www.china.org.cn"),
    Source("The Paper (China)", "https://www.thepaper.cn"),
    Source("NHK World", "https://www3.nhk.or.jp/nhkworld/"),
    Source("Japan Times", "https://www.japantimes.co.jp"),
    Source("Korea Herald", "https://www.koreaherald.com"),
    Source("Yonhap News", "https://en.yna.co.kr"),
    Source("CNA (Singapore)", "https://www.channelnewsasia.com"),
    Source("Straits Times", "https://www.straitstimes.com"),
    # Africa
    Source("AllAfrica", "https://allafrica.com"),
    Source("News24", "https://www.news24.com"),
    Source("Daily Nation", "https://nation.africa"),
    Source("SABC News", "https://www.sabcnews.com/sabcnews/"),
    Source("BBC Africa", "https://www.bbc.com/news/world/africa"),
    Source("Al Jazeera Africa", "https://www.aljazeera.com/africa/"),
    Source("The Citizen (Tanzania)", "https://www.thecitizen.co.tz"),
    Source("The Standard (Kenya)", "https://www.standardmedia.co.ke"),
    Source("The East African", "https://www.theeastafrican.co.ke"),
    Source("Daily Maverick", "https://www.dailymaverick.co.za"),
    Source("Mail & Guardian", "https://mg.co.za"),
    Source("Business Day (Nigeria)", "https://businessday.ng"),
    Source("Premium Times", "https://www.premiumtimesng.com"),
    Source("The Punch", "https://punchng.com"),
    Source("The Guardian (Nigeria)", "https://guardian.ng"),
    Source("Vanguard (Nigeria)", "https://www.vanguardngr.com"),
    Source("Daily Monitor (Uganda)", "https://www.monitor.co.ug"),
    Source("ZBC News", "https://www.zbcnews.co.zw"),
]


def _same_domain(base: str, candidate: str) -> bool:
    try:
        return urlparse(base).netloc == urlparse(candidate).netloc
    except Exception:
        return False


def _looks_like_feed(url: str) -> bool:
    lowered = url.lower()
    return any(token in lowered for token in ("rss", "atom", "feed", "/feeds"))


def _normalize(url: str) -> str:
    return url.split("#", 1)[0]


def discover_feed_links(base_url: str, client: httpx.Client) -> List[str]:
    try:
        resp = client.get(base_url, timeout=8.0)
        resp.raise_for_status()
    except Exception:
        return []
    soup = BeautifulSoup(resp.text, "html.parser")
    feeds: List[str] = []
    for link in soup.find_all("link"):
        rel = " ".join(link.get("rel", [])).lower()
        link_type = (link.get("type") or "").lower()
        href = link.get("href")
        if not href:
            continue
        if "alternate" in rel and ("rss" in link_type or "atom" in link_type or "xml" in link_type):
            feeds.append(urljoin(base_url, href))
    for anchor in soup.find_all("a"):
        href = anchor.get("href")
        if not href:
            continue
        if _looks_like_feed(href):
            feeds.append(urljoin(base_url, href))
    return list(dict.fromkeys(_normalize(feed) for feed in feeds))


def discover_section_links(base_url: str, client: httpx.Client) -> List[str]:
    try:
        resp = client.get(base_url, timeout=8.0)
        resp.raise_for_status()
    except Exception:
        return []
    soup = BeautifulSoup(resp.text, "html.parser")
    links: List[str] = []
    keywords = {"world", "news", "us", "local", "weather", "alerts", "breaking", "politics"}
    for anchor in soup.find_all("a"):
        href = anchor.get("href")
        if not href:
            continue
        url = urljoin(base_url, href)
        if not _same_domain(base_url, url):
            continue
        path = urlparse(url).path.lower()
        if any(word in path for word in keywords):
            links.append(_normalize(url))
    return list(dict.fromkeys(links))


def _validate_feed(url: str, client: httpx.Client) -> bool:
    try:
        resp = client.get(url, timeout=8.0)
        resp.raise_for_status()
        text = resp.text.lower()
        return "<rss" in text or "<feed" in text
    except Exception:
        return False


def _root_url(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return url
    return f"{parsed.scheme}://{parsed.netloc}"


def _is_ignored_domain(url: str) -> bool:
    ignored = (
        "facebook.com",
        "instagram.com",
        "linkedin.com",
        "twitter.com",
        "x.com",
        "youtube.com",
    )
    netloc = urlparse(url).netloc.lower()
    return any(netloc.endswith(domain) for domain in ignored)


def _extract_ddg_url(href: str) -> Optional[str]:
    if not href:
        return None
    if href.startswith("http"):
        parsed = urlparse(href)
        if parsed.netloc.endswith("duckduckgo.com") and parsed.path.startswith("/l/"):
            qs = parse_qs(parsed.query)
            uddg = qs.get("uddg")
            if uddg:
                return unquote(uddg[0])
        return href
    return None


def _search_duckduckgo(query: str, client: httpx.Client) -> List[str]:
    try:
        resp = client.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=8.0,
        )
        resp.raise_for_status()
    except Exception:
        return []
    soup = BeautifulSoup(resp.text, "html.parser")
    links = []
    for anchor in soup.find_all("a", class_="result__a"):
        href = _extract_ddg_url(anchor.get("href", ""))
        if not href:
            continue
        if not href.startswith("http"):
            continue
        if _is_ignored_domain(href):
            continue
        links.append(href)
    return list(dict.fromkeys(links))


def discover_local_source_feeds(
    location_name: str,
    zip_code: Optional[str] = None,
    max_feeds: int = 20,
) -> List[str]:
    location_hint = " ".join(part for part in [location_name, zip_code] if part)
    if not location_hint:
        return []
    queries = [
        f"{location_hint} police department",
        f"{location_hint} sheriff office",
        f"{location_hint} public safety",
        f"{location_hint} fire department",
        f"{location_hint} emergency management",
        f"{location_hint} local news",
        f"{location_hint} newspaper",
        f"{location_hint} tv station news",
    ]
    candidate_paths = (
        "rss",
        "feed",
        "news/rss",
        "news/feed",
        "press/rss",
        "press-releases/rss",
        "police/rss",
        "sheriff/rss",
        "public-safety/rss",
        "alerts/rss",
    )
    feeds: List[str] = []
    with httpx.Client(follow_redirects=True, timeout=8.0) as client:
        for query in queries:
            for result_url in _search_duckduckgo(query, client)[:6]:
                if len(feeds) >= max_feeds:
                    return feeds
                root_url = _root_url(result_url)
                for base_url in (result_url, root_url):
                    for feed in discover_feed_links(base_url, client):
                        if feed in feeds:
                            continue
                        if _validate_feed(feed, client):
                            feeds.append(feed)
                            if len(feeds) >= max_feeds:
                                return feeds
                for path in candidate_paths:
                    if len(feeds) >= max_feeds:
                        return feeds
                    candidate = f"{root_url.rstrip('/')}/{path}"
                    if candidate in feeds:
                        continue
                    if _validate_feed(candidate, client):
                        feeds.append(candidate)
    return feeds


def build_default_feeds(max_feeds: int = 180) -> List[str]:
    feeds: List[str] = []
    with httpx.Client(follow_redirects=True, timeout=8.0) as client:
        for source in DEFAULT_SOURCES:
            if len(feeds) >= max_feeds:
                break
            found = discover_feed_links(source.url, client)
            for feed in found:
                if feed not in feeds and _validate_feed(feed, client):
                    feeds.append(feed)
                    if len(feeds) >= max_feeds:
                        break
            if len(feeds) >= max_feeds:
                break
            for section in discover_section_links(source.url, client)[:5]:
                if len(feeds) >= max_feeds:
                    break
                for candidate in (f"{section}/rss", f"{section}/feed", f"{section}/rss.xml"):
                    if candidate in feeds:
                        continue
                    if _validate_feed(candidate, client):
                        feeds.append(candidate)
                        if len(feeds) >= max_feeds:
                            break
    return feeds


def ensure_seed_feeds(existing: List[str]) -> List[str]:
    if existing:
        return existing
    feeds = build_default_feeds()
    if feeds:
        return feeds
    return [
        "http://feeds.bbci.co.uk/news/rss.xml",
        "http://rss.cnn.com/rss/cnn_topstories.rss",
        "https://feeds.skynews.com/feeds/rss/home.xml",
    ]


def build_local_feeds(location_name: str, zip_code: Optional[str] = None) -> List[str]:
    queries = []
    if location_name:
        queries.append(location_name)
    if zip_code:
        queries.append(zip_code)
    if not queries:
        return []
    base = "https://news.google.com/rss/search"
    feed_queries = [
        " ".join(queries + ["police"]),
        " ".join(queries + ["sheriff"]),
        " ".join(queries + ["fire department"]),
        " ".join(queries + ["emergency management"]),
        " ".join(queries + ["weather alert"]),
        " ".join(queries + ["road closure"]),
    ]
    feeds = []
    for q in feed_queries:
        query = "+".join(
            part.strip().replace(" ", "+") for part in q.split() if part.strip()
        )
        feeds.append(f"{base}?q={query}&hl=en-US&gl=US&ceid=US:en")
    return feeds


def build_social_feeds(
    subject: str, location_name: str, zip_code: Optional[str] = None
) -> List[str]:
    if not subject:
        return []
    queries = [subject.strip()]
    location_hint = " ".join(part for part in [location_name, zip_code] if part)
    if location_hint:
        queries.append(f"{subject.strip()} {location_hint}".strip())
    feeds = []
    for query in dict.fromkeys(q for q in queries if q):
        encoded = quote_plus(query)
        feeds.append(f"https://www.reddit.com/search.rss?q={encoded}&sort=new")
    return feeds
