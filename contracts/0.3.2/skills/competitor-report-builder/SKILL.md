# Skill: competitor-report-builder

## Purpose

Publish the initial evidence-linked Competitor Report from the verified publication projection and completed chart collection.

## Trigger

Run only after `report-publication-projection` has produced the verified Builder-facing projection.

## Inputs

Require the immutable `report_publication_projection`, its exact `chart_bundle_collection`, and the active `product_profile`; accept Source Index context only for the verified citation metadata already selected by the projection.

## Reads

Read only the declared publication projection, completed chart collection, optional Source Index, and `templates/competitor-report.html`.

## Tasks

Project the verified Fact Groups and citation metadata verbatim into the static template, reference only chart assets already declared by the chart collection, and ask the Runtime-owned immutable Publisher to commit the initial offline HTML Bundle with a null base Report.

## Required Outputs

Write one typed `competitor_report` with `publication_kind: INITIAL`, `base_report_ref: null`, `verification: PENDING/null`, and `scoring: NOT_PERFORMED/null`, backed by the committed offline HTML Bundle.

## Evidence Rules

Visible citation publisher, title, excerpt, and canonical URL values must come from verified citation metadata, be projected verbatim, and be safely escaped. The Builder must not infer, summarize, rewrite, fetch, or invent citation metadata.

## Completion Criteria

The immutable initial Report references the exact publication projection and chart collection, uses only contained local assets, records the initial section states, and is published append-only through current-root compare-and-swap and idempotent replay.

## Verification

Validate projection and chart collection identity, template structure, verbatim citation metadata, local asset containment, initial publication kind, null base, section states, and output-path containment.

## Failure Conditions

Report missing or mismatched projection inputs, an incomplete chart collection, schema failure, stale current-root state, or template failure without fabricating data or changing upstream artifacts.

## Retry Strategy

Replay an identical publication request idempotently; reject a stale or conflicting base instead of overwriting it. Return upstream projection or chart defects to their owning node.

## Forbidden Behavior

Do not generate Chart Data, Chart Specs, SVG, or PNG; do not select or execute a renderer; do not alter the Profile, projection, chart collection, verified citations, or successor sections.

## Permissions

Use no external access or secrets and write only the declared immutable Report Bundle and typed Report path through the Runtime-owned Publisher.

## Budget

Use at most 5 minutes and no new external sources.

## Executor Requirements

The executor consumes renderer results as immutable inputs and must preserve all non-presentation facts, exact Artifact identities, safe relative paths, and verified citation metadata.

## Next

Pass the initial Report to the optional Score Publisher path and then to `competitor-verifier`.
