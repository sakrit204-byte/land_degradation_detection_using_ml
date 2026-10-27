"""Builds CARE-EW_Conference_Paper.docx (repo root) in the IEEE conference format required by
AI_Project_Ideas_Conference_Paper_Guide.pdf: two-column, single-spaced, Times New Roman 10 pt; title, author block,
abstract (150-250 words), index terms (4-6), I Introduction ... VI Conclusion, numbered tables/figures/equations,
IEEE numbered references. Numbers come from outputs/results/metrics.json and the accuracy report.
Run with a Python that has python-docx:  python paper/build_conference_docx.py
Figures: python paper/make_paper_figs.py (run first)."""
from pathlib import Path
from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, Inches, RGBColor

ROOT = Path(__file__).resolve().parents[1]
FIG = ROOT / "paper" / "figs"
OUT = ROOT / "CARE-EW_Conference_Paper.docx"
FONT = "Times New Roman"
COLW = 3.5                                   # IEEE US-letter column width (in)

doc = Document()
st = doc.styles["Normal"]
st.font.name = FONT; st.font.size = Pt(10)
st.element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
pf = st.paragraph_format; pf.space_before = Pt(0); pf.space_after = Pt(0); pf.line_spacing = 1.0

sec = doc.sections[0]
sec.page_width, sec.page_height = Inches(8.5), Inches(11)
sec.top_margin, sec.bottom_margin = Inches(0.75), Inches(1.0)
sec.left_margin = sec.right_margin = Inches(0.625)


def cols(section, n, space=0.25):
    c = section._sectPr.find(qn("w:cols"))
    if c is None:
        c = OxmlElement("w:cols"); section._sectPr.append(c)
    c.set(qn("w:num"), str(n)); c.set(qn("w:space"), str(int(space * 1440)))


def run(p, text, size=10, bold=False, italic=False, caps=False, sup=False):
    r = p.add_run(text); r.font.name = FONT; r.font.size = Pt(size)
    r.bold, r.italic = bold, italic
    if caps:
        r.font.small_caps = True
    if sup:
        r.font.superscript = True
    return r


def rich(p, text, size=10):
    """**bold** and *italic* inline markup."""
    import re
    for part in re.split(r"(\*\*[^*]+\*\*|\*[^*]+\*)", text):
        if part.startswith("**"):
            run(p, part[2:-2], size, bold=True)
        elif part.startswith("*") and len(part) > 1:
            run(p, part[1:-1], size, italic=True)
        elif part:
            run(p, part, size)


def para(text, indent=True, size=10, align=WD_ALIGN_PARAGRAPH.JUSTIFY, after=0):
    p = doc.add_paragraph(); p.alignment = align
    if indent:
        p.paragraph_format.first_line_indent = Inches(0.17)
    p.paragraph_format.space_after = Pt(after)
    rich(p, text, size)
    return p


def bullets(items, size=10):
    for it in items:
        p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        p.paragraph_format.left_indent = Inches(0.25); p.paragraph_format.first_line_indent = Inches(-0.14)
        run(p, "• ", size); rich(p, it, size)


ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII"]
_h = [0]; _s = [0]


def heading(text, numbered=True):
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(8); p.paragraph_format.space_after = Pt(4); p.paragraph_format.keep_with_next = True
    if numbered:
        run(p, f"{ROMAN[_h[0]]}. ", caps=True); _h[0] += 1
    run(p, text, caps=True); _s[0] = 0


def subheading(text):
    p = doc.add_paragraph(); p.paragraph_format.space_before = Pt(4); p.paragraph_format.space_after = Pt(2)
    p.paragraph_format.keep_with_next = True
    run(p, f"{chr(65 + _s[0])}. {text}", italic=True); _s[0] += 1


_eq = [0]


def equation(*parts):
    """parts: (text, italic) tuples or plain strings (italic). Centered, number right-aligned."""
    _eq[0] += 1
    p = doc.add_paragraph(); p.paragraph_format.space_before = Pt(3); p.paragraph_format.space_after = Pt(3)
    ts = p.paragraph_format.tab_stops
    ts.add_tab_stop(Inches(COLW / 2), WD_TAB_ALIGNMENT.CENTER); ts.add_tab_stop(Inches(COLW), WD_TAB_ALIGNMENT.RIGHT)
    run(p, "\t")
    for x in parts:
        if isinstance(x, str):
            run(p, x, italic=True)
        else:
            t, it = x[0], x[1]; sub = len(x) > 2 and x[2]
            r = run(p, t, italic=it)
            if sub == "sub":
                r.font.subscript = True
            elif sub == "sup":
                r.font.superscript = True
    run(p, f"\t({_eq[0]})")
    return _eq[0]


_fig = [0]


