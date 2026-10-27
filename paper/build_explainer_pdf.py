"""Plain-language explainer of the whole project for the team (not for submission).
Output: CARE-EW_Explained.pdf in the repo root.   python paper/build_explainer_pdf.py  (needs reportlab)"""
from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY, TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak,
                                KeepTogether, ListFlowable, ListItem)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "CARE-EW_Explained.pdf"
FIG = ROOT / "paper" / "figs"; OFIG = ROOT / "outputs" / "figures"

F = "C:/Windows/Fonts/"
pdfmetrics.registerFont(TTFont("Body", F + "arial.ttf")); pdfmetrics.registerFont(TTFont("Body-B", F + "arialbd.ttf"))
pdfmetrics.registerFont(TTFont("Body-I", F + "ariali.ttf")); pdfmetrics.registerFont(TTFont("Body-BI", F + "arialbi.ttf"))
pdfmetrics.registerFontFamily("Body", normal="Body", bold="Body-B", italic="Body-I", boldItalic="Body-BI")

INK = colors.HexColor("#1d2733"); ACC = colors.HexColor("#1f5fa8"); SOFT = colors.HexColor("#eef3f9")
NOTE = colors.HexColor("#fff6e0"); GRID = colors.HexColor("#c9d3df")
S = {
    "title": ParagraphStyle("t", fontName="Body-B", fontSize=22, leading=27, textColor=INK, spaceAfter=6),
    "sub": ParagraphStyle("s", fontName="Body", fontSize=11.5, leading=15, textColor=colors.HexColor("#4a5868"), spaceAfter=14),
    "h1": ParagraphStyle("h1", fontName="Body-B", fontSize=15, leading=19, textColor=ACC, spaceBefore=14, spaceAfter=6),
    "h2": ParagraphStyle("h2", fontName="Body-B", fontSize=11.5, leading=15, textColor=INK, spaceBefore=9, spaceAfter=3),
    "p": ParagraphStyle("p", fontName="Body", fontSize=10, leading=14.2, textColor=INK, alignment=TA_JUSTIFY, spaceAfter=5),
    "cell": ParagraphStyle("c", fontName="Body", fontSize=8.8, leading=11.4, textColor=INK),
    "cellb": ParagraphStyle("cb", fontName="Body-B", fontSize=8.8, leading=11.4, textColor=INK),
    "eq": ParagraphStyle("eq", fontName="Body", fontSize=11.5, leading=16, alignment=TA_CENTER, spaceBefore=4, spaceAfter=4),
    "cap": ParagraphStyle("cap", fontName="Body-I", fontSize=8.5, leading=11, textColor=colors.HexColor("#4a5868"), spaceAfter=8),
    "box": ParagraphStyle("box", fontName="Body", fontSize=9.6, leading=13.4, textColor=INK, alignment=TA_JUSTIFY),
}
story = []
P = lambda t, st="p": story.append(Paragraph(t, S[st]))
H1 = lambda t: story.append(Paragraph(t, S["h1"]))
H2 = lambda t: story.append(Paragraph(t, S["h2"]))
W = A4[0] - 4 * cm


def box(html, bg=SOFT):
    t = Table([[Paragraph(html, S["box"])]], colWidths=[W])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), bg), ("BOX", (0, 0), (-1, -1), 0.5, GRID),
                           ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 9),
                           ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
    story.append(t); story.append(Spacer(1, 7))


def table(rows, widths, header=True):
    data = [[Paragraph(str(c), S["cellb" if (header and i == 0) else "cell"]) for c in r] for i, r in enumerate(rows)]
    t = Table(data, colWidths=[w * W for w in widths], repeatRows=1 if header else 0)
    st = [("GRID", (0, 0), (-1, -1), 0.4, GRID), ("VALIGN", (0, 0), (-1, -1), "TOP"),
          ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
          ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]
    if header:
        st.append(("BACKGROUND", (0, 0), (-1, 0), SOFT))
    t.setStyle(TableStyle(st)); story.append(t); story.append(Spacer(1, 8))


def eq(text, symbols):
    """An equation followed by a 'what each symbol means' table."""
    story.append(Paragraph(text, S["eq"]))
    table([["Symbol", "What it means"]] + symbols, [0.16, 0.84])


def fig(path, caption, width_frac=0.92):
    from PIL import Image as PI
    w, h = PI.open(path).size; ww = W * width_frac
    story.append(KeepTogether([Image(str(path), width=ww, height=ww * h / w), Paragraph(caption, S["cap"])]))


def bullets(items):
    story.append(ListFlowable([ListItem(Paragraph(i, S["p"]), leftIndent=12) for i in items], bulletType="bullet",
                              start="\u2022", leftIndent=12, bulletFontSize=9))


# ============================================================================ cover
P("CARE-EW, explained from zero", "title")
P("What we built, how it works, what every term and symbol means, what the numbers say, and how to answer questions "
  "about it. Written for readers with no background in forestry, geology or remote sensing and little background in AI. "
  "This is a study guide for the team, not the submitted paper.", "sub")
