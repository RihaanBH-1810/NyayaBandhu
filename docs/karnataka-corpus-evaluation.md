# Karnataka corpus evaluation

This is a repeatable check of short Karnataka legislation against the English
PDF parser and the amendment intake workflow. The candidate list is in
[`scripts/karnataka_corpus.json`](../scripts/karnataka_corpus.json). Downloads,
XML and the JSON report go to the gitignored
`consolidation-data/karnataka-corpus-evaluation/` directory. No version is
approved by this script.

## Candidate documents

| Base Act | Official source | Reason for inclusion |
| --- | --- | --- |
| Shree Renuka Yellamma Kshetra Tourism Development Board Act, 2023 | [Karnataka Tourism PDF](https://karnatakatourism.org/department/wp-content/uploads/2025/01/Sri-Renuka-Yellamma-Tourism-Development-Board-Act-2023.pdf); [India Code fallback](https://www.indiacode.nic.in/bitstream/123456789/20169/1/05of2024renukayellamma%28e%29.pdf) | Short base Act with provisions and definitions |
| Karnataka Motor Transport and Other Allied Workers' Social Security and Welfare Act, 2024 | [India Code PDF](https://www.indiacode.nic.in/bitstream/123456789/20133/1/13of2024%28e%29motortransportworkers.pdf) | Short base Act with a different gazette layout |
| Karnataka Scheduled Castes Sub-Allocation and Tribal Sub-Allocation Act, 2013, compiled through 2017 | [India Code PDF](https://upload.indiacode.nic.in/showfile?actid=AC_KA_71_598_00008_65_1552031496775&filename=65of2013%28e%29.pdf&type=actfile) | About 28 sections; small base for an intake check with the 2023 amendment |
| Karnataka Religious Structures (Protection) Act, 2021 | [India Code PDF](https://www.indiacode.nic.in/bitstream/123456789/17227/1/42_of_2021%28e%29.pdf) | Compact Act with definitions and an overriding provision |
| Karnataka Tourism Ropeways Act, 2024 | [Karnataka Tourism PDF](https://karnatakatourism.org/department/wp-content/uploads/2025/01/karnataka-tourism-ropeway-act-2025.pdf); [India Code fallback](https://www.indiacode.nic.in/bitstream/123456789/21667/1/08of2025%28e%29tourismropeway.pdf) | Tests a different subject and nested definitions |
| Lakkundi Heritage Area Development Authority Act, 2020 | [India Code PDF](https://www.indiacode.nic.in/bitstream/123456789/17226/1/50_of_2020_%28e%29.pdf) | Authority Act with schedules and nested provisions |
| Basavanabagewadi Development Authority Act, 2024 | [India Code PDF](https://www.indiacode.nic.in/bitstream/123456789/21662/1/04of2025%28e%29basavanabagewadi.pdf) | Authority Act with a schedule and provisos |
| Karnataka Border Area Development Authority Act, 2010 | [India Code PDF](https://www.indiacode.nic.in/bitstream/123456789/7522/1/12of2010%28e%29.pdf) | Older gazette layout and schedule |
| Sarvajna Kshetra Development Authority Act, 2020 | [India Code PDF](https://www.indiacode.nic.in/bitstream/123456789/17242/1/38_of_2020_%28e%29.pdf) | Authority Act with heritage provisions |
| Karnataka State Public Records Act, 2010 | [India Code PDF](https://www.indiacode.nic.in/bitstream/123456789/7525/1/9of2011%28e%29.pdf) | Records subject matter and older layout |

| Amendment | Official source | Reason for inclusion |
| --- | --- | --- |
| Karnataka Scheduled Castes Sub-Allocation and Tribal Sub-Allocation (Amendment) Act, 2023, Act 6 of 2024 | [Karnataka Legislative Council Gazette PDF](https://kla.kar.nic.in/council/house/bills/151/g_9.pdf) | Short amendment affecting sections 3, 5 and 7 |
| Karnataka Gram Swaraj and Panchayat Raj (Amendment) Act, 2023, Act 1 of 2024 | [Karnataka Legislative Council Gazette PDF](https://kla.kar.nic.in/council/house/bills/151/g_11.pdf) | Short amendment with a text insertion and repeal/savings |

The Karnataka Tourism PDFs are department-hosted gazette scans with Kannada
and English pages. The evaluator tries them first and then the listed India
Code URLs. It records the URL used beside each downloaded PDF. A manually
downloaded PDF can also be placed at
`consolidation-data/karnataka-corpus-evaluation/sources/<case-id>.pdf` and
checked with `--offline`; its report source will say `locally supplied PDF`.
The PDF source and its printed Act number must be checked before a reviewer
registers any instrument. India Code may host updated compilations; the script
checks the title and validates generated XML, but it cannot certify that a base
PDF represents the original as-published version. The Scheduled Castes base is
explicitly a compilation through the 2017 amendment and also appends that
amending Act. Its use in the temporary CMS pair check is diagnostic only; a
reviewer must prepare a clean predecessor before legal consolidation. The
evaluator refuses a base PDF over 40 pages or an amendment PDF over 12 pages.

## Run

```bash
cd /home/liege/workspace/NyayaBandhu-workspace/NyayaBandhu
source .venv/bin/activate
export PYTHONPATH="$PWD/scripts"
python scripts/evaluate_karnataka_corpus.py
```

The script downloads PDFs, checks their file signature and expected title,
parses English AKN, runs XSD and identifier/reference/language checks, and
records pages, section count, runtime and SHA-256. For the Scheduled Castes pair
it also imports the parsed base and amendment into a temporary CMS store and
extracts candidate instructions if both parse. It does not accept instructions,
confirm commencement or produce an approved consolidated version. The JSON
report and generated XML remain under the isolated evaluation directory.

Use `--offline` to rerun only cached PDFs, or `--workdir PATH` to keep a separate
evaluation. An unsuccessful download leaves a per-document error in the report
and the command exits nonzero.

## Results in this workspace

On 4 November 2026, all twelve candidate PDF downloads failed with DNS resolution
errors, including both newly found Karnataka Tourism hosts. Neither `curl` nor
Python could resolve any external host from this container, and a direct IP
connection also failed. The saved report is at
`consolidation-data/karnataka-corpus-evaluation/report.json`. **There is no
parsing or stitching verdict for the twelve candidate documents yet.** The
ten base Acts have been identified from official sources, but their PDF page
counts and parser performance remain unverified. The 40-page limit will reject
any candidate that turns out to be too long.

The Tourism department links were found on its current [Acts, Rules and
Legislations page](https://karnatakatourism.org/en/businesses/acts-rules-legislations/).
India Code's former site now [announces migration](https://www.indiacode.nic.in/?pageid=38&search=Search)
to `indiacode.gov.in`; direct download behavior at the new host could not be
verified here. Search indexes still expose the older PDF links, but an indexed
result alone does not prove that a fresh download succeeds. A PRS India search
result for the Renuka Yellamma Act redirected to an unrelated Chhattisgarh PDF,
so it was not added as a fallback.

A 37-page gazette already in `data/v0s/kan_eng/` for the Chandraguthi Shree
Renukamba Kshetra Development Authority Act was parsed locally as a control:
XSD valid, 1,054 eIds, no reported schema errors or dangling references. It is
not counted among the ten new base Act candidates.

The evaluator was exercised against two existing local gazettes in a separate
temporary directory:

| Local control | Parse and validation | CMS intake |
| --- | --- | --- |
| Teachers base Act | 19 PDF pages; 20 sections; XSD valid; 412 eIds; 0.70 seconds | Existing base import also used by the amendment check |
| First Teachers amendment | 4 PDF pages; 3 sections; XSD valid; 119 eIds; 0.12 seconds | Base and amendment imported; 3 instruction candidates extracted |

These checks show that the evaluation path works with local files; they do not
measure accuracy on the twelve candidate documents. The earlier 264-page BBMP control
was removed from this corpus following the request for smaller sources.

## Review required after downloads succeed

1. Compare each generated XML with its PDF, especially document identity,
   provision numbering, language spans, quotations and references.
2. Confirm whether each base PDF is an as-published Act or a later compilation.
   A later compilation must not be used as an earlier predecessor expression.
3. For the Scheduled Castes pair, review every extracted instruction against
   the source Gazette PDF, prepare a clean predecessor expression,
   determine legal effective dates and sequence, bind targets, then run a full
   consolidation preview. Do not interpret candidate extraction as acceptance.
4. Record any parser or engine failure from `report.json` with the PDF hash and
   affected page/provision so it can be reproduced.
