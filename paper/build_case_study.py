"""Case study (Word + PDF) summarising the paper and the deck, with figures and UI screenshots.
Style rule from the team: no hyphens, double hyphens or dashes in the written text; short, plain sentences.
Output: ~/Desktop/Case_Study_Land_Degradation_Early_Warning.docx (override with env CASE_OUT)."""
import os
import re
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

ROOT = Path(__file__).resolve().parents[1]
SS = ROOT / "outputs" / "screenshots"; FIG = ROOT / "outputs" / "figures"; PF = ROOT / "paper" / "figs"
OUT = Path(os.environ.get("CASE_OUT", Path.home() / "Desktop" / "Case_Study_Land_Degradation_Early_Warning.docx"))
GREEN, DARK, SOIL, GREY = RGBColor(0x2E, 0x6B, 0x3F), RGBColor(0x15, 0x29, 0x1C), RGBColor(0xB5, 0x56, 0x2B), RGBColor(0x55, 0x55, 0x55)
WRITTEN = []  # every string we write, checked for dashes at the end


def loco_chart():
    rows = [("Australia", 13.8), ("Ethiopia", 10.2), ("Senegal", 9.8), ("Kenya", 7.0), ("Nepal", 6.2),
            ("Spain", 4.6), ("India", 4.1), ("Brazil", 2.3)][::-1]
    fig, ax = plt.subplots(figsize=(6.2, 3.0))
    ax.barh([r[0] for r in rows], [r[1] for r in rows], color="#9aa79c", height=0.62)
    for i, (_, v) in enumerate(rows):
        ax.text(v + 0.2, i, f"{v:.1f}×", va="center", fontsize=9)
    ax.axvline(1, color="#b5562b", ls="--", lw=1)
    ax.text(1.15, -0.9, "chance level", color="#b5562b", fontsize=8.5)
    ax.set_xlabel("Lift over chance (PR AUC divided by the base rate)")
    ax.set_xlim(0, 15.5); ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout(); p = PF / "case_loco.png"; fig.savefig(p, dpi=220); plt.close(fig)
    return p


doc = Document()
sec = doc.sections[0]
sec.page_width, sec.page_height = Inches(8.27), Inches(11.69)
for side in ("left_margin", "right_margin"):
    setattr(sec, side, Inches(0.95))
sec.top_margin = sec.bottom_margin = Inches(0.9)
st = doc.styles["Normal"]; st.font.name = "Calibri"; st.font.size = Pt(11)
st.element.rPr.rFonts.set(qn("w:eastAsia"), "Calibri")
st.paragraph_format.space_after = Pt(6); st.paragraph_format.line_spacing = 1.12
for lvl, size in ((1, 16), (2, 13)):
    h = doc.styles[f"Heading {lvl}"]; h.font.name = "Cambria"; h.font.size = Pt(size); h.font.color.rgb = GREEN
    h.font.bold = True; h.paragraph_format.space_before = Pt(14 if lvl == 1 else 10); h.paragraph_format.space_after = Pt(4)

FIGN = [0]; TABN = [0]


def W(s):
    WRITTEN.append(s); return s


def para(text, bold_lead=None, size=None, italic=False, color=None, align=None, after=None):
    p = doc.add_paragraph()
    if bold_lead:
        r = p.add_run(W(bold_lead) + " "); r.bold = True
        if size: r.font.size = Pt(size)
    r = p.add_run(W(text)); r.italic = italic
    if size: r.font.size = Pt(size)
    if color: r.font.color.rgb = color
    if align: p.alignment = align
    if after is not None: p.paragraph_format.space_after = Pt(after)
    return p


def h1(t): doc.add_heading(W(t), level=1)
def h2(t): doc.add_heading(W(t), level=2)


def bullets(items, style="List Bullet"):
    for it in items:
        p = doc.add_paragraph(style=style)
        if isinstance(it, tuple):
            r = p.add_run(W(it[0]) + " "); r.bold = True; p.add_run(W(it[1]))
        else:
            p.add_run(W(it))
        p.paragraph_format.space_after = Pt(3)


def shade(cell, hexcolor):
    tcPr = cell._tc.get_or_add_tcPr(); s = OxmlElement("w:shd")
    s.set(qn("w:val"), "clear"); s.set(qn("w:color"), "auto"); s.set(qn("w:fill"), hexcolor); tcPr.append(s)