box("<b>The project in four sentences.</b> We use free satellite photos of the Earth, taken every few days, to watch how "
    "green the land is, month by month, at a resolution of 10 m \u00d7 10 m. We remove the part of each change that weather explains "
    "(a dry year makes everything browner) and the part that the whole neighbourhood shares. What is left, the "
    "<i>unexplained</i> change, is fed to a machine-learning model that predicts, for every 10 m square, the probability that the "
    "land there will start a long-lasting decline in the next six months. The prediction is shown on a web map so that a "
    "forest or land officer can decide where to send field staff <i>before</i> the damage becomes permanent.")

H1("1. The problem in plain words")
P("<b>Land degradation</b> means land losing its ability to support plants for a long time: forest thinned by cutting or "
  "grazing, topsoil washed away on slopes, grassland overgrazed into bare ground, farmland abandoned or salted, land dug up "
  "for mining. It is slow and spread over huge areas, so it is hard to watch from the ground.")
P("Satellites see all of it, but most existing satellite products are <b>retrospective</b>: they show where land "
  "<i>has already</i> degraded, usually years later. Our question is different and harder: <b>can we warn early?</b> Given "
  "everything known up to this month, which places are likely to <i>start</i> degrading within the next six months?")
P("That is a <b>forecast</b>, like a weather forecast for land health, and it is judged like one: by how often its "
  "warnings come true, how many real events it catches, and how honest its stated probabilities are.")

# ============================================================================ glossary first
H1("2. Key words you need first")
H2("2.1 Satellites and images")
table([["Term", "Meaning in plain words"],
       ["Satellite image", "A photo of the Earth taken from space. Unlike a phone photo it records more \u201ccolours\u201d, including "
        "infrared light that our eyes cannot see."],
       ["Pixel", "The smallest square in an image. In our main data one pixel = 10 m \u00d7 10 m on the ground (about a small "
        "house plot). Our study areas are 512 \u00d7 512 pixels = 5.12 km \u00d7 5.12 km."],
       ["Sentinel-2", "Two free European satellites (ESA / Copernicus) that photograph all land roughly every 5 days at 10 m. "
        "Our main data source, available since 2017."],
       ["MODIS", "Older NASA satellite sensor with coarse pixels (250 m) but a long record since 2000. Used for long-term history."],
       ["Landsat", "NASA/USGS satellites with 30 m pixels. Used only to cross-check that our labels are real."],
       ["Band / spectral band", "One \u201ccolour channel\u201d of the image: e.g. red, green, near-infrared (NIR), short-wave "
        "infrared (SWIR)."],
       ["Reflectance (\u03c1, rho)", "The fraction of sunlight a surface reflects in one band, from 0 (absorbs all) to 1 (reflects all)."],
       ["Near-infrared (NIR)", "Invisible light just beyond red. Healthy leaves reflect it very strongly, so it is the key to "
        "measuring plant health."],
       ["NDVI", "Normalised Difference Vegetation Index, a 'greenness score' computed from red and NIR. About 0.6\u20130.9 for "
        "dense healthy vegetation, 0.2\u20130.4 for sparse grass or shrubs, about 0.1 for bare soil, below 0 for water."],
       ["NDMI, NBR, BSI", "Similar indices: NDMI = moisture in plants, NBR = burn severity, BSI = how much bare soil is exposed."],
       ["Cloud mask / scene classification", "ESA labels every pixel of every photo as cloud, shadow, vegetation, soil, water, etc. "
        "We throw away cloud and shadow pixels."],
       ["Monthly composite", "One clean image per month made by taking, for each pixel, the median of the (up to 4) "
        "cloud-free photos of that month."],
       ["BOA offset / processing baseline", "Since 2022 ESA stores pixel values with +1000 added (a technical change). "
        "We subtract it so that old and new photos are comparable; forgetting this is a common bug."],
       ["MGRS tile", "Sentinel-2 cuts the world into 110 km \u00d7 110 km squares with names like 45RUK. Each of our areas sits inside one tile."],
       ["Land cover", "What covers the ground: tree, shrub, grass, crop, built-up, bare, water. From ESA WorldCover 2021 (10 m)."],
       ["ERA5 / ERA5-Land", "A free global record of past weather (rain, temperature, soil moisture) produced by ECMWF, "
        "the European weather centre. Pixels of 9\u201325 km."],
       ["DEM / NASADEM", "Digital Elevation Model: height of the ground for every 30 m. Gives slope and elevation."],
       ["HydroRIVERS, GloFAS", "Free maps of rivers and their flow. Used to show upstream rivers in the console, not as model inputs."],
       ["VHR imagery", "Very-high-resolution photos (under 1 m pixels, e.g. Esri World Imagery), where individual trees and houses "
        "are visible. Used for today's visual check."]],
      [0.24, 0.76])

