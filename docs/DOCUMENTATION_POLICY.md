# Documentation policy

[English](DOCUMENTATION_POLICY.md) | [Español](DOCUMENTATION_POLICY-es.md)

Project documentation uses English as its primary language. Every project-owned Markdown document has a complete Spanish counterpart beside it: `NAME.md` and `NAME-es.md`. Both variants describe the same behavior, evidence and limitations.

Update both files in the same change. Translate headings, paragraphs, lists, table descriptions and link labels. Link to the corresponding language when the target has both variants, and keep a language switch near the beginning of each document.

Keep commands, code examples, paths, filenames, identifiers, API names, hashes and recorded output unchanged. Existing filenames remain stable even when they contain Spanish words, because scripts and historical references may depend on them.

Historical logs, JSON reports, manifests, archived evidence, upstream documentation and authoritative license texts retain their original content. Translate the project explanation around them rather than rewriting the evidence itself. Documentation translation does not change the validation status of a build.

The initial bilingual conversion uses local translation models with structural checks. Technical meaning still requires editorial review when a document is revised; automatic checks cannot establish translation accuracy.

Check the pairs and their navigation links from the repository root:

```sh
python3 tools/check-docs-bilingual.py
```