def table(title, rows, widths, size=10):
    TABN[0] += 1
    cp = para(f"Table {TABN[0]}. {title}", size=10, color=DARK, after=2); cp.runs[0].bold = True
    cp.paragraph_format.keep_with_next = True
    t = doc.add_table(rows=len(rows), cols=len(rows[0])); t.style = "Table Grid"; t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, row in enumerate(rows):
        for j, val in enumerate(row):
            c = t.cell(i, j); c.width = Inches(widths[j]); c.text = ""
            r = c.paragraphs[0].add_run(W(str(val))); r.font.size = Pt(size)
            c.paragraphs[0].paragraph_format.space_after = Pt(0)
            c.paragraphs[0].paragraph_format.keep_with_next = i < len(rows) - 1
            if i == 0:
                r.bold = True; r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF); shade(c, "2E6B3F")
            elif i % 2 == 0:
                shade(c, "EAF2EC")
    doc.add_paragraph().paragraph_format.space_after = Pt(2)


def figure(path, width, title, desc):
    FIGN[0] += 1
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run().add_picture(str(path), width=Inches(width)); p.paragraph_format.keep_with_next = True
    p.paragraph_format.space_after = Pt(2)
    c = doc.add_paragraph(); r = c.add_run(W(f"Figure {FIGN[0]}. {title}") + " "); r.bold = True; r.font.size = Pt(9.5)
    r.font.color.rgb = DARK
    r2 = c.add_run(W(desc)); r2.font.size = Pt(9.5); r2.font.color.rgb = GREY
    c.paragraph_format.space_after = Pt(10)


def page_break():
    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)


# ================================================================ title page
for _ in range(2):
    doc.add_paragraph()
p = para("CASE STUDY", size=11, color=SOIL); p.runs[0].bold = True
t = doc.add_paragraph(); r = t.add_run(W("Seeing Land Degradation Before It Happens")); r.font.size = Pt(26); r.bold = True
r.font.name = "Cambria"; r.font.color.rgb = DARK
para("How the CARE EW system uses Sentinel 2 satellite images and machine learning to warn, up to six months "
     "ahead, where land is likely to start a long decline.", size=13, color=GREY, after=18)
figure(SS / "ui_final" / "03_hotspot_panel.png", 6.3, "The CARE EW web console.",
       "Kenya, Baringo study area, September 2026. Red boxes are hotspots ranked H1 to H10, each labelled with its "
       "probability and area. The panel on the right explains hotspot H1: a mean risk of 0.175, an area of 281 ha, a first "
       "warning in August 2026, NDVI at 0.487 against a normal of 0.580 (16 percent below), a rainfall anomaly of "
       "minus 1.8 standard deviations, the five strongest drivers and Sentinel 2 images from before and after.")
para("Team", bold_lead=None, size=11, color=SOIL).runs[0].bold = True
for n in ("Ankur Bhattarai, 24BCE2954", "Rohit Kumar Chaurasiya, 24BDS0451", "Roshan Jaishwal, 24BCE2965"):
    para(n, size=11, after=1)
para("Based on our conference paper and project presentation. October 2026.", size=10, color=GREY)
page_break()

# ================================================================ 1 summary
h1("1. Executive summary")
para("Land degradation is the slow loss of healthy soil and plant cover. Most monitoring tools report it after the damage "
     "is done. We asked a simple question. Can free satellite data and machine learning warn us months before a long "
     "decline begins, without raising an alarm every time a dry year arrives?")
para("We built CARE EW to answer it. The name stands for Climate Adjusted, Resilience Enhanced Early Warning. The system "
     "reads monthly Sentinel 2 images at 10 m detail. It removes the part of each change that the weather explains. It then "
     "measures how well the land bounces back after stress. A small LightGBM model turns these signals into a calibrated "
     "probability that a pixel will start a persistent decline within six months.")
para("We tested it on 17 landscapes in 9 countries, using data the model had never seen. The main results are below. "
     "We also built a web console so that anyone can explore the warnings on a 3D globe.")
table("Key results on the unseen test set", [
    ["Measure", "Result", "In plain words"],
    ["Data size", "4.29 million pixel months", "One pixel month is one 10 m square seen in one month"],
    ["ROC AUC", "0.805", "Given one pixel that degrades and one that does not, the model ranks them correctly 8 times in 10"],
    ["Lift over chance", "5.7 times", "Warnings find real cases 5.7 times more often than random picks"],
    ["Calibration error", "0.0025", "A 20 percent warning comes true about 20 percent of the time"],
    ["Events warned early", "41 percent", "Median warning came 3 months before the decline began"],
    ["Confident answers", "ROC AUC 0.877", "On the half of cases where the model is sure, it is much sharper"],
    ["New countries", "2.3 to 13.8 times chance", "It beat chance in every country left out of training"],
], [1.45, 1.6, 3.25])
para("We also ran a blind check with very high resolution images. That check did not confirm the warnings. It was "
     "small and was scored by an AI reviewer, so it cannot settle the question either way. Section 8 explains it.")

