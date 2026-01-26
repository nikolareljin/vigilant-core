"""Curated sources and RSS discovery helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional
from urllib.parse import parse_qs, quote_plus, unquote, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup


@dataclass(frozen=True)
class Source:
    name: str
    url: str


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str


# US State abbreviations for NWS alerts
US_STATES: Dict[str, str] = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming", "DC": "District of Columbia",
    "PR": "Puerto Rico", "VI": "Virgin Islands", "GU": "Guam",
}

# ZIP code prefix to state mapping (first 3 digits) - Complete mapping
ZIP_TO_STATE: Dict[str, str] = {
    # Puerto Rico / Virgin Islands
    "006": "PR", "007": "PR", "009": "PR",
    "008": "VI",  # Virgin Islands uses 008xx
    # Massachusetts
    "010": "MA", "011": "MA", "012": "MA", "013": "MA", "014": "MA",
    "015": "MA", "016": "MA", "017": "MA", "018": "MA", "019": "MA",
    "020": "MA", "021": "MA", "022": "MA", "023": "MA", "024": "MA",
    "025": "MA", "026": "MA", "027": "MA", "055": "MA",
    # Rhode Island
    "028": "RI", "029": "RI",
    # New Hampshire
    "030": "NH", "031": "NH", "032": "NH", "033": "NH", "034": "NH", "038": "NH",
    # Vermont
    "035": "VT", "036": "VT", "037": "VT",
    "050": "VT", "051": "VT", "052": "VT", "053": "VT", "054": "VT",
    "056": "VT", "057": "VT", "058": "VT", "059": "VT",
    # Maine
    "039": "ME", "040": "ME", "041": "ME", "042": "ME", "043": "ME", "044": "ME",
    "045": "ME", "046": "ME", "047": "ME", "048": "ME", "049": "ME",
    # Connecticut
    "060": "CT", "061": "CT", "062": "CT", "063": "CT", "064": "CT",
    "065": "CT", "066": "CT", "067": "CT", "068": "CT", "069": "CT",
    # New Jersey
    "070": "NJ", "071": "NJ", "072": "NJ", "073": "NJ", "074": "NJ",
    "075": "NJ", "076": "NJ", "077": "NJ", "078": "NJ", "079": "NJ",
    "080": "NJ", "081": "NJ", "082": "NJ", "083": "NJ", "084": "NJ",
    "085": "NJ", "086": "NJ", "087": "NJ", "088": "NJ", "089": "NJ",
    # Military (AE, AP, AA)
    "090": "AE", "091": "AE", "092": "AE", "093": "AE", "094": "AE",
    "095": "AE", "096": "AE", "097": "AE", "098": "AE", "099": "AE",
    # New York
    "100": "NY", "101": "NY", "102": "NY", "103": "NY", "104": "NY",
    "105": "NY", "106": "NY", "107": "NY", "108": "NY", "109": "NY",
    "110": "NY", "111": "NY", "112": "NY", "113": "NY", "114": "NY",
    "115": "NY", "116": "NY", "117": "NY", "118": "NY", "119": "NY",
    "120": "NY", "121": "NY", "122": "NY", "123": "NY", "124": "NY",
    "125": "NY", "126": "NY", "127": "NY", "128": "NY", "129": "NY",
    "130": "NY", "131": "NY", "132": "NY", "133": "NY", "134": "NY",
    "135": "NY", "136": "NY", "137": "NY", "138": "NY", "139": "NY",
    "140": "NY", "141": "NY", "142": "NY", "143": "NY", "144": "NY",
    "145": "NY", "146": "NY", "147": "NY", "148": "NY", "149": "NY",
    # Pennsylvania
    "150": "PA", "151": "PA", "152": "PA", "153": "PA", "154": "PA",
    "155": "PA", "156": "PA", "157": "PA", "158": "PA", "159": "PA",
    "160": "PA", "161": "PA", "162": "PA", "163": "PA", "164": "PA",
    "165": "PA", "166": "PA", "167": "PA", "168": "PA", "169": "PA",
    "170": "PA", "171": "PA", "172": "PA", "173": "PA", "174": "PA",
    "175": "PA", "176": "PA", "177": "PA", "178": "PA", "179": "PA",
    "180": "PA", "181": "PA", "182": "PA", "183": "PA", "184": "PA",
    "185": "PA", "186": "PA", "187": "PA", "188": "PA", "189": "PA",
    "190": "PA", "191": "PA", "192": "PA", "193": "PA", "194": "PA",
    "195": "PA", "196": "PA",
    # Delaware
    "197": "DE", "198": "DE", "199": "DE",
    # DC
    "200": "DC", "201": "DC", "202": "DC", "203": "DC", "204": "DC", "205": "DC",
    # Maryland (complete)
    "206": "MD", "207": "MD", "208": "MD", "209": "MD",
    "210": "MD", "211": "MD", "212": "MD", "213": "MD", "214": "MD", "215": "MD",
    "216": "MD", "217": "MD", "218": "MD", "219": "MD",
    # Virginia
    "220": "VA", "221": "VA", "222": "VA", "223": "VA", "224": "VA",
    "225": "VA", "226": "VA", "227": "VA", "228": "VA", "229": "VA",
    "230": "VA", "231": "VA", "232": "VA", "233": "VA", "234": "VA",
    "235": "VA", "236": "VA", "237": "VA", "238": "VA", "239": "VA",
    "240": "VA", "241": "VA", "242": "VA", "243": "VA", "244": "VA",
    "245": "VA", "246": "VA",
    # West Virginia
    "247": "WV", "248": "WV", "249": "WV",
    "250": "WV", "251": "WV", "252": "WV", "253": "WV", "254": "WV",
    "255": "WV", "256": "WV", "257": "WV", "258": "WV", "259": "WV",
    "260": "WV", "261": "WV", "262": "WV", "263": "WV", "264": "WV",
    "265": "WV", "266": "WV", "267": "WV", "268": "WV", "269": "WV",
    # North Carolina
    "270": "NC", "271": "NC", "272": "NC", "273": "NC", "274": "NC",
    "275": "NC", "276": "NC", "277": "NC", "278": "NC", "279": "NC",
    "280": "NC", "281": "NC", "282": "NC", "283": "NC", "284": "NC",
    "285": "NC", "286": "NC", "287": "NC", "288": "NC", "289": "NC",
    # South Carolina
    "290": "SC", "291": "SC", "292": "SC", "293": "SC", "294": "SC",
    "295": "SC", "296": "SC", "297": "SC", "298": "SC", "299": "SC",
    # Georgia
    "300": "GA", "301": "GA", "302": "GA", "303": "GA", "304": "GA",
    "305": "GA", "306": "GA", "307": "GA", "308": "GA", "309": "GA",
    "310": "GA", "311": "GA", "312": "GA", "313": "GA", "314": "GA",
    "315": "GA", "316": "GA", "317": "GA", "318": "GA", "319": "GA",
    # Florida (complete)
    "320": "FL", "321": "FL", "322": "FL", "323": "FL", "324": "FL",
    "325": "FL", "326": "FL", "327": "FL", "328": "FL", "329": "FL",
    "330": "FL", "331": "FL", "332": "FL", "333": "FL", "334": "FL",
    "335": "FL", "336": "FL", "337": "FL", "338": "FL", "339": "FL",
    "340": "FL", "341": "FL", "342": "FL", "343": "FL", "344": "FL",
    "345": "FL", "346": "FL", "347": "FL", "348": "FL", "349": "FL",
    # Alabama (complete)
    "350": "AL", "351": "AL", "352": "AL", "353": "AL", "354": "AL", "355": "AL",
    "356": "AL", "357": "AL", "358": "AL", "359": "AL",
    "360": "AL", "361": "AL", "362": "AL", "363": "AL", "364": "AL",
    "365": "AL", "366": "AL", "367": "AL", "368": "AL", "369": "AL",
    # Tennessee
    "370": "TN", "371": "TN", "372": "TN", "373": "TN", "374": "TN",
    "375": "TN", "376": "TN", "377": "TN", "378": "TN", "379": "TN",
    "380": "TN", "381": "TN", "382": "TN", "383": "TN", "384": "TN",
    "385": "TN",
    # Mississippi
    "386": "MS", "387": "MS", "388": "MS", "389": "MS",
    "390": "MS", "391": "MS", "392": "MS", "393": "MS", "394": "MS",
    "395": "MS", "396": "MS", "397": "MS", "398": "MS", "399": "MS",
    # Kentucky (complete - includes 419-427)
    "400": "KY", "401": "KY", "402": "KY", "403": "KY", "404": "KY",
    "405": "KY", "406": "KY", "407": "KY", "408": "KY", "409": "KY",
    "410": "KY", "411": "KY", "412": "KY", "413": "KY", "414": "KY",
    "415": "KY", "416": "KY", "417": "KY", "418": "KY", "419": "KY",
    "420": "KY", "421": "KY", "422": "KY", "423": "KY", "424": "KY",
    "425": "KY", "426": "KY", "427": "KY",
    # Ohio
    "430": "OH", "431": "OH", "432": "OH", "433": "OH", "434": "OH",
    "435": "OH", "436": "OH", "437": "OH", "438": "OH", "439": "OH",
    "440": "OH", "441": "OH", "442": "OH", "443": "OH", "444": "OH",
    "445": "OH", "446": "OH", "447": "OH", "448": "OH", "449": "OH",
    "450": "OH", "451": "OH", "452": "OH", "453": "OH", "454": "OH",
    "455": "OH", "456": "OH", "457": "OH", "458": "OH", "459": "OH",
    # Indiana
    "460": "IN", "461": "IN", "462": "IN", "463": "IN", "464": "IN",
    "465": "IN", "466": "IN", "467": "IN", "468": "IN", "469": "IN",
    "470": "IN", "471": "IN", "472": "IN", "473": "IN", "474": "IN",
    "475": "IN", "476": "IN", "477": "IN", "478": "IN", "479": "IN",
    # Michigan
    "480": "MI", "481": "MI", "482": "MI", "483": "MI", "484": "MI",
    "485": "MI", "486": "MI", "487": "MI", "488": "MI", "489": "MI",
    "490": "MI", "491": "MI", "492": "MI", "493": "MI", "494": "MI",
    "495": "MI", "496": "MI", "497": "MI", "498": "MI", "499": "MI",
    # Iowa
    "500": "IA", "501": "IA", "502": "IA", "503": "IA", "504": "IA",
    "505": "IA", "506": "IA", "507": "IA", "508": "IA", "509": "IA",
    "510": "IA", "511": "IA", "512": "IA", "513": "IA", "514": "IA",
    "515": "IA", "516": "IA",
    # Wisconsin
    "520": "WI", "521": "WI", "522": "WI", "523": "WI", "524": "WI",
    "525": "WI", "526": "WI", "527": "WI", "528": "WI", "529": "WI",
    "530": "WI", "531": "WI", "532": "WI", "533": "WI", "534": "WI",
    "535": "WI", "536": "WI", "537": "WI", "538": "WI", "539": "WI",
    # Minnesota
    "540": "MN", "541": "MN", "542": "MN", "543": "MN", "544": "MN",
    "545": "MN", "546": "MN", "547": "MN", "548": "MN", "549": "MN",
    "550": "MN", "551": "MN", "552": "MN", "553": "MN", "554": "MN",
    "555": "MN", "556": "MN", "557": "MN", "558": "MN", "559": "MN",
    # South Dakota
    "560": "SD", "561": "SD", "562": "SD", "563": "SD", "564": "SD",
    "565": "SD", "566": "SD", "567": "SD",
    "570": "SD", "571": "SD", "572": "SD", "573": "SD", "574": "SD",
    "575": "SD", "576": "SD", "577": "SD",
    # North Dakota
    "580": "ND", "581": "ND", "582": "ND", "583": "ND", "584": "ND",
    "585": "ND", "586": "ND", "587": "ND", "588": "ND",
    # Montana
    "590": "MT", "591": "MT", "592": "MT", "593": "MT", "594": "MT",
    "595": "MT", "596": "MT", "597": "MT", "598": "MT", "599": "MT",
    # Illinois
    "600": "IL", "601": "IL", "602": "IL", "603": "IL", "604": "IL",
    "605": "IL", "606": "IL", "607": "IL", "608": "IL", "609": "IL",
    "610": "IL", "611": "IL", "612": "IL", "613": "IL", "614": "IL",
    "615": "IL", "616": "IL", "617": "IL", "618": "IL", "619": "IL",
    "620": "IL", "621": "IL", "622": "IL", "623": "IL", "624": "IL",
    "625": "IL", "626": "IL", "627": "IL", "628": "IL", "629": "IL",
    # Missouri
    "630": "MO", "631": "MO", "632": "MO", "633": "MO", "634": "MO",
    "635": "MO", "636": "MO", "637": "MO", "638": "MO", "639": "MO",
    "640": "MO", "641": "MO", "642": "MO", "643": "MO", "644": "MO",
    "645": "MO", "646": "MO", "647": "MO", "648": "MO", "649": "MO",
    "650": "MO", "651": "MO", "652": "MO", "653": "MO", "654": "MO",
    "655": "MO", "656": "MO", "657": "MO", "658": "MO",
    # Kansas
    "660": "KS", "661": "KS", "662": "KS", "663": "KS", "664": "KS",
    "665": "KS", "666": "KS", "667": "KS", "668": "KS", "669": "KS",
    "670": "KS", "671": "KS", "672": "KS", "673": "KS", "674": "KS",
    "675": "KS", "676": "KS", "677": "KS", "678": "KS", "679": "KS",
    # Nebraska
    "680": "NE", "681": "NE", "682": "NE", "683": "NE", "684": "NE",
    "685": "NE", "686": "NE", "687": "NE", "688": "NE", "689": "NE",
    "690": "NE", "691": "NE", "692": "NE", "693": "NE",
    # Louisiana
    "700": "LA", "701": "LA", "702": "LA", "703": "LA", "704": "LA",
    "705": "LA", "706": "LA", "707": "LA", "708": "LA",
    "710": "LA", "711": "LA", "712": "LA", "713": "LA", "714": "LA",
    # Arkansas
    "716": "AR", "717": "AR", "718": "AR", "719": "AR",
    "720": "AR", "721": "AR", "722": "AR", "723": "AR", "724": "AR",
    "725": "AR", "726": "AR", "727": "AR", "728": "AR", "729": "AR",
    # Oklahoma
    "730": "OK", "731": "OK", "732": "OK", "733": "OK", "734": "OK",
    "735": "OK", "736": "OK", "737": "OK", "738": "OK", "739": "OK",
    "740": "OK", "741": "OK", "742": "OK", "743": "OK", "744": "OK",
    "745": "OK", "746": "OK", "747": "OK", "748": "OK", "749": "OK",
    # Texas
    "750": "TX", "751": "TX", "752": "TX", "753": "TX", "754": "TX",
    "755": "TX", "756": "TX", "757": "TX", "758": "TX", "759": "TX",
    "760": "TX", "761": "TX", "762": "TX", "763": "TX", "764": "TX",
    "765": "TX", "766": "TX", "767": "TX", "768": "TX", "769": "TX",
    "770": "TX", "771": "TX", "772": "TX", "773": "TX", "774": "TX",
    "775": "TX", "776": "TX", "777": "TX", "778": "TX", "779": "TX",
    "780": "TX", "781": "TX", "782": "TX", "783": "TX", "784": "TX",
    "785": "TX", "786": "TX", "787": "TX", "788": "TX", "789": "TX",
    "790": "TX", "791": "TX", "792": "TX", "793": "TX", "794": "TX",
    "795": "TX", "796": "TX", "797": "TX", "798": "TX", "799": "TX",
    # Colorado
    "800": "CO", "801": "CO", "802": "CO", "803": "CO", "804": "CO",
    "805": "CO", "806": "CO", "807": "CO", "808": "CO", "809": "CO",
    "810": "CO", "811": "CO", "812": "CO", "813": "CO", "814": "CO",
    "815": "CO", "816": "CO",
    # Wyoming
    "820": "WY", "821": "WY", "822": "WY", "823": "WY", "824": "WY",
    "825": "WY", "826": "WY", "827": "WY", "828": "WY", "829": "WY",
    "830": "WY", "831": "WY",
    # Idaho
    "832": "ID", "833": "ID", "834": "ID", "835": "ID", "836": "ID", "837": "ID", "838": "ID",
    # Utah
    "840": "UT", "841": "UT", "842": "UT", "843": "UT", "844": "UT",
    "845": "UT", "846": "UT", "847": "UT",
    # Arizona (complete)
    "850": "AZ", "851": "AZ", "852": "AZ", "853": "AZ", "854": "AZ", "855": "AZ",
    "856": "AZ", "857": "AZ", "858": "AZ", "859": "AZ",
    "860": "AZ", "861": "AZ", "862": "AZ", "863": "AZ", "864": "AZ", "865": "AZ",
    # New Mexico
    "870": "NM", "871": "NM", "872": "NM", "873": "NM", "874": "NM",
    "875": "NM", "877": "NM", "878": "NM", "879": "NM",
    "880": "NM", "881": "NM", "882": "NM", "883": "NM", "884": "NM",
    # Nevada
    "889": "NV", "890": "NV", "891": "NV", "893": "NV", "894": "NV",
    "895": "NV", "897": "NV", "898": "NV",
    # California
    "900": "CA", "901": "CA", "902": "CA", "903": "CA", "904": "CA",
    "905": "CA", "906": "CA", "907": "CA", "908": "CA",
    "910": "CA", "911": "CA", "912": "CA", "913": "CA", "914": "CA",
    "915": "CA", "916": "CA", "917": "CA", "918": "CA",
    "919": "CA", "920": "CA", "921": "CA", "922": "CA", "923": "CA",
    "924": "CA", "925": "CA", "926": "CA", "927": "CA", "928": "CA",
    "930": "CA", "931": "CA", "932": "CA", "933": "CA", "934": "CA",
    "935": "CA", "936": "CA", "937": "CA", "938": "CA", "939": "CA",
    "940": "CA", "941": "CA", "942": "CA", "943": "CA", "944": "CA",
    "945": "CA", "946": "CA", "947": "CA", "948": "CA", "949": "CA",
    "950": "CA", "951": "CA", "952": "CA", "953": "CA", "954": "CA",
    "955": "CA", "956": "CA", "957": "CA", "958": "CA", "959": "CA",
    "960": "CA", "961": "CA",
    # Hawaii
    "967": "HI", "968": "HI",
    # Oregon
    "970": "OR", "971": "OR", "972": "OR", "973": "OR", "974": "OR",
    "975": "OR", "976": "OR", "977": "OR", "978": "OR", "979": "OR",
    # Washington
    "980": "WA", "981": "WA", "982": "WA", "983": "WA", "984": "WA",
    "985": "WA", "986": "WA", "988": "WA", "989": "WA",
    "990": "WA", "991": "WA", "992": "WA", "993": "WA", "994": "WA",
    # Alaska
    "995": "AK", "996": "AK", "997": "AK", "998": "AK", "999": "AK",
}


def get_state_from_zip(zip_code: str) -> Optional[str]:
    """Get state abbreviation from ZIP code.

    Args:
        zip_code: A valid US ZIP code (5 digits or 5+4 format like "12345-6789")

    Returns:
        Two-letter state abbreviation or None if invalid/not found
    """
    if not zip_code:
        return None

    # Strip whitespace and handle 5+4 format
    cleaned = zip_code.strip()
    if "-" in cleaned:
        cleaned = cleaned.split("-")[0]

    # Validate: must be exactly 5 digits
    if len(cleaned) != 5 or not cleaned.isdigit():
        return None

    prefix = cleaned[:3]
    return ZIP_TO_STATE.get(prefix)


def get_state_name(state_abbrev: str) -> Optional[str]:
    """Get full state name from abbreviation."""
    return US_STATES.get(state_abbrev.upper())


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
    # Handle protocol-relative URLs (e.g., //duckduckgo.com/l/...)
    if href.startswith("//"):
        href = "https:" + href
    if href.startswith("http"):
        parsed = urlparse(href)
        if parsed.netloc.endswith("duckduckgo.com") and parsed.path.startswith("/l/"):
            qs = parse_qs(parsed.query)
            uddg = qs.get("uddg")
            if uddg:
                return unquote(uddg[0])
        return href
    return None


def _search_duckduckgo_urls(query: str, client: httpx.Client) -> List[str]:
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


def _search_duckduckgo_results(query: str, client: httpx.Client) -> List[SearchResult]:
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
    results: List[SearchResult] = []
    for result in soup.select(".result"):
        anchor = result.select_one("a.result__a")
        if not anchor:
            continue
        href = _extract_ddg_url(anchor.get("href", ""))
        if not href or not href.startswith("http") or _is_ignored_domain(href):
            continue
        title = anchor.get_text(strip=True)
        snippet = ""
        snippet_el = result.select_one(".result__snippet")
        if snippet_el:
            snippet = snippet_el.get_text(" ", strip=True)
        results.append(SearchResult(title=title or "(no title)", url=href, snippet=snippet))
    return results


def search_duckduckgo_results(query: str, max_results: int = 20) -> List[SearchResult]:
    if not query:
        return []
    with httpx.Client(follow_redirects=True, timeout=8.0) as client:
        results = _search_duckduckgo_results(query, client)
    if max_results > 0:
        return results[:max_results]
    return results


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
            for result_url in _search_duckduckgo_urls(query, client)[:6]:
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


def build_all_feeds(max_feeds: int = 400) -> List[str]:
    return build_default_feeds(max_feeds=max_feeds)


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
    location_str = " ".join(queries)
    feed_queries = [
        f"{location_str} police",
        f"{location_str} sheriff",
        f"{location_str} fire department",
        f"{location_str} emergency management",
        f"{location_str} weather alert",
        f"{location_str} road closure",
    ]
    feeds = []
    for q in feed_queries:
        feeds.append(f"{base}?q={quote_plus(q)}&hl=en-US&gl=US&ceid=US:en")
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


def build_nws_weather_feeds(
    zip_code: Optional[str] = None,
    state_abbrev: Optional[str] = None,
) -> List[str]:
    """Build NWS weather alert feeds based on location.

    Returns state-specific CAP (Common Alerting Protocol) feeds from NWS.
    """
    feeds: List[str] = []

    # Determine state from ZIP if not provided
    if not state_abbrev and zip_code:
        state_abbrev = get_state_from_zip(zip_code)

    if state_abbrev:
        state = state_abbrev.lower()
        # NWS CAP alerts for the state
        feeds.append(f"https://alerts.weather.gov/cap/{state}.php?x=0")
        # Atom feed version
        feeds.append(f"https://alerts.weather.gov/cap/{state}.atom")

    # Always include national severe weather alerts
    feeds.append("https://alerts.weather.gov/cap/us.php?x=0")

    return feeds


def build_utility_search_queries(
    location_name: str,
    zip_code: Optional[str] = None,
    state_abbrev: Optional[str] = None,
) -> List[str]:
    """Build search queries for local utility companies and outage information."""
    queries: List[str] = []
    location_hint = " ".join(part for part in [location_name, zip_code] if part)

    if not location_hint:
        return queries

    # Get state name for more specific searches
    state_name = ""
    if state_abbrev:
        state_name = get_state_name(state_abbrev) or ""
    elif zip_code:
        state_abbrev = get_state_from_zip(zip_code)
        if state_abbrev:
            state_name = get_state_name(state_abbrev) or ""

    # Power/electric utility searches
    queries.extend([
        f"{location_hint} electric utility power outage",
        f"{location_hint} power company outage map",
        f"{location_hint} electric company service alerts",
    ])

    if state_name:
        queries.append(f"{state_name} power outage map")

    # Gas utility searches
    queries.append(f"{location_hint} gas utility emergency")

    # Water utility searches
    queries.append(f"{location_hint} water utility alerts")

    return queries


def build_emergency_service_queries(
    location_name: str,
    zip_code: Optional[str] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
) -> List[str]:
    """Build search queries for local emergency services."""
    queries: List[str] = []
    location_hint = " ".join(part for part in [location_name, zip_code] if part)

    if not location_hint:
        return queries

    # Police and law enforcement
    queries.extend([
        f"{location_hint} police department alerts",
        f"{location_hint} sheriff department news",
        f"{location_hint} police blotter",
    ])

    # Fire department
    queries.extend([
        f"{location_hint} fire department alerts",
        f"{location_hint} fire rescue news",
    ])

    # Emergency management
    queries.extend([
        f"{location_hint} emergency management alerts",
        f"{location_hint} office emergency services",
        f"{location_hint} public safety alerts",
    ])

    # Road and transportation
    queries.extend([
        f"{location_hint} road closure alerts",
        f"{location_hint} traffic alerts",
        f"{location_hint} department transportation alerts",
    ])

    return queries


def search_local_emergency_sources(
    location_name: str,
    zip_code: Optional[str] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    max_results: int = 30,
) -> List[SearchResult]:
    """Search for local emergency service information and sources."""
    results: List[SearchResult] = []

    # Build queries for emergency services
    queries = build_emergency_service_queries(
        location_name, zip_code, latitude, longitude
    )

    # Add utility queries
    state_abbrev = get_state_from_zip(zip_code) if zip_code else None
    queries.extend(build_utility_search_queries(location_name, zip_code, state_abbrev))

    seen_urls: set = set()
    with httpx.Client(follow_redirects=True, timeout=8.0) as client:
        for query in queries[:10]:  # Limit to avoid too many searches
            if len(results) >= max_results:
                break
            for result in _search_duckduckgo_results(query, client)[:5]:
                if result.url in seen_urls:
                    continue
                seen_urls.add(result.url)
                results.append(result)
                if len(results) >= max_results:
                    break

    return results


def discover_emergency_feeds(
    location_name: str,
    zip_code: Optional[str] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    max_feeds: int = 20,
) -> List[str]:
    """Discover RSS feeds from local emergency services, utilities, and government."""
    feeds: List[str] = []

    # Get state info
    state_abbrev = get_state_from_zip(zip_code) if zip_code else None
    state_name = get_state_name(state_abbrev) if state_abbrev else None

    # Add NWS weather feeds first (most reliable)
    nws_feeds = build_nws_weather_feeds(zip_code, state_abbrev)
    feeds.extend(nws_feeds)

    # Build search queries
    emergency_queries = build_emergency_service_queries(
        location_name, zip_code, latitude, longitude
    )
    utility_queries = build_utility_search_queries(location_name, zip_code, state_abbrev)

    # Additional targeted queries
    location_hint = " ".join(part for part in [location_name, zip_code] if part)
    targeted_queries = []
    if location_hint:
        targeted_queries = [
            f"{location_hint} county emergency alerts RSS",
            f"{location_hint} city government news RSS",
            f"{location_hint} local news RSS feed",
        ]
        if state_name:
            targeted_queries.append(f"{state_name} emergency management RSS")
            targeted_queries.append(f"{state_name} state police alerts RSS")

    all_queries = emergency_queries[:6] + utility_queries[:4] + targeted_queries

    candidate_paths = (
        "rss",
        "feed",
        "rss.xml",
        "atom.xml",
        "feed.xml",
        "news/rss",
        "news/feed",
        "alerts/rss",
        "alerts/feed",
        "press/rss",
        "media/rss",
    )

    with httpx.Client(follow_redirects=True, timeout=8.0) as client:
        for query in all_queries:
            if len(feeds) >= max_feeds:
                break

            # Search for potential sources
            for result_url in _search_duckduckgo_urls(query, client)[:4]:
                if len(feeds) >= max_feeds:
                    break

                root_url = _root_url(result_url)

                # Try to discover RSS feeds from the page
                for base_url in (result_url, root_url):
                    if len(feeds) >= max_feeds:
                        break

                    for feed in discover_feed_links(base_url, client):
                        if feed in feeds:
                            continue
                        if _validate_feed(feed, client):
                            feeds.append(feed)
                            if len(feeds) >= max_feeds:
                                break

                # Try common feed paths
                for path in candidate_paths:
                    if len(feeds) >= max_feeds:
                        break
                    candidate = f"{root_url.rstrip('/')}/{path}"
                    if candidate in feeds:
                        continue
                    if _validate_feed(candidate, client):
                        feeds.append(candidate)

    return feeds


def build_comprehensive_local_feeds(
    subject: str,
    location_name: str,
    zip_code: Optional[str] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
) -> List[str]:
    """Build a comprehensive list of feeds for a location including emergency services,
    weather, utilities, and local news.

    This is the main function to call for location-based feed discovery.
    """
    feeds: List[str] = []
    seen: set = set()

    def add_feed(feed: str) -> None:
        if feed and feed not in seen:
            seen.add(feed)
            feeds.append(feed)

    # Get state info
    state_abbrev = get_state_from_zip(zip_code) if zip_code else None

    # 1. NWS Weather alerts (high priority, very reliable)
    for feed in build_nws_weather_feeds(zip_code, state_abbrev):
        add_feed(feed)

    # 2. Google News feeds for local topics
    for feed in build_local_feeds(location_name, zip_code):
        add_feed(feed)

    # 3. Subject + location Google News feed
    if subject and location_name:
        query_parts = [subject, location_name]
        if zip_code:
            query_parts.append(zip_code)
        query = " ".join(part.strip() for part in query_parts if part.strip())
        add_feed(f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=en-US&gl=US&ceid=US:en")

    # 4. Emergency services and utility feeds (discovered)
    try:
        emergency_feeds = discover_emergency_feeds(
            location_name, zip_code, latitude, longitude, max_feeds=15
        )
        for feed in emergency_feeds:
            add_feed(feed)
    except Exception:
        pass  # Don't fail if discovery fails

    # 5. Local source feeds (police, fire, news)
    try:
        local_feeds = discover_local_source_feeds(location_name, zip_code, max_feeds=10)
        for feed in local_feeds:
            add_feed(feed)
    except Exception:
        pass  # Don't fail if local source discovery fails

    return feeds


def search_emergency_info(
    subject: str,
    location_name: str,
    zip_code: Optional[str] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    max_results: int = 30,
) -> List[SearchResult]:
    """Search for emergency-related information for a subject at a location.

    This combines subject-specific searches with location-specific emergency services.
    """
    results: List[SearchResult] = []
    seen_urls: set = set()

    # Get location context
    location_hint = " ".join(part for part in [location_name, zip_code] if part)
    state_abbrev = get_state_from_zip(zip_code) if zip_code else None
    state_name = get_state_name(state_abbrev) if state_abbrev else None

    # Build targeted queries combining subject with emergency context
    queries: List[str] = []

    if subject and location_hint:
        # Subject + emergency context for the location
        queries.extend([
            f"{subject} {location_hint} emergency alert",
            f"{subject} {location_hint} warning",
            f"{subject} {location_hint} advisory",
            f"{subject} {location_hint} safety",
        ])

        # Power/utility related if relevant keywords in subject
        power_keywords = {"storm", "weather", "outage", "power", "electric", "winter", "ice", "snow", "wind"}
        if any(kw in subject.lower() for kw in power_keywords):
            queries.extend([
                f"{location_hint} power outage",
                f"{location_hint} electric utility outage map",
                f"{location_hint} power restoration",
            ])
            if state_name:
                queries.append(f"{state_name} power outage map")

        # Road conditions if relevant
        road_keywords = {"storm", "weather", "snow", "ice", "flood", "road", "travel", "drive"}
        if any(kw in subject.lower() for kw in road_keywords):
            queries.extend([
                f"{location_hint} road conditions",
                f"{location_hint} road closure",
                f"{location_hint} travel advisory",
            ])

    # Search with the queries
    with httpx.Client(follow_redirects=True, timeout=8.0) as client:
        for query in queries[:12]:  # Limit queries
            if len(results) >= max_results:
                break
            for result in _search_duckduckgo_results(query, client)[:5]:
                if result.url in seen_urls:
                    continue
                seen_urls.add(result.url)
                results.append(result)
                if len(results) >= max_results:
                    break

    return results
