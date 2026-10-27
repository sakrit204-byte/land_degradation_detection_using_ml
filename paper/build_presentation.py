"""20-slide presentation for CARE-EW -> CARE-EW_Presentation.pptx (repo root).
Slides 2-3 are a glossary; every content slide carries an "explainer" box for the terms it uses.
Numbers come from outputs/results/metrics.json; references are read from build_conference_docx.py (REFS).
Run with the system Python (python-pptx):  python paper/build_presentation.py"""
import ast, json, os, re
from pathlib import Path
from PIL import Image
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION, XL_LEGEND_POSITION

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(os.environ.get("PPT_OUT", ROOT / "CARE-EW_Presentation.pptx"))
M = json.load(open(ROOT / "outputs" / "results" / "metrics.json"))
FM = M["final_model"]
SS = ROOT / "outputs" / "screenshots"; FIG = ROOT / "outputs" / "figures"; PF = ROOT / "paper" / "figs"

_src = (ROOT / "paper" / "build_conference_docx.py").read_text(encoding="utf-8")
_i = _src.index("REFS = ["); REFS = ast.literal_eval(_src[_i + 7:_src.index("\n]", _i) + 2])

DARK, GREEN, SOIL, INK, MUTED = "15291C", "2E6B3F", "B5562B", "1E2420", "5E6A62"
TINT, TINT_LINE, CARD, WHITE = "EAF2EC", "A9C7B2", "F4F6F5", "FFFFFF"
HEAD, BODY = "Cambria", "Calibri"
W, H = 13.333, 7.5


def rgb(h):
    return RGBColor.from_string(h)


prs = Presentation(); prs.slide_width = Inches(W); prs.slide_height = Inches(H)
BLANK = prs.slide_layouts[6]
N = [0]


def text(sl, x, y, w, h, runs, size=15, color=INK, bold=False, font=BODY, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP,
         margin=0.04, space=0):
    """runs: str, or list of paragraphs; a paragraph is str or list of (text, {opts})."""
    tb = sl.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h)); tf = tb.text_frame
    tf.word_wrap = True; tf.vertical_anchor = anchor
    for side in ("left", "right", "top", "bottom"):
        setattr(tf, f"margin_{side}", Inches(margin))
    paras = runs if isinstance(runs, list) else [runs]
    for k, p in enumerate(paras):
        para = tf.paragraphs[0] if k == 0 else tf.add_paragraph()
        para.alignment = align; para.space_after = Pt(space)
        for t, o in ([(p, {})] if isinstance(p, str) else p):
            r = para.add_run(); r.text = t; f = r.font
            f.name = o.get("font", font); f.size = Pt(o.get("size", size)); f.bold = o.get("bold", bold)
            f.italic = o.get("italic", False); f.color.rgb = rgb(o.get("color", color))
    return tb


def box(sl, x, y, w, h, fill=CARD, line=None, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.06):
    s = sl.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w), Inches(h))
    s.fill.solid(); s.fill.fore_color.rgb = rgb(fill)
    if line:
        s.line.color.rgb = rgb(line); s.line.width = Pt(0.75)
    else:
        s.line.fill.background()
    s.shadow.inherit = False
    if shape == MSO_SHAPE.ROUNDED_RECTANGLE:
        s.adjustments[0] = radius
    return s


def circle(sl, x, y, d, fill, label, size=12, color=WHITE):
    s = box(sl, x, y, d, d, fill=fill, shape=MSO_SHAPE.OVAL)
    tf = s.text_frame; tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    p = tf.paragraphs[0]; p.alignment = PP_ALIGN.CENTER; r = p.add_run(); r.text = label
    r.font.size = Pt(size); r.font.bold = True; r.font.color.rgb = rgb(color); r.font.name = HEAD
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    return s


def picture(sl, path, x, y, w, h, align="center"):
    iw, ih = Image.open(path).size
    s = min(w / iw, h / ih); pw, ph = iw * s, ih * s
    px = x + (w - pw) / 2 if align == "center" else x
    sl.shapes.add_picture(str(path), Inches(px), Inches(y + (h - ph) / 2), Inches(pw), Inches(ph))
    return px, y + (h - ph) / 2, pw, ph


def slide(title, notes, dark=False):
    sl = prs.slides.add_slide(BLANK); N[0] += 1
    bg = sl.background.fill; bg.solid(); bg.fore_color.rgb = rgb(DARK if dark else WHITE)
    if title:
        text(sl, 0.55, 0.3, W - 1.1, 0.75, title, size=30, bold=True, font=HEAD, color=WHITE if dark else DARK,
             anchor=MSO_ANCHOR.MIDDLE, margin=0)
    text(sl, 0.55, H - 0.42, 7, 0.3, "CARE-EW · satellite early warning of persistent land degradation", size=10,
         color="9DB3A5" if dark else MUTED, margin=0)
    text(sl, W - 1.55, H - 0.42, 1.0, 0.3, str(N[0]), size=10, color="9DB3A5" if dark else MUTED,
         align=PP_ALIGN.RIGHT, margin=0)
    sl.notes_slide.notes_text_frame.text = notes
    return sl


def explainer(sl, x, y, w, h, items, size=12, title="EXPLAINER"):
    """The deck's motif: a tinted rounded box with an 'i' badge defining the terms used on this slide."""
    box(sl, x, y, w, h, fill=TINT, line=TINT_LINE)
    circle(sl, x + 0.15, y + 0.13, 0.32, SOIL, "i", size=13)
    text(sl, x + 0.55, y + 0.12, w - 0.7, 0.34, title, size=11, bold=True, color=SOIL, anchor=MSO_ANCHOR.MIDDLE, margin=0)
    paras = [[(t + " — ", {"bold": True, "color": GREEN}), (d, {})] for t, d in items]
    text(sl, x + 0.15, y + 0.55, w - 0.3, h - 0.65, paras, size=size, space=5, margin=0)


def bullets(sl, x, y, w, h, items, size=15, space=8, color=INK):
    paras = []
    for it in items:
        if isinstance(it, tuple):
            paras.append([("▪  ", {"color": SOIL, "bold": True}), (it[0], {"bold": True}), (it[1], {})])
        else:
            paras.append([("▪  ", {"color": SOIL, "bold": True}), (it, {})])
    return text(sl, x, y, w, h, paras, size=size, space=space, color=color, margin=0)


def stat(sl, x, y, w, h, value, label, sub=None, fill=CARD, vcolor=GREEN):
    box(sl, x, y, w, h, fill=fill)
    text(sl, x + 0.15, y + 0.1, w - 0.3, h * 0.5, value, size=34, bold=True, font=HEAD, color=vcolor,
         anchor=MSO_ANCHOR.BOTTOM, margin=0)
    text(sl, x + 0.15, y + h * 0.5 + 0.12, w - 0.3, h * 0.5 - 0.2,
         [[(label, {"bold": True})]] + ([[(sub, {"size": 11, "color": MUTED})]] if sub else []), size=13, margin=0)


