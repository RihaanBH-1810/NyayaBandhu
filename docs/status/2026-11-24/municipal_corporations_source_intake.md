# Municipal Corporations source intake

The supplied `karnataka_acts/BBMP/01 of 2022 (E) (14 of 1977).pdf` is the required **Karnataka Municipal Corporations Act, 1976 (Karnataka Act 14 of 1977)**. Its front matter explicitly lists amendments through Act 1 of 2022. It is an amended compilation, not the original 1977 Gazette.

The unchanged PDF has been added to `NyayaBandhu/data/acts/1977/ka-0014-1977/karnataka-municipal-corporations-act-1976__consolidated-through-act-0001-2022__eng.pdf` and indexed in `data/catalog.json`. Its SHA-256 checksum is `f4080d77d155cef0154bfb30670561c03323bcc4d24859ae1444ad72256d3dfc`. Act 37 of 2024 already links to this principal Act in the catalog. The uploaded original remains in brief.

**Conversion is blocked.** The existing parser confuses the arrangement of sections, inserted chapter labels, amendment footnotes, and bracketed statutory provisions with the operative hierarchy. An initial conversion fails with duplicate chapter IX identifiers. Experimental fixes revealed further duplicate sections and clauses, so those incomplete parser changes were not retained. No successful XML import or consolidated version is claimed.

The compilation also appends the Karnataka Municipal Corporations and Certain Other Law (Amendment) Act, 2021, Act 1 of 2022. Its section 3 introduces BBMP sections 240A–240C. This supplies evidence for a previously missing BBMP predecessor amendment, but that appended instrument has not yet been separately extracted, cataloged, or applied.

Next engineering work: support annotated compilations without merging editorial notes into statutory wording; separate appended instruments with original-page provenance; verify the principal text and the 2022 amendment independently before rerunning Act 37/2024 and the BBMP chain. The 2022 consolidation cannot be assumed to represent the historical text on every retrospective effective date.
