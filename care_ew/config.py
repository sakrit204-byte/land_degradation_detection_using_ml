"""Central configuration for the CARE-EW pipeline.

Every threshold used anywhere in the pipeline lives here so that the project log,
the paper and the code cannot drift apart. Change a value here -> re-run -> log it.
"""
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RAW = DATA / "raw"
PROC = DATA / "processed"
OUT = ROOT / "outputs"
FIG = OUT / "figures"
SHOT = OUT / "screenshots"
MODELS = OUT / "models"
for p in (RAW, PROC, FIG, SHOT, MODELS):
    p.mkdir(parents=True, exist_ok=True)

STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"


@dataclass(frozen=True)
class AOI:
    key: str          # short id, ISO3 + landscape
    country: str
    landscape: str    # biome / land-use context
    lon: float        # centre
    lat: float
    rationale: str
    half_km: float = 2.5   # box half-width -> 5 x 5 km

    @property
    def bbox(self):
        import math
        dlat = self.half_km / 110.574
        dlon = self.half_km / (111.320 * math.cos(math.radians(self.lat)))
        return [self.lon - dlon, self.lat - dlat, self.lon + dlon, self.lat + dlat]

    @property
    def utm_epsg(self):
        zone = int((self.lon + 180) // 6) + 1
        return (32600 if self.lat >= 0 else 32700) + zone


# Nine nations, five continents, contrasting climates/land uses. All labels are
# derived from ONE data provider (ESA Copernicus Sentinel-2 L2A) with ONE rule,
# expressed in locally standardised units, so they are consistent across nations.
AOIS = [
    AOI("NPL_chure", "Nepal", "Siwalik (Chure) foothill forest/agri mosaic", 85.95, 27.05,
        "Chure range: documented forest loss, erosion and sediment delivery to the Terai."),
    AOI("IND_bundelkhand", "India", "Semi-arid rainfed cropland / scrub", 79.60, 25.40,
        "Bundelkhand: recurrent drought, soil erosion and land abandonment."),
    AOI("ETH_tigray", "Ethiopia", "Highland cropland and degraded hillslopes", 39.50, 13.60,
        "Tigray highlands: classic soil-degradation region; strong drought & conflict shocks (2020-22)."),
    AOI("KEN_baringo", "Kenya", "Semi-arid rangeland", 35.98, 0.47,
        "Marigat / Il Chamus plains, Baringo: overgrazing, gully erosion, invasive Prosopis. (Moved from 36.05, 0.65: "
        "that block was 78 % Lake Baringo - PROJECT_LOG I-015.)"),
    AOI("SEN_ferlo", "Senegal", "Sahelian rangeland", -14.90, 15.40,
        "Ferlo: Sahel rainfall-driven greening/browning; tests climate conditioning."),
    AOI("ESP_murcia", "Spain", "Mediterranean semi-arid dryland", -1.35, 37.75,
        "Murcia: EU desertification hotspot; irrigated expansion vs abandoned drylands."),
    AOI("BRA_matopiba", "Brazil", "Cerrado savanna frontier", -45.90, -12.20,
        "Western Bahia (MATOPIBA): rapid native-vegetation conversion; strong true positives."),
    AOI("MNG_steppe", "Mongolia", "Temperate steppe", 106.50, 46.40,
        "Central Mongolia: grazing pressure + dzud/drought; cold-season snow masking."),
    AOI("AUS_murraydarling", "Australia", "Semi-arid rangeland / dryland cropping", 146.00, -31.50,
        "Western NSW: 2017-19 Millennium-scale drought -> decline that is CLIMATE, not degradation."),
]
# ---- expansion v2 (2026-10-20, PROJECT_LOG E-005): 4 more sites each in Nepal and India, screened for land
# cover before download (scripts/screen_sites.py -> data/candidates/screen.json). One site per nation could not
# represent within-nation variety; the learning curve (R-005) was still rising.
AOIS += [
    AOI("NPL_chure_dang", "Nepal", "Siwalik (Chure) hills, Dang - western Chure", 82.45, 27.95,
        "Western Chure: forest degradation, gravel mining, erosion into the Rapti valley."),
    AOI("NPL_chure_sarlahi", "Nepal", "Eastern Chure foothills, Sarlahi", 85.55, 27.10,
        "Eastern Chure: deforestation and erosion feeding Terai rivers."),
    AOI("NPL_kavre", "Nepal", "Middle-hills terraced farmland and degraded slopes", 85.62, 27.55,
        "Kavrepalanchok mid-hills: terrace abandonment, landslides, soil erosion."),
    AOI("NPL_surkhet", "Nepal", "Mid-western dry hills (Surkhet / Bheri)", 81.65, 28.55,
        "Surkhet: forest and shrubland degradation in the mid-western dry hills."),
    AOI("IND_banni", "India", "Banni grassland, Kachchh", 69.70, 23.65,
        "Banni: Asia's largest tropical grassland, degraded by Prosopis invasion and salinity."),
    AOI("IND_jharia", "India", "Jharia coalfield", 86.38, 23.75,
        "Jharia: open-cast coal mining, underground fires and subsidence."),
    AOI("IND_chambal", "India", "Chambal ravines", 78.30, 26.65,
        "Chambal ravines (Morena): one of Asia's largest gully-erosion badlands."),
    AOI("IND_thar", "India", "Thar desert margin", 72.70, 26.55,
        "Western Rajasthan (Jodhpur): desertification, wind erosion, overgrazing."),
    # ---- E-008 expansion (D-025): siblings for priority / poorly transferring landscapes; screened in
    # data/candidates/screen_v2.json (WorldCover usable share 0.96-1.00, no lakes or towns)
    AOI("NPL_chure_udayapur", "Nepal", "Eastern Chure foothills, Udayapur", 86.75, 26.90,
        "Eastern Chure: forest degradation, river-bed mining and erosion toward the Koshi/Terai."),
    AOI("NPL_chure_kailali", "Nepal", "Far-western Chure foothills, Kailali", 80.75, 28.85,
        "Far-western Chure: encroachment, fuelwood extraction and erosion feeding Terai rivers."),
    AOI("NPL_sindhupalchok", "Nepal", "Middle-hills forest/terraces and landslide slopes", 85.70, 27.85,
        "Sindhupalchok mid-hills: landslides (2015 earthquake legacy), terrace abandonment."),
    AOI("IND_marathwada", "India", "Marathwada semi-arid rainfed cropland", 75.65, 18.75,
        "Marathwada (Beed): recurrent drought, soil erosion, groundwater depletion."),
    AOI("IND_singrauli", "India", "Singrauli coalfield", 82.65, 24.15,
        "Singrauli: large open-cast coal mines and power plants; second mining landscape after Jharia."),
    AOI("IND_shivalik", "India", "Shivalik foothill forest, Uttarakhand", 78.05, 30.05,
        "Shivalik hills near Dehradun: foothill forest and scrub, same range as Nepal's Chure."),
]
NEW_SITES_E008 = ["NPL_chure_udayapur", "NPL_chure_kailali", "NPL_sindhupalchok", "IND_marathwada", "IND_singrauli", "IND_shivalik"]
AOI_BY_KEY = {a.key: a for a in AOIS}

# User-drawn areas (app "Draw box" tool, care_ew/ondemand.py). They are ONLY prediction targets: they are added
# to AOI_BY_KEY so every module can process them, but NOT to AOIS, so they never enter training/validation.
USER_AOI_FILE = DATA / "user_aois.json"
if USER_AOI_FILE.exists():
    import json as _json
    for _k, _d in _json.load(open(USER_AOI_FILE)).items():
        AOI_BY_KEY[_k] = AOI(_k, _d.get("country", "User area"), _d.get("landscape", "user area"),
                             float(_d["lon"]), float(_d["lat"]), _d.get("rationale", "user-drawn box"))

# ---------------------------------------------------------------- time axis
import os
S2_START = "2017-01"
S2_END = os.environ.get("CAREEW_S2_END", "2026-09")   # monthly composites (inclusive); operational updates override
MODIS_START = "2000-02"
CALIB_YEARS = (2017, 2020)                   # baseline climatology + climate model fit ONLY

# ---------------------------------------------------------------- Sentinel-2
S2_BANDS = ["B02", "B03", "B04", "B08", "B11", "B12", "SCL"]
S2_MAX_CLOUD = 70            # scene-level pre-filter (%); pixel masking does the real work
SCL_VALID = (4, 5, 6)        # vegetation, bare soil, water
BOA_OFFSET_BASELINE = 4.0    # baselines >= 04.00 carry BOA_ADD_OFFSET = -1000

# ---------------------------------------------------------------- labels (see labels.py)
@dataclass(frozen=True)
class LabelCfg:
    resid_thr: float = -1.0     # residual (z-units) at/below which a month is "below expectation"
    min_run: int = 6            # consecutive months required -> persistent (> one cropping season; D-015)
    min_abs_drop: float = 0.05  # mean NDVI loss vs peers over the first min_run months of a run (D-017)
    month_floor: float = 0.02   # per-month NDVI loss vs peers needed for a month to count (noise floor)
    horizon: int = 6            # predict onset in (t, t+H]
    max_gap_fill: int = 2       # months of linear interpolation allowed

LABEL = LabelCfg()
LABEL_SENSITIVITY = [LabelCfg(resid_thr=r, min_run=m) for r in (-0.75, -1.0, -1.5) for m in (4, 6, 9)]

# ---------------------------------------------------------------- sampling / splits
PIX_PER_AOI = 5000           # random pixels sampled per AOI (stratified on grid)
BLOCK_PX = 100               # 1 km spatial blocks for spatial CV
SPLIT = dict(
    train_end="2022-03",     # training: <= train_end   (its labels see data up to 2023-02)
    val_start="2023-03", val_end="2023-12",   # (val labels see data up to 2024-11)
    test_start="2024-12",    # test: >= test_start (final unseen; last labelable t = S2_END - 11 = 2025-10)
)
# embargo: gap between splits >= horizon + min_run - 1 months so that no label
# window of an earlier split can see the months of a later split.
SEED = 42