H2("2.2 Ecology words")
table([["Term", "Meaning in plain words"],
       ["Persistent decline", "Vegetation staying clearly below its normal level for at least 6 months in a row \u2014 not just one "
        "dry month."],
       ["Climate-unexplained", "A decline that weather (rain, heat, soil dryness) does not explain. If rain failed, plants get brown "
        "everywhere; that is drought, not degradation."],
       ["Peers", "Other pixels of the same land-cover class in the same 5 km area. If all forest pixels drop together, that is a "
        "regional effect; if one drops while its peers do not, something local is happening."],
       ["Onset", "The first month of a persistent, climate-unexplained decline."],
       ["Resilience", "How quickly land recovers after a disturbance such as a drought. Healthy land bounces back; weakened land recovers slowly."],
       ["Critical slowing down", "A general rule from physics and ecology: just before a system collapses, it recovers more and more "
        "slowly from small shocks. In data this shows up as rising autocorrelation (AC1) and variance. Our resilience features "
        "test this idea."],
       ["Hotspot", "A cluster of high-risk pixels shown as a box on the map, with its area in hectares (1 ha = 100 m \u00d7 100 m)."],
       ["Land-use change", "People changing what the land is used for (forest to farm, farm to housing). It looks like degradation in "
        "satellite data but is not always degradation."]],
      [0.24, 0.76])

H2("2.3 AI and machine-learning words")
table([["Term", "Meaning in plain words"],
       ["Machine learning (ML) model", "A program that learns a pattern from many solved examples, then applies it to new "
        "cases. Here: learns from past months which situations were followed by decline."],
       ["Classifier", "A model that answers a yes/no question (here: \u201cwill decline start within 6 months?\u201d) with a probability."],
       ["Label (y)", "The correct answer for a training example: y = 1 (decline started within 6 months) or y = 0 (it did not)."],
       ["Feature", "One input number describing a pixel at a month, e.g. \u201cNDVI change over the last 3 months\u201d. We use 64."],
       ["Causal feature", "A feature computed only from data up to the current month. Using future data would be cheating."],
       ["Decision tree", "A flow-chart of yes/no questions (\u201cIs NDVI below 0.3? Is the residual falling?\u201d) ending in a score. "
        "A <b>leaf</b> is one end box of the flow-chart."],
       ["Gradient boosting / LightGBM", "Builds hundreds of small decision trees one after another; each new tree corrects the "
        "mistakes of the previous ones. LightGBM is a fast, widely used free implementation (Microsoft)."],
       ["Random forest", "Many decision trees built independently and averaged. We use it as a comparison (baseline)."],
       ["Hyperparameter", "A setting chosen by us, not learned: tree size, learning rate, penalty strength."],
       ["Overfitting", "The model memorises its training examples instead of learning a general rule; it then fails on new data. "
        "Our biggest risk, because each pixel gives ~40 very similar monthly rows."],
       ["Underfitting", "The model is too simple to capture the pattern."],
       ["Regularisation", "Penalties that force the model to stay simple and so reduce overfitting (small trees, L2 penalty)."],
       ["Loss function", "The number the model tries to make small during training; it measures how wrong the predictions are."],
       ["Training / validation / test set", "Training: examples the model learns from. Validation: used to choose settings. Test: "
        "kept locked away and used once at the end to measure true performance."],
       ["Data leakage", "When information from the test set accidentally reaches training, making results look better than they are."],
       ["Spatial block hold-out", "The map is cut into 1 km squares; whole squares go to training, validation or test, so the test "
        "uses places the model never saw."],
       ["Temporal hold-out and embargo", "Training uses months up to March 2022; testing uses months from December 2024. The gap "
        "(embargo) is longer than the 11 months a label looks ahead, so no training label can peek into test months."],
       ["Calibration", "Adjusting scores so that probabilities are honest: of all pixels given 10 % risk, about 10 % should really decline."],
       ["Isotonic regression", "The calibration method we use: it maps raw scores to probabilities with a staircase-shaped curve that only goes up."],
       ["Conformal prediction", "A method that wraps a model and guarantees a chosen error rate (we use \u03b1 = 10 %). When the model "
        "cannot decide within that guarantee, it says <b>abstain</b> (\u201cuncertain, inspect in the field\u201d)."],
       ["Threshold", "The probability above which we issue a warning (ours: 0.129, chosen on the calibration set)."],
       ["Ablation", "Removing or adding one group of features at a time to see how much each group actually helps."],
       ["Baseline", "A simple method we must beat to show the model is worth it (e.g. \u201cwhat is falling now keeps falling\u201d)."],
       ["Ensemble / seed", "Ensemble: average of several models. Seed: the random starting number; different seeds give slightly "
        "different models, so we test important choices with 5 seeds."],
       ["Walk-forward retraining", "Retraining each year with all data so far and testing on the next year, the way the system would run in real life."],
       ["Pre-registration", "Writing down the test and the pass/fail rule <i>before</i> running it, so we cannot adjust the rule after seeing the result."]],
      [0.24, 0.76])