def figure(path, caption, width=3.45):
    _fig[0] += 1
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER; p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.keep_with_next = True
    p.add_run().add_picture(str(path), width=Inches(width))
    c = doc.add_paragraph(); c.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY; c.paragraph_format.space_after = Pt(8)
    run(c, f"Fig. {_fig[0]}.  ", 8); rich(c, caption, 8)
    return _fig[0]


_tab = [0]


def borders(cell, top=None, bottom=None):
    tcPr = cell._tc.get_or_add_tcPr(); b = OxmlElement("w:tcBorders")
    for side, val in (("top", top), ("bottom", bottom), ("left", None), ("right", None)):
        e = OxmlElement(f"w:{side}")
        if val:
            e.set(qn("w:val"), "single"); e.set(qn("w:sz"), str(val)); e.set(qn("w:color"), "000000")
        else:
            e.set(qn("w:val"), "nil")
        b.append(e)
    tcPr.append(b)


def table(title, header, rows, widths, size=7.5, note=None):
    _tab[0] += 1
    cap = doc.add_paragraph(); cap.alignment = WD_ALIGN_PARAGRAPH.CENTER; cap.paragraph_format.space_before = Pt(6)
    cap.paragraph_format.keep_with_next = True
    run(cap, f"TABLE {ROMAN[_tab[0] - 1]}", 8, caps=True)
    cap2 = doc.add_paragraph(); cap2.alignment = WD_ALIGN_PARAGRAPH.CENTER; cap2.paragraph_format.space_after = Pt(3)
    cap2.paragraph_format.keep_with_next = True
    run(cap2, title, 8, caps=True)
    t = doc.add_table(rows=1 + len(rows), cols=len(header)); t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = False
    for i, row in enumerate([header] + rows):
        for j, val in enumerate(row):
            cell = t.cell(i, j); cell.width = Inches(widths[j])
            p = cell.paragraphs[0]; p.alignment = WD_ALIGN_PARAGRAPH.LEFT if j == 0 else WD_ALIGN_PARAGRAPH.CENTER
            rich(p, str(val), size) if i else run(p, str(val), size, bold=True)
            last = i == len(rows)
            if not last:
                p.paragraph_format.keep_with_next = True
            borders(cell, top=8 if i == 0 else (4 if i == 1 else None), bottom=8 if last else None)
    if note:
        n = doc.add_paragraph(); n.paragraph_format.space_before = Pt(2); n.paragraph_format.space_after = Pt(6)
        rich(n, note, 7)
    else:
        doc.add_paragraph().paragraph_format.space_after = Pt(4)
    return _tab[0]


# ============================================================================ title + authors (one column)
p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER; p.paragraph_format.space_after = Pt(10)
run(p, "Early Warning of Persistent Land Degradation from Sentinel-2 Time Series Using Climate-Conditioned "
       "Resilience Features and Calibrated Gradient Boosting", 22)

auth = doc.add_table(rows=1, cols=3); auth.alignment = WD_TABLE_ALIGNMENT.CENTER
members = [("Ankur Bhattarai", "Reg. No. 24BCE2954"), ("________________", "Reg. No. ____________"),
           ("________________", "Reg. No. ____________")]
for j, (name, reg) in enumerate(members):
    c = auth.cell(0, j); c.width = Inches(2.4); borders(c)
    lines = [(name, 11, False), (reg, 9, False), ("Department of ____________", 9, True), ("____________ (Institution)", 9, True),
             ("City, Country", 9, True), ("email: ____________", 9, False)]
    c.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
    run(c.paragraphs[0], lines[0][0], lines[0][1])
    for text, size, it in lines[1:]:
        q = c.add_paragraph(); q.alignment = WD_ALIGN_PARAGRAPH.CENTER; run(q, text, size, italic=it)
doc.add_paragraph().paragraph_format.space_after = Pt(6)

body = doc.add_section(WD_SECTION.CONTINUOUS); cols(body, 2)

# ============================================================================ abstract + index terms
ABSTRACT = (
    "Satellite monitoring of land degradation is usually retrospective: it maps vegetation loss after it has happened. "
    "This paper addresses the forecasting problem instead. Given open Earth-observation data up to month t, the task is to "
    "estimate the probability that a 10 m pixel will enter a persistent, climate-unexplained vegetation decline within the "
    "next six months. The proposed system, CARE-EW, builds monthly Sentinel-2 composites and removes the climate-driven part "
    "of each pixel's vegetation anomaly with a land-cover-specific ridge model and a peer-relative correction. It derives "
    "resilience indicators such as lag-1 autocorrelation and variance of the residual, and feeds 64 causal features to a "
    "heavily regularised LightGBM classifier with isotonic calibration and Mondrian conformal abstention. One labelling rule "
    "is used in every country. On 4.29 million labelled pixel-months from 17 sites in nine countries, evaluated on a hold-out "
    "that is new in both space and time, the model reaches a ROC-AUC of 0.805 and a PR-AUC of 0.144, 5.7 times the 2.5 % base "
    "rate. At a 2.7 % false-alarm rate it gives precision 0.22 and recall 0.29, with an expected calibration error of 0.0025, "
    "and 41 % of degradation onsets are warned at least one month ahead. Without retraining, six further sites in Nepal and "
    "India give a ROC-AUC of 0.839. Ablation shows that the climate-conditioned residual and the resilience features, not "
    "spectral state or raw weather, carry the predictive signal.")
