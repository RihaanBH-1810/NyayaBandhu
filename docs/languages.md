# Languages and text encoding

How a bilingual gazette is separated into one language, what happens to the
other language, and what the parser does when the source text cannot be
trusted.

Implemented in `akn_parser/language.py`, `akn_parser/extract.py` and
`akn_parser/transliterate.py`.

## Background

A Karnataka gazette carries each Act twice: the Kannada text as enacted, and
an English translation published under Article 348(3) of the Constitution. The
two are usually on separate pages, but the notification and colophon pages mix
them within a single sentence.

The Kannada appears in two different encodings, which is why the languages
cannot be separated by inspecting bytes:

| Encoding | What the PDF yields | Example |
| --- | --- | --- |
| Unicode Kannada | Codepoints in U+0C80–U+0CFF | `ಕರ್ನಾಟಕ ರಾಜ್ಯ` |
| Legacy ASCII-mapped (Nudi, Baraha, BRH families) | Latin-1 bytes; only the font renders them as Kannada | `PÀ£ÁðlPÀ gÁdå` |
| English | Latin text in a Latin font | `Karnataka State` |

Filtering on codepoint alone fails in both directions: it discards real
Kannada and retains legacy Kannada as though it were English.

## Span classification

`classify_span_detail(text, font)` returns `(language, encoding)` for one PDF
text span, using both the codepoints and the font name the PDF reports.

| Test | Result |
| --- | --- |
| Contains a character in the Kannada block | `(kan, unicode)` |
| Contains Latin letters and the font name matches a legacy Kannada family | `(kan, legacy)` |
| Contains Latin letters, more than 25% of which are accented | `(kan, legacy)` |
| Contains Latin letters | `(eng, unicode)` |
| Contains no letters | `(neutral, "")` |

The third test is a fallback for PDFs that do not report usable font names:
legacy Kannada is dense in Latin-1 accented characters that English legal
prose does not use.

Font families recognised as legacy Kannada: `nudi`, `baraha`, `brh*`,
`shreelipi`, `akshar`, `kannada`, `kailasam`, `sampige`, `nadanika`, `kedage`,
`malige`. The pattern is `_LEGACY_KANNADA_FONTS` in `akn_parser/language.py`.

Script-neutral spans — digits, punctuation, whitespace — are kept whichever
language is requested. A page number set in a Kannada font does not drag the
line out of the English text.

## Page selection

After spans are filtered, a page is kept when both hold:

- it has at least 200 letters of the target language, and
- those letters are at least 55% of its letters.

Gaps inside the resulting run of pages are then re-admitted, so that a
table-heavy page in the middle of an Act — which can fall below the letter
threshold — is not dropped.

```
    pages          : 10-19 of 19
```

Thresholds are constructor arguments on `TextExtractor`
(`min_page_letters`, `min_page_ratio`).

## Text in the other language

Text in the language that was not requested is **preserved, not deleted**.
Most of it is not noise: in these gazettes the runs of Kannada inside the
English pages are the Act's own title, quoted in the notification and in the
closing publication formula.

Each run is emitted as a `<span>` carrying an `xml:lang` tag that states both
the language and the state of its codepoints:

```xml
<p eId="preface__p_1">Ordered that the translation of
  <span eId="preface__p_1__span_1" xml:lang="kn-Latn-x-nudi"
    >PÀ£ÁðlPÀ gÁdå ¹«¯ï ¸ÉÃªÉUÀ¼ÀÄ (²PÀëPÀgÀ ªÀUÁðªÀuÉ ¤AiÀÄAvÀæt) «zsÉÃAiÀÄPÀ, 2020</span>
  in the English language, be published as authorised by the Governor of
  Karnataka under clause (3) of Article 348 …</p>
```

### The tags

| Tag | Meaning |
| --- | --- |
| `kn` | Kannada, in Kannada codepoints |
| `kn-Latn-x-nudi` | Kannada, stored as Latin-1 bytes for a Nudi-family font — needs transliteration |
| `kn-x-misencoded` | Kannada codepoints, but a measurable share of them belong to unrelated Unicode blocks — needs repair |