H2("2.4 Accuracy words (the metrics)")
P("Every prediction falls into one of four boxes. These four counts are the basis of every metric:")
table([["", "Decline really started (y = 1)", "No decline (y = 0)"],
       ["Model warned", "<b>TP</b> \u2014 true positive: correct warning", "<b>FP</b> \u2014 false positive: false alarm"],
       ["Model did not warn", "<b>FN</b> \u2014 false negative: missed event", "<b>TN</b> \u2014 true negative: correctly quiet"]],
      [0.24, 0.38, 0.38])
table([["Metric", "Formula", "Plain meaning"],
       ["Accuracy", "(TP + TN) / all", "Share of all predictions that were right. Misleading when events are rare."],
       ["Precision", "TP / (TP + FP)", "Of the warnings issued, how many came true?"],
       ["Recall (sensitivity)", "TP / (TP + FN)", "Of the real events, how many did we warn about?"],
       ["F1-score", "2 \u00b7 P \u00b7 R / (P + R)", "One number balancing precision (P) and recall (R)."],
       ["Specificity", "TN / (TN + FP)", "Of the stable places, how many did we correctly leave alone?"],
       ["False-alarm rate (FAR)", "FP / (FP + TN)", "Of the stable places, how many did we wrongly warn about? (= 1 \u2212 specificity)"],
       ["NPV", "TN / (TN + FN)", "Negative predictive value: when the system says \u201csafe\u201d, how often is it right?"],
       ["Base rate", "events / all", "How common events are. Ours is 2.5 %, so a random guess is right about 2.5 % of the time."],
       ["ROC curve, ROC-AUC", "area under TPR-vs-FPR curve", "Probability that a random real event gets a higher risk score "
        "than a random non-event. 0.5 = coin toss, 1.0 = perfect."],
       ["PR curve, PR-AUC", "area under precision-vs-recall curve", "Average precision over all thresholds. For rare events "
        "this is the honest headline. Chance level = base rate (0.025)."],
       ["Lift", "PR-AUC / base rate", "How many times better than random picking."],
       ["Brier score", "mean of (p \u2212 y)\u00b2", "Average squared error of the probabilities (lower is better)."],
       ["ECE", "mean |stated \u2212 observed|", "Expected calibration error: how far stated probabilities are from what really happens."],
       ["Confidence interval (CI)", "bootstrap", "A range that very probably contains the true value. We use 95 % CIs from a "
        "<i>bootstrap</i>: recomputing the metric many times on resampled blocks of the map."],
       ["Lead time", "onset month \u2212 first warning month", "How many months of warning we gave before decline began."]],
      [0.2, 0.22, 0.58])

# ============================================================================ pipeline
PageBreak()
H1("3. What we built, step by step")
fig(FIG / "arch.png", "Figure 1. The whole pipeline. Read top to bottom: free data in, cleaning, removing weather effects, "
    "building features, labels, the model, calibration, and the map shown to users.", 0.78)

H2("Step 1 \u2014 Choose the study areas")
P("23 squares of 5.12 km \u00d7 5.12 km. Seventeen are used for training and testing: Nepal (Chure, Dang, Sarlahi, Kavre, "
  "Surkhet), India (Bundelkhand, Chambal, Thar, Banni, Jharia), Ethiopia (Tigray), Kenya (Baringo), Senegal (Ferlo), "
  "Spain (Murcia), Brazil (Matopiba), Mongolia (steppe) and Australia (Murray\u2013Darling). Six more (Udayapur, Kailali, "
  "Sindhupalchok in Nepal; Marathwada, Singrauli, Shivalik in India) were kept completely out of training and used only "
  "as an independent test. The mix covers forests, farmland, grassland, drylands and mines, so the model cannot just learn one landscape.")

H2("Step 2 \u2014 Download and clean the satellite photos")
P("For each area and each month from 2017 to 2026 we take the 4 least-cloudy Sentinel-2 photos, remove duplicate "
  "copies of the same photo, correct the +1000 offset, delete cloud and shadow pixels, and take the per-pixel median to get "
  "one clean monthly image. From it we compute NDVI and the other indices.")
eq("NDVI = (\u03c1<sub>NIR</sub> \u2212 \u03c1<sub>red</sub>) / (\u03c1<sub>NIR</sub> + \u03c1<sub>red</sub>)",
   [["\u03c1<sub>NIR</sub>", "Reflectance in near-infrared (Sentinel-2 band 8). High for healthy leaves."],
    ["\u03c1<sub>red</sub>", "Reflectance in red light (band 4). Low for healthy leaves, because chlorophyll absorbs red."],
    ["\u03c1 = (DN \u2212 1000) / 10000", "How reflectance is obtained from the stored number DN for newer images (the BOA offset correction)."]])

H2("Step 3 \u2014 What is \u201cnormal\u201d for this pixel? (baseline and anomaly)")
P("Vegetation is greener in the rainy season and browner in the dry season, so a low NDVI in May may be perfectly normal. "
  "For every pixel we compute its normal value for each calendar month from 2017\u20132020, and then express each month as "
  "how unusual it is:")