# ================================================================ 2 problem
h1("2. Background and problem")
para("Farmers lose harvests, herders lose grazing land and "
     "rivers fill with eroded soil. The United Nations tracks this through Sustainable Development Goal indicator 15.3.1. "
     "About a fifth of land area shows falling productivity in global assessments [2]. Artificial intelligence is now widely used to map degradation and predict its drivers [1].")
para("Current tools have three gaps.")
bullets([("They look backward.", "Trend maps and yearly reports show where land has already declined. Repair is then slow "
                                  "and costly."),
         ("They confuse drought with damage.", "Plants brown in every dry season. A tool that cannot separate weather from "
                                               "real loss sends many false alarms, and users stop listening."),
         ("They are too coarse.", "Many products use 250 m to 1 km pixels. A degraded field or a new gully is much smaller "
                                  "than that.")])
para("Our goal was a tool that fixes all three. It should look forward, ignore normal weather swings and work at field "
     "scale. It should also be honest about how sure it is.")

h2("Objectives")
bullets(["Predict, six months ahead, which 10 m pixels will begin a persistent decline.",
         "Separate human or ecological damage from the effect of rain and temperature.",
         "Give probabilities that can be trusted, and say \"not sure\" when the evidence is weak.",
         "Test the model on future years and on countries it never saw.",
         "Deliver the results in an easy web console for field teams."], style="List Number")

# ================================================================ 3 data
h1("3. Study areas and data")
para("We chose 17 landscapes in 9 countries: Nepal, India, Ethiopia, Kenya, Senegal, Spain, Brazil, Mongolia and Australia. "
     "Each study area is a square of 5.12 km. Together they cover dry rangeland, shrubland, savanna, cropland, forest "
     "frontier and mining land. Nepal and India hold 9 of the 17 sites because they are close to our team and have "
     "many kinds of degradation.")
figure(FIG / "fig01_study_areas.png", 6.2, "Location of the 17 study areas.",
       "Each dot is one 5.12 km study area. The spread across five continents lets us test whether the model works in "
       "places with very different climates and land use.")
para("All inputs are free and open. We downloaded them from the Microsoft Planetary Computer.")
table("Data sources", [
    ["Source", "What we use", "Detail"],
    ["Sentinel 2 L2A", "Four plant and soil indices: NDVI, NDMI, NBR, BSI", "10 m, monthly, 2017 to 2026"],
    ["MODIS MOD13Q1", "A long NDVI history for resilience signals", "250 m, from 2000"],
    ["ERA5 and ERA5 Land", "Rain, temperature and soil water", "9 to 31 km, monthly"],
    ["ESA WorldCover", "Land cover class of each pixel", "10 m"],
    ["NASADEM", "Elevation and slope", "30 m"],
    ["JRC water and HydroRIVERS", "Distance to water and the river network", "30 m and vector"],
    ["GloFAS", "River discharge for the console", "about 5 km"],
], [1.75, 2.85, 1.7])
para("The final table holds 4.29 million pixel months. Only 2.5 percent of them are followed by a real decline. This "
     "makes the task a rare event problem, which shapes how we judge the results.")

# ================================================================ 4 method
h1("4. How the system works")
para("The system runs the same chain of steps every month. Figure 3 shows the full pipeline. Each step is explained below "
     "in plain words.")
figure(PF / "arch.png", 4.3, "The CARE EW pipeline.",
       "Four groups of inputs are cleaned into monthly images. A climate model removes what the weather explains. Features "
       "describe the state, change, residual and resilience of each pixel. LightGBM predicts, and calibration with a "
       "conformal step makes the probability honest. The output is a monthly risk map with explanations.")
h2("Step 1. Clean the images")
para("Sentinel 2 images contain clouds, shadows and duplicate scenes. We remove duplicates and fix a known offset of 1000 "
     "in newer images. A cloud mask hides bad pixels. We then take the median of each month for every pixel, which gives "
     "one clean picture per month.")
