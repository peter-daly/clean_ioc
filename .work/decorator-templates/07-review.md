# M07 independent review

Reviewer `/root/m07_review`, gpt-6-astra high, fresh read-only review of `4e9174a..d1d7ff7`.

## Round 1: request changes

Independent **598 focused tests passed** (5.07s); diff check passed. Three reproduced P2 findings:

1. `container.py:5239`: anchored cloning selects current occurrence-keyed explanations before inherited maps; separate compilers reuse integer IDs. Parent singleton Source and decorated singleton Target, overlay adds named singleton Source: target explanation describes Source, wrapper explanation describes ordinary Source selection. Select by source graph before remapping. Test shifted numbering for target and wrapper.
2. `container.py:6395`, originating2745: callable decorator `__signature__` raising RuntimeError with sentinel secret leaks text through materialization/report. Keep trusted compiler validation distinct; arbitrary introspection errors expose only exception type, preserve local cause. Include hostile exception `__str__` test.
3. `container.py:7380`: source filter/factory can raise ContainerBuildError with private code/path; wrapper redacts message but exports code/path. Callback phases must use fixed expansion code and compiler-owned IDs/path; trusted compiler phases may retain structured context.

No reviewer edits/commits. Verification reopened. Restoring original implementation agent via followup was rejected twice by collaboration with `agent thread limit reached`; fresh replacement spawn also failed. The independent reviewer attempted a separate Sol High repair child and received the same error. No repair code was written and no failed gate was committed as acceptance.
