# Skill: report-publication-projection

## Purpose

Generate the Profile-required chart bundles and the evidence-linked Competitor Report from normalized data and completed analyses.

## Trigger

Run after all required competitor analysis nodes finish.

## Inputs

Require `competitor_dataset`, the `competitor_analysis` collection, `research_contract`, and active `product_profile`; accept Source Index context.

## Reads

Read the declared dataset, analyses, Research Contract, Profile directory, Source Index, and `templates/competitor-report.html`.

## Tasks

Resolve the approved visualization list, generate renderer-independent data and chart specs, write insights, and assemble the static HTML report. SVG is the required canonical chart artifact; PNG is an optional compatibility artifact.

## Required Outputs

Write a `chart_bundle` collection beneath `visualizations/` and `competitor-report.html` from the declared template.

## Evidence Rules

Chart data must trace to normalized fields and Evidence IDs; qualitative axes must declare methodology and insufficient data must remain explicit.

## Completion Criteria

Every approved required visualization exists with data, spec, canonical SVG, and insight; optional PNG rendering never replaces SVG; the report references the resulting bundles.

## Verification

Validate Profile and Research Contract coverage, Chart Schema conformance, template structure, evidence links, and output-path containment.

## Failure Conditions

Report missing analysis inputs, visualization data insufficiency, a missing required canonical SVG, schema failure, or template failure without fabricating data.

## Retry Strategy

Retry recoverable chart-bundle assembly failures locally; emit a targeted Research Gap when required data is insufficient. Renderer-specific retry and fallback behavior remain deferred to Decision B.

## Forbidden Behavior

Do not lower the approved chart count, guess missing values, alter the Profile, or embed untraceable claims in the report.

## Permissions

Use no external access or secrets and write only the declared visualization directory and report path.

## Budget

Use at most 20 minutes and no new external sources.

## Executor Requirements

The executor must preserve the declarative data and chart specification. Renderer selection, SVG generation mechanics, optional PNG generation, and any fallback policy are deferred to Decision B and are not selected by this Contract Amendment.

## Next

Pass the dataset, analyses, visualizations, and report to `competitor-verifier`.