h2("Step 2. Measure plant and soil health")
para("From the clean bands we compute four indices. NDVI measures green leaves. NDMI measures moisture in the plants. NBR "
     "picks up burns and damage. BSI measures bare soil. Healthy land has high NDVI and low BSI.")
h2("Step 3. Compare each month with its own normal")
para("Every pixel has its own seasonal pattern. We take its usual value for each calendar month from 2017 to 2020. We also "
     "measure how much it normally varies. The z score then says how many normal swings this month is above or below "
     "the usual value. A z score of minus 2 means the pixel is unusually brown for that time of year.")
h2("Step 4. Remove the weather and compare with peers")
para("A low z score can simply mean a dry year. So we fit a small ridge regression on rain, temperature and soil water. It "
     "predicts the z score the weather alone would cause. We subtract that prediction. We then subtract the median of "
     "nearby pixels with the same land cover. What remains is the residual R. A pixel with a low R is doing worse than "
     "both the weather and its neighbours can explain. That is the signal we care about.")
figure(FIG / "fig03_method_example.png", 6.0, "Worked example on one real pixel in Murcia, Spain.",
       "Panel a shows the observed NDVI in blue against the pixel's normal seasonal curve in grey. From 2023 the green "
       "peaks fall short. Panel b shows the anomaly z in blue and the part the weather explains in green. The weather "
       "explains very little of the deep drops. Panel c shows the residual R in orange. The red lines mark the start of "
       "a persistent decline. The shaded months before each red line are the months the model must learn to warn about.")
h2("Step 5. Define what counts as degradation")
para("A single bad month is not degradation. We call it a persistent decline when all of these hold:")
bullets(["R stays at or below minus 1 for at least six months in a row,",
         "the pixel is at least 0.02 NDVI below its peers,",
         "at least 75 percent of those months have a clear image,",
         "the mean NDVI loss compared with peers is at least 0.05."])
para("The model's target for each month is simple. Will such a decline begin in the next six months? Yes or no.")
h2("Step 6. Build the features")
para("For each pixel and month the model reads 64 numbers, grouped into six families.")
table("Feature groups", [
    ["Group", "What it describes", "Examples"],
    ["A1 State", "How the land looks now", "Current NDVI, normal variation, land cover"],
    ["A2 Change", "How it has changed", "NDVI change over 3, 12 and 36 months"],
    ["A3 Climate", "Recent weather", "Rain, temperature and soil water anomalies"],
    ["A4 Residual", "Unexplained loss", "Mean and minimum R, months below expectation, run length"],
    ["A5 Resilience", "How fast it recovers", "Autocorrelation (AC1), variance, 5 year MODIS signals"],
    ["A6 Context", "Where it sits", "Distance to river, slope, elevation, water"],
], [1.25, 1.75, 3.3])
para("The resilience group is the new idea in this work. Ecology theory says that a system close to a tipping point "
     "recovers more slowly from each shock. In the data this shows up as rising autocorrelation and variance before the "
     "collapse.")
h2("Step 7. Predict with a small LightGBM model")
para("LightGBM builds many small decision trees, one after another. Each new tree fixes some of the errors left by the "
     "trees before it. We kept the model deliberately small so that it learns general rules and not the quirks of one "
     "place.")
table("Model settings and why we chose them", [
    ["Setting", "Value", "Why"],
    ["Leaves per tree", "7", "Each tree stays a tiny rule set, so it cannot memorise"],
    ["Minimum pixels per leaf", "4,000", "No rule may rest on a handful of pixels"],
    ["Features and rows per tree", "40 percent and 70 percent", "Random subsets make the trees diverse"],
    ["L2 penalty, extra trees", "50, on", "Strong smoothing and random split points"],
    ["Learning rate", "0.03", "Small steps that add up slowly"],
    ["Early stopping", "on PR AUC", "Training stops when validation stops improving"],
], [1.9, 1.6, 2.8])
para("Training on 800,784 rows took about 14 seconds on a laptop processor.")
h2("Step 8. Make the probability honest")
para("Raw model scores are not true probabilities. Isotonic calibration maps them onto real observed rates, so a score "
     "of 0.2 means about a 20 percent chance. A Mondrian conformal predictor with a 10 percent error level then checks "
     "each case. If both answers, event and no event, remain plausible, the model abstains. Those pixels are marked with "
     "purple hatching in the console as \"inspect in the field\".")