p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY; p.paragraph_format.space_after = Pt(6)
run(p, "Abstract", 9, bold=True, italic=True); run(p, "—" + ABSTRACT, 9, bold=True)
p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY; p.paragraph_format.space_after = Pt(4)
run(p, "Index Terms", 9, bold=True, italic=True)
run(p, "—land degradation, early warning, Sentinel-2, gradient boosting, conformal prediction, critical slowing down", 9, bold=True)

# ============================================================================ I. Introduction
heading("Introduction")
para("Land degradation affects a large share of the world's drylands, forests and croplands and is tracked by "
     "Sustainable Development Goal indicator 15.3.1 [1], [2]. Operational assessment relies on trends in productivity, "
     "land cover and soil carbon computed over multi-year windows [2], [3]. These products answer the question "
     "*where has degradation already occurred?* A forest department or district office needs a different answer: "
     "*where is degradation likely to start in the next few months*, with an honest statement of uncertainty, so that "
     "field teams can be sent before damage becomes persistent.")
para("Two lines of research point toward such a warning system, but neither delivers it. Residual-trend methods "
     "separate rainfall-driven from human-driven vegetation change [4], [5], yet they are retrospective. Studies of "
     "resilience show that ecosystems approaching a transition recover more slowly from disturbance, visible as rising "
     "lag-1 autocorrelation and variance of their time series [6], [7]. Satellite records have been used to map these "
     "indicators at continental and global scale [8]–[10], but not to issue calibrated, pixel-level forecasts with a "
     "measured lead time and a controlled false-alarm rate. Machine-learning studies in remote sensing also tend to "
     "overstate accuracy because spatially and temporally autocorrelated samples leak between training and test sets [11], [12].")
para("This paper makes the following contributions:", after=2)
bullets([
    "**A forecasting target.** The label is the onset of a persistent (at least six months), climate-unexplained decline "
    "within the next six months, defined by one rule in all countries, so the task is prediction rather than mapping.",
    "**Climate conditioning and resilience features** tested by ablation rather than assumed: the residual after removing "
    "climate and landscape-wide effects, and its autocorrelation and variance.",
    "**Calibrated probabilities with abstention.** Isotonic calibration and Mondrian conformal prediction let the system say "
    "“uncertain — inspect” instead of forcing a decision.",
    "**A leakage-resistant evaluation.** Test pixels are new in space (1 km blocks) and time (an embargoed future period), with "
    "transfer tests to unseen countries and to six independent sites.",
    "**An open, reproducible pipeline and web console** that uses only free data and runs on a laptop.",
])
para("Section II reviews related work. Section III describes the data, the system architecture, the model and the "
     "training setup. Section IV reports results against baselines and discusses limitations. Section V concludes and "
     "lists concrete future work.")

# ============================================================================ II. Related work
heading("Related Work")
subheading("Retrospective trend and residual methods")
para("RESTREND regresses vegetation index on rainfall and treats a declining residual as human-induced degradation [4]. "
     "Local Net Production Scaling compares each pixel with land-cover peers in the same region [5]. BFAST decomposes a "
     "time series into trend and season and detects breaks [13], and Trends.Earth packages trend, land-cover and carbon "
     "sub-indicators for SDG reporting [3]. All are designed to detect change that has already happened.")
subheading("Machine-learning disturbance mapping")
para("Large-scale forest products use decision trees on Landsat to map annual tree-cover loss [14], and radar alerts from "
     "Sentinel-1 flag disturbance in humid tropical forests within weeks [15]. These systems are accurate for abrupt "
     "clearing but react to disturbance under way and are mostly limited to forests.")
subheading("Resilience and early-warning signals")
para("Critical-slowing-down theory predicts rising autocorrelation and variance before a transition [6], [7]. "
     "Satellite studies found lower resilience in drought-sensitive tropical forests [8], widespread resilience loss "
     "since the early 2000s [9], [10], and spatial-pattern indicators of desertification [16]. These are descriptive; "
     "whether they improve held-out forecasts is rarely tested.")
