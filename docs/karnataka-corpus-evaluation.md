# Karnataka corpus evaluation

This is a repeatable check of additional Karnataka legislation against the
English PDF parser and the amendment intake workflow. The candidate list is in
[`scripts/karnataka_corpus.json`](../scripts/karnataka_corpus.json). Downloads,
XML and the JSON report go to the gitignored
`consolidation-data/karnataka-corpus-evaluation/` directory. No version is
approved by this script.

## Candidate documents

| Document | Official source | Why it was selected |
| --- | --- | --- |
| Shree Renuka Yellamma Kshetra Tourism Development Board Act, 2023 | [India Code PDF](https://www.indiacode.nic.in/bitstream/123456789/20169/1/05of2024renukayellamma%28e%29.pdf) | New base Act with provisions and definitions |
| Karnataka Motor Transport and Other Allied Workers' Social Security and Welfare Act, 2024 | [India Code PDF](https://www.indiacode.nic.in/bitstream/123456789/20133/1/13of2024%28e%29motortransportworkers.pdf) | New base Act with a different gazette layout |
| Bruhat Bengaluru Mahanagara Palike (Amendment) Act, 2024 | [BBMP-hosted Gazette PDF](https://site.bbmp.gov.in/PDF/BBMP%20Amendment%20Act%202024%20-%20Notification.pdf) | Amendments to the BBMP base Act already in this repository; includes omissions, insertion and substitution |
| Karnataka Gram Swaraj and Panchayat Raj (Amendment) Act, 2023, published as Act 1 of 2024 | [Karnataka Legislative Council Gazette PDF](https://kla.kar.nic.in/council/house/bills/151/g_11.pdf) | Short amendment with a text insertion and repeal/savings |

The PDF source and its printed Act number must be checked before a reviewer
registers any instrument. India Code may host updated compilations; the script
checks the title and validates generated XML, but it cannot certify that a base
PDF represents the original as-published version. The BBMP amendment is linked
to the repository's existing base only for an isolated import and extraction
smoke test. It is not automatically stitched or approved.

## Run

```bash
cd /home/liege/workspace/NyayaBandhu-workspace/NyayaBandhu
source .venv/bin/activate
export PYTHONPATH="$PWD/scripts"
python scripts/evaluate_karnataka_corpus.py
```

The script downloads PDFs, checks their file signature and expected title,
parses English AKN, runs XSD and identifier/reference/language checks, and
records pages, section count, runtime and SHA-256. For the BBMP amendment it
then imports the existing BBMP base and the new amendment into a temporary CMS
store and extracts candidate instructions. It does not accept instructions,
confirm commencement or produce an approved consolidated version. The JSON
report and generated XML remain under the isolated evaluation directory.

Use `--offline` to rerun only cached PDFs, or `--workdir PATH` to keep a separate
evaluation. An unsuccessful download leaves a per-document error in the report
and the command exits nonzero.

## Results in this workspace

On 4 November 2026, all four new PDF downloads failed with DNS resolution
errors. Neither `curl` nor Python could resolve the government/India Code hosts
from this container. The saved report is at
`consolidation-data/karnataka-corpus-evaluation/report.json`. **There is no
parsing or stitching verdict for the four new documents yet.**

The evaluator was exercised against three existing local gazettes in a separate
temporary directory:

| Local control | Parse and validation | CMS intake |
| --- | --- | --- |
| Teachers base Act | 19 PDF pages; 20 sections; XSD valid; 412 eIds; 0.70 seconds | Existing base import also used by the amendment check |
| First Teachers amendment | 4 PDF pages; 3 sections; XSD valid; 119 eIds; 0.12 seconds | Base and amendment imported; 3 instruction candidates extracted |
| BBMP base Act | 264 PDF pages, English starts on PDF page 139; 376 parsed sections; XSD valid; 6,308 eIds; 10.58 seconds | Existing BBMP base XML/PDF imported successfully; no new amendment PDF was available locally |

The BBMP base XML and PDF also imported successfully into a temporary CMS
store. These checks show that the evaluation path works with local files; they
do not measure accuracy on the four new documents.
The BBMP parse reported 10 unresolved citation warnings despite passing the
validation gate. Its provision count and wording still need comparison with
the Gazette before use as a legal text.

## Review required after downloads succeed

1. Compare each generated XML with its PDF, especially document identity,
   provision numbering, language spans, quotations and references.
2. Confirm whether each base PDF is an as-published Act or a later compilation.
   A later compilation must not be used as an earlier predecessor expression.
3. For BBMP, review every extracted instruction against the source Gazette PDF,
   determine legal effective dates and sequence, bind targets, then run a full
   consolidation preview. Do not interpret candidate extraction as acceptance.
4. Record any parser or engine failure from `report.json` with the PDF hash and
   affected page/provision so it can be reproduced.