# ================================================================ 5 testing
h1("5. How we tested it fairly")
para("Satellite data have a trap. Neighbouring pixels and neighbouring months look alike. If they end up on both sides of "
     "the split, a model can look brilliant while it is only copying. We closed this trap in two ways.")
bullets([("Split by time.", "The model learned only from months up to March 2022. It was tested only on months from "
                            "December 2024 onward. Validation and calibration used March to December 2023."),
         ("Split by place.", "We cut every study area into 1 km blocks. Each block went into exactly one group: 60 percent "
                             "for training, 20 percent for calibration and 20 percent for testing.")])
table("Data splits", [
    ["Set", "Period", "Rows"],
    ["Training", "Up to March 2022, training blocks", "800,784"],
    ["Early stopping", "March to December 2023, validation blocks", "169,049"],
    ["Calibration", "March to December 2023, calibration blocks", "378,057"],
    ["Test", "December 2024 onward, test blocks only", "132,230"],
], [1.5, 3.4, 1.4])
para("We also ran three harder tests. We left out one whole country at a time. We retrained the model every January and "
     "tested on the year after. We applied the final model to six brand new sites in Nepal and India.")

# ================================================================ 6 results
h1("6. Results")
h2("6.1 Ranking skill")
figure(PF / "roc_pr.png", 5.6, "ROC and precision recall curves on the test set.",
       "The blue line is CARE EW. The other lines are simpler methods: a random forest on Sentinel 2 only, a residual "
       "rule and plain anomaly persistence. In panel a, a curve closer to the top left is better. In panel b, a curve "
       "higher above the flat chance line is better. CARE EW leads on both.")
para("CARE EW reached a ROC AUC of 0.805, with a 95 percent confidence range of 0.766 to 0.838. Its PR AUC was 0.144, with "
     "a range of 0.112 to 0.184. Chance on this test set is 0.025, so the model is 5.7 times better than random. The "
     "Brier score was 0.0228 and the calibration error was only 0.0025.")
h2("6.2 The confusion matrix")
para("To turn probabilities into yes or no warnings we need a cut off. We used 0.129, the value that gave the best F1 "
     "score on the calibration set.")
table("Confusion matrix at the 0.129 cut off (132,230 test pixel months)", [
    ["", "Decline began later", "Stayed healthy"],
    ["Warned", "963 (true positive)", "3,468 (false alarm)"],
    ["Not warned", "2,364 (missed)", "125,435 (true negative)"],
], [1.6, 2.35, 2.35], size=10.5)
bullets([("Precision 0.217.", "About 1 warning in 5 was correct. With a base rate of 2.5 percent this is a large gain."),
         ("Recall 0.289.", "We caught 29 percent of declines at this cut off. A lower cut off catches more but raises more "
                           "false alarms."),
         ("Specificity 0.973.", "Almost all healthy land was left alone. The false alarm rate was 2.7 percent."),
         ("Accuracy 0.956.", "This sounds high but means little. A tool that always says \"no problem\" scores 0.975 and "
                             "helps nobody. That is why we report PR AUC and lift instead.")])
h2("6.3 Which signals matter")
figure(PF / "ablation.png", 5.4, "Test PR AUC as feature groups are added.",
       "Grey bars are simple baselines. Light blue bars add the state, change and climate groups. Dark blue bars add the "
       "residual, resilience and context groups. The red dashed line is chance.")
para("The simple baselines scored between 0.036 and 0.055. Adding state, change and climate features kept the model near "
     "0.03. The big jump came with the residual group, which lifted PR AUC to 0.131. Resilience raised it to 0.143 and "
     "context to 0.152. In short, removing the weather and measuring recovery are what make the warnings work.")
figure(FIG / "fig13_shap.png", 4.9, "The features that drive the warnings.",
       "Mean absolute SHAP value of each feature on the test set. Longer bars mean more influence. Pink bars are "
       "resilience features and orange bars are residual features.")
para("The strongest single driver is the five year variance of MODIS NDVI. Next come the share of the last 12 months "
     "with a residual below minus 1, the lag one autocorrelation over 24 months and its trend. Seven of the top ten "
     "drivers belong to the resilience and residual groups. This matches the theory that land loses resilience before "
     "it declines.")
h2("6.4 Knowing when to say \"not sure\"")
para("The conformal step abstained on 52 percent of test pixel months. This sounds like a lot, but it buys real quality. "
     "On the remaining cases the ROC AUC rose to 0.877. When the model said \"no event\", it was right 99.6 percent of "
     "the time. Field teams can therefore skip confident \"no\" areas and send people to the warnings and the abstentions.")