table("Comparison of Prior Work",
      ["Work", "Method", "Data / region", "Outcome", "Gap for early warning"],
      [["[4]", "Rainfall–NDVI residual trend", "AVHRR, S. Africa", "Separates human vs. rain effects", "Retrospective, annual"],
       ["[5]", "Peer scaling (LNS)", "MODIS, Zimbabwe", "Relative productivity loss", "Retrospective"],
       ["[13]", "Trend–season breaks", "MODIS NDVI", "Abrupt and gradual breaks", "Detects after change"],
       ["[14]", "Decision trees", "Landsat, global", "Annual tree-cover loss", "Forest only, after loss"],
       ["[15]", "Radar change detection", "Sentinel-1, tropics", "Near-real-time alerts", "Disturbance under way"],
       ["[8]", "AC1 resilience", "AVHRR, tropics", "Low resilience before drought impact", "No pixel forecast"],
       ["[9]", "AC1 trends", "AVHRR/MODIS, global", "Resilience loss mapped", "Descriptive"],
       ["**Ours**", "LightGBM + residual + resilience + conformal", "Sentinel-2, 23 sites, 9 countries",
        "ROC 0.805, PR-AUC 0.144 (5.7×) on space–time hold-out", "Precision 0.22; cropland weak"]],
      [0.42, 0.78, 0.74, 0.86, 0.7], size=6.5)

# ============================================================================ III. Methodology
heading("Proposed Methodology")
subheading("System architecture")
figure(FIG / "arch.png", "CARE-EW architecture. Open data are composited monthly, the climate-driven part of the anomaly is "
       "removed, causal features feed a regularised LightGBM model, and calibrated probabilities are turned into warning, "
       "no-event or abstain decisions shown in a web console.")
para("Fig. 1 shows the pipeline. Every step uses data at or before the prediction month *t*; unit tests perturb future "
     "values and confirm that no feature changes.")
subheading("Dataset")
para("**Study areas.** The model is trained on 17 areas of 5.12 × 5.12 km (512 × 512 pixels) in nine countries: "
     "Nepal (5), India (5), Ethiopia, Kenya, Senegal, Spain, Brazil, Mongolia and Australia. They cover Himalayan "
     "foothill forest, semi-arid cropland, rangeland, Mediterranean dryland and a mining landscape. Six further sites "
     "(Udayapur, Kailali and Sindhupalchok in Nepal; Marathwada, Singrauli and Shivalik in India) are used only as "
     "independent test sites.")
para("**Sources.** All inputs are open: Sentinel-2 L2A [23] (10–20 m, 2017–2026), MODIS MOD13Q1 NDVI (250 m, 2000–), "
     "ERA5/ERA5-Land [24] climate (precipitation, temperature, soil moisture, reference evapotranspiration), ESA WorldCover "
     "2021 [17], NASADEM terrain, JRC surface water and HydroRIVERS. Landsat 8/9 is used only to check labels.")
para("**Preprocessing.** For each month the four least-cloudy Sentinel-2 scenes of one MGRS tile are used. Duplicate "
     "processings are removed, and the bottom-of-atmosphere offset of processing baseline 04.00 and later is corrected. "
     "Pixels outside the vegetation, soil and water scene classes are masked. NDVI, NDMI, NBR and BSI are computed per scene "
     "and composited by the monthly median:")
equation("NDVI = (", ("ρ", True), ("NIR", False, "sub"), " − ", ("ρ", True), ("red", False, "sub"), ") / (",
         ("ρ", True), ("NIR", False, "sub"), " + ", ("ρ", True), ("red", False, "sub"), ")")
para("A seasonal baseline μₘ (calendar-month median, 2017–2020) and a robust spread σ (1.4826 × MAD) give "
     "the standardised anomaly:", indent=False)
equation("z", ("t", True, "sub"), " = (Y", ("t", True, "sub"), " − μ", ("m(t)", True, "sub"), ") / σ")
para("**Size.** The labelled table holds 4,294,330 pixel-months, from 5000 sampled pixels per site (Table II).", indent=False)
table("Study Areas (5.12 × 5.12 km Each)",
      ["Region", "Sites", "Landscape", "Role"],
      [["Nepal", "Chure, Dang, Sarlahi, Kavre, Surkhet", "foothill forest, mid-hills", "train / test"],
       ["India", "Bundelkhand, Chambal, Thar, Banni, Jharia", "cropland, rangeland, mining", "train / test"],
       ["Africa", "Tigray (ET), Baringo (KE), Ferlo (SN)", "highland crop, rangeland", "train / test"],
       ["Other", "Murcia (ES), Matopiba (BR), steppe (MN), Murray–Darling (AU)", "dryland, cerrado, steppe, woodland",
        "train / test"],
       ["Nepal", "Udayapur, Kailali, Sindhupalchok", "foothills, landslide hills", "independent test"],
       ["India", "Marathwada, Singrauli, Shivalik", "rainfed crop, mining, forest", "independent test"]],
      [0.5, 1.35, 1.05, 0.6], size=6.5)
subheading("Climate conditioning and residual")
para("For each site and land-cover class, a ridge regression *g* predicts the class-mean anomaly from 1/3/6/12-month "
     "standardised precipitation, temperature and soil-moisture anomalies, and climatic water balance. It is fitted only "
     "on the training period and cross-fitted by leaving one year out. Pixel sensitivity β is shrunk toward 1. The residual "
     "is taken relative to landscape peers, so that a drought or haze affecting every pixel of a class is not called "
     "degradation:")
