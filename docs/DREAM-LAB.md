# Dream Lab development preview

Dream Lab is `3.7.0-dev-beta.9`, available in Personal and Commercial. It combines
memories from the selected project into an interactive offline prototype. Find it
under **Dream Lab** in the web navigation. Native mobile UI is a later milestone.

## Try a dream

1. Add at least two current memories to a project. Include problems, constraints,
   abandoned ideas, or things you would like to make easier.
2. Open Dream Lab, optionally give a direction, and choose **Dream something up**.
3. Leave the worker to generate it with your configured Ollama chat model. The
   page refreshes queued/running status automatically. Provider failures appear
   as failed runs, without leaking provider errors or configuration.
4. Open a completed dream. Read its inspiration quotations, experiment report,
   suggested human tests and limitations.
5. Open the disposable sandbox to interact with the prototype. Its control checks
   run in the browser. Close it to discard input values and reset the preview.
6. **Keep** retains the dream here. To **Evolve**, enter a new direction and use
   the evolve action on the completed dream. The new version has its own run;
   the original is preserved. **Destroy** removes the dream, never its source memories.

## What this build can invent

The model composes a tested toolkit: bounded numeric inputs, calculated metrics,
checklists, searchable boards and explanatory panels. A dream can combine them
into a capacity planner, an interactive decision aid, a recovery checklist or a
different offline tool. It cannot build an arbitrary application, execute shell
commands, install dependencies, connect to live services, or deploy itself.

The model emits validated JSON, not HTML or code. A trusted renderer turns the
data into a sandboxed iframe with an opaque origin, no network connections,
no external resources, forms, popups, parent access, persistent storage or credentials.
Generated strings are rendered as text. The preview uses illustrative assumptions
where evidence does not supply numbers; check those before making decisions.

The server checks schema limits, at least two distinct supporting memories, exact
quotations, calculation references and baseline calculations. Browser control
checks run only when the preview opens. These checks establish structure and
interaction, not whether an invention is useful or factually correct. Follow its
human test steps. Keeping a dream is not approval to deploy or to create new facts.

## Overnight generation and limits

Nightly generation is **off by default**. Enable one run per selected project at
a chosen UTC hour. The connector scheduler and RQ worker must both be running.
Busy/full projects skip that night. One active run and 50 retained dreams per
project bound queue and storage growth. Each generation samples up to eight
current memories, 1,000 characters each; it is not an exhaustive project review.
Cross-project mixing is intentionally unavailable. Evolution reuses its parent's
sources and requires that they remain current. Source edits, expiry or deletion
withhold the old prototype and quotations; generate a fresh dream to continue.

No new service or container runtime is required. This keeps the disposable 2 GB
beta VM viable while its existing Ollama host handles model inference. The model
call has a three-minute timeout and a 4,500-token output budget; RQ jobs have a
five-minute timeout. A subsequent submission clears abandoned runs after 15 minutes.
Stopping or destroying a running dream prevents publication, but an already-started
Ollama request may consume compute until its timeout.

## Existing installations

Back up first, then apply `db/migrations/019_dream_lab.sql` with the database
administrator before starting the new API/worker/scheduler images. Fresh installs
apply it through Compose's database initialization. It adds two project-isolated
tables and does not rewrite memories. Keep the migration when rolling application
images back; old images ignore these tables. Disable nightly generation before rollback.

## Next qualification gates

- Real-model prototype quality across several populated project types.
- Overnight scheduling and prolonged worker interruption on the disposable VM.
- Broader browser/device accessibility and usability checks.
- Explicit export/promotion design before any live integrations or deployments.
- Native mobile Dream Lab review, without changing existing installed runtimes.
