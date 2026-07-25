# MedNexus Public Health — Architecture (Living Document)

Status: Prototype phase (Day 0)
Last updated: 2026-07-22

## 1. Purpose

A platform-independent module that ingests public health reports (notifiable
disease case reports, immunization records, laboratory reports, syndromic
surveillance, outbreak reports), extracts structured fields, and prepares
data for statistics and indicators.

This is a separate project from the MedNexus de-identification tool, but
shares its visual identity and long-term engine-agnostic principles.

## 2. Current Phase: Static UI Prototype

No backend yet. The frontend prototype (`frontend/prototype/`) is a static
HTML/CSS/JS page used to validate the interaction flow before any extraction
logic is written.

Flow: select report type → provide input (paste/upload) → request extraction
→ view structured result.

## 3. Report Types (initial set)

| Type | Description |
|---|---|
| Notifiable Disease | Individual case reports for mandatory-reporting infectious diseases |
| Immunization | Vaccination records: dose, lot, date, coverage |
| Laboratory | Test results feeding surveillance/case confirmation |
| Syndromic | Symptom-based reports for early outbreak detection |
| Outbreak / Cluster | Group-level reports for a detected outbreak event |

Full field definitions per type live in `docs/report-types.md` (to be
populated as extraction schemas are designed).

## 4. Planned Pipeline (not yet implemented)

1. Report ingestion (file/text input, later batch + API)
2. Structured extraction (rules + AI hybrid, per report type)
3. Terminology normalization (ICD-10, LOINC, vaccine codes)
4. Statistics and indicators
5. Forecasting (deferred until stages 1-4 are validated)

## 5. Open Decisions

Tracked in `docs/decisions-log.md`. Add an entry any time a structural
choice is made — do not let decisions live only in chat history.