equation("R", ("t", True, "sub"), " = (z", ("t", True, "sub"), " − βg", ("t", True, "sub"),
         ") − med", ("peer", False, "sub"), "(z − βg)")
para("Climate adjustment is applied only where its leave-one-year-out R² is at least 0.05; elsewhere *R* = *z* minus the peer "
     "median. Weather data are therefore used only where they demonstrably help.", indent=False)
subheading("Labels")
para("Month *s* is below expectation when Rₛ ≤ −1 and the peer-relative NDVI deviation is ≤ −0.02. An onset occurs when such a "
     "run starts and lasts at least six months, with at least 75 % real observations and a mean loss of at least 0.05 NDVI. "
     "The prediction target at month *t* is:")
equation("y", ("t", True, "sub"), " = 1  if an onset occurs in (t, t + 6]")
para("Labels are undefined when fewer than 60 % of the following 11 months are observed. The same rule and thresholds are "
     "used in every country. Fig. 2 traces one pixel through the steps.", indent=False)
figure(ROOT / "outputs" / "figures" / "fig03_method_example.png",
       "One Murcia (Spain) pixel: (a) observed NDVI and its 2017–2020 seasonal baseline; (b) the anomaly *z* and the climate-"
       "expected anomaly; (c) the peer-relative residual *R*, two onsets (red lines) and the months labelled *y* = 1 (shaded).")
subheading("Features")
para("64 features in six groups, all causal: A1 spectral state; A2 change (1/3/12-month differences and slopes); "
     "A3 climate; A4 residual statistics; A5 resilience; A6 spatial and terrain context. The resilience features use the "
     "lag-1 autocorrelation and variance of the high-pass-filtered residual *x* over 12- and 24-month windows:")
equation("AC1 = Σ(x", ("t", True, "sub"), " − x̄)(x", ("t−1", True, "sub"), " − x̄) / Σ(x",
         ("t", True, "sub"), " − x̄)", ("2", False, "sup"))
para("together with months since the last dip, recovery fraction and MODIS 60-month variance and autocorrelation.", indent=False)
subheading("Model, calibration and abstention")
para("LightGBM [18] minimises the weighted logistic loss with an L2 penalty on leaf values *v*:")
equation("L = −Σ", ("i", True, "sub"), " w", ("i", True, "sub"), "[y", ("i", True, "sub"), " ln p", ("i", True, "sub"),
         " + (1−y", ("i", True, "sub"), ")ln(1−p", ("i", True, "sub"), ")] + ½λΣ", ("j", True, "sub"), " v",
         ("j", True, "sub"), ("2", False, "sup"))
para("Each pixel contributes about 40 strongly autocorrelated monthly rows, so deep trees memorise pixels. Trees are "
     "therefore kept small (Table III). Scores are calibrated by isotonic regression [19] on a disjoint calibration set. A "
     "Mondrian split-conformal predictor [20], [21] with α = 0.10 returns the prediction set:")
equation("Γ(x) = {y : s", ("y", True, "sub"), "(x) ≤ q̂", ("y", True, "sub"), "}")
para("A set {0, 1} is reported as *abstain*. The warning threshold maximises F1 on the calibration set.", indent=False)
subheading("Training setup")
table("Training Setup and Hyperparameters",
      ["Item", "Setting"],
      [["Model", "LightGBM, binary log-loss, early stopping on AP"],
       ["Trees", "7 leaves, ≥ 4000 rows per leaf, learning rate 0.03"],
       ["Regularisation", "L2 λ = 50, feature fraction 0.4, bagging 0.7, extra-trees"],
       ["Class balance", "weight √(neg/pos), area-balanced sample weights"],
       ["Train", "months ≤ 2022-03, 60 % of 1 km blocks; 800,784 rows"],
       ["Validation / calibration", "2023-03 … 2023-12; 169,049 / 378,057 rows"],
       ["Test (locked)", "months ≥ 2024-12 on test blocks; 132,230 rows"],
       ["Embargo", "≥ 11-month gaps = label look-ahead (no leakage)"],
       ["Hardware", "Intel Core 5 210H, 16 GB RAM, CPU only; final fit 14 s"],
       ["Decision rule", "a change is adopted only if validation AP gains ≥ 0.005 (5 seeds)"]],
      [1.15, 2.3], size=7)
para("Model choices were made on validation data only. The test set was evaluated once. 95 % confidence intervals use a "
     "cluster bootstrap over (site, block).")

# ============================================================================ IV. Results and discussion
heading("Results and Discussion")
subheading("Evaluation metrics")
para("Degradation onsets are rare (2.5 % of test pixel-months). A model that never warns would therefore score 97.5 % accuracy, "
     "so PR-AUC and its lift over chance are the primary metrics. Table IV reports all metrics at the calibrated threshold "
     "(p = 0.129) on the locked test set.")