h2("6.5 How early the warnings come")
figure(FIG / "fig12_lead_time.png", 4.8, "Warning lead time for the 1,444 test events.",
       "The grey bar counts events with no warning before they began. Blue bars count events by how many months of "
       "warning they received. Many warnings come one month ahead, and the rest are spread fairly evenly up to six months.")
para("Of 1,444 decline events in the test period, 41 percent received a warning before they started. The median lead "
     "time was 3 months. That is enough time to visit a site, check grazing pressure or plan soil work before the next "
     "season.")
h2("6.6 Does it work in new places?")
figure(loco_chart(), 5.6, "Leave one country out test.",
       "For each bar the model was trained without that country and then tested on it. The dashed line marks chance. "
       "Every country is well above it.")
para("The model kept its skill in every country it had never seen. It was strongest in the dry rangelands of Australia, "
     "Ethiopia and Senegal and weakest in Brazil. On six new sites in Nepal and India that were not part of training, "
     "it reached a ROC AUC of 0.839 and 8.6 times chance overall. The weakest new site was Marathwada in India, with a ROC "
     "AUC of 0.597 and 1.7 times chance.")
table("Skill by land cover on the test set", [
    ["Land cover", "PR AUC", "ROC AUC"],
    ["Shrubland", "0.275", "0.858"],
    ["Grassland", "0.218", "0.870"],
    ["Bare or sparse", "0.123", "0.755"],
    ["Tree cover", "0.110", "0.812"],
    ["Cropland", "0.096", "0.743"],
], [2.4, 1.6, 1.6])
para("Natural vegetation is easiest. Cropland is hardest because sowing and harvest create big swings that look like "
     "decline.")
h2("6.7 Does it improve over time?")
figure(PF / "walk_forward.png", 5.6, "Walk forward test.",
       "The model was retrained every January on all earlier data and tested on the following year. The blue line is "
       "test PR AUC. The dotted line is chance. Pale bars show how many training rows were available.")
para("With little history in 2021 and 2022 the model was no better than chance, at a PR AUC of 0.034 and 0.028. From 2023 "
     "it improved every year: 0.072 in 2023, 0.140 in 2024 and 0.179 in 2025. This is what we would expect from a real "
     "signal. More years of data mean a clearer picture of each pixel's normal behaviour.")
h2("6.8 What the risk maps look like")
figure(PF / "risk_maps.png", 6.0, "Predicted risk maps for nine study areas, September 2026.",
       "Colour shows the probability of a persistent decline within six months, from pale yellow (low) to dark red (0.3 "
       "or more). Grey pixels are water, built land or masked areas. Risk follows real features: field edges in Brazil "
       "and Spain, gullies in Ethiopia and riverbanks in Nepal.")

# ================================================================ 7 app
h1("7. The web console")
para("Numbers in a paper do not help a field officer. So we built a web console with FastAPI on the server and CesiumJS "
     "for the 3D globe. It runs on a normal laptop. A one click launcher, START_DEMO.bat, sets up Python, starts the "
     "server and opens the browser.")
figure(SS / "ui_final" / "01_globe.png", 6.2, "Globe view.",
       "Every study area appears as a pin coloured by its mean risk, from low to high. The sidebar lists the areas with "
       "their mean risk, number of hotspots and trend. Users can search by country or landscape.")
figure(SS / "ui_final" / "02_aoi_hotspots_rivers.png", 6.2, "Area view with hotspots and rivers.",
       "Opening an area flies the camera in. Red boxes are hotspots, ranked by risk. The cyan lines are the upstream "
       "river network and the gold line is the outlet reach. The time slider at the bottom steps through every month of "
       "risk maps.")
figure(SS / "ui_final" / "04_pixel_inspector.png", 6.2, "Pixel inspector.",
       "Clicking any point inside an area shows that pixel's full history: NDVI, the z score against the residual R and "
       "the predicted risk. Red marks show where a decline began. This lets a user see why the model is worried.")
figure(SS / "ui_timelapse" / "03_H12_mid_2023-08.png", 6.2, "Sentinel 2 time lapse for one hotspot.",
       "Hotspot H12 in Kenya has been below its peers for 38 months, with NDVI at 0.323 against a normal of 0.709 (54 "
       "percent lower). The time lapse plays every cloud free month for this block only. The \"same season only\" option "
       "steps one year at a time, so normal seasons cannot fool the eye.")
