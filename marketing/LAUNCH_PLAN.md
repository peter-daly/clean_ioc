# Clean IoC launch plan

## The diagnosis

The repository has had a discovery and positioning problem more than a capability problem. Its most distinctive features—context-aware resolution, generic handler discovery, decorator pipelines, ownership-aware scopes, and agent guidance—were buried behind a README that opened with “simple dependency injection” and four long registration examples.

That language put Clean IoC into the busiest, least differentiated part of the category. It gave a visitor no urgent reason to replace manual wiring, framework-native dependencies, or a tiny service registry.

## The category sentence

> Clean IoC is the Python dependency-injection container that can prove and explain its object graph before the application starts.

Use this sentence consistently for the release, repository About text, article, and launch posts. The supporting story is:

1. application code remains ordinary typed Python;
2. `validate()` catches broken and unsafe wiring without creating resources;
3. `explain()` turns the architecture into reviewable text or Mermaid;
4. scopes, async cleanup, contextual filters, and generics handle the systems where a container actually earns its keep.

## Ideal first adopters

Do not market to “all Python developers.” Start with maintainers who already feel composition pain:

- FastAPI teams using Clean Architecture or hexagonal boundaries;
- CQRS/event-driven systems with typed handler families;
- applications with request/job scopes plus long-lived clients and pools;
- libraries or products that must keep domain code portable across entry points;
- senior engineers reviewing or untangling deep dependency graphs.

The anti-audience is equally useful: tiny scripts and shallow, stable object graphs should keep manual wiring.

## The 20-second demo

Every launch asset should show the same loop:

```python
container.register(OrderRepository, SqlOrderRepository, lifespan=Lifespan.scoped)
container.register(CreateOrder, lifespan=Lifespan.singleton)
container.validate(CreateOrder)
```

```text
[captive-dependency] Singleton CreateOrder cannot depend on scoped OrderRepository
(CreateOrder -> OrderRepository)
```

Then change `CreateOrder` to `once_per_graph`, rerun validation, and print:

```python
print(container.explain(CreateOrder).to_text())
```

The visual arc is “hidden production bug → precise startup failure → reviewable architecture.” It demonstrates a result rather than narrating features.

## Release sequence

### Before publishing

- Review the complete local diff and merge it without squashing away the feature story.
- Apply the About description, website, topics, and social preview from `.github/REPOSITORY_PROFILE.md`.
- Enable GitHub Discussions and pin the adopter question in that file.
- Confirm the documentation deployment and v1.25.0 release workflow in a pull request.
- Record the 20-second validation demo as a small GIF for the README and launch posts.

### Launch day

1. Publish v1.25.0 and verify the GitHub Release, PyPI page, and docs.
2. Post the technical launch to r/Python and the Python Discourse “Showcase” area, adapting the prepared copy rather than cross-posting identical text.
3. Post the short version on LinkedIn, Mastodon/X, and internal alumni networks.
4. Share directly with 5–10 maintainers of architecture-heavy Python projects where the graph-validation idea is genuinely relevant. Ask for critique, not stars.
5. Reply to every substantive question with a runnable example or documentation improvement.

### Following four weeks

| Week | Asset | Purpose |
| --- | --- | --- |
| 1 | “The dependency bug that only appears on the cold path” article | Teach the validation problem |
| 2 | FastAPI Clean Architecture walkthrough | Reach the strongest integration audience |
| 3 | CQRS generic handler + decorator example | Demonstrate the niche depth |
| 4 | “What our DI container can and cannot prove statically” | Build technical credibility |

Each piece should link to one focused docs page, not just the repository home.

## Distribution rules

- Lead with a bug or architecture decision, never “I made a DI library.”
- Show complete, copyable code before listing capabilities.
- Say when manual wiring is the better option; credibility is more valuable than total-addressable-market language.
- Avoid download/stars begging in technical communities. Ask for graph examples that validation should handle.
- Turn every repeated question into a docs section or runnable example.
- Submit focused talks to Python/FastAPI meetups: “Proving dependency graphs before startup” is a talk; “Introducing Clean IoC” is an advert.

## Success measures

For the first 30 days, measure whether the positioning attracts real users:

- 50 non-coworker stars;
- 5 substantive issues, discussions, or external examples;
- 2 maintainers reporting a trial in a real application;
- documentation traffic landing directly on validation, FastAPI, or generics pages;
- at least one external comparison, article, or sample repository.

Stars are the discovery signal, not the product outcome. The strongest metric is an unfamiliar maintainer describing the problem Clean IoC solved in their own words.

## Next feature bets—only after feedback

Do not immediately expand the API. First observe what adopters ask the validator to model. Likely candidates are:

- a CLI that imports a composition-root function and writes Mermaid/JSON in CI;
- first-class framework adapters beyond FastAPI;
- machine-readable plan serialization for architecture tooling;
- richer source locations in validation issues;
- an opt-in strict mode for opaque custom value providers.

Choose the next feature based on repeated graph-validation use cases. The new positioning is strongest when additions deepen proof and observability rather than widening into a general application framework.