eq("z<sub>t</sub> = (Y<sub>t</sub> \u2212 \u03bc<sub>m(t)</sub>) / \u03c3",
   [["Y<sub>t</sub>", "The pixel's NDVI in month t."],
    ["m(t)", "The calendar month (January \u2026 December) of month t."],
    ["\u03bc<sub>m</sub> (mu)", "The pixel's normal NDVI for calendar month m: the median of 2017\u20132020 values of that month."],
    ["\u03c3 (sigma)", "The pixel's typical month-to-month wobble, computed as 1.4826 \u00d7 MAD (median absolute deviation), a "
     "version of standard deviation that is not fooled by a few extreme values. Never allowed below 0.02."],
    ["z<sub>t</sub>", "The anomaly: how many 'typical wobbles' the pixel is above (+) or below (\u2212) normal. z = \u22122 means "
     "unusually brown."]])

H2("Step 4 \u2014 Remove weather and neighbourhood effects (the residual)")
P("A drought makes everything brown, and that is not degradation. So for each area and land-cover class we fit a simple "
  "statistical model (ridge regression) that predicts how much browning the weather alone should cause, from rainfall over "
  "the last 1, 3, 6 and 12 months, temperature, soil moisture and water balance. We then subtract that, and also subtract "
  "what the pixel's peers did in the same month:")
eq("R<sub>t</sub> = (z<sub>t</sub> \u2212 \u03b2 \u00b7 g<sub>t</sub>) \u2212 median<sub>peers</sub>(z \u2212 \u03b2 \u00b7 g)",
   [["g<sub>t</sub>", "Weather-expected anomaly for the land-cover class in month t, from the ridge regression."],
    ["\u03b2 (beta)", "How strongly this particular pixel reacts to weather compared with its class (1 = average, 0 = not at all, "
     "up to 3). Pulled toward 1 when data are few."],
    ["median<sub>peers</sub>", "The middle value of the same quantity over all pixels of the same land cover in the same area and month."],
    ["R<sub>t</sub>", "The <b>residual</b>: what is left unexplained by weather and by the neighbourhood. Strongly negative R "
     "means this pixel is browning for local reasons."],
    ["Ridge regression", "Ordinary line-fitting with a small penalty that keeps coefficients stable when inputs are correlated."]])
box("<b>Rule we followed:</b> weather data are used only where they help. If the weather model cannot predict browning in "
    "years it was not trained on (its leave-one-year-out R\u00b2 is below 0.05), we skip it for that area and class. R\u00b2 is "
    "the share of variation a model explains (0 = nothing, 1 = everything).", NOTE)

H2("Step 5 \u2014 Define the event we want to predict (labels)")
P("A month counts as <b>below expectation</b> when R \u2264 \u22121 and the pixel is at least 0.02 NDVI below its peers. An "
  "<b>onset</b> is the first month of a run of below-expectation months that lasts at least 6 months, is mostly real data "
  "(at least 75 % of those months actually observed, not filled in), and loses at least 0.05 NDVI on average. Then, for "
  "every month t:")
eq("y<sub>t</sub> = 1 if an onset happens in months t+1 \u2026 t+6, otherwise y<sub>t</sub> = 0",
   [["y<sub>t</sub>", "The label (correct answer) for month t."],
    ["(t, t+6]", "The next six months after t. This is why we call it a six-month early warning."]])
P("Why six months? A single bad month can be a cloud, a harvest or a late monsoon. Six months is longer than one cropping "
  "season, so the label focuses on lasting change. The same rule is used in every country. An earlier version of the "
  "label was rejected because in India 57 % of its 'events' fell in July\u2013August, so it was really detecting monsoon timing "
  "and clouds. That was caught and fixed.")
fig(OFIG / "fig03_method_example.png", "Figure 2. One real pixel in Spain. (a) Blue = observed NDVI, dashed = its normal "
    "seasonal pattern. (b) Blue = anomaly z, green = what the weather explains. (c) Orange = residual R; red lines = "
    "onsets; shaded = months whose label is y = 1 (an onset follows within 6 months).", 0.95)

H2("Step 6 \u2014 Describe each pixel with 64 numbers (features)")
table([["Group", "What it describes", "Examples"],
       ["A1 State", "How the pixel looks now", "NDVI, z, moisture, burn and bare-soil indices, season, land cover"],
       ["A2 Change", "How it has been changing", "NDVI change over 1, 3, 12 months; 12- and 36-month trends"],
       ["A3 Climate", "Recent weather", "rainfall anomalies, temperature, soil moisture"],
       ["A4 Residual", "The unexplained part", "mean of R over 3/6/12 months, its minimum, slope, months spent below \u22121"],
       ["A5 Resilience", "How well it recovers", "AC1 and variance of R over 12 and 24 months, months since last dip, recovery fraction, MODIS 5-year statistics"],
       ["A6 Context", "Surroundings and terrain", "neighbours' residual within 50 and 210 m, elevation, slope, distance to river, surface water"]],
      [0.16, 0.28, 0.56])