def table(sl, x, y, w, rows, colw, size=12, rowh=0.36, header_fill=GREEN):
    t = sl.shapes.add_table(len(rows), len(rows[0]), Inches(x), Inches(y), Inches(w), Inches(rowh * len(rows))).table
    for j, cw in enumerate(colw):
        t.columns[j].width = Inches(cw)
    for i, row in enumerate(rows):
        t.rows[i].height = Inches(rowh)
        for j, v in enumerate(row):
            c = t.cell(i, j); c.text = ""; c.margin_left = c.margin_right = Inches(0.06)
            c.margin_top = c.margin_bottom = Inches(0.02); c.vertical_anchor = MSO_ANCHOR.MIDDLE
            r = c.text_frame.paragraphs[0].add_run(); r.text = str(v); r.font.size = Pt(size); r.font.name = BODY
            r.font.bold = i == 0; r.font.color.rgb = rgb(WHITE if i == 0 else INK)
            c.fill.solid(); c.fill.fore_color.rgb = rgb(header_fill if i == 0 else (CARD if i % 2 else WHITE))
    return t


def style_chart(ch, title, size=11):
    ch.has_title = True; ch.chart_title.text_frame.text = title
    tr = ch.chart_title.text_frame.paragraphs[0].runs[0]; tr.font.size = Pt(13); tr.font.bold = True
    tr.font.color.rgb = rgb(INK); tr.font.name = BODY
    ch.font.size = Pt(size); ch.font.name = BODY; ch.font.color.rgb = rgb(MUTED)
    va = ch.value_axis; va.has_major_gridlines = True; va.major_gridlines.format.line.color.rgb = rgb("DDE3DF")
    va.format.line.fill.background(); ch.category_axis.format.line.color.rgb = rgb("B8C2BB")
    va.tick_labels.font.size = Pt(size); ch.category_axis.tick_labels.font.size = Pt(size)


def bar_chart(sl, x, y, w, h, cats, vals, title, colors, fmt='0.000', horizontal=False, size=11):
    cd = CategoryChartData(); cd.categories = cats; cd.add_series("v", vals)
    kind = XL_CHART_TYPE.BAR_CLUSTERED if horizontal else XL_CHART_TYPE.COLUMN_CLUSTERED
    ch = sl.shapes.add_chart(kind, Inches(x), Inches(y), Inches(w), Inches(h), cd).chart
    style_chart(ch, title, size); ch.has_legend = False
    pl = ch.plots[0]; pl.gap_width = 60; pl.has_data_labels = True
    dl = pl.data_labels; dl.number_format = fmt; dl.number_format_is_linked = False
    dl.position = XL_LABEL_POSITION.OUTSIDE_END; dl.font.size = Pt(size); dl.font.color.rgb = rgb(INK)
    for k, pt in enumerate(pl.series[0].points):
        pt.format.fill.solid(); pt.format.fill.fore_color.rgb = rgb(colors[k] if isinstance(colors, list) else colors)
    ch.value_axis.tick_labels.number_format = fmt; ch.value_axis.tick_labels.number_format_is_linked = False
    return ch


def caption(sl, x, y, w, s, size=11):
    text(sl, x, y, w, 0.3, s, size=size, color=MUTED, margin=0)


# ---------------------------------------------------------------- 1 title
sl = slide(None, "Introduce the project in one sentence: we use free satellite images and machine learning to warn, months "
           "ahead, where land is starting a long-lasting decline that the weather does not explain. The next two slides "
           "define every technical word used in the talk, so the audience can refer back to them.", dark=True)
picture(sl, SS / "ui_final" / "02_aoi_hotspots_rivers.png", 6.9, 0.0, 6.433, 7.5)
text(sl, 0.7, 1.2, 6.0, 0.4, "AI PROJECT · CONFERENCE PRESENTATION", size=12, bold=True, color="E3A27E", margin=0)
text(sl, 0.7, 1.7, 6.0, 1.9, "CARE-EW", size=60, bold=True, font=HEAD, color=WHITE, margin=0)
text(sl, 0.7, 2.75, 6.0, 1.5, "Climate-Adjusted, Resilience-Enhanced Early Warning of persistent land degradation "
     "from Sentinel-2 satellite imagery", size=20, color="DCE8E0", margin=0)
text(sl, 0.7, 4.55, 6.0, 1.4, [[("Ankur Bhattarai", {"bold": True}), ("  ·  24BCE2954", {})],
                               [("Team member 2  ·  ____________", {})], [("Team member 3  ·  ____________", {})]],
     size=15, color=WHITE, space=4, margin=0)
text(sl, 0.7, 6.15, 6.0, 0.4, "17 landscapes · 9 countries · 4.29 million pixel-months · 10 m resolution", size=13,
     color="9DB3A5", margin=0)

# ---------------------------------------------------------------- 2-3 glossary
GLOSS1 = [
    ("Remote sensing", "Measuring the Earth from a distance; here, cameras on satellites."),
    ("Sentinel-2", "European satellite pair imaging all land every ~5 days at 10 m detail in 13 colour bands."),
    ("Pixel", "One 10 m × 10 m square of ground: the unit we make a prediction for."),
    ("Spectral band", "One colour channel the camera records, e.g. red or near-infrared (NIR)."),
    ("Reflectance (BOA, L2A)", "Share of sunlight the ground reflects (0–1), corrected for the atmosphere."),
    ("Cloud mask (SCL)", "ESA's per-pixel flag for cloud, shadow and snow, so those pixels are dropped."),
    ("Monthly composite", "Median of all clear images in a month: one clean picture per month."),
    ("NDVI", "Greenness index (NIR − Red)/(NIR + Red): bare soil ≈ 0.1, dense crop ≈ 0.8."),
    ("NDMI · NBR · BSI", "Companion indices for leaf moisture, burn scars and bare soil."),
    ("MODIS", "NASA sensor, coarser (250 m) but imaging since 2000: gives the long history."),
    ("ERA5 / ERA5-Land", "Reanalysis: gap-free global weather (rain, temperature, soil water) from models + observations."),
    ("Land cover (WorldCover)", "ESA 10 m map labelling every pixel tree, shrub, grass, crop, bare …"),
    ("DEM", "Digital elevation model: a map of ground height (NASADEM, 30 m)."),
    ("GIS", "Geographic information systems: software and methods for maps and location data."),
    ("AOI", "Area of interest: one 5.12 × 5.12 km study landscape."),
    ("STAC / Planetary Computer", "Online catalogue and archive we search and download imagery from."),
    ("Land degradation", "Long-lasting loss of the land's ability to grow vegetation and hold soil."),
    ("VHR imagery", "Very-high-resolution (< 1 m) imagery; used to check warnings by eye."),
]
GLOSS2 = [
    ("Machine learning (ML)", "Software that learns a pattern from examples instead of hand-written rules."),
    ("Feature", "One input number per pixel-month, e.g. the 3-month NDVI change. We use 64."),
    ("Label (y)", "The answer to learn: 1 if a persistent decline starts within 6 months, else 0."),
    ("Baseline (μ)", "Normal value for that pixel and calendar month: median over 2017–2020."),
    ("Anomaly z-score", "How many typical deviations this month is from normal: z = (Y − μ)/σ."),
    ("MAD", "Median absolute deviation, a robust spread; σ = 1.4826 × MAD."),
    ("Residual (R)", "The part of the anomaly NOT explained by weather or by similar neighbours."),
    ("Resilience · AC1", "How fast land recovers; rising lag-1 autocorrelation = slower recovery = warning sign."),
    ("LightGBM", "Gradient-boosted decision trees: many small trees, each correcting the previous ones."),
    ("Overfitting", "Memorising training data, so accuracy collapses on new places or years."),
    ("Calibration", "Re-mapping scores so that “0.2” really means a 20 % chance (isotonic regression)."),
    ("Conformal prediction", "Adds a guarantee: answer “event”, “no event”, or abstain when unsure."),
    ("SHAP", "Explains a prediction by how much each feature pushed it up or down."),
    ("Spatial block split", "Test pixels come from 1 km blocks never used in training: no leakage."),
    ("Confusion matrix", "Counts of hits (TP), false alarms (FP), misses (FN), correct no's (TN)."),
    ("Precision · Recall", "Share of warnings that were right · share of real events we caught."),
    ("ROC-AUC · PR-AUC", "Ranking quality over all thresholds; PR-AUC suits rare events like ours."),
    ("Base rate · Lift", "Share of positives (2.5 %); lift = PR-AUC ÷ base rate = × better than chance."),
]


