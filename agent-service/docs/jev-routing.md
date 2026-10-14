# Jev routing, phase 2

The server uses a separate TypeSafe System One HTTP client with
`TYPESAFE_API_KEY` and `JEV_MODEL=jev-latest`. It does not use ChatOpenAI for
Jev. The client follows the [official API contract](https://docs.typesafe.ai/api):
one state and five questions in one request, three Choice answers (`intent`,
`scope`, `explicit_import`) and two Noul answers (`depends_on_previous`, `multiple_tasks`). The
key stays in the Python service environment.

Jev sees the current question, a small set of prior structured slots, and Hive
availability. It does not extract slots or generate SQL. A separate structured
generator extracts explicit QuestionSlots. Code validates locations, enums,
months, layout and ranking ranges, then applies inheritance and overrides.
The policy maps the requested data scope to an executable MySQL/Hive source, chooses a fixed view and constructs the phase 1 tool registry. Schema,
metric lookup and query execution use those tools; SQLGlot still runs on every
query tool call. An explicit Hive/import request cannot fall back to MySQL.
If `explicit_import` and `scope` disagree, a structured review runs; an unresolved
conflict asks for clarification rather than querying MySQL. Data quality requires Hive.

`JEV_CONFIDENCE_THRESHOLD` defaults to 0.7; `JEV_NOUL_MARGIN` defaults to 0.15.
Low confidence, uncertain or positive Noul values, intent/scope conflicts,
explicit Hive contradictions and Jev failure
trigger one structured generative review. If review fails, the Agent asks for
clarification. These thresholds are starting values and need calibration with
Chinese project data and the operational cost of incorrect routes.

The 88 case / 97 turn dataset has decision, source and table labels, but no
intent labels. Offline tests feed gold route labels to a mock Jev response and
verify the permission policy. They cover all 63 query turns, 17 reject turns,
6 unsupported turns, and check the remaining 11 clarification labels separately.
With gold-fed decisions, the policy maps query views 63/63 and reject/unsupported
to no source 23/23. Clarifications deliberately use final source `none`: the
dataset labels 9 of them `mysql` and 2 `hive`, so source comparison for those
11 is a known mismatch; 2 also carry a listing view label that is not exposed
until clarified. This is a policy-label difference, not measured Jev accuracy.

The original 16 manually labeled Chinese examples remain as a small mock-policy
regression. They are not used to estimate live model accuracy.
The larger 160-question corpus and its label rules are documented in
`docs/jev-routing-labels.md`. Run `python -m app.evaluation.jev_routing
--dataset 160 --split dev --limit 80` for the development set, or select
`--split test` for the held-out set. The Jev probe never queries MySQL/Hive.
`app.evaluation.jev_review` can replay saved Jev reports through the same
structured review prompt as production without database calls. Review results
and limitations are in `docs/evaluation/jev-routing-final-reviewed.json`.