These are BCP-47 tags. `kn-Latn-x-nudi` reads as: the Kannada language, written
in the Latin script, in the private-use `nudi` encoding. A consumer can
therefore tell converted text from unconverted text without inspecting the
characters, and a converter can find every run that still needs work with a
single XPath:

```xpath
//*[starts-with(@xml:lang, 'kn-Latn')]
```

`kn` asserts that the codepoints are in the Kannada block. It does not assert
that the text is orthographically correct: the `kn-x-misencoded` test detects
codepoints in the wrong *block*, not glyphs in the wrong *order*.

### Policies

`--foreign` selects what happens to these runs:

| Value | Behaviour |
| --- | --- |
| `tag` (default) | Keep the text, tagged with `xml:lang` as above |
| `mark` | Replace each run with an Akoma Ntoso `<omissis/>` marker |
| `omit` | Remove silently |
| `keep` | Leave the text in place with no tag |

`mark` is appropriate where carrying unconverted bytes in a published document
is unacceptable; the omission is still recorded in the XML rather than leaving
a hole in the sentence. `keep` is a diagnostic aid — it produces documents
that fail the untagged-script check and should not be published.

Adjacent runs of the same language and encoding are merged into one element,
including across a line break, so a title that wrapped in the gazette becomes
a single `<span>` rather than two.

### The enacting-language title

The notification names the Act in Kannada before saying that a translation is
being published. Because that run is the Act's own name rather than incidental
foreign text, it is also lifted into the metadata as a Work-level alias:

```xml
<FRBRWork>
  <FRBRalias name="title" value="THE KARNATAKA STATE CIVIL SERVICES … ACT, 2020"/>
  <FRBRalias name="title" xml:lang="kn-Latn-x-nudi"
             value="PÀ£ÁðlPÀ gÁdå ¹«¯ï ¸ÉÃªÉUÀ¼ÀÄ …"/>
</FRBRWork>
```

It is a **Work**-level alias because it names the Work, which is the same
Work the English expression belongs to — not a property of the English
expression alone.

## Transliteration

`akn_parser/transliterate.py` defines the interface for converting legacy
encodings to Unicode. **No converter ships with the parser.**

Converting Nudi to Unicode is a real transformation, not a byte substitution:
it needs a glyph table plus reordering rules for dependent vowels, vattakshara
and legacy symbol combinations. A table that has not been checked by someone
who reads Kannada would be worse than none, because it would turn a visibly
broken document into an invisibly wrong one.

Registering a converter converts every legacy run in every document on the
next run, and the tags change from `kn-Latn-x-nudi` to `kn` automatically:

```python
from akn_parser import transliterate

def nudi_to_unicode(text: str) -> str:
    ...

transliterate.register("kan", "nudi", nudi_to_unicode)
```

Contract:

- A converter is a pure function of its input.
- It returns Unicode text in the target script.
- It raises, or returns `None`, if it cannot convert the input. It must never
  return a partial result — the parser keeps the original text and its legacy
  tag rather than accepting half a conversion.

Existing implementations that could be adapted, subject to a licence check:

