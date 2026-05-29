/**
 * Patient Feedback Intelligence — curated metrics
 * Reddit CSV: merged_all_cleaned__*_only.csv
 * UOAA JSON: uoaa_*_results (2).json
 * Branded %: presentation slides 27/31
 * Hollister topics: Ostomy_submissions_Hollister_Unsupervised_Topics_2025-11-10.json
 */

const DATA = {
  reddit: {
    hollister: { n: 1345, positive: 48.85, neutral: 27.06, negative: 24.09 },
    coloplast: { n: 1360, positive: 56.69, neutral: 26.62, negative: 16.69 },
  },
  uoaa: {
    hollister: { n: 1210, positive: 45.3, neutral: 28.5, negative: 26.2 },
    coloplast: { n: 982, positive: 47.3, neutral: 23.8, negative: 28.9 },
  },
  presentationReddit: {
    hollister: { positive: 50.53, neutral: 26.12, negative: 23.35 },
    coloplast: { positive: 56.52, neutral: 26.84, negative: 16.64 },
  },
  // Negative-impact index by brand (top 6 attributes) — TODO: replace with CSV aspect counts
  topConcernsByBrand: {
    hollister: {
      labels: ["Adhesive", "Leakage", "Skin irritation", "Fit", "Wear time", "Odor control"],
      values: [92, 88, 75, 48, 42, 35],
    },
    coloplast: {
      labels: ["Leakage", "Adhesive", "Skin irritation", "Durability", "Fit", "Ease of use"],
      values: [85, 58, 55, 45, 38, 28],
    },
  },
  attributes: {
    labels: [
      "Leakage",
      "Adhesive",
      "Skin irritation",
      "Comfort",
      "Fit",
      "Wear time",
      "Odor control",
      "Ease of use",
      "Support",
      "Daily confidence",
    ],
    hollister: { positive: [22, 68, 38, 78, 72, 80, 85, 68, 75, 82], negative: [88, 92, 75, 28, 48, 42, 35, 30, 40, 25] },
    coloplast: { positive: [90, 72, 82, 80, 85, 70, 62, 78, 52, 78], negative: [85, 58, 55, 25, 38, 45, 32, 28, 35, 30] },
  },
  emotions: {
    labels: ["Frustration", "Relief", "Concern", "Satisfaction", "Discomfort"],
    hollister: [12, 18, 5, 35, 8],
    coloplast: [14, 16, 6, 34, 10],
  },
  hollister: {
    pos: ["Reliability & wear time", "Odor control (M9)", "Support & samples", "Comfort & fit"],
    neg: ["Adhesive / barrier issues", "Leakage & seal", "Skin irritation"],
    takeaway:
      "Negative experiences are commonly associated with adhesive performance and leakage; positive experiences frequently mention reliability, comfort, and odor control.",
  },
  coloplast: {
    pos: ["Leak prevention / seal", "Skin comfort", "Ease of use"],
    neg: ["Leaks & blowouts", "Pouch durability", "Adhesive irritation (select)"],
    takeaway:
      "Patients often praise seal performance and comfort; negative themes still include leaks and durability concerns for some users.",
  },
  opportunities: {
    hollister: {
      strengths: ["System reliability", "Pouch usability", "Odor control", "Support & samples"],
      pain: ["Adhesive failure", "Leakage", "Irritation in bags/wafers"],
      opp: ["Adhesive longevity", "Barrier resilience", "Movement performance"],
    },
    coloplast: {
      strengths: ["Skin comfort", "Seal narrative", "Higher Reddit positive share"],
      pain: ["Leak anxiety", "Durability", "UOAA polarization"],
      opp: ["Durability messaging", "Sensitive-skin guidance", "Maintain comfort positioning"],
    },
    shared: [
      "Reduce leakage and seal-related concerns",
      "Improve adhesive comfort and reliability",
      "Address skin irritation with clearer education",
      "Use recurring themes to guide product and support teams",
      "Maintain baseline tracking for future launches",
    ],
  },
};

const C = {
  pos: "#10b981",
  neu: "#94a3b8",
  neg: "#f97316",
  h: "#2563eb",
  c: "#7c3aed",
  teal: "#0d9488",
  grid: "rgba(15, 23, 42, 0.06)",
  text: "#64748b",
};

const charts = {};

Chart.defaults.font.family = "'Inter', system-ui, sans-serif";
Chart.defaults.font.size = 12;
Chart.defaults.color = C.text;

function weightedSentiment() {
  const parts = [
    [DATA.reddit.hollister, DATA.reddit.hollister.n],
    [DATA.reddit.coloplast, DATA.reddit.coloplast.n],
    [DATA.uoaa.hollister, DATA.uoaa.hollister.n],
    [DATA.uoaa.coloplast, DATA.uoaa.coloplast.n],
  ];
  let n = 0,
    p = 0,
    u = 0,
    neg = 0;
  parts.forEach(([d, count]) => {
    n += count;
    p += d.positive * count;
    u += d.neutral * count;
    neg += d.negative * count;
  });
  return [p / n, u / n, neg / n];
}