table("Test-Set Performance (132,230 Pixel-Months)",
      ["Metric", "Value", "Metric", "Value"],
      [["ROC-AUC", "0.805 (0.766–0.838)", "Precision", "0.217"],
       ["PR-AUC", "0.144 (0.112–0.184)", "Recall", "0.289"],
       ["Lift over chance", "5.7×", "F1-score", "0.248"],
       ["Accuracy", "95.6 %", "False-alarm rate", "2.7 %"],
       ["ECE / Brier", "0.0025 / 0.0228", "Specificity", "97.3 %"],
       ["Onsets warned ≥ 1 mo", "41 % (median 3 mo)", "NPV of “no event”", "99.6 %"],
       ["Confusion: TP / FP", "963 / 3,468", "FN / TN", "2,364 / 125,435"]],
      [0.95, 0.95, 0.8, 0.75], size=7,
      note="Brackets: 95 % cluster-bootstrap CI. NPV refers to the conformal “no event” decisions; the system abstains on 52 % of "
           "pixels, and on the confident remainder ROC-AUC is 0.877.")
figure(FIG / "roc_pr.png", "ROC and precision–recall curves on the locked test set for CARE-EW and three baselines. The "
       "grey line in (b) is the 2.5 % base rate.")
subheading("Comparison with baselines and ablation")
para("Fig. 3 and Fig. 4 compare CARE-EW with three non-deep baselines on the same rows: anomaly persistence (PR-AUC 0.036), "
     "a residual threshold rule (0.055) and a random forest on Sentinel-2 state and change features (0.044). Adding feature "
     "groups one at a time shows where the signal lies. Spectral state, change and raw climate stay near chance "
     "(0.032–0.036). The climate-conditioned residual lifts PR-AUC to 0.131, and resilience and context features to 0.152. "
     "Weather data matter only through the residual, not as direct inputs.")
figure(FIG / "ablation.png", "Cumulative ablation on the locked test set (uncalibrated scores). Grey: baselines; light blue: "
       "groups that add no skill; dark blue: residual, resilience and context.")
para("Further pre-registered experiments were rejected because they did not raise validation AP by at least 0.005: "
     "GLCM texture, red-edge chlorophyll indices, doubling the pixels per site, confident-learning label cleaning [22], "
     "a five-seed ensemble and training on all 23 sites.")
subheading("Over- and under-fitting")
para("Fig. 5(a) varies tree size from 3 to 255 leaves. Validation PR-AUC stays within 0.13–0.15 and training AP never runs "
     "far above it, so larger trees add no skill. In Fig. 5(b), validation and test PR-AUC rise with training size (test "
     "0.068 at 5 % of pixels to 0.152 at 100 %). The model is limited by data, not capacity.")
figure(FIG / "fit_curves.png", "(a) Validation curve over model capacity (dashed: chosen 7 leaves). (b) Learning curve over "
       "training size.")
subheading("Generalisation across countries, sites and time")
para("When each country is held out entirely, lift remains 2.3–13.8×: Australia 13.8, Ethiopia 10.2, Senegal 9.8, Kenya 7.0, "
     "Nepal 6.2, Spain 4.6, India 4.1, Brazil 2.3. Mongolia has no test events. The 17-site model, without retraining, was "
     "applied to six new sites (Table V); together they reach ROC-AUC 0.839, lift 8.6× and PR-AUC 0.217. In walk-forward "
     "retraining (Fig. 6), test-year PR-AUC rises from chance in 2021 to 0.179 in 2025 as the Sentinel-2 record grows.")
table("Independent Test on Six New Sites",
      ["Site", "Landscape", "ROC-AUC", "Lift"],
      [["Sindhupalchok (NP)", "mid-hill forest, landslides", "0.873", "9.8×"],
       ["Singrauli (IN)", "coal mining", "0.876", "6.8×"],
       ["Udayapur (NP)", "Chure foothills", "0.844", "7.0×"],
       ["Kailali (NP)", "Chure foothills", "0.803", "10.1×"],
       ["Shivalik (IN)", "foothill forest", "0.782", "12.7×"],
       ["Marathwada (IN)", "rainfed cropland", "0.597", "1.7×"],
       ["**All six**", "", "**0.839**", "**8.6×**"]],
      [1.0, 1.25, 0.6, 0.55], size=7)
figure(FIG / "walk_forward.png", "Walk-forward retraining: test-year PR-AUC (line) and training rows (bars).")
subheading("Operational output")
para("For every site and month the system produces a risk map, hotspot boxes with hectares at risk, a process explanation "
     "and the upstream river network. A user can also draw a box anywhere to run the full pipeline on demand (Fig. 7). "
     "Fig. 8 shows the maps for nine sites. By land cover (Table VI), skill is highest in shrubland and grassland and lowest "
     "in cropland, where sowing and harvest changes resemble degradation.")