| Project | Language |
| --- | --- |
| [`aravindavk/ascii2unicode`](https://github.com/aravindavk/ascii2unicode) | Python 3, Nudi and Baraha |
| [`looped-labs/asciikannada2unicode`](https://github.com/looped-labs/asciikannada2unicode) | Java |
| [Sanka](https://aravindavk.in/sanka/) | Browser tool |

None is published on PyPI, so integration means vendoring or reimplementation.

## Encoding checks

Two conditions cause extraction to stop with `UnusableEncodingError` rather
than emit text. Both would otherwise produce a document that is valid Akoma
Ntoso and unreliable as law.

### Legacy-font text

Raised when at least 50% of the **target-language** letters come from spans in
a legacy ASCII-mapped font. Note the asymmetry with the section above: legacy
runs in the *other* language are tagged and kept, because they are quoted
fragments; a document whose *requested* language is mostly legacy-encoded has
no usable text at all.

### Misencoded glyphs

Raised for Kannada when at least 5% of the characters that should be Kannada
came out in unrelated Unicode blocks — chiefly General Punctuation (`⁏`, `⁄`,
`⁋`). This indicates that the embedded font's `ToUnicode` map is wrong or
incomplete.

`misencoded_share(text, script_range)` measures this: it counts characters in
the script's own block against characters in U+2000–U+2BFF that are not
legitimate typography (dashes, quotation marks, ellipsis, bullet, prime,
rupee sign, numero sign are allowed). The same measure, applied per run,
produces the `kn-x-misencoded` tag.

## Kannada support

Kannada extraction is not supported. `--lang kan` on the sample gazettes stops
with a diagnostic:

```
FAILED: UnusableEncodingError: tranfer_of_teachers.pdf: 14% of the Kannada
characters came out as unrelated codepoints (mostly General Punctuation), which
means the font's ToUnicode map is wrong or incomplete. Roughly one letter in 7
would be incorrect. …
```

The two encoding problems are separate and affect different pages:

| Pages | Problem | Fix |
| --- | --- | --- |
| English pages (Kannada quotations) | Legacy Nudi encoding | A registered transliterator |
| Kannada pages (the enacted text) | Broken `ToUnicode` map | OCR or per-font glyph repair |

A transliterator therefore recovers the Kannada titles on the English pages
but does **not** unblock `--lang kan`.

Supporting Kannada fully also needs structural rules: the patterns in
`akn_parser/normalize.py` and `akn_parser/structure.py` match English keywords
(`Provided that`, `Explanation`, `CHAPTER`) and Latin enumerators. Two-column
page handling would need attention too, since the Kannada pages are set in two
columns.

## How other jurisdictions model this

Worth knowing, because it constrains what the right answer is.

Every mature multilingual legal-XML programme models **each language as a
separate Expression of the same Work**, never as parallel text inside one
document:

- **AKN4UN** gives each language its own Expression IRI —
  `…/A-RES-66-1/eng@2013-12-12`, `…/fra@2013-12-12`.
- **Laws.Africa / Indigo** treats a Work as issued in multiple languages, one
  expression each.
- **AKN4EU** keeps the XML tree of each linguistic version structurally
  identical across all 24 languages.

That is already this parser's model: `--lang` selects which expression to
emit, and the Kannada expression would be `…/kan@2020-03-27`, a separate
document.

Inline `xml:lang` is for *incidental* foreign text — a quoted name or term
inside a sentence — which is exactly what the Kannada title in an English
notification is. It is not a way to carry parallel translations.

Akoma Ntoso does define a `mul` language code for genuinely mixed documents
(`/akn/mg/act/2003-03-12/3/mul` in the naming convention's own examples), but
in practice it is used for records that code-switch mid-stream, such as
parliamentary debates, not for parallel translations.

### One difference that matters here

Canada, Switzerland, Belgium, Hong Kong and the EU apply the **equal
authenticity rule**: every language version is equally authentic and none is a
translation. India does not work that way for state legislation. Article
348(3) provides that where a State prescribes another language for its Acts, an
English translation published under the Governor's authority "shall be deemed
to be the authoritative text thereof in the English language".

Which text is the *master expression* for `wId` purposes therefore deserves a
legal opinion rather than a parser default. See
[identifiers.md](identifiers.md#wid).

## Reporting

```
    other language : 11 run(s) kept and tagged
```

Runs preserved with an `xml:lang` tag.

```
    UNTAGGED script: {'kan': 646}
```

Letters of another script that reached the output **without** a tag. This
should always be absent; it means span classification missed something,
usually a legacy font not in `_LEGACY_KANNADA_FONTS`. Text inside a tagged
element is not counted.
