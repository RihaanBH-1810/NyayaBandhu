// Tab switching, outline navigation, split view, and raw-XML syntax colouring
// for the document viewer (webui/templates/view.html). No framework and no
// CDN dependency, in keeping with the parser's own no-network-access rule for
// anything that runs at conversion time. This only runs in the browser,
// but there is no reason to introduce a build step for a page this small.

const panels = document.getElementById("viewer-panels");
const splitToggle = document.getElementById("split-toggle");
const rawTabButton = document.getElementById("raw-tab-button");
const resizer = document.getElementById("split-resizer");
const tabButtons = [...document.querySelectorAll(".tab-button")];

const SPLIT_RESIZER_WIDTH = 10; // px; matches the middle grid track in style.css
const SPLIT_MIN_FRACTION = 0.15;
const SPLIT_MAX_FRACTION = 0.85;
const SPLIT_STORAGE_KEY = "nyayabandhu-split-fraction";

let rawXmlLoaded = false;
let rawXmlLoading = null;
let eidToLine = {};

// -- tabs ---------------------------------------------------------------

function activateTab(name) {
  tabButtons.forEach((btn) => {
    const isActive = btn.dataset.tab === name;
    btn.classList.toggle("active", isActive);
    btn.setAttribute("aria-selected", String(isActive));
    btn.tabIndex = isActive ? 0 : -1;
  });
  document.querySelectorAll(".tab-panel").forEach((panel) => {
    panel.dataset.active = panel.id === `tab-${name}` ? "true" : "false";
  });
  if (name === "raw" || splitToggle.checked) loadRawXml();
}

tabButtons.forEach((btn) => {
  btn.addEventListener("click", () => activateTab(btn.dataset.tab));
});

// Left/right arrows move between tabs, as the tablist role promises.
document.querySelector(".tabs").addEventListener("keydown", (event) => {
  const step = { ArrowLeft: -1, ArrowRight: 1 }[event.key];
  if (!step) return;
  const visible = tabButtons.filter((btn) => !btn.hidden);
  const current = visible.findIndex((btn) => btn.classList.contains("active"));
  const next = visible[(current + step + visible.length) % visible.length];
  activateTab(next.dataset.tab);
  next.focus();
  event.preventDefault();
});

// -- navigating to a provision ------------------------------------------

// Jumping is done here rather than by following the '#eid' href, because the
// target may be on a tab that is not open. Flashing the destination is the
// only confirmation the reader gets that the jump landed where they meant,
// so it stands in for the :target highlight an ordinary anchor would give.
function goToProvision(eid) {
  activateTab("document");
  const target = document.getElementById(eid);
  if (!target) return;
  target.scrollIntoView({ behavior: "smooth", block: "start" });
  document.querySelectorAll(".akn-landed").forEach((el) => el.classList.remove("akn-landed"));
  target.classList.add("akn-landed");
}

document.querySelectorAll(".outline-link").forEach((link) => {
  link.addEventListener("click", (event) => {
    event.preventDefault();
    goToProvision(link.dataset.eid);
  });
});

// One delegated listener rather than one per citation: a long Act has
// hundreds of them.
document.addEventListener("click", (event) => {
  const ref = event.target.closest(".akn-ref[href^='#']");
  if (!ref) return;
  event.preventDefault();
  goToProvision(ref.getAttribute("href").slice(1));
});

// -- outline filter ------------------------------------------------------

const outlineFilter = document.getElementById("outline-filter");

if (outlineFilter) {
  outlineFilter.addEventListener("input", () => {
    const needle = outlineFilter.value.trim().toLowerCase();
    const items = document.querySelectorAll("#outline li");
    let matches = 0;

    items.forEach((li) => {
      const link = li.querySelector(":scope > a, :scope > details > summary > a");
      const text = link ? link.textContent.toLowerCase() : "";
      const hit = needle !== "" && text.includes(needle);
      li.dataset.hit = hit ? "true" : "false";
      if (hit) matches += 1;
    });

    // A match is only useful if it can be seen, so show every ancestor of a
    // hit and open the <details> that would otherwise hide it.
    items.forEach((li) => {
      const hasHit = li.dataset.hit === "true" || li.querySelector('[data-hit="true"]');
      li.hidden = needle !== "" && !hasHit;
      const details = li.querySelector(":scope > details");
      if (details && needle !== "") details.open = Boolean(hasHit);
    });

    document.getElementById("outline-empty").hidden = needle === "" || matches > 0;
  });
}

// -- split view ----------------------------------------------------------
// Document/Outline/Metadata on the left, raw XML pinned on the right.
// Toggled by the checkbox in the tab bar rather than a fifth tab, since the
// point is to see two panes at once. Defaults on (see view.html).

function setSplitMode(on) {
  panels.classList.toggle("split-mode", on);
  rawTabButton.hidden = on;
  if (on) {
    if (document.querySelector('.tab-panel[data-active="true"]').id === "tab-raw") {
      activateTab("document");
    }
    loadRawXml();
  }
}

splitToggle.addEventListener("change", () => setSplitMode(splitToggle.checked));
setSplitMode(splitToggle.checked);