def glossary(title, items, notes):
    sl = slide(title, notes)
    cw, chh, gx, gy, x0, y0 = 3.95, 0.88, 0.17, 0.08, 0.55, 1.15
    for k, (t, d) in enumerate(items):
        c, r = k % 3, k // 3; x, y = x0 + c * (cw + gx), y0 + r * (chh + gy)
        box(sl, x, y, cw, chh, fill=CARD)
        circle(sl, x + 0.12, y + 0.14, 0.3, GREEN if c != 1 else SOIL, str(k + 1), size=10)
        text(sl, x + 0.52, y + 0.1, cw - 0.62, chh - 0.15, [[(t, {"bold": True, "color": DARK, "size": 13})], [(d, {})]],
             size=11.5, margin=0)
    return sl


glossary("Key terms 1/2 · satellites, land and GIS", GLOSS1,
         "Walk through the satellite vocabulary. Stress three things: a pixel is 10 m; NDVI is a greenness number "
         "from two colours; ERA5 is the weather record we use to tell drought apart from damage.")
glossary("Key terms 2/2 · machine learning and evaluation", GLOSS2,
         "Walk through the AI vocabulary. The essential idea: the model outputs a probability; we check it is honest "
         "(calibration), say when it is unsure (conformal), and measure it on places it never saw (spatial blocks).")

# ---------------------------------------------------------------- 4 problem
sl = slide("Why an early warning, not another damage map",
           "Land degradation is slow. Maps that show where vegetation already declined arrive too late for cheap "
           "action, and they confuse a dry year with real damage. Our question is predictive: will this pixel start a "
           "persistent, weather-unexplained decline within six months?")
cards = [("The problem", "Over-grazing, mining, clearing and erosion strip vegetation slowly. When it is obvious, "
                         "recovery is slow and expensive."),
         ("The gap", "Common tools (e.g. SDG 15.3.1 trend maps) report damage after it happened, at 250 m–1 km, and "
                     "struggle to separate drought from human-driven decline."),
         ("Our aim", "For every 10 m pixel and month, the probability that a persistent decline starts in the next "
                     "6 months, after removing what the weather explains, plus an honest “not sure”.")]
for k, (t, d) in enumerate(cards):
    y = 1.25 + k * 1.33
    box(sl, 0.55, y, 6.3, 1.18)
    circle(sl, 0.72, y + 0.33, 0.52, [SOIL, MUTED, GREEN][k], str(k + 1), size=16)
    text(sl, 1.42, y + 0.1, 5.3, 1.0, [[(t, {"bold": True, "size": 16, "color": DARK})], [(d, {})]], size=14, margin=0)
explainer(sl, 0.55, 5.3, 6.3, 1.65, [("Persistent", "below expectation for ≥ 6 months in a row, not a single bad month"),
                                    ("Early warning", "a forecast issued before the decline starts (here up to 6 months)")])
px, py, pw, ph = picture(sl, PF / "risk_maps.png", 7.2, 1.2, 5.6, 5.6)
caption(sl, 7.2, py + ph + 0.02, 5.6, "Predicted risk maps, nine study areas, Sept 2026 (red = higher probability)")

# ---------------------------------------------------------------- 5 study areas + data
sl = slide("17 landscapes, 9 countries, 7 open data sources",
           "Each study area is 5.12 km square. Landscapes span drylands, rangelands, cropland, forest frontier and mining "
           "areas on five continents. All inputs are free and open; Sentinel-2 drives the 10 m detail.")
px, py, pw, ph = picture(sl, FIG / "fig01_study_areas.png", 0.45, 1.15, 6.6, 3.6)
caption(sl, 0.55, py + ph + 0.02, 6.4, "Study areas (Nepal and India hold 9 of the 17 sites)")
table(sl, 7.25, 1.2, 5.55, [["Source", "What we use", "Detail"],
                            ["Sentinel-2 L2A", "NDVI, NDMI, NBR, BSI", "10 m, 2017–2026"],
                            ["MODIS MOD13Q1", "NDVI history", "250 m, 2000–"],
                            ["ERA5 / ERA5-Land", "rain, temperature, soil water", "9–31 km"],
                            ["ESA WorldCover", "land-cover class", "10 m"],
                            ["NASADEM", "elevation, slope", "30 m"],
                            ["JRC water · HydroRIVERS", "distance to water, rivers", "30 m / vector"],
                            ["GloFAS", "river discharge", "~5 km"]], [1.85, 2.3, 1.4], size=12, rowh=0.4)
stat(sl, 0.55, 5.2, 2.05, 1.6, "4.29 M", "pixel-months", "rows in the dataset")
stat(sl, 2.75, 5.2, 2.05, 1.6, "64", "features", "per pixel-month")
stat(sl, 4.95, 5.2, 2.05, 1.6, "2.5 %", "positives", "rare-event problem")
explainer(sl, 7.25, 4.7, 5.55, 2.25, [("L2A", "Sentinel-2 product already corrected for the atmosphere"),
                                     ("Reanalysis", "weather model re-run with past observations to fill every gap"),
                                     ("Discharge", "volume of water flowing in a river, m³/s")])

# ---------------------------------------------------------------- 6 pipeline
sl = slide("From raw images to a warning: the pipeline",
           "Explain the flow top to bottom. Inputs are cleaned into monthly pictures; a climate model removes what the "
           "weather explains; features describe state, change, residual and resilience; LightGBM predicts; "
           "calibration and conformal prediction make the probability honest.")