eq("AC1 = \u03a3 (x<sub>t</sub> \u2212 x\u0304)(x<sub>t\u22121</sub> \u2212 x\u0304) / \u03a3 (x<sub>t</sub> \u2212 x\u0304)<sup>2</sup>",
   [["x<sub>t</sub>", "The residual R in month t after removing its slow trend (12-month moving average)."],
    ["x\u0304 (x-bar)", "The average of x over the window (12 or 24 months)."],
    ["\u03a3 (sigma)", "\u201cAdd up over all months in the window\u201d."],
    ["AC1", "Lag-1 autocorrelation, between \u22121 and 1: how much this month resembles last month. High AC1 = slow recovery = "
     "weakened resilience (critical slowing down)."]])

H2("Step 7 \u2014 Train the model (LightGBM)")
P("The model sees millions of examples of (64 features at month t, label y). It builds small decision trees one after "
  "another, each fixing the errors of the previous ones, and outputs a risk score for each pixel-month. During training it "
  "minimises this loss:")
eq("L = \u2212\u03a3<sub>i</sub> w<sub>i</sub> [ y<sub>i</sub> ln p<sub>i</sub> + (1 \u2212 y<sub>i</sub>) ln(1 \u2212 p<sub>i</sub>) ] "
   "+ \u00bd \u03bb \u03a3<sub>j</sub> v<sub>j</sub><sup>2</sup>",
   [["i", "One training example (one pixel in one month)."],
    ["y<sub>i</sub>", "Its true label (0 or 1)."],
    ["p<sub>i</sub>", "The model's predicted probability that y<sub>i</sub> = 1."],
    ["ln", "Natural logarithm. The first part is the 'log-loss': it is small when p is close to the true y and very large when "
     "the model is confidently wrong."],
    ["w<sub>i</sub>", "Weight of the example: events are rare, so they get more weight (\u221a(non-events/events)); each area gets equal total weight."],
    ["v<sub>j</sub>", "The score stored in leaf j of a tree."],
    ["\u03bb (lambda) = 50", "Strength of the L2 penalty: the second part punishes large leaf scores, keeping the model cautious "
     "(regularisation)."]])
P("Settings that prevent overfitting: only 7 leaves per tree, at least 4000 examples per leaf, each tree sees a random 40 % "
  "of the features and 70 % of the rows, learning rate 0.03, and training stops when validation performance stops improving. "
  "It trains in about 14 seconds on a laptop CPU (Intel Core 5 210H, 16 GB RAM).")

H2("Step 8 \u2014 Make the probabilities honest (calibration) and allow \u201cI don't know\u201d (conformal)")
P("Raw tree scores are not true probabilities. <b>Isotonic calibration</b>, learned on a separate set of 378,057 examples, "
  "converts them so that 'a 20 % risk' really means about 20 out of 100 such pixels decline. Then <b>Mondrian conformal "
  "prediction</b> builds, for each pixel, the set of answers it cannot rule out at a 10 % error level:")
eq("\u0393(x) = { y : s<sub>y</sub>(x) \u2264 q\u0302<sub>y</sub> }",
   [["x", "The 64 features of one pixel-month."],
    ["\u0393(x) (Gamma)", "The prediction set: {0} = no event, {1} = event, {0, 1} = <b>abstain</b> (both still possible)."],
    ["s<sub>y</sub>(x)", "A 'strangeness score' of answer y for this pixel, e.g. 1 \u2212 probability of y."],
    ["q\u0302<sub>y</sub> (q-hat)", "A cut-off learned on calibration data so that the true answer is excluded at most 10 % of the "
     "time, separately for events and non-events ('Mondrian')."],
    ["\u03b1 = 0.10", "The allowed error rate (10 %)."]])

H2("Step 9 \u2014 Test fairly")
table([["Set", "Months", "Places", "Rows", "Used for"],
       ["Training", "up to Mar 2022", "60 % of 1 km blocks", "800,784", "learning"],
       ["Validation", "Mar\u2013Dec 2023", "20 % of blocks", "169,049", "choosing settings, early stopping"],
       ["Calibration", "Mar\u2013Dec 2023", "", "378,057", "calibration and conformal cut-offs"],
       ["Test (locked)", "Dec 2024 onwards", "remaining 20 % of blocks", "132,230", "final score, used once"]],
      [0.17, 0.18, 0.25, 0.13, 0.27])
P("Test places are new <i>and</i> test months are in the future, which is harder and more honest than a random split. "
  "In total the dataset has 4,294,330 labelled pixel-months. A new idea is accepted only if it raises validation PR-AUC "
  "by at least 0.005, averaged over 5 random seeds.")

H2("Step 10 \u2014 The web console")
P("A Google-Earth-like map (runs in a browser at localhost:8765) that shows risk maps, hotspot boxes with hectares, monthly "
  "charts, upstream rivers, a Sentinel-2 time-lapse per hotspot, and a 'draw a box anywhere' tool that runs the whole "
  "pipeline on a new area.")

