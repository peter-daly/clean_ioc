# Filter documentation comprehension check

Date: 2026-09-27\
Status: complete — documentation clarified; quiz errors resolved on retest and targeted reread\
Readers: GPT-6 Luna, low reasoning, with no inherited conversation context

## Method

The maintainer requested a minimally briefed Luna low reader, followed by a quiz
and documentation improvements if it misunderstood the behavior. Each reader
received only `docs/advanced/filtering.md` and `docs/advanced/arguments.md`, with
permission to follow documentation links. Source code, tests, work items, prior
chat, other agents' output, edits and code execution were explicitly excluded.
Each reader finished reading before receiving its quiz. The coordinator checked
answers against the implementation; answer keys were not given to the readers.

The first reader received 14 behavior questions and a documentation-consistency
question. After a documentation revision it received 11 new behavior questions
and an uncertainty question. A second revision was then checked by a fresh Luna
low reader without either earlier quiz or response in its context, using 12 new
scenario groups. Repeated questioning of one reader alone could reflect learning
from the conversation; the fresh reader avoids that particular limitation.

## Findings from the original documentation

| Topic | Reader response | Assessment |
| --- | --- | --- |
| Consumer stage evaluations | Claimed two calls at each stage for three incoming candidates narrowing to two, then one; also included an eliminated candidate in the next stage | Incorrect. Three calls, then two; only incoming survivors are evaluated |
| All-false registration stage | Correct final winner but described both false candidates as matching | Imprecise explanation: neither matched; both were retained as fallbacks |
| Collection ordering | Registering A then B was said to produce `[A, B]` | Incorrect. In one layer/tier, the candidate order is `[B, A]` |
| Several eligible roots | Explicitly said the docs did not establish which root wins | Documentation gap: root selection's candidate order was insufficiently explicit |
| Boundary-masked precedence against a negative local value | Explicitly said the numeric comparison was not specified | Documentation gap: “neutral” needed the exact effective value, zero |
| Arguments-page tie rule | Noted that the page described maximum precedence followed by LIFO without the preference phases | Stale summary conflicted with the complete filtering guide |

The reader correctly explained hard versus soft selection, explicit/default name
filters, consumer-before-registration preference order, early stopping, provider
ambiguity, wrapper parents, selector defaults, lack of automatic specificity,
build/runtime separation, failure behavior, overlays and patching.

## Revisions and intermediate retest

The first revision added an early complete selection sequence, precise root and
collection order, explicit-filter replacement semantics, a stage trace, exact
boundary-neutral comparisons, and a matching arguments-page summary.

The intermediate reader then answered the ordering, root, boundary and conflict
questions correctly. It still made two errors:

- In a new four-candidate, three-stage scenario, it counted stage matches rather
  than all incoming evaluations and prematurely selected the eventual winner.
- For a registration with no chain, it counted a callback at the first stage,
  despite correctly treating later missing stages as callback-free.

The second revision added a compact algorithm that evaluates all incoming
candidates before narrowing, a two-candidate true/false example, explicit
preservation of survivor order, and the rule that an absent registration chain
invokes zero callbacks at every stage, including the first. The fresh reader
received different candidates and stage orders, without the previous answer key.

## Final fresh-reader quiz

The new reader received 12 scenario groups after reading the revised docs. It
correctly explained selection phases, callback counts for an all-false consumer
stage, single/collection/root differences, name defaults, parent wrappers,
failure/lifecycle rules, immutable patching and selectors. It still misapplied
three scenarios on its first answer:

| Scenario | Initial fresh-reader error | Corrected answer on targeted reread |
| --- | --- | --- |
| F1: A blue/EU, B blue/US, C green/US, D green/EU; prefer EU then blue | Misread green D as blue, despite correctly classifying it in F2 | EU evaluates D,C,B,A and keeps D,A (4 calls); blue evaluates D=false,A=true (2 calls); A wins |
| F3: two different registration-chain pairs | Mixed the pairs' missing predicates and their stage counts; also misstated initial LIFO order | X=[false,false] versus absent Y makes 1+1 calls and leaves Y the final LIFO winner; X=[false,false,true] versus Y=[false] makes 2+1+1 calls and selects X; order Y,X |
| F8: boundary-neutral zero versus local -3,0,3 | Stated correct effective value but gave inconsistent numeric comparisons | Exported zero beats -3, ties 0 and loses to 3; exported registration chain never runs |

The coordinator identified the erroneous question numbers and asked the reader
to rederive its answers from the candidate facts and documented rules. No answer
key or source code was supplied. The reader then gave the correct traces and
comparisons, recognizing that its earlier answers had misapplied stated rules.
This was **not a flawless first-pass quiz**; the corrected answers should not be
represented as a cold-reader 12/12 score.

The reader also flagged three documentation omissions: whether `is_named` is an
actual helper, whether runtime `resolve` accepts `prefer`, and the explicit failure
outcome of duplicate provider-map keys or ambiguous boundary selection. The final
revision documents those directly, with links for the latter two error cases.
After rereading those passages, the reader correctly answered all four final
checks: both named helpers and their meanings; no runtime `prefer` keyword;
unchanged build errors; no remaining underdetermined quiz question under the
stated single-layer/tier assumptions.

No extra prose was added to redefine basic colour or numeric comparisons: those
were application errors rather than missing library rules. The substantive docs
changes address the observed omissions, stale summary and stage-evaluation model.

## Validation and scope

`make docs-check` passes, as does `git diff --check`. The coordinator also ran
real-compiler checks for two four-candidate stage traces (9 and 11 callbacks),
root/collection LIFO order, and boundary-masked precedence against local -2, 0
and 2. The boundary preference callback count was zero in all three builds.

All 38 production Python file hashes match their values at the start of this
follow-up. Edits are documentation only. No implementation, test, package version, commit,
push or release changes are part of this follow-up. A successful reader quiz is
evidence of comprehension by this reader, not a guarantee that every reader will
interpret every case correctly.