figure(ROOT / "outputs" / "screenshots" / "ui_final" / "02_aoi_hotspots_rivers.png",
       "Web console: September 2026 warning hotspots (red boxes, probability and area) over Baringo, Kenya, with the "
       "upstream river network and monthly NDVI, residual, risk and rainfall series.")
table("Test Performance by Land Cover",
      ["Land cover", "PR-AUC", "Lift", "ROC-AUC", "Recall", "FAR"],
      [["Shrubland", "0.275", "6.8×", "0.858", "0.42", "3.6 %"],
       ["Grassland", "0.218", "6.6×", "0.870", "0.38", "3.8 %"],
       ["Bare / sparse", "0.123", "4.1×", "0.755", "0.25", "4.1 %"],
       ["Tree cover", "0.110", "8.8×", "0.812", "0.36", "2.3 %"],
       ["Cropland", "0.096", "3.5×", "0.743", "0.17", "2.1 %"]],
      [0.85, 0.5, 0.45, 0.6, 0.5, 0.5], size=7, note="FAR: false-alarm rate at the operating threshold.")
figure(FIG / "risk_maps.png",
       "Six-month risk maps for September 2026 at nine training sites (5.12 km each). Warm colours: probability of onset; grey: "
       "pixels already below their peers (not eligible for an early warning) or masked.")
subheading("Discussion")
para("The ablation supports the central hypothesis in a falsifiable way. If future degradation could be read from present "
     "greenness or from weather alone, groups A1–A3 would score well; they do not. Skill appears only once each pixel is "
     "compared with what climate and its landscape peers predict, and it grows when the autocorrelation and variance of that "
     "residual are added. This is the pattern critical-slowing-down theory predicts [6], [7], here tested on held-out data "
     "rather than assumed. We do not claim that rising autocorrelation marks a tipping point, only that it improves forecasts.")
para("Calibration makes the scores usable. A stated 10 % risk corresponds to about 10 % observed onsets (ECE 0.0025), so a "
     "district officer can rank hotspots by expected hectares rather than by an arbitrary score. Abstention is the price of "
     "moderate discrimination at a 2.5 % base rate. The system clears about half of the landscape with 99.6 % reliability "
     "and sends the uncertain half to field teams. Label design mattered more than model choice: an earlier label that "
     "followed monsoon timing produced plausible but meaningless accuracy and was rejected on validation diagnostics.")
subheading("Limitations")
bullets([
    "**Labels are satellite proxies, not field data.** Persistent unexplained decline also captures land-use change, fire "
    "and harvest timing. Cropland remains the weak case (Marathwada ROC 0.60).",
    "**Moderate precision.** About one warning in five is followed by an onset, so the system suits triage of field "
    "inspections, not enforcement.",
    "**No independent visual confirmation yet.** In a blind pilot on 233 before/after pairs of sub-metre imagery, a visible "
    "change was seen at 19.6 % of warnings and 24.5 % of safe pixels (difference −4.9 points, 95 % CI −15 to +6). The "
    "pilot was underpowered and mostly showed abrupt events rather than gradual thinning.",
    "**Short baseline and coarse climate.** The Sentinel-2 baseline covers only 2017–2020, and climate is at 9–25 km.",
    "**Single validation year.** Model selection used one validation year, whose seed noise is close to the decision margin.",
])

# ============================================================================ V. Conclusion
heading("Conclusion and Future Work")
para("CARE-EW turns free satellite and climate data into calibrated six-month warnings of persistent land degradation at "
     "10 m. On a hold-out new in both space and time it ranks future onsets with ROC-AUC 0.805 (0.839 on six unseen sites), "
     "at a 2.7 % false-alarm rate. The predictive signal comes from the climate-conditioned residual and resilience "
     "indicators, not from spectral state or raw weather.")
para("Future work is specific:", after=2)
bullets([
    "crop-calendar-aware labels and more cropland sites, to lift cropland ROC-AUC above 0.60;",
    "an independent human review of the 233 image pairs, followed by a power-calculated campaign of at least 300 pairs per "
    "group with same-season imagery taken within six months before the warning;",
    "a prospective test on months after October 2025, comparing the 17-site model, a 23-site model and a seed ensemble;",
    "Sentinel-1 radar features to fill monsoon cloud gaps.",
])

