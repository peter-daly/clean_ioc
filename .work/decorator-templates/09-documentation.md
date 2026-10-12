# 09 — Standalone documentation and comprehension

Status: Accepted; all applicable gates passed, reader round2 20/20. Dependency: 08 accepted (`2ba08f2`).
Read the [workflow](README.md) and [documentation review protocol](documentation-review.md).
Implementation/review agents may read the feature contract; the fresh reader must not receive it.

| Role | Model | Reasoning |
| --- | --- | --- |
| Code search | gpt-6-luna | low |
| Implementation / documentation author | gpt-6-sol | high |
| Independent technical review | gpt-6-astra | high |
| Additional fresh documentation reader | gpt-6-luna | low |

Sol High is recommended for writing and validating examples against a settled API.
The fresh Luna reader is an additional agent, distinct from every agent previously used on the feature.

## Bounded outcome

Publish-ready standalone documentation teaches the implemented feature without any bark-core reference or adaptation.
A fresh reader must demonstrate understanding by answering a later quiz, not merely say the prose looks clear.

## Search assignment

Locate public docs structure, ordinary decorators, registration/generic/discovery guidance, component filters,
ProviderMapGroup docs, examples validator, exports and bundle protocol. Report documentation gaps from the public API.
Do not suggest bark-core examples or pass integration code as a writing reference.

## Implementation assignment

- Use independently invented examples, such as processing stages with configurable audit sinks. Define all example
  types locally and depend only on Clean IoC and the standard library where practical.
- Explain the template factory and source metadata, exact source binding, source_filter versus when, ServiceGroup
  identity/contributions, DerivedServices selection, generic projection, deferred discovery, lifecycle/ordering,
  overlays/boundaries, edits, errors, and supported limits.
- Include a small working example, a two-source example, and an explicit-group versus automatic-selection comparison.
  Explain that target declarations create neither handlers nor injectable provider maps.
- Update feature docs, relevant existing guides, public API references and changelog without publishing/releasing.
- Run examples through the repository's validator; ensure examples use implemented spellings rather than draft APIs.
- Keep internal task notes and bark-core evidence out of the public docs, examples, and any reader packet.

## Verification and review gate

First Astra High checks technical accuracy, scope, independent authorship, and executable examples.
Then follow the fresh-reader protocol: fresh Luna Low reads only the public documentation packet and reviews it;
only after that response, send the quiz to the same reader without answers or coaching.
Astra High grades against the implementation/contract, distinguishes documentation defects from reader mistakes,
and records evidence. Revise documentation for gaps and repeat with a NEW fresh reader after substantive revision.
No gate passes merely because the reader was taught the missing facts during review.

Store review/quiz evidence internally, separate from public docs and the isolated packet.
M09 requires both technical acceptance and a passing fresh-reader quiz before M10 starts.
