---
status: accepted
date: 2026-03-14
deciders: Nikita Kizevich
consulted: Data & Analytics Architecture
informed: Core Engineering
---

# ADR-0016: SQLite Export as an Embedded Analytics Surface

## Context and Problem Statement

JSON metadata files are excellent for human inspection and lightweight provenance tracking, but querying, joining, aggregating, and comparing large datasets across dozens of harvest runs using flat JSON files is cumbersome and slow. Data analysts and researchers require a relational query interface without needing to set up external database servers. How should harvest analytics be exposed?

## Decision Drivers

- Zero runtime dependency overhead using Python standard library.
- Fast relational querying, filtering, and cross-run aggregation via standard SQL.
- Atomic batch ingestion using SQLite transactions (`executemany`).

## Considered Options

1. **Embedded SQLite Export (`--export-sqlite`)**: Use Python standard library `sqlite3` to create a structured relational schema (`runs`, `repositories`, `search_results`) with indexed fields and batch transaction insertion.
2. **External Database Connector (PostgreSQL / MySQL)**: Require users to configure and connect to a database server.
3. **Flat CSV Export Only**: Provide flat CSV files without relational joins or indexing.

## Decision Outcome

Chosen option: **Embedded SQLite Export (`--export-sqlite`)**.

### Positive Consequences
- Zero third-party dependencies required; operates out-of-the-box on standard Python runtimes.
- Enables instant SQL exploration of harvested repositories, topics, stars, and AI relevance scores.
- Runs and repository entities are normalized with foreign keys and unique constraints.

### Negative Consequences
- Opt-in flag requires additional disk space for the `.sqlite` database file when enabled.