# ============================================================================ References
heading("References", numbered=False)
REFS = [
    "M. Cherlet et al., Eds., *World Atlas of Desertification*, 3rd ed. Luxembourg: Publications Office of the EU, 2018.",
    "N. C. Sims et al., “Good practice guidance: SDG indicator 15.3.1, version 2.0,” UNCCD, Bonn, Germany, 2021.",
    "M. Gonzalez-Roglich et al., “Synergizing global tools to monitor progress towards land degradation neutrality: Trends.Earth "
    "and the World Overview of Conservation Approaches and Technologies sustainable land management database,” *Environ. Sci. "
    "Policy*, vol. 93, pp. 34–42, 2019.",
    "K. J. Wessels et al., “Can human-induced land degradation be distinguished from the effects of rainfall variability? A case "
    "study in South Africa,” *J. Arid Environ.*, vol. 68, no. 2, pp. 271–297, 2007.",
    "S. D. Prince, I. Becker-Reshef, and K. Rishmawi, “Detection and mapping of long-term land degradation using local net "
    "production scaling: Application to Zimbabwe,” *Remote Sens. Environ.*, vol. 113, no. 5, pp. 1046–1057, 2009.",
    "M. Scheffer et al., “Early-warning signals for critical transitions,” *Nature*, vol. 461, pp. 53–59, 2009.",
    "V. Dakos et al., “Methods for detecting early warnings of critical transitions in time series illustrated using simulated "
    "ecological data,” *PLoS ONE*, vol. 7, no. 7, e41010, 2012.",
    "J. Verbesselt et al., “Remotely sensed resilience of tropical forests,” *Nature Clim. Change*, vol. 6, pp. 1028–1031, 2016.",
    "T. Smith, D. Traxl, and N. Boers, “Empirical evidence for recent global shifts in vegetation resilience,” *Nature Clim. "
    "Change*, vol. 12, pp. 477–484, 2022.",
    "C. A. Boulton, T. M. Lenton, and N. Boers, “Pronounced loss of Amazon rainforest resilience since the early 2000s,” "
    "*Nature Clim. Change*, vol. 12, pp. 271–278, 2022.",
    "P. Ploton et al., “Spatial validation reveals poor predictive performance of large-scale ecological mapping models,” "
    "*Nature Commun.*, vol. 11, 4540, 2020.",
    "H. Meyer and E. Pebesma, “Predicting into unknown space? Estimating the area of applicability of spatial prediction "
    "models,” *Methods Ecol. Evol.*, vol. 12, no. 9, pp. 1620–1633, 2021.",
    "J. Verbesselt, R. Hyndman, G. Newnham, and D. Culvenor, “Detecting trend and seasonal changes in satellite image time "
    "series,” *Remote Sens. Environ.*, vol. 114, no. 1, pp. 106–115, 2010.",
    "M. C. Hansen et al., “High-resolution global maps of 21st-century forest cover change,” *Science*, vol. 342, "
    "pp. 850–853, 2013.",
    "J. Reiche et al., “Forest disturbance alerts for the Congo Basin using Sentinel-1,” *Environ. Res. Lett.*, vol. 16, "
    "no. 2, 024005, 2021.",
    "S. Kéfi et al., “Spatial vegetation patterns and imminent desertification in Mediterranean arid ecosystems,” "
    "*Nature*, vol. 449, pp. 213–217, 2007.",
    "D. Zanaga et al., “ESA WorldCover 10 m 2021 v200,” Zenodo, 2022, doi: 10.5281/zenodo.7254221.",
    "G. Ke et al., “LightGBM: A highly efficient gradient boosting decision tree,” in *Proc. NeurIPS*, 2017, pp. 3146–3154.",
    "B. Zadrozny and C. Elkan, “Transforming classifier scores into accurate multiclass probability estimates,” in *Proc. "
    "ACM SIGKDD*, 2002, pp. 694–699.",
    "V. Vovk, A. Gammerman, and G. Shafer, *Algorithmic Learning in a Random World*. New York, NY, USA: Springer, 2005.",
    "A. N. Angelopoulos and S. Bates, “Conformal prediction: A gentle introduction,” *Found. Trends Mach. Learn.*, vol. 16, "
    "no. 4, pp. 494–591, 2023.",
    "C. Northcutt, L. Jiang, and I. Chuang, “Confident learning: Estimating uncertainty in dataset labels,” *J. Artif. "
    "Intell. Res.*, vol. 70, pp. 1373–1411, 2021.",
    "M. Drusch et al., “Sentinel-2: ESA's optical high-resolution mission for GMES operational services,” *Remote Sens. "
    "Environ.*, vol. 120, pp. 25–36, 2012.",
    "J. Muñoz-Sabater et al., “ERA5-Land: A state-of-the-art global reanalysis dataset for land applications,” *Earth "
    "Syst. Sci. Data*, vol. 13, pp. 4349–4383, 2021.",
]
for i, r in enumerate(REFS, 1):
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p.paragraph_format.left_indent = Inches(0.25); p.paragraph_format.first_line_indent = Inches(-0.25)
    run(p, f"[{i}] ", 8); rich(p, r, 8)

doc.core_properties.title = "Early Warning of Persistent Land Degradation from Sentinel-2 Time Series"
doc.core_properties.author = "Ankur Bhattarai"
doc.save(OUT)
print("wrote", OUT)
