# Agent tool boundary (phase 1)

`build_tool_registry` creates a registry for one turn from trusted routing state:
`source`, `selected_tables`, runtime `Settings`, and the existing read-only database
adapters. The registry exposes only metric lookup and the selected source's schema
and query tools. SQL and question text are the only model-supplied fields; extra
fields fail Pydantic validation. The caller must create a fresh registry after
choosing this turn's source and views, and must not accept those choices from tool
arguments.

Each query invocation runs SQLGlot validation using that turn's immutable view
set, applies the configured SQL row limit, uses the existing adapter's execution
limits, and caps the returned rows again. Errors have stable, limited codes and
never include adapter exception text. Schema output contains only selected Agent
views and their allowed columns. Query rows are returned to the caller and are
not stored by this registry. The existing workflow marks its `query_result` as
`UntrackedValue` in checkpoint state.

These contracts are not attached to a model or the ChatResponse API in phase 1.