picture(sl, PF / "arch.png", 0.45, 1.1, 6.4, 5.85)
steps = [("Clean", "remove duplicates, fix the +1000 offset, mask cloud, take the monthly median"),
         ("Normalise", "compare each month with that pixel's own 2017–2020 normal → z-score"),
         ("Remove climate", "ridge model of the weather's effect; subtract it and the neighbours' median → residual R"),
         ("Label", "mark where a ≥ 6-month unexplained decline begins; target = onset within 6 months"),
         ("Learn", "64 features → LightGBM → isotonic calibration → conformal abstain"),
         ("Serve", "monthly risk map, hotspots and explanations in the web console")]
for k, (t, d) in enumerate(steps):
    y = 1.15 + k * 0.66
    circle(sl, 7.1, y + 0.06, 0.42, GREEN if k < 5 else SOIL, str(k + 1), size=13)
    text(sl, 7.65, y, 5.2, 0.62, [[(t + "  ", {"bold": True, "color": DARK}), (d, {"size": 13})]], size=14, margin=0)
explainer(sl, 7.1, 5.2, 5.7, 1.75, [("Pipeline", "fixed chain of steps run the same way for every area"),
                                   ("Median composite", "middle value of a month's clear images; ignores outliers"),
                                   ("Ridge", "linear regression with a penalty that keeps weights small and stable")],
          size=12)

# ---------------------------------------------------------------- 7 worked numbers 1
sl = slide("Worked example 1 · from a raw pixel to an anomaly",
           "Go through the arithmetic slowly. The +1000 offset was added by ESA from processing baseline 04.00 (2022); "
           "forgetting it makes recent images look darker and would invent a fake decline. The z-score of −2.5 means "
           "this month is 2.5 typical deviations below this pixel's normal for this calendar month.")
cols = [("1 · Raw → reflectance", ["Red band DN = 2 500", "NIR band DN = 5 000", "ρ = (DN − 1 000) / 10 000",
                                  "Red = 0.15 · NIR = 0.40"]),
        ("2 · Greenness (NDVI)", ["NDVI = (NIR − Red)/(NIR + Red)", "= (0.40 − 0.15)/(0.40 + 0.15)", "= 0.25 / 0.55",
                                 "= 0.45"]),
        ("3 · Normal for this month", ["μ = median NDVI of all", "Julys 2017–2020 = 0.60", "MAD = 0.04",
                                      "σ = 1.4826 × 0.04 = 0.059"]),
        ("4 · Anomaly z-score", ["z = (Y − μ) / σ", "= (0.45 − 0.60) / 0.059", "= −2.5",
                                "well below normal"])]
for k, (t, lines) in enumerate(cols):
    x = 0.55 + k * 3.12
    box(sl, x, 1.25, 2.85, 2.55, fill=CARD)
    text(sl, x + 0.15, 1.35, 2.6, 0.45, t, size=15, bold=True, color=SOIL if k == 3 else DARK, margin=0)
    text(sl, x + 0.15, 1.9, 2.6, 2.3, [[(l, {"bold": i == 3, "size": 16 if i == 3 else 14,
                                            "color": GREEN if i == 3 else INK})] for i, l in enumerate(lines)],
         space=6, margin=0)
    if k < 3:
        a = sl.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, Inches(x + 2.88), Inches(2.35), Inches(0.22), Inches(0.32))
        a.fill.solid(); a.fill.fore_color.rgb = rgb(SOIL); a.line.fill.background()
text(sl, 0.55, 4.1, 12.2, 0.6, [[("Why this matters: ", {"bold": True, "color": DARK}),
                                  ("each pixel is compared with its own past, so a naturally sparse desert pixel and a "
                                   "lush forest pixel are judged on the same scale.", {})]], size=14, margin=0)
explainer(sl, 0.55, 4.85, 6.0, 2.1, [("DN", "digital number: the integer the satellite stores"),
                                    ("+1000 offset", "added by ESA to images processed since 2022; we subtract it"),
                                    ("σ floor 0.02", "σ is never below 0.02 so tiny wobbles do not look extreme")],
          size=12)
explainer(sl, 6.8, 4.85, 6.0, 2.1, [("μ (mu)", "the pixel's normal value for that calendar month"),
                                   ("σ (sigma)", "the pixel's typical deviation from normal"),
                                   ("1.4826", "constant that makes MAD comparable to a standard deviation")],
          size=11.5, title="SYMBOLS")

# ---------------------------------------------------------------- 8 climate + labels
sl = slide("Worked example 2 · separating drought from damage",
           "Same z-score, two different stories. In a drought year the weather model expects the drop, so the residual "
           "is small and nothing is flagged. In a normal-rain year the same drop is unexplained, and if it persists "
           "six months it becomes a labelled degradation onset. The figure shows a real Spanish pixel.")
box(sl, 0.55, 1.2, 6.5, 0.75, fill=DARK)
text(sl, 0.7, 1.2, 6.2, 0.75, "R = (z − β·g) − median of same-land-cover peers", size=19, bold=True, font=HEAD,
     color=WHITE, anchor=MSO_ANCHOR.MIDDLE, margin=0)
table(sl, 0.55, 2.1, 6.5, [["", "Drought year", "Normal-rain year"],
                           ["Anomaly z", "−2.5", "−2.5"],
                           ["Weather-expected g (β = 1)", "−2.0", "0.0"],
                           ["z − β·g", "−0.5", "−2.5"],
                           ["Peers' median", "−0.3", "0.0"],
                           ["Residual R", "−0.2", "−2.5"],
                           ["Below expectation? (R ≤ −1)", "No: weather explains it", "Yes"]],
      [2.7, 1.9, 1.9], size=13, rowh=0.38)
text(sl, 0.55, 4.8, 6.5, 0.85, [[("Label rule: ", {"bold": True, "color": DARK}),
                                  ("onset = ≥ 6 months in a row below expectation (and ≥ 0.02 NDVI under peers), "
                                   "≥ 75 % of months observed, mean loss ≥ 0.05 NDVI. Target yₜ = 1 if an onset "
                                   "falls in months t+1 … t+6.", {})]], size=13.5, margin=0)
explainer(sl, 0.55, 5.65, 6.5, 1.35, [("g, β", "g = weather-predicted anomaly from rain, temperature, soil water; "
                                                "β = how strongly this pixel follows it (0–3)"),
                                     ("Peers", "pixels of the same land cover in the same area")], size=11)
px, py, pw, ph = picture(sl, FIG / "fig03_method_example.png", 7.3, 1.15, 5.5, 5.5)
caption(sl, 7.3, py + ph + 0.02, 5.5, "Real pixel (Spain): observation, climate-expected, residual, labelled onsets")