function kill(id) {
  charts[id]?.destroy();
  delete charts[id];
}

function donut(id, data, labels = ["Positive", "Neutral", "Negative"]) {
  kill(id);
  const el = document.getElementById(id);
  if (!el) return;
  charts[id] = new Chart(el, {
    type: "doughnut",
    data: {
      labels,
      datasets: [
        {
          data,
          backgroundColor: [C.pos, C.neu, C.neg],
          borderWidth: 0,
          hoverOffset: 6,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: "72%",
      plugins: {
        legend: { position: "bottom", labels: { boxWidth: 10, padding: 12, font: { size: 11 } } },
      },
    },
  });
}

function hbar(id, labels, values, color) {
  kill(id);
  const el = document.getElementById(id);
  if (!el) return;
  charts[id] = new Chart(el, {
    type: "bar",
    data: {
      labels,
      datasets: [{ data: values, backgroundColor: color, borderRadius: 6, barThickness: 14 }],
    },
    options: {
      indexAxis: "y",
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { beginAtZero: true, max: 100, grid: { color: C.grid }, ticks: { font: { size: 10 } } },
        y: { grid: { display: false }, ticks: { font: { size: 11 } } },
      },
    },
  });
}

function groupedBar(id, labels, ds) {
  kill(id);
  const el = document.getElementById(id);
  if (!el) return;
  charts[id] = new Chart(el, {
    type: "bar",
    data: { labels, datasets: ds },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { position: "top", labels: { boxWidth: 10, font: { size: 11 } } } },
      scales: {
        x: { grid: { display: false } },
        y: { beginAtZero: true, max: 70, grid: { color: C.grid } },
      },
    },
  });
}

