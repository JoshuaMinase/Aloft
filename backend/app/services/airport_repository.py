from __future__ import annotations

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.airport import Airport

# Static coords for major world airports -- covers the vast majority of
# routes without burning an AviationStack request. Source: OurAirports
# public dataset (ourairports.com), WGS84 coordinates.
# When an IATA code isn't here, fall back to get_cached_airport() (DB
# cache from a prior AviationStack lookup) or call AviationStack directly.
_STATIC_AIRPORTS: dict[str, tuple[float, float]] = {
    # Africa
    "ADD": (8.9779, 38.7993),   # Addis Ababa Bole
    "NBO": (-1.3192, 36.9275),  # Nairobi Jomo Kenyatta
    "JNB": (-26.1392, 28.2460), # Johannesburg OR Tambo
    "CPT": (-33.9649, 18.6017), # Cape Town
    "LOS": (6.5774, 3.3216),    # Lagos
    "CAI": (30.1219, 31.4056),  # Cairo
    "CMN": (33.3675, -7.5900),  # Casablanca Mohammed V
    "ABJ": (5.2613, -3.9263),   # Abidjan
    "ACC": (5.6052, -0.1668),   # Accra
    "DAR": (-6.8781, 39.2026),  # Dar es Salaam
    "KGL": (-1.9686, 30.1395),  # Kigali
    "EBB": (0.0424, 32.4435),   # Entebbe
    # Middle East
    "DXB": (25.2532, 55.3657),  # Dubai
    "AUH": (24.4430, 54.6511),  # Abu Dhabi
    "DOH": (25.2731, 51.6080),  # Doha Hamad
    "RUH": (24.9576, 46.6988),  # Riyadh King Khalid
    "JED": (21.6796, 39.1565),  # Jeddah
    "AMM": (31.7226, 35.9932),  # Amman Queen Alia
    "BEY": (33.8209, 35.4884),  # Beirut
    "KWI": (29.2267, 47.9689),  # Kuwait City
    "BAH": (26.2708, 50.6336),  # Bahrain
    "MCT": (23.5933, 58.2844),  # Muscat
    # Europe
    "LHR": (51.4775, -0.4614),  # London Heathrow
    "CDG": (49.0097, 2.5479),   # Paris Charles de Gaulle
    "FRA": (50.0379, 8.5622),   # Frankfurt
    "AMS": (52.3086, 4.7639),   # Amsterdam Schiphol
    "MAD": (40.4936, -3.5668),  # Madrid Barajas
    "BCN": (41.2971, 2.0785),   # Barcelona
    "FCO": (41.8003, 12.2389),  # Rome Fiumicino
    "MXP": (45.6306, 8.7281),   # Milan Malpensa
    "MUC": (48.3537, 11.7750),  # Munich
    "ZRH": (47.4647, 8.5492),   # Zurich
    "VIE": (48.1103, 16.5697),  # Vienna
    "BRU": (50.9014, 4.4844),   # Brussels
    "ARN": (59.6519, 17.9186),  # Stockholm Arlanda
    "CPH": (55.6180, 12.6508),  # Copenhagen
    "OSL": (60.1939, 11.1004),  # Oslo Gardermoen
    "HEL": (60.3172, 24.9633),  # Helsinki
    "IST": (41.2753, 28.7519),  # Istanbul
    "ATH": (37.9364, 23.9445),  # Athens
    "LIS": (38.7813, -9.1359),  # Lisbon
    # Asia
    "DXB": (25.2532, 55.3657),  # Dubai (already above)
    "SIN": (1.3644, 103.9915),  # Singapore Changi
    "BKK": (13.6811, 100.7475), # Bangkok Suvarnabhumi
    "KUL": (2.7456, 101.7099),  # Kuala Lumpur
    "CGK": (-6.1256, 106.6559), # Jakarta
    "MNL": (14.5086, 121.0197), # Manila
    "ICN": (37.4602, 126.4407), # Seoul Incheon
    "NRT": (35.7653, 140.3856), # Tokyo Narita
    "HND": (35.5494, 139.7798), # Tokyo Haneda
    "PEK": (40.0799, 116.6031), # Beijing Capital
    "PVG": (31.1443, 121.8083), # Shanghai Pudong
    "HKG": (22.3080, 113.9185), # Hong Kong
    "DEL": (28.5562, 77.1000),  # Delhi Indira Gandhi
    "BOM": (19.0896, 72.8656),  # Mumbai
    "BLR": (13.1986, 77.7066),  # Bangalore
    "MAA": (12.9900, 80.1693),  # Chennai
    "CCU": (22.6542, 88.4467),  # Kolkata
    "KHI": (24.9065, 67.1608),  # Karachi
    "LHE": (31.5216, 74.4036),  # Lahore
    "ISB": (33.6167, 73.0997),  # Islamabad
    "CMB": (7.1808, 79.8841),   # Colombo
    "DAC": (23.8433, 90.3978),  # Dhaka
    "KTM": (27.6966, 85.3591),  # Kathmandu
    "RGN": (16.9073, 96.1332),  # Yangon
    # North America
    "JFK": (40.6413, -73.7781), # New York JFK
    "LAX": (33.9425, -118.4081),# Los Angeles
    "ORD": (41.9742, -87.9073), # Chicago O'Hare
    "DFW": (32.8998, -97.0403), # Dallas Fort Worth
    "MIA": (25.7959, -80.2870), # Miami
    "SFO": (37.6213, -122.3790),# San Francisco
    "ATL": (33.6407, -84.4277), # Atlanta
    "YYZ": (43.6777, -79.6248), # Toronto Pearson
    "YVR": (49.1947, -123.1792),# Vancouver
    "MEX": (19.4363, -99.0721), # Mexico City
    # South America
    "GRU": (-23.4356, -46.4731),# São Paulo Guarulhos
    "EZE": (-34.8222, -58.5358),# Buenos Aires Ezeiza
    "SCL": (-33.3930, -70.7858),# Santiago
    "BOG": (4.7016, -74.1469),  # Bogotá
    "LIM": (-12.0219, -77.1143),# Lima
    # Oceania
    "SYD": (-33.9461, 151.1772),# Sydney
    "MEL": (-37.6733, 144.8430),# Melbourne
    "BNE": (-27.3842, 153.1175),# Brisbane
    "AKL": (-37.0082, 174.7917),# Auckland
}


def lookup_static_airport(iata_code: str) -> tuple[float, float] | None:
    """Return (lat, lng) for a known IATA code from the static dataset.

    Returns None if the code isn't in the dataset -- caller should then
    try get_cached_airport() (DB cache) or fall back to AviationStack.
    """
    return _STATIC_AIRPORTS.get(iata_code.upper())


async def get_cached_airport(db: AsyncIOMotorDatabase, iata_code: str) -> Airport | None:
    doc = await db.airports.find_one({"iata_code": iata_code})
    if doc is None:
        return None
    doc.pop("_id", None)
    return Airport(**doc)


async def save_airport(db: AsyncIOMotorDatabase, airport: Airport) -> None:
    await db.airports.update_one(
        {"iata_code": airport.iata_code},
        {"$set": airport.to_mongo_dict()},
        upsert=True,
    )
