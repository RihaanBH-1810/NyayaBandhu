# Viewer

A local browser viewer for the Akoma Ntoso XML this parser produces. It is not
part of the conversion pipeline: it reads finished documents from `out/`, or
runs `akn_parser` over a source PDF when asked to, and shows the result as
something a person can read.

For what the XML itself contains, see [akn-mapping.md](akn-mapping.md).

## Running it

```bash
.venv/Scripts/python webui/run.py
```

Then open `http://127.0.0.1:8000`. On macOS and Linux the interpreter is
`.venv/bin/python`.

The server runs until it is stopped with Ctrl+C. It does not reload itself;
after changing a `.py` file under `webui/`, restart it. Templates and static
files are read on every request and need only a browser refresh.

## The index page

Every `.xml` under `out/`, newest first, with its size and when it was
written.

Below the list, a form converts any PDF under `data/`. It uses the same
`ActParser` as the CLI and writes to the same place, `out/<type>/<lang>/`,
so converting a document here and converting it with `akn-parser.py -t` give
you one file, not two. The request blocks until conversion finishes. That
takes a couple of seconds for the Teachers Transfer Act and about half a
minute for the BBMP Act, and the form shows a progress note meanwhile. A
conversion that fails comes back to the index page with the error the CLI
would have printed after `FAILED:`.

## Reading a document

| Tab | Content |
| --- | --- |
| Document | The Act as continuous prose: headings, numbered provisions, tables. A citation that resolved to a provision is a link; following it scrolls to the target and briefly highlights it. |
| Outline | The provision hierarchy as a collapsible tree, as in [akn-mapping.md](akn-mapping.md#hierarchy). Selecting an entry opens it in Document. The filter box narrows the tree by number or heading, opening whichever chapters hold a match. |
| Raw XML | The file as written, syntax-coloured. Hidden while the split view is on, since the XML is already beside the text. |
| Metadata & validation | FRBR identity and URIs ([identifiers.md](identifiers.md)), and the schema, eId, reference and language checks from the CLI report ([cli.md](cli.md#output-report)). |

The Outline filter earns its place on long Acts. The BBMP Act's tree has 2,073
entries; `property tax` brings it down to the four sections about it.

Left and right arrow keys move between tabs.

### What the styling means

| Looks like | Is |
| --- | --- |
| Blue text, dotted underline | A citation that resolved to a provision in this document |
| Grey text, dotted underline | A citation of another component or instrument, left unlinked. Hover to see the target URI. |
| Bold, dotted underline | A defined term (`<def>`). Hover to see the `TLCTerm` it refers to. |
| Grey shading | Text in another language, kept and tagged. Hover to see its `xml:lang`. |
| Amber shading, dashed underline | The same, but still in a legacy font encoding: `kn-Latn-x-nudi` or `kn-x-misencoded` |
| *[omitted]* | Other-language text replaced by `<omissis/>` under `--foreign mark` |

The amber runs look like mojibake because they are. The bytes are Latin-1
codes that only a Nudi-family font draws as Kannada, and no converter ships
with the parser; see [languages.md](languages.md#transliteration). The viewer
marks them wherever they turn up: in the document body, in the page header
(where the Act's title in the enacting language is shown under the English
one) and in the Metadata tab.

## Split view

"Split with XML" is on by default. It puts the raw XML beside whichever tab is
open, so a provision can be read against its markup.

Clicking a paragraph, a section number or a table cell in the rendered
document scrolls the XML pane to that element and highlights its line. Clicking
a citation moves both panes to the cited provision, not to the sentence the
citation sits in, so the two sides stay on the same text. A click that ends a
text selection is ignored, so copying a passage does not move the XML pane.

The divider between the panes can be dragged anywhere from 15% to 85%. The
position is remembered in the browser's local storage; double-clicking the
divider puts it back to 50/50. On a window narrower than 1120px (the Codex
tablet breakpoint) the panes stack instead.

## How it is built

| File | Lines | Responsibility |
| --- | --- | --- |
| `app.py` | 188 | Routes, path checks, calling `ActParser` for the conversion form |
| `akn_view.py` | 410 | XML to HTML, the outline tree, metadata, validation |
| `run.py` | 11 | Starts uvicorn on port 8000 |
| `templates/` | 260 | Jinja2 pages: `base.html`, `index.html`, `view.html` |
| `static/app.js` | 267 | Tabs, split view, divider, outline filter, XML colouring |
| `static/style.css` | 388 | Layout and styling on Wikimedia Codex design tokens |

### Routes

| Route | Does |
| --- | --- |
| `GET /` | Index page. `?error=` shows a banner. |
| `POST /convert` | Converts `pdf` (relative to `data/`) with `doc_type`, `lang` and `foreign`, then redirects to `/view` |
| `GET /view?path=` | One document, `path` relative to `out/` |
| `GET /raw?path=` | The document's XML, fetched by the page for the Raw XML pane |

A `path` or `pdf` that resolves outside `out/` or `data/` is refused.

### Rendering

`akn_view.py` works from the finished XML, not from the parser's internal
`ActDocument`. It will therefore render any conformant Akoma Ntoso 3.0
document, including ones this repository did not produce. Every element that
has an `eId` keeps it as its HTML `id`, which is what makes `<ref href="#sec_7">`
work as an ordinary in-page link.

An element the renderer has no specific handling for is descended into rather
than dropped. Its text still appears, only without special styling.

### Validation

The Metadata tab's checks come from `akn_parser.validate.Validator`, the class
`ActParser.parse` uses. Nothing is re-implemented. There is one difference:
a document read back from disk has no `CitationResolver`, so the unresolved
citation count, which exists only during conversion, is not shown.

The `Validator` is built once per schema path and kept. Compiling the Akoma
Ntoso XSD took 0.16s, more than the rest of a page view put together, and
the schema does not change while the server runs. With it cached, the
Teachers Transfer Act opens in about 15ms instead of 220ms.

### The browser side

There is no JavaScript build step and nothing is loaded from a CDN.
`static/app.js` is served as written. It includes a short XML colouriser
rather than a highlighting library, since one `<pre>` block does not need one.
The Codex tokens at the top of `style.css` are copied from
`@wikimedia/codex-design-tokens` 2.7.0, and only the ones the page uses are
included.

The XML pane works out which line to scroll to by reading the `eId` off each
line of the file. That relies on every opening tag being on its own line,
which `render.serialise` guarantees by calling `etree.indent`.

## Requirements

The viewer's dependencies (`fastapi`, `uvicorn`, `jinja2`, `python-multipart`)
are listed under "Web UI" in `requirements.txt` and install with everything
else; see [README.md](../README.md#installation). Nothing under `scripts/`
imports them, so an installation that only needs the conversion pipeline can
leave them out.