function radar(id, labels, h, c) {
  kill(id);
  const el = document.getElementById(id);
  if (!el) return;
  charts[id] = new Chart(el, {
    type: "radar",
    data: {
      labels,
      datasets: [
        { label: "Hollister", data: h, borderColor: C.h, backgroundColor: "rgba(37,99,235,0.12)", borderWidth: 2, pointRadius: 2 },
        { label: "Coloplast", data: c, borderColor: C.c, backgroundColor: "rgba(124,58,237,0.1)", borderWidth: 2, pointRadius: 2 },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: { r: { beginAtZero: true, max: 100, ticks: { stepSize: 25, font: { size: 9 } }, grid: { color: C.grid } } },
      plugins: { legend: { position: "top", labels: { boxWidth: 10 } } },
    },
  });
}

function formatPctBlock(d) {
  return `Positive ${d.positive.toFixed(1)}% · Neutral ${d.neutral.toFixed(1)}% · Negative ${d.negative.toFixed(1)}%`;
}

function renderVoicePctLabels() {
  const map = [
    ["pctHollisterReddit", DATA.reddit.hollister],
    ["pctColoplastReddit", DATA.reddit.coloplast],
    ["pctHollisterUoaa", DATA.uoaa.hollister],
    ["pctColoplastUoaa", DATA.uoaa.coloplast],
  ];
  map.forEach(([id, d]) => {
    const el = document.getElementById(id);
    if (el) el.textContent = formatPctBlock(d);
  });
}

function initVoiceCharts() {
  donut("voiceHollisterReddit", [
    DATA.reddit.hollister.positive,
    DATA.reddit.hollister.neutral,
    DATA.reddit.hollister.negative,
  ]);
  donut("voiceColoplastReddit", [
    DATA.reddit.coloplast.positive,
    DATA.reddit.coloplast.neutral,
    DATA.reddit.coloplast.negative,
  ]);
  donut("voiceHollisterUoaa", [
    DATA.uoaa.hollister.positive,
    DATA.uoaa.hollister.neutral,
    DATA.uoaa.hollister.negative,
  ]);
  donut("voiceColoplastUoaa", [
    DATA.uoaa.coloplast.positive,
    DATA.uoaa.coloplast.neutral,
    DATA.uoaa.coloplast.negative,
  ]);
  donut("voiceCombinedChart", weightedSentiment());

  const th = DATA.topConcernsByBrand.hollister;
  hbar("topConcernsHollisterChart", th.labels, th.values, C.h);
  const tc = DATA.topConcernsByBrand.coloplast;
  hbar("topConcernsColoplastChart", tc.labels, tc.values, C.c);

  renderVoicePctLabels();
}

function initCharts() {
  initVoiceCharts();

  const pr = DATA.presentationReddit;
  groupedBar("brandSentimentComparisonChart", ["Positive", "Neutral", "Negative"], [
    { label: "Hollister", data: [pr.hollister.positive, pr.hollister.neutral, pr.hollister.negative], backgroundColor: C.h, borderRadius: 6 },
    { label: "Coloplast", data: [pr.coloplast.positive, pr.coloplast.neutral, pr.coloplast.negative], backgroundColor: C.c, borderRadius: 6 },
  ]);

  const a = DATA.attributes;
  radar("attributeRadarChart", a.labels, a.hollister.positive, a.coloplast.positive);

  groupedBar("platformComparisonChart", ["Reddit", "UOAA"], [
    { label: "Hollister % positive", data: [DATA.reddit.hollister.positive, DATA.uoaa.hollister.positive], backgroundColor: C.h, borderRadius: 6 },
    { label: "Coloplast % positive", data: [DATA.reddit.coloplast.positive, DATA.uoaa.coloplast.positive], backgroundColor: C.c, borderRadius: 6 },
  ]);

  groupedBar("emotionChart", DATA.emotions.labels, [
    { label: "Hollister", data: DATA.emotions.hollister, backgroundColor: C.h, borderRadius: 6 },
    { label: "Coloplast", data: DATA.emotions.coloplast, backgroundColor: C.c, borderRadius: 6 },
  ]);

  const negH = a.hollister.negative;
  const negC = a.coloplast.negative;
  groupedBar("attributeImpactChart", a.labels, [
    { label: "Hollister negative impact", data: negH, backgroundColor: "rgba(249,115,22,0.8)", borderRadius: 4 },
    { label: "Coloplast negative impact", data: negC, backgroundColor: "rgba(124,58,237,0.75)", borderRadius: 4 },
  ]);

  donut("hollisterMiniChart", [DATA.reddit.hollister.positive, DATA.reddit.hollister.neutral, DATA.reddit.hollister.negative]);
  donut("coloplastMiniChart", [DATA.reddit.coloplast.positive, DATA.reddit.coloplast.neutral, DATA.reddit.coloplast.negative]);
}

function renderAttributeTags() {
  const el = document.getElementById("attributeTags");
  if (!el) return;
  const items = DATA.attributes.labels.map((label, i) => {
    const hn = DATA.attributes.hollister.negative[i];
    const hp = DATA.attributes.hollister.positive[i];
    let tag = "mixed";
    if (hn > 70 && hn > hp) tag = "negative";
    else if (hp > 70 && hp > hn) tag = "positive";
    return `<div class="attr-tag attr-tag--${tag}"><span class="attr-name">${label}</span><span class="attr-badge">${tag}</span></div>`;
  });
  el.innerHTML = items.join("");
}

function renderLists() {
  const fill = (id, items, cls) => {
    const el = document.getElementById(id);
    if (el) el.innerHTML = items.map((t) => `<li class="${cls}">${t}</li>`).join("");
  };
  fill("hPos", DATA.hollister.pos, "tag-pos");
  fill("hNeg", DATA.hollister.neg, "tag-neg");
  fill("cPos", DATA.coloplast.pos, "tag-pos");
  fill("cNeg", DATA.coloplast.neg, "tag-neg");
  ["hTake", "cTake"].forEach((id, i) => {
    const el = document.getElementById(id);
    if (el) el.textContent = i === 0 ? DATA.hollister.takeaway : DATA.coloplast.takeaway;
  });
  const opp = (pid, obj) => {
    const el = document.getElementById(pid);
    if (!el) return;
    el.innerHTML = `
      <div class="opp-col"><h4>Strengths</h4><ul>${obj.strengths.map((s) => `<li>${s}</li>`).join("")}</ul></div>
      <div class="opp-col opp-col--pain"><h4>Pain points</h4><ul>${obj.pain.map((s) => `<li>${s}</li>`).join("")}</ul></div>
      <div class="opp-col opp-col--opp"><h4>Opportunities</h4><ul>${obj.opp.map((s) => `<li>${s}</li>`).join("")}</ul></div>`;
  };
  opp("oppH", DATA.opportunities.hollister);
  opp("oppC", DATA.opportunities.coloplast);
  const sh = document.getElementById("oppShared");
  if (sh) sh.innerHTML = DATA.opportunities.shared.map((s) => `<li>${s}</li>`).join("");
}

function setupNav() {
  const nav = document.getElementById("topNav");
  const links = nav?.querySelectorAll("a[href^='#']");
  links?.forEach((a) => {
    a.addEventListener("click", (e) => {
      e.preventDefault();
      document.querySelector(a.getAttribute("href"))?.scrollIntoView({ behavior: "smooth" });
    });
  });
  const sections = document.querySelectorAll("section[id]");
  const obs = new IntersectionObserver(
    (entries) => {
      entries.forEach((en) => {
        if (en.isIntersecting) {
          links?.forEach((l) => l.classList.toggle("active", l.getAttribute("href") === `#${en.target.id}`));
        }
      });
    },
    { rootMargin: "-20% 0px -70% 0px" }
  );
  sections.forEach((s) => obs.observe(s));
}

document.addEventListener("DOMContentLoaded", () => {
  renderLists();
  renderAttributeTags();
  setupNav();
  initCharts();
});