# ============================================================================ results
H1("4. What the numbers say")
H2("4.1 The confusion matrix on the test set (132,230 pixel-months)")
table([["", "Decline really started", "No decline", "Total"],
       ["Model warned", "TP = 963", "FP = 3,468", "4,431"],
       ["Model did not warn", "FN = 2,364", "TN = 125,435", "127,799"],
       ["Total", "3,327 (2.5 %)", "128,903", "132,230"]],
      [0.28, 0.26, 0.26, 0.2])
table([["Metric", "Our value", "What it means for us"],
       ["Accuracy", "95.6 %", "Looks great but is misleading: a model that never warns would score 97.5 % because declines are rare."],
       ["Precision", "21.7 %", "About 1 in 5 warnings comes true. That is 8.6\u00d7 better than random at this threshold (2.5 %)."],
       ["Recall", "28.9 %", "We catch about 3 in 10 declines at this threshold."],
       ["F1-score", "0.248", "Balance of the two above."],
       ["Specificity / FAR", "97.3 % / 2.7 %", "Only 2.7 % of stable places get a false alarm."],
       ["ROC-AUC", "0.805 (CI 0.766\u20130.838)", "80 % of the time a real event is ranked above a stable pixel."],
       ["PR-AUC", "0.144 (CI 0.112\u20130.184)", "5.7\u00d7 the 0.025 chance level: our headline number."],
       ["ECE / Brier", "0.0025 / 0.0228", "Probabilities are honest: a stated 10 % risk is close to 10 % observed."],
       ["Early warning", "41 % of onsets, median 3 months", "41 % of declines received a warning at least 1 month before they started."],
       ["Conformal", "abstains on 52 %", "On the other 48 % it is confident: ROC-AUC 0.877 there, and its 'safe' calls are right 99.6 % of the time."]],
      [0.17, 0.24, 0.59])
box("<b>How to say it in one line:</b> \u201cThe model is a good ranker of where to look (ROC 0.80, 5.7\u00d7 better than chance), "
    "very reliable when it says an area is safe (99.6 %), and about 1 in 5 of its warnings comes true, so it is a triage tool "
    "for planning field visits, not a replacement for them.\u201d", NOTE)
fig(FIG / "roc_pr.png", "Figure 3. Left: ROC curves; the further toward the top-left, the better; the grey diagonal is a coin "
    "toss. Right: precision\u2013recall; the grey line is chance (2.5 %). Blue is our model; the others are simple baselines.", 0.8)

H2("4.2 What actually helps (ablation)")
fig(FIG / "ablation.png", "Figure 4. Adding feature groups one at a time. State, change and raw weather (light blue) stay near "
    "chance. The jump comes from the residual (A4) and then resilience (A5) and context (A6).", 0.8)
P("This is the key scientific finding: you cannot predict future decline from how green the land is now, or from the "
  "weather directly. You can predict it once you look at the <i>unexplained</i> part of the change and at <i>how slowly</i> "
  "the land is recovering.")

H2("4.3 Ideas we tested and rejected (honestly)")
table([["Idea", "Result", "Decision"],
       ["Texture (patchiness of greenness, GLCM)", "validation 0.134 vs 0.138", "rejected"],
       ["Red-edge bands (leaf chlorophyll, dry shrubs)", "0.137 vs 0.138", "rejected"],
       ["Texture + red-edge together", "+0.003 over 5 seeds (rule needs +0.005)", "rejected"],
       ["Twice as many pixels per site", "0.120 vs 0.122", "rejected"],
       ["Cleaning suspicious labels (confident learning)", "\u22120.0005", "rejected"],
       ["Average of 5 models (ensemble)", "+0.004", "narrowly rejected"],
       ["Training on all 23 sites", "\u22120.001 over 5 seeds", "rejected; new sites kept as independent test"]],
      [0.45, 0.33, 0.22])
P("Some rejected ideas looked slightly better on the test set. We did not switch, because choosing after looking at the "
  "test set would be cheating. Instead a <b>prospective test</b> is planned on future months that do not yet have labels.")

H2("4.4 Does it work in new places and over time?")
bullets(["<b>Country left out entirely:</b> trained on the other countries, still 2.3\u201313.8\u00d7 better than chance "
         "(Australia 13.8, Ethiopia 10.2, Senegal 9.8, Kenya 7.0, Nepal 6.2, Spain 4.6, India 4.1, Brazil 2.3).",
         "<b>Six brand-new sites, no retraining:</b> ROC-AUC 0.839 and 8.6\u00d7 lift. Best: Singrauli 0.876, Sindhupalchok 0.873; "
         "weakest: Marathwada farmland 0.597.",
         "<b>Over time:</b> retraining each year, test PR-AUC rose from chance in 2021 to 0.179 in 2025 as more satellite history "
         "accumulated, so the system improves as it runs.",
         "<b>By land cover:</b> best in shrubland (PR-AUC 0.275) and grassland (0.218), weakest in cropland (0.096), because "
         "sowing and harvesting look like decline."])

