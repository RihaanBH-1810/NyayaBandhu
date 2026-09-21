"""Local viewer for Akoma Ntoso documents produced by ``akn_parser``.

Not part of the conversion pipeline. Reads finished XML from ``out/`` (or
drives ``akn_parser`` to produce it on demand) and renders it for reading in
a browser: a section-by-section document view with clickable cross-references,
a collapsible outline, the raw XML, and the same validation report the CLI
prints. See ``docs/webui.md``.
"""