// -- adjustable divider --------------------------------------------------
// Drag the bar between the panes to change their share of the width. Held
// as a fraction rather than a pixel width so it still means the same thing
// after the window is resized.

let splitFraction = 0.5;
let dragging = false;

// Ignores anything not a real number: a container with no measurable width
// (hidden pane, minimised window) would otherwise divide by zero and put a
// NaN into both the grid template and localStorage, where it would persist.
function applySplitFraction(fraction) {
  if (!Number.isFinite(fraction)) return;
  splitFraction = Math.min(SPLIT_MAX_FRACTION, Math.max(SPLIT_MIN_FRACTION, fraction));
  const half = SPLIT_RESIZER_WIDTH / 2;
  panels.style.gridTemplateColumns =
    `calc(${splitFraction * 100}% - ${half}px) ${SPLIT_RESIZER_WIDTH}px ` +
    `calc(${(1 - splitFraction) * 100}% - ${half}px)`;
}

applySplitFraction(parseFloat(localStorage.getItem(SPLIT_STORAGE_KEY)));

resizer.addEventListener("mousedown", (event) => {
  dragging = true;
  resizer.classList.add("dragging");
  document.body.style.userSelect = "none";
  event.preventDefault();
});

window.addEventListener("mousemove", (event) => {
  if (!dragging) return;
  const rect = panels.getBoundingClientRect();
  if (!rect.width) return;
  applySplitFraction((event.clientX - rect.left) / rect.width);
});

window.addEventListener("mouseup", () => {
  if (!dragging) return;
  dragging = false;
  resizer.classList.remove("dragging");
  document.body.style.userSelect = "";
  localStorage.setItem(SPLIT_STORAGE_KEY, splitFraction);
});

resizer.addEventListener("dblclick", () => {
  panels.style.gridTemplateColumns = "";
  splitFraction = 0.5;
  localStorage.removeItem(SPLIT_STORAGE_KEY);
});

// -- keeping the two panes on the same provision -------------------------

// Clicking anything in the rendered document (a paragraph, a section
// number, a table cell) locates the nearest element with an eId in the
// XML pane and scrolls it into view there. A citation link is handled by
// the delegated handler above, which sends the *target's* eId here, so both
// panes land on the same provision. Skipped mid-selection, so dragging to
// copy text is never hijacked.
document.addEventListener("click", (event) => {
  if (!panels.classList.contains("split-mode")) return;
  if (window.getSelection().toString()) return;
  if (!event.target.closest(".akn-document")) return;

  const ref = event.target.closest(".akn-ref[href^='#']");
  if (ref) {
    locateInXml(ref.getAttribute("href").slice(1));
    return;
  }
  const owner = event.target.closest("[data-eid]");
  if (owner && owner.dataset.eid) locateInXml(owner.dataset.eid);
});

function loadRawXml() {
  if (rawXmlLoaded) return Promise.resolve();
  if (rawXmlLoading) return rawXmlLoading;
  const pre = document.getElementById("raw-xml");
  if (!pre) return Promise.resolve();

  rawXmlLoading = fetch(pre.dataset.src)
    .then((response) => response.text())
    .then((text) => {
      const lines = text.split("\n");
      const highlightedLines = highlightXml(text).split("\n");
      eidToLine = {};
      pre.innerHTML = lines
        .map((line, index) => {
          const match = line.match(/eId="([^"]+)"/);
          if (match) eidToLine[match[1]] = index;
          return `<span class="xml-line" id="xml-line-${index}">${highlightedLines[index] ?? ""}</span>`;
        })
        .join("\n");
      rawXmlLoaded = true;
    })
    .catch(() => {
      pre.textContent = "Could not load the XML for this document.";
    });
  return rawXmlLoading;
}

function locateInXml(eid) {
  loadRawXml().then(() => {
    const index = eidToLine[eid];
    if (index === undefined) return;
    const line = document.getElementById(`xml-line-${index}`);
    if (!line) return;
    document.querySelectorAll(".xml-line.located").forEach((el) => el.classList.remove("located"));
    line.classList.add("located");
    line.scrollIntoView({ behavior: "smooth", block: "center" });
  });
}

// Minimal XML colouriser: enough to tell tags, attributes and values apart
// at a glance without pulling in a highlighting library for one <pre> block.
// Safe to run line-by-line because every generated document is indented with
// etree.indent, which puts one element's opening tag per line.
function highlightXml(source) {
  const escaped = source
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");

  return escaped
    .replace(/(&lt;!--[\s\S]*?--&gt;)/g, '<span class="xml-comment">$1</span>')
    .replace(
      /(&lt;\/?[\w:.-]+)((?:\s+[\w:.-]+="[^"]*")*)(\s*\/?&gt;)/g,
      (whole, open, attrs, close) => {
        const coloured = attrs.replace(
          /([\w:.-]+)(=)("[^"]*")/g,
          '<span class="xml-attr">$1</span>$2<span class="xml-value">$3</span>'
        );
        return `<span class="xml-tag">${open}</span>${coloured}<span class="xml-tag">${close}</span>`;
      }
    );
}