H2("4.5 The blind photo check (27 Oct 2026)")
P("Question: when the model warns, can you actually see damage in very sharp photos afterwards? We picked 6 warnings and "
  "6 'safe' pixels per site, fetched before/after sub-metre photos, shuffled them and judged them without knowing which "
  "was which. Of 233 usable pairs, a visible change was seen at 19.6 % of warnings and 24.5 % of safe pixels: <b>no "
  "difference</b> (\u22124.9 points, 95 % CI \u221215 to +6). The test was too small to detect a modest effect, the photos were often "
  "1\u20133 years and a season apart, and what is visible in photos (new roads, buildings, clearings) is not the same as the "
  "gradual thinning the model predicts. The judge was the AI assistant, so it is only a pilot; a human review is pending.")

# ============================================================================ viva
H1("5. Questions your faculty may ask, and honest answers")
qa = [
    ("Accuracy is 95.6 %. Why do you say it is misleading?",
     "Only 2.5 % of cases are declines. Saying 'no decline' every time would already give 97.5 %. That is why we report "
     "precision, recall and PR-AUC, which focus on the rare events we care about."),
    ("Precision is only 22 %. Isn't that bad?",
     "For a rare event it is 8.6\u00d7 better than random picking. Earthquake, disease and fraud warnings have similar "
     "precision. The system is meant to prioritise field visits, and its 'safe' calls are 99.6 % reliable, which saves effort."),
    ("Why not deep learning (CNN, LSTM, transformer)?",
     "Our inputs are 64 engineered numbers per pixel-month, not raw images; gradient-boosted trees are the strongest "
     "method for such tabular data, train in seconds on a laptop, and can be explained. The main problem was overfitting to "
     "autocorrelated pixels; a bigger model makes that worse (validation curve, paper Fig. 5)."),
    ("How do you know the model is not cheating?",
     "Test places are 1 km blocks never used in training, test months are 2.5 years after the last training month with "
     "an embargo longer than the label look-ahead, all features use only past data (checked by unit tests), and the test set "
     "was evaluated once."),
    ("How do you know the labels are real degradation?",
     "We cannot fully; they are satellite-based proxies. Landsat (a different satellite) independently sees lower greenness "
     "at our events in most areas, but land-use change and harvests are also captured. Field data are the missing piece."),
    ("Why remove weather?",
     "Otherwise every drought would trigger warnings everywhere. Weather explains the shared browning; degradation is the local, "
     "unexplained part. The ablation shows raw weather inputs do not help, but weather-adjusted residuals do."),
    ("What is new in your work?",
     "Turning resilience theory into a tested, calibrated six-month forecast with abstention, using one label rule across nine "
     "countries and a leakage-proof evaluation, plus a working console. Each piece exists separately; the integrated, falsifiable "
     "test is the contribution."),
    ("What would you do next?",
     "Crop-calendar-aware labels for farmland, a human-judged and larger photo check, a prospective test on future months, and "
     "Sentinel-1 radar, which sees through monsoon clouds."),
]
for q, a in qa:
    story.append(KeepTogether([Paragraph(f"<b>Q. {q}</b>", S["p"]), Paragraph(a, S["p"]), Spacer(1, 3)]))

H1("6. Where things are in the project folder")
table([["Path", "What it contains"],
       ["CARE-EW_Conference_Paper.docx", "The submitted paper (IEEE format)."],
       ["CARE-EW_Explained.pdf", "This guide."],
       ["README.md", "How to install and run."],
       ["care_ew/", "All pipeline code: s2.py (satellite download), labels.py, features.py, train.py, predict.py, ondemand.py \u2026"],
       ["app/", "The web console (server.py + static web page)."],
       ["docs/PROJECT_LOG.md", "Every decision (D-xxx) and result (R-xxx) in order, including rejected ideas."],
       ["docs/ACCURACY_REPORT.md", "All accuracy tables per site, land cover and experiment."],
       ["outputs/results/metrics.json", "The raw numbers behind every table."],
       ["outputs/figures/, paper/figs/", "All figures."],
       ["scripts/vhr_campaign.py, /review.html", "The blind photo check and its review page."]],
      [0.36, 0.64])


def footer(c, d):
    c.saveState(); c.setFont("Body", 8); c.setFillColor(colors.HexColor("#7a8796"))
    c.drawString(2 * cm, 1.2 * cm, "CARE-EW explained \u2014 study guide for the team")
    c.drawRightString(A4[0] - 2 * cm, 1.2 * cm, str(d.page)); c.restoreState()


SimpleDocTemplate(str(OUT), pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=1.8 * cm, bottomMargin=1.8 * cm,
                  title="CARE-EW explained", author="Ankur Bhattarai").build(story, onFirstPage=footer, onLaterPages=footer)
print("wrote", OUT)