# ---------------------------------------------------------------- 9 features + model
sl = slide("What the model sees and how it learns",
           "Sixty-four features in six groups. The resilience group is the novel part: when land loses resilience it "
           "recovers more slowly, which shows up as rising autocorrelation and variance before the decline. LightGBM is "
           "deliberately kept small and heavily regularised so it generalises to new places.")
groups = [("A1 State", "current NDVI, σ, land cover", GREEN), ("A2 Change", "NDVI change over 3, 12, 36 months", GREEN),
          ("A3 Climate", "rain, temperature, soil-water anomalies", GREEN),
          ("A4 Residual", "R mean, minimum, months below, run length", SOIL),
          ("A5 Resilience", "AC1, variance (24 mo), MODIS 5-year signals", SOIL),
          ("A6 Context", "distance to river, slope, elevation, water", GREEN)]
for k, (t, d, c) in enumerate(groups):
    x, y = 0.55 + (k % 2) * 3.15, 1.2 + (k // 2) * 1.02
    box(sl, x, y, 3.0, 0.9)
    circle(sl, x + 0.12, y + 0.22, 0.46, c, t.split()[0], size=11)
    text(sl, x + 0.68, y + 0.08, 2.25, 0.8, [[(t.split(" ", 1)[1], {"bold": True, "color": DARK})], [(d, {"size": 12})]],
         size=14, margin=0)
table(sl, 7.0, 1.2, 5.8, [["LightGBM setting", "Plain meaning"],
                          ["7 leaves per tree", "each tree is a tiny rule set → less memorising"],
                          ["≥ 4 000 pixels per leaf", "no rule may rest on a handful of pixels"],
                          ["40 % features · 70 % rows", "each tree sees a random subset → diversity"],
                          ["L2 = 50 · extra-trees", "strong penalty, random split points → smooth"],
                          ["learning rate 0.03", "small steps; many trees add up slowly"],
                          ["early stop on PR-AUC", "stop when validation score stops improving"]],
      [2.4, 3.4], size=12, rowh=0.42)
text(sl, 7.0, 4.25, 5.8, 0.5, [[("Training: ", {"bold": True, "color": DARK}),
                                ("800,784 rows, 14 s on a laptop CPU (Core 5 210H).", {})]], size=13.5, margin=0)
explainer(sl, 0.55, 4.35, 6.2, 2.6, [("Decision tree", "a flowchart of yes/no questions on features ending in a score"),
                                    ("Gradient boosting", "add trees one by one, each fixing the errors left so far"),
                                    ("AC1", "correlation of a month with the month before; near 1 = slow recovery"),
                                    ("Regularisation", "rules that stop a model from becoming too complex")],
          size=12)
explainer(sl, 7.0, 4.85, 5.8, 2.1, [("Leaf", "end point of a tree, holding one score"),
                                   ("Early stopping", "halting training at the best validation score"),
                                   ("Validation set", "held-out data used only to tune, never to report")], size=12)

# ---------------------------------------------------------------- 10 calibration + honest testing
sp = M["split_sizes"]
sl = slide("Honest probabilities and honest testing",
           "Two ideas. First, the score is calibrated so 0.13 really means about a 13 % chance, and conformal prediction "
           "lets the model abstain when it cannot be confident. Second, test pixels are from different 1 km blocks and a "
           "later time than training, with gaps so the 6-month label window cannot leak.")
table(sl, 0.55, 1.2, 6.7, [["Set", "Months", "Pixel-months", "Used for"],
                           ["Train", "≤ 2022-03", f"{sp['train']['rows']:,}", "fit the trees"],
                           ["Early stop", "2023-03 … 12", f"{sp['early_stop']['rows']:,}", "when to stop"],
                           ["Calibration", "2023-03 … 12", f"{sp['calibration']['rows']:,}", "isotonic + conformal"],
                           ["Test", "≥ 2024-12, test blocks", f"{sp['test']['rows']:,}", "every reported number"]],
      [1.35, 2.0, 1.55, 1.8], size=12.5, rowh=0.42)
text(sl, 0.55, 3.45, 6.7, 0.7, [[("1 km blocks ", {"bold": True, "color": DARK}),
                                 ("are split 60/20/20, so neighbouring pixels never sit on both sides of the "
                                  "train/test line.", {})]], size=13.5, margin=0)
outs = [("p ≥ 0.129", "WARNING", "≈ 5× the 2.5 % base rate", SOIL), ("conformal: no event", "NO EVENT", "NPV 99.6 %", GREEN),
        ("conformal: both possible", "ABSTAIN", "52 % of pixel-months → inspect", MUTED)]
for k, (a, b, c, col) in enumerate(outs):
    x = 7.5 + 0
    y = 1.2 + k * 1.0
    box(sl, x, y, 5.3, 0.85)
    circle(sl, x + 0.12, y + 0.12, 0.6, col, "!" if k == 0 else ("✓" if k == 1 else "?"), size=16)
    text(sl, x + 0.85, y + 0.06, 4.35, 0.75, [[(b, {"bold": True, "color": col}), ("   " + a, {"size": 12, "color": MUTED})],
                                              [(c, {"size": 13})]], size=15, margin=0)
explainer(sl, 0.55, 4.3, 6.7, 2.65, [("Isotonic calibration", "step-wise mapping from raw score to observed frequency, "
                                                              "learnt on the calibration set"),
                                    ("Conformal, α = 0.10", "sets of answers that contain the truth ≥ 90 % of the time; "
                                                            "a two-answer set means “abstain”"),
                                    ("Data leakage", "test information sneaking into training; inflates scores"),
                                    ("NPV", "of the “no event” calls, the share that were right")], size=12)
explainer(sl, 7.5, 4.3, 5.3, 2.65, [("Threshold 0.129", "the cut-off that maximises F1 on the calibration set"),
                                   ("Abstain", "the model says “inspect in the field” instead of guessing"),
                                   ("Base rate", "share of pixel-months that truly had an onset ahead (2.5 %)")],
          size=12)

# ---------------------------------------------------------------- 11 headline results
sl = slide("Headline results on 132,230 unseen test pixel-months",
           f"ROC-AUC 0.805 means: pick one pixel that degraded and one that did not; 80 % of the time the model ranks "
           f"the degrading one higher. PR-AUC 0.144 is 5.7 times the 0.025 chance level. Brackets are 95 % bootstrap "
           f"confidence intervals. All three simpler baselines are far behind.")
ci_r, ci_p = FM["roc_auc_ci"], FM["pr_auc_ci"]
stat(sl, 0.55, 1.25, 2.9, 1.75, f"{FM['roc_auc']:.3f}", "ROC-AUC", f"95 % CI {ci_r[0]:.3f}–{ci_r[1]:.3f}")
stat(sl, 3.6, 1.25, 2.9, 1.75, f"{FM['pr_auc']:.3f}", "PR-AUC", f"95 % CI {ci_p[0]:.3f}–{ci_p[1]:.3f}")
stat(sl, 0.55, 3.15, 2.9, 1.75, f"{FM['pr_auc_lift']:.1f}×", "better than chance", "lift = 0.144 ÷ 0.025",
     vcolor=SOIL)
stat(sl, 3.6, 3.15, 2.9, 1.75, f"{FM['ece']:.4f}", "calibration error (ECE)", f"Brier score {FM['brier']:.4f}")
bar_chart(sl, 6.85, 1.15, 5.95, 3.85, ["Chance", "Anomaly persistence", "RF, Sentinel-2 only", "Residual rule", "CARE-EW"],
          [FM["base_rate"], 0.036, 0.044, 0.055, FM["pr_auc"]], "Test PR-AUC: CARE-EW vs simpler methods",
          ["B8C2BB", "B8C2BB", "B8C2BB", "B8C2BB", GREEN], size=11)
explainer(sl, 0.55, 5.1, 6.0, 1.85, [("95 % CI", "range from bootstrap resamples of the test blocks"),
                                    ("ECE", "average gap between predicted and observed frequency (0 = perfect)"),
                                    ("Brier", "mean squared error of the probability (lower = better)")], size=12)
explainer(sl, 6.85, 5.1, 5.95, 1.85, [("Persistence", "“what was bad stays bad”: recent anomaly as the score"),
                                     ("Residual rule", "hand-made score from the recent residual R, no ML"),
                                     ("RF, S2-only", "random forest on Sentinel-2 features only")], size=11.5,
          title="BASELINES")

# ---------------------------------------------------------------- 12 confusion matrix
TP, FP, FN, TN = 963, 3468, 2364, 125435
n = TP + FP + FN + TN
sl = slide("Confusion matrix at the warning threshold (p ≥ 0.129)",
           "Read the four boxes, then the arithmetic. Accuracy is 95.6 %, but a model that always says 'no' would score "
           "97.5 % because events are rare, so accuracy is the wrong yardstick. Precision 0.22 means about one warning "
           "in five is followed by an onset, versus one in forty by chance.")
gx, gy, cw2, chh = 1.75, 1.75, 2.35, 1.55
text(sl, gx, 1.15, 2 * cw2 + 0.1, 0.35, "Actual outcome in next 6 months", size=13, bold=True, color=MUTED,
     align=PP_ALIGN.CENTER, margin=0)
text(sl, gx, 1.45, cw2, 0.3, "Onset", size=13, bold=True, align=PP_ALIGN.CENTER, margin=0)
text(sl, gx + cw2 + 0.1, 1.45, cw2, 0.3, "No onset", size=13, bold=True, align=PP_ALIGN.CENTER, margin=0)
text(sl, 0.45, gy + 0.55, 1.25, 0.5, "Warned", size=13, bold=True, align=PP_ALIGN.RIGHT, margin=0)
text(sl, 0.45, gy + chh + 0.65, 1.25, 0.5, "Not warned", size=13, bold=True, align=PP_ALIGN.RIGHT, margin=0)
cells = [(0, 0, "TP", TP, "hits", GREEN), (1, 0, "FP", FP, "false alarms", SOIL),
         (0, 1, "FN", FN, "misses", "8A5A44"), (1, 1, "TN", TN, "correct no's", "4F7D5C")]
for c, r, a, v, d, col in cells:
    x, y = gx + c * (cw2 + 0.1), gy + r * (chh + 0.1)
    box(sl, x, y, cw2, chh, fill=col)
    text(sl, x, y + 0.12, cw2, 1.3, [[(f"{v:,}", {"size": 30, "bold": True, "font": HEAD})], [(f"{a} · {d}", {})]],
         size=13, color=WHITE, align=PP_ALIGN.CENTER, margin=0)
rows = [["Metric", "Formula", "Value"],
        ["Precision", f"TP/(TP+FP) = {TP}/{TP + FP:,}", f"{TP / (TP + FP):.3f}"],
        ["Recall", f"TP/(TP+FN) = {TP}/{TP + FN:,}", f"{TP / (TP + FN):.3f}"],
        ["F1", "2·P·R/(P+R)", f"{2 * TP / (2 * TP + FP + FN):.3f}"],
        ["Specificity", f"TN/(TN+FP)", f"{TN / (TN + FP):.3f}"],
        ["False-alarm rate", "FP/(FP+TN)", f"{FP / (FP + TN):.3f}"],
        ["Accuracy", f"(TP+TN)/{n:,}", f"{(TP + TN) / n:.3f}"],
        ["“Always no” accuracy", f"{TN + FP:,}/{n:,}", f"{(TN + FP) / n:.3f}"]]
table(sl, 7.0, 1.2, 5.8, rows, [1.9, 2.75, 1.15], size=12.5, rowh=0.4)
explainer(sl, 0.55, 5.25, 6.2, 1.7, [("Why not accuracy?", "with 2.5 % positives, saying “no” to everything already "
                                                          "scores 97.5 %"),
                                    ("Precision 0.217", "1 in 5 warnings is right, vs 1 in 40 by chance")], size=12)
explainer(sl, 7.0, 4.65, 5.8, 2.3, [("Specificity", "share of non-events correctly left unwarned"),
                                   ("False-alarm rate", "share of non-events wrongly warned (2.7 %)"),
                                   ("F1", "one number balancing precision and recall")], size=12)

# ---------------------------------------------------------------- 13 curves + ablation
sl = slide("Which ingredients matter · curves and ablation",
           "Left: CARE-EW's curves sit above every baseline at every threshold. Right: we add feature groups one at a "
           "time. State, change and climate alone barely beat chance; the jump comes from the climate-adjusted residual "
           "(A4) and resilience (A5). Ablation values are the raw model score before calibration.")
px, py, pw, ph = picture(sl, PF / "roc_pr.png", 0.45, 1.15, 6.5, 4.3)
caption(sl, 0.55, py + ph + 0.02, 6.4, "(a) ROC and (b) precision–recall curves on the test set")
abl = [("+A1 state", 0.032), ("+A2 change", 0.036), ("+A3 climate", 0.034), ("+A4 residual", 0.131),
       ("+A5 resilience", 0.143), ("+A6 context", 0.152)]
bar_chart(sl, 7.15, 1.15, 5.65, 4.3, [a for a, _ in abl], [v for _, v in abl], "Test PR-AUC as feature groups are added",
          ["9DB8A6", "9DB8A6", "9DB8A6", SOIL, SOIL, GREEN], size=11)
explainer(sl, 0.55, 5.75, 6.4, 1.2, [("ROC curve", "hit rate vs false-alarm rate as the threshold slides"),
                                    ("PR curve", "precision vs recall; the honest view for rare events")], size=12)
explainer(sl, 7.15, 5.75, 5.65, 1.2, [("Ablation", "remove or add one ingredient at a time to measure what it "
                                                   "contributes")], size=12)

# ---------------------------------------------------------------- 14 generalisation
loco = {k: v["pr_auc_lift"] for k, v in M["leave_one_country_out"].items() if v.get("pr_auc_lift")}
loco = dict(sorted(loco.items(), key=lambda kv: kv[1]))
wf = M["walk_forward"]
sl = slide("Does it work somewhere new, and in a later year?",
           "Leave-one-country-out: train without a country, test on it. Every country beats chance, from 2.3× (Brazil) "
           "to 13.8× (Australia); Mongolia had no events to score. Walk-forward: retrain each January and test on the "
           "next year; skill grows as more history accumulates. Six brand-new sites added later scored 8.6× lift.")
bar_chart(sl, 0.45, 1.1, 5.0, 4.4, list(loco), list(loco.values()), "Lift when the whole country is held out",
          GREEN, fmt='0.0"×"', horizontal=True, size=11)
cd = CategoryChartData(); cd.categories = [str(w["test_year"]) for w in wf]
cd.add_series("CARE-EW PR-AUC", [round(w["pr_auc"], 3) for w in wf]); cd.add_series("Chance", [round(w["base_rate"], 3) for w in wf])
ch = sl.shapes.add_chart(XL_CHART_TYPE.LINE_MARKERS, Inches(5.6), Inches(1.1), Inches(4.0), Inches(4.4), cd).chart
style_chart(ch, "Walk-forward: test PR-AUC by year"); ch.has_legend = True; ch.legend.position = XL_LEGEND_POSITION.BOTTOM
ch.legend.include_in_layout = False; ch.legend.font.size = Pt(11)
for s, col in zip(ch.plots[0].series, [GREEN, "A0AAA3"]):
    s.format.line.color.rgb = rgb(col); s.format.line.width = Pt(2.25); s.smooth = False
    s.marker.format.fill.solid(); s.marker.format.fill.fore_color.rgb = rgb(col); s.marker.format.line.color.rgb = rgb(col)
ch.value_axis.tick_labels.number_format = "0.00"; ch.value_axis.tick_labels.number_format_is_linked = False
table(sl, 9.8, 1.15, 3.0, [["New site", "ROC", "Lift"], ["Sindhupalchok", "0.873", "9.8×"], ["Singrauli", "0.876", "6.8×"],
                           ["Udayapur", "0.844", "7.0×"], ["Kailali", "0.803", "10.1×"], ["Shivalik", "0.782", "12.7×"],
                           ["Marathwada", "0.597", "1.7×"], ["All six", "0.839", "8.6×"]],
      [1.4, 0.75, 0.85], size=11.5, rowh=0.38)
text(sl, 9.8, 4.3, 3.0, 1.2, "Six sites never used in development (Nepal, India). Weakest: Marathwada cropland.",
     size=12, color=MUTED, margin=0)
explainer(sl, 0.55, 5.75, 12.25, 1.2, [("Leave-one-country-out", "the model has never seen a single pixel of that "
                                                                  "country"),
                                      ("Walk-forward", "always train on the past, test on the following year, like real "
                                                       "use")], size=12)

# ---------------------------------------------------------------- 15 when + why
lt = FM["lead_time"]
sl = slide("When it warns, and why",
           f"Of {lt['n_events']:,} test onsets, {lt['warned_frac']:.0%} received a warning beforehand; the median lead is "
           f"{lt['median_lead_months']:.0f} months. SHAP shows the top drivers are resilience signals (5-year MODIS "
           f"variance, AC1 and its trend) and the residual (share of the last 12 months below expectation). It works best "
           f"in shrub and grassland, weakest in cropland, where farming cycles mimic decline.")
px, py, pw, ph = picture(sl, FIG / "fig12_lead_time.png", 0.45, 1.15, 5.2, 3.35)
caption(sl, 0.55, py + ph + 0.02, 5.0, "Months of warning before onset (grey = missed)")
picture(sl, FIG / "fig13_shap.png", 5.85, 1.1, 4.3, 3.45)
stat(sl, 10.35, 1.15, 2.45, 1.55, f"{lt['warned_frac']:.0%}", f"of {lt['n_events']:,} onsets warned")
stat(sl, 10.35, 2.85, 2.45, 1.55, f"{lt['median_lead_months']:.0f} mo", "median lead time", vcolor=SOIL)
table(sl, 0.55, 4.8, 5.1, [["Land cover", "PR-AUC", "ROC-AUC"], ["Shrubland", "0.275", "0.858"], ["Grassland", "0.218", "0.870"],
                           ["Bare / sparse", "0.123", "0.755"], ["Tree cover", "0.110", "0.812"], ["Cropland", "0.096", "0.743"]],
      [2.3, 1.4, 1.4], size=11.5, rowh=0.35)
explainer(sl, 5.85, 4.75, 6.95, 2.2, [("modis_var_60", "variance of MODIS NDVI over the last 60 months"),
                                     ("R_fracbelow12", "share of the last 12 months with residual below −1"),
                                     ("ac1_24 · ac1_trend", "lag-1 autocorrelation over 24 months, and its slope"),
                                     ("Lead time", "months between the warning and the onset")], size=12)

# ---------------------------------------------------------------- 16 UI 1
sl = slide("Application demo 1 · from the globe to a single pixel",
           "Live web console (FastAPI + CesiumJS). Start on the globe with each study area coloured by mean risk; open an "
           "area to see hotspots over Esri imagery with rivers; click a hotspot for its risk, area, first warning, top "
           "drivers and Sentinel-2 before/after chips; the pixel inspector shows that pixel's full history.")
shots = [("ui_final/01_globe.png", "1  Globe: every study area coloured by mean risk"),
         ("ui_final/02_aoi_hotspots_rivers.png", "2  Area view: hotspots H1–H8, river network, time slider"),
         ("ui_final/03_hotspot_panel.png", "3  Hotspot panel: risk 0.175, drivers, before/after"),
         ("ui_final/04_pixel_inspector.png", "4  Pixel inspector: NDVI, z vs residual R, predicted risk")]
for k, (f, c) in enumerate(shots):
    x, y = 0.5 + (k % 2) * 4.55, 1.1 + (k // 2) * 2.95
    px, py, pw, ph = picture(sl, SS / f, x, y, 4.4, 2.6)
    caption(sl, x, y + 2.62, 4.4, c, size=11)
explainer(sl, 9.75, 1.1, 3.05, 5.85, [("Hotspot", "a cluster of high-risk pixels, ranked H1, H2 …"),
                                     ("Risk layer", "colour = calibrated probability of an onset within 6 months"),
                                     ("Hatching", "pixels where the model abstains (inspect in the field)"),
                                     ("Before/after chips", "Sentinel-2 true-colour images of the hotspot"),
                                     ("Esri imagery", "high-detail basemap for context")], size=12)

# ---------------------------------------------------------------- 17 UI 2
sl = slide("Application demo 2 · time-lapse, rivers and any new area",
           "The time-lapse plays every cloud-free Sentinel-2 month for a hotspot and marks when it fell below peers. The "
           "river tab compares mean and low flow before 2000 with today. Draw box lets a user analyse a new 5 km area: the "
           "server downloads the data, runs the same pipeline, and opens the result, with a warning that it is outside "
           "the training areas.")
shots = [("ui_timelapse/03_H12_mid_2023-08.png", "1  Time-lapse: H12 below peers for 38 months"),
         ("ui_final/05_ndvi_riverflow.png", "2  NDVI anomaly layer + river flow before vs now"),
         ("ui_drawbox/01_draw_box_plan.png", "3  Draw a box anywhere: size and download plan"),
         ("ui_drawbox/05_job_done_jobs_panel.png", "4  Job finished: new area opens with hotspots")]
for k, (f, c) in enumerate(shots):
    x, y = 0.5 + (k % 2) * 4.55, 1.1 + (k // 2) * 2.95
    picture(sl, SS / f, x, y, 4.4, 2.6)
    caption(sl, x, y + 2.62, 4.4, c, size=11)
explainer(sl, 9.75, 1.1, 3.05, 5.85, [("Time-lapse", "monthly images played in order; cloudy months skipped"),
                                     ("Below peers", "residual R ≤ −1 versus same-cover neighbours"),
                                     ("Low flow (Q90)", "flow exceeded 90 % of the time: dry-season water"),
                                     ("On-demand job", "the full pipeline run for a user-drawn area"),
                                     ("Indicative", "outside training areas; treat with caution")], size=12)

# ---------------------------------------------------------------- 18 VHR pilot + limitations
sl = slide("A blind check against sub-metre imagery, and our limits",
           "We sampled 276 points (half warnings, half controls), fetched Esri Wayback images before and after, and "
           "judged visible change without knowing which was which. The first pass was done by an AI reviewer; answers "
           "were hashed before unblinding. No detectable difference, and the test was underpowered, so it neither "
           "confirms nor refutes the model. An independent human review is the next step.")
bar_chart(sl, 0.45, 1.1, 4.3, 3.9, ["Warned points", "Control points"], [21 / 107, 26 / 106],
          "Visible change in VHR imagery", [SOIL, "A0AAA3"], fmt="0.0%", size=12)
bullets(sl, 4.95, 1.2, 3.6, 3.8, [("233 usable pairs ", "of 276 sampled (43 lacked imagery)"),
                                  ("Warned: ", "21 / 107 = 19.6 %"), ("Control: ", "26 / 106 = 24.5 %"),
                                  ("Difference ", "−4.9 pp (95 % CI −15.3 to +6.4)"), ("Fisher p ", "= 0.85"),
                                  ("Power ", "≈ 38 % to detect +10 pp")], size=13.5, space=7)
box(sl, 8.8, 1.15, 4.0, 3.85)
text(sl, 9.0, 1.25, 3.7, 0.4, "Limitations", size=16, bold=True, color=DARK, margin=0)
bullets(sl, 9.0, 1.7, 3.7, 3.2, ["Labels come from the same satellite data, not field visits",
                                 "Precision 0.22: most warnings are not followed by an onset",
                                 "Weakest on cropland (farming cycles)", "Optical only: clouds hide monsoon months",
                                 "Wayback dates are approximate"], size=12.5, space=5)
explainer(sl, 0.55, 5.3, 12.25, 1.65, [("Blind test", "the reviewer does not know which points were warnings, so cannot "
                                                       "be biased"),
                                      ("Fisher p = 0.85", "how often pure chance would give a gap at least this favourable to the "
                                                          "model; 0.85 = no evidence of a difference"),
                                      ("Statistical power", "chance a study detects an effect that is really there")],
          size=12)

# ---------------------------------------------------------------- 19 conclusion
sl = slide("Conclusion and next steps",
           "Summarise: a 10 m, climate-adjusted, resilience-aware early warning that ranks future degradation 5.7 times "
           "better than chance on unseen places, generalises across countries and later years, is calibrated, says when "
           "it is unsure, and ships as a working web application. Then the honest next steps.", dark=True)
take = [("5.7×", "better than chance at finding future onsets on unseen land"),
        ("0.805", "ROC-AUC; 0.839 on six brand-new sites"),
        ("3 mo", "median warning lead; 41 % of onsets warned"),
        ("52 %", "abstains instead of guessing; NPV 99.6 %")]
for k, (v, d) in enumerate(take):
    x = 0.55 + k * 3.1
    box(sl, x, 1.25, 2.9, 2.0, fill="22402C")
    text(sl, x + 0.2, 1.35, 2.5, 0.9, v, size=36, bold=True, font=HEAD, color="E3A27E", margin=0)
    text(sl, x + 0.2, 2.25, 2.5, 0.95, d, size=13.5, color=WHITE, margin=0)
text(sl, 0.55, 3.55, 6.0, 0.45, "Next steps", size=18, bold=True, color=WHITE, margin=0)
bullets(sl, 0.55, 4.05, 6.0, 2.8, ["Independent human review of the VHR sample, larger and better powered",
                                   "Prospective test: freeze the model, score warnings issued from 2027",
                                   "Crop-aware labels to stop farming cycles reading as decline",
                                   "Add Sentinel-1 radar, which sees through cloud"], size=14, space=8, color=WHITE)
box(sl, 6.9, 3.55, 5.9, 2.45, fill=TINT, line=TINT_LINE)
circle(sl, 7.05, 3.68, 0.32, SOIL, "i", size=13)
text(sl, 7.45, 3.67, 5.2, 0.34, "EXPLAINER", size=11, bold=True, color=SOIL, anchor=MSO_ANCHOR.MIDDLE, margin=0)
text(sl, 7.05, 4.1, 5.6, 2.8, [[("Prospective test — ", {"bold": True, "color": GREEN}),
                                ("predictions made before the outcome exists, the strongest proof", {})],
                               [("Sentinel-1 — ", {"bold": True, "color": GREEN}),
                                ("radar satellite; measures surface structure day or night through cloud", {})],
                               [("Crop-aware labels — ", {"bold": True, "color": GREEN}),
                                ("labels that know the planting calendar", {})]], size=12.5, space=6, margin=0)

# ---------------------------------------------------------------- 20 references
sl = slide("References", "All references are from 2020 or later and concern land degradation, Earth-observation data, "
                         "GIS, machine learning and computer vision. Full details are in the conference paper.")


def short(r):
    r = r.replace("*", "")
    r = re.sub(r",? (Art\. no\.|vol\.|no\.|pp\.|version) [^,]+", "", r)
    r = re.sub(r",? doi: \S+", "", r)
    r = r.replace(",”,", ",”")
    return r.strip().rstrip(".") + "."


half = (len(REFS) + 1) // 2
for c in range(2):
    sub = list(enumerate(REFS, 1))[c * half:(c + 1) * half]
    text(sl, 0.55 + c * 6.2, 1.1, 6.0, 5.85, [[(f"[{k}] ", {"bold": True, "color": GREEN}), (short(r), {})] for k, r in sub],
         size=8.5, space=2.5, margin=0)

assert N[0] <= 20, N[0]
prs.save(OUT)
print("saved", OUT, N[0], "slides")