figure(SS / "ui_final" / "05_ndvi_riverflow.png", 6.2, "NDVI anomaly layer and river flow.",
       "The map shows where vegetation is below or above normal, from brown to green. The river flow tab compares mean "
       "and low flow from 1984 to 2000 with flow since 2016.")
figure(SS / "ui_drawbox" / "01_draw_box_plan.png", 6.2, "Analysing a new area.",
       "A user can draw a box anywhere on Earth. The planner reports how many 5.12 km blocks are needed and how long the "
       "download and analysis will take. The server then runs the same pipeline and opens the result, with a note that "
       "the area lies outside the training regions.")
para("Hotspots can be exported as GeoJSON or CSV for field teams. Each export carries the model version and a reminder that "
     "the probabilities come from satellite proxies and are not yet field verified.")

# ================================================================ 8 blind check
h1("8. Blind check with very high resolution images")
para("Our labels come from the same satellites the model reads. A fair critic could say the model only learned to "
     "predict its own labels. So we planned an outside check.")
para("We picked sites the model had warned about and an equal number of control sites it had not. A reviewer looked at "
     "very high resolution images of each site and judged whether it showed degradation. The reviewer did not know which "
     "group a site belonged to.")
table("Blind check result", [
    ["Group", "Sites", "Judged degraded"],
    ["Warned by the model", "107", "21 (19.6 percent)"],
    ["Control, not warned", "106", "26 (24.5 percent)"],
], [2.6, 1.2, 2.5])
para("The warned sites were not judged degraded more often. The difference was minus 4.9 percentage points. Its 95 "
     "percent range ran from minus 15.3 to plus 6.4. Fisher's exact test gave p = 0.85, so there is no evidence of a "
     "difference.")
para("We report this result as it is, but it has clear limits. The sample had only about 38 percent power to detect the "
     "effect we expected. The reviewer was an AI model, not a trained analyst. Degradation that is just starting is also "
     "hard to see in a single image. So this check neither proves nor disproves the model. It tells us that the next "
     "step must be a larger check with human experts.")

# ================================================================ 9 limits
h1("9. Limits")
bullets([("Labels come from satellites.", "There are no field visits yet. A label means the greenness stayed low, not that "
                                          "a person saw damage."),
         ("Many false alarms.", "Four out of five warnings did not become a decline. The tool is best used to rank where "
                                "to look first."),
         ("Cropland is hard.", "Farming cycles hide slow loss, so scores there are the lowest."),
         ("Rainfall data are coarse.", "ERA5 misses local storms, which can blur the weather correction in the tropics."),
         ("Many abstentions.", "The model says \"not sure\" on about half of pixel months. That is honest, but those places "
                               "still need a human look."),
         ("Clouds.", "Monsoon months often have no clear image, so some months are missing.")])

# ================================================================ 10 lessons
h1("10. Lessons learned")
bullets([("Remove the weather first.", "The residual and resilience features gave by far the biggest gains."),
         ("Small models travel better.", "A tightly limited model with 7 leaves did better on held out data than larger "
                                         "ones."),
         ("Accuracy can mislead.", "With a 2.5 percent base rate, PR AUC, lift and calibration tell the real story."),
         ("Let the model abstain.", "Saying \"not sure\" made the confident answers far more reliable."),
         ("Split by time and place.", "Without block and time splits the scores would have looked much better and meant "
                                      "much less."),
         ("Report negative results.", "The blind check showed exactly where the proof is still missing.")])

# ================================================================ 11 next
h1("11. Next steps")
bullets(["Repeat the blind check with trained human reviewers and a larger sample, so it has enough power.",
         "Run a true forward test: freeze the model now and score it on 2027 data.",
         "Build crop aware labels that understand sowing and harvest dates.",
         "Add Sentinel 1 radar, which sees through clouds in the monsoon.",
         "Work with local partners to collect field observations at warned sites."])

# ================================================================ 12 conclusion
h1("12. Conclusion")
para("CARE EW shows that free satellite data can give useful early warnings of land degradation at 10 m detail. Removing "
     "the weather and measuring resilience were the keys. The model ranks risk well, its probabilities can be trusted "
     "and it keeps its skill in new countries and new years. It also knows when it is unsure. The open question is "
     "whether its warnings match what people see on the ground. Answering that is the next stage of our work.")

