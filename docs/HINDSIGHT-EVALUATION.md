# Hindsight retrieval pilot — 2026-10-20

Keep Engram as the primary system. This small pilot does not establish a
retrieval benefit from replacing it with Hindsight. The immediate change is
to give Ask the existing hybrid retriever while retaining its current-only,
project, memory-type and inclusive UTC updated-date constraints.

## Observed results

Twenty current canonical memories were copied from Personal using a read-only
database transaction. Pending import candidates and historical/deleted memories
were excluded. Credential-related keywords were excluded from the sample;
the private corpus and questions are not committed to this repository.

Qwen3:4b generated one question per memory. Each question was retained only
when its supporting quote matched the original content exactly. These are
model-generated exploratory labels, not independently adjudicated answers.

| Pass | Engine | Expected source in top five | Mean reciprocal rank | Median retrieval time |
| --- | --- | --- | --- | --- |
| Rank fusion | Existing Ask search | 20/20 | 0.975 | 40.61 ms |
| Rank fusion | Engram hybrid search | 20/20 | 0.975 | 44.32 ms |
| Rank fusion | Hindsight, RRF only | 19/20 | 0.860 | 42.45 ms |
| Neural reranking | Existing Ask search | 20/20 | 0.975 | 26.18 ms |
| Neural reranking | Engram hybrid search | 20/20 | 0.975 | 29.08 ms |
| Neural reranking | Hindsight, local cross-encoder | 20/20 | 0.856 | 390.84 ms |

The hybrid change does not improve this sample's measured hit rate. It unifies
Ask with the richer existing retriever and adds lexical-only source eligibility.
The PostgreSQL regression covers that behaviour and candidate filtering with
more excluded near-neighbours than the search limit, UTC boundaries, historical
and deleted rows, a different memory type, and a second project.

## Configuration and limits

- Hindsight 1.0.0 image digest:
  `sha256:a88678c038b0e4340822b02a5efc566c56d8176b5bffa731bc433fd37f978e4c`.
- Both engines used local Ollama `all-minilm` embeddings. Hindsight retention
  and question generation used local `qwen3:4b`.
- The neural pass used `cross-encoder/ms-marco-MiniLM-L-6-v2` on CPU.
  Hindsight was capped at three CPUs and 4 GiB RAM, with no published ports.
- Hindsight used `mid` recall, a 4,096-token budget and raw world/experience
  facts. Automatic observation consolidation was disabled for this recall test.
- Multiple returned facts from one original document count as one source.
  Hindsight banks are separated by project, and results outside the approved
  project corpus abort the evaluator.
- Retrieval counters were reset in the disposable Engram database before each
  measurement. Source importance, confidence and trust were preserved.
- This measures expected-source recall, not generated-answer correctness,
  abstention, multi-hop reasoning, Reflect, observations or mental models.
- Timings are single measurements per question in fixed engine order. Engram
  uses application function calls including embedding/database work; Hindsight
  uses HTTP calls including embedding/retrieval. Cache, batching and transport
  differences limit direct latency comparisons. The second pass's faster
  Engram timings illustrate this variability.
- The small, short-memory sample is not representative of every project or a
  large memory bank. A larger, human-labelled query set is needed before a
  backend decision. Existing Engram RLS tests are not a Hindsight security audit.

## Repeating the experiment

Use a separate disposable PostgreSQL database with Engram's schema and migrations
009–012, an isolated Redis, and a private Hindsight instance. Never point the
evaluator at production: it seeds copied records and updates retrieval counters.
It requires `DATABASE_URL` to name an `engram_eval_*` database and requires an
empty database when seeding.

The private input formats are documented in
`backend/scripts/evaluate_hindsight.py`. Validate expected source IDs and their
project assignments before running. The evaluator does not generate questions.

```sh
export PYTHONPATH=backend
# Configure DATABASE_URL, REDIS_URL, PUBLIC_HOST, PUBLIC_ORIGIN,
# MINIO_ACCESS_KEY, MINIO_SECRET_KEY and OLLAMA_URL for the isolated environment.
# Set HINDSIGHT_EVAL_API_KEY if the private Hindsight instance requires it.
python backend/scripts/evaluate_hindsight.py \
  --corpus /private/corpus.json --cases /private/cases.json \
  --hindsight-url http://private-hindsight:8888 \
  --seed --retain --output /private/results.json
```

For a second ranking configuration, reuse the same corpus and cases, preserve
Hindsight's private database, and omit `--seed --retain`. Start from fresh
disposable stores if changing the corpus. Reports omit private questions and
memory content, but still contain source IDs and should be kept private.
Stop and remove the experimental services and database volumes after testing.

Engram's version remains **2.7.0**. This work does not publish or retag a release.