# ================================================================ glossary
h1("Glossary")
table("Terms used in this case study", [
    ["Term", "Meaning"],
    ["Sentinel 2", "A pair of European satellites that photograph all land every 5 days at 10 m detail"],
    ["NDVI", "Normalised Difference Vegetation Index. High values mean dense green plants"],
    ["NDMI, NBR, BSI", "Indices for plant moisture, burn damage and bare soil"],
    ["z score", "How many normal swings a value is above or below its usual level"],
    ["Residual R", "The part of a change that neither the weather nor neighbouring land explains"],
    ["Resilience", "How quickly land recovers after a shock such as a drought"],
    ["AC1", "Lag one autocorrelation. How much this month looks like last month. It rises as recovery slows"],
    ["LightGBM", "A fast machine learning method that adds many small decision trees together"],
    ["Calibration", "Adjusting scores so that a 20 percent warning comes true about 20 percent of the time"],
    ["Conformal prediction", "A method that lets a model say \"not sure\" with a known error rate"],
    ["ROC AUC", "Chance that the model ranks a true case above a false one. 0.5 is a coin flip"],
    ["PR AUC", "Average precision across all cut offs. Best for rare events. Chance equals the base rate"],
    ["Lift", "How many times better than random the model finds real cases"],
    ["Precision and recall", "Share of warnings that were right, and share of real cases that were warned"],
    ["SHAP", "A way to measure how much each feature pushed a prediction up or down"],
    ["Hotspot", "A cluster of high risk pixels, shown as a box in the console"],
], [1.6, 4.7])

# ================================================================ references
h1("References")
refs = [
    "S. Ghosh and J. V. Sharma, “Artificial intelligence for restoring land: A review of land degradation mapping, "
    "climate change prediction and ecosystem service valuation,” Int. J. Environ. Clim. Change, vol. 16, no. 5, "
    "pp. 352 to 375, 2026.",
    "UNCCD, Global Land Outlook, 2nd ed. Bonn, Germany: United Nations Convention to Combat Desertification, 2022.",
    "A. L. Burrell, J. P. Evans and M. G. De Kauwe, “Anthropogenic climate change has driven over 5 million km² "
    "of drylands towards desertification,” Nature Commun., vol. 11, Art. no. 3853, 2020.",
    "T. M. Bury et al., “Deep learning for early warning signals of tipping points,” Proc. Natl. Acad. Sci. USA, "
    "vol. 118, no. 39, 2021.",
    "T. M. Lenton et al., “A resilience sensing system for the biosphere,” Phil. Trans. R. Soc. B, vol. 377, "
    "2022.",
    "D. Phiri et al., “Sentinel 2 data for land cover/use mapping: A review,” Remote Sens., vol. 12, no. 14, "
    "2020.",
    "L. Grinsztajn, E. Oyallon and G. Varoquaux, “Why do tree based models still outperform deep learning on typical "
    "tabular data?” in Proc. NeurIPS Datasets and Benchmarks Track, vol. 35, 2022.",
    "T. Silva Filho et al., “Classifier calibration: A survey on how to assess and improve predicted class "
    "probabilities,” Mach. Learn., vol. 112, no. 9, 2023.",
    "V. Vovk, A. Gammerman and G. Shafer, Algorithmic Learning in a Random World, 2nd ed. Cham, Switzerland: Springer, 2022.",
    "S. M. Lundberg et al., “From local explanations to global understanding with explainable AI for trees,” "
    "Nature Mach. Intell., vol. 2, no. 1, 2020.",
    "D. Valle, R. Izbicki and R. V. Leite, “Quantifying uncertainty in land use land cover classification using "
    "conformal statistics,” Remote Sens. Environ., vol. 295, 2023.",
    "C. F. Brown et al., “Dynamic World, near real time global 10 m land use land cover mapping,” Sci. Data, "
    "vol. 9, 2022.",
]
for i, r in enumerate(refs, 1):
    p = para(f"[{i}] {r}", size=9.5, after=3)

# footer page numbers
fp = sec.footer.paragraphs[0]; fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = fp.add_run(); f1 = OxmlElement("w:fldChar"); f1.set(qn("w:fldCharType"), "begin")
it = OxmlElement("w:instrText"); it.text = "PAGE"; f2 = OxmlElement("w:fldChar"); f2.set(qn("w:fldCharType"), "end")
run._r.extend([f1, it, f2]); run.font.size = Pt(9)

bad = [s for s in WRITTEN if re.search("[-‐‑‒–—―−]", s)]
assert not bad, bad
doc.save(OUT)
print("saved", OUT, "figures", FIGN[0], "tables", TABN[0])
