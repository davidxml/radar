# radar

Pick up any codebase where it was left off. One command, no setup, no API key.

`radar` reads your git history and working tree to show where work stopped, which architectural decisions were made, and where to continue. It also copies a compact AI handoff prompt to your clipboard so any LLM can start with full project context.

## Install

```bash
pip install radar-cli
```

Requires Python 3.9+ and Git.

## Usage

```bash
cd your-project
radar
```

| Flag | Description |
|---|---|
| `--md` | Copy a Markdown briefing instead of XML |
| `--budget <n>` | Lower the prompt cap (default 1,400 tokens, never above 1,450) |
| `--full` | Opt out of the cap (prints a size warning) |
| `--diagram` | Include a plain-ASCII activity diagram in the prompt (off by default, costs more tokens) |
| `--no-copy` | Skip the clipboard export |
| `--run-tests` | Run the test suite and include failures (off by default) |

## What it shows

- **Resume Here**: uncommitted changes, stale branches, and `TODO`/`FIXME` comments added in recent commits, with file paths and line numbers.
- **Decision archaeology**: architectural changes inferred from code, not commit messages. It looks at reverts, large deletions, and dependency diffs (for example, `bullmq` added and `node-cron` removed).
- **Activity timeline**: a chronological sequence of major events (scaffolding, dependency swaps, reverts, large deletions, and where work stopped), grouped into phases by gaps in activity. Rendered as an ASCII diagram in the terminal and as a compact text list in the prompt.
- **Stubs**: empty or unimplemented functions, found with Tree-sitter in any supported language.
- **Hotspots**: files that frequently change together.
- **Environment check**: missing keys from `.env.example`, runtime version mismatches, and local services (Docker, databases) that aren't running.

## AI handoff prompt

By default, `radar` copies an XML handoff prompt to your clipboard. Paste it into Claude, ChatGPT, OpenCode, or any LLM to continue work immediately.

Each finding is labeled:

- `[e]` evidence: a fact from the repo (a commit, a diff, a file).
- `[i]` inferred: a conclusion drawn from evidence. The receiving LLM is instructed to treat these as hypotheses and confirm before relying on them.

Example timeline section:

```xml
<timeline>
2026-02-02 | swap: -node-cron +bullmq [i] | a1b2c3
2026-03-11 | revert: session refactor [e] | d4e5f6
2026-03-28 | stop: v2_auth.py WIP [e]
</timeline>
```

## Token usage

`radar` uses zero tokens itself. The handoff prompt is capped at ~1,400 tokens by default (hard limit 1,450), no matter how large the repo is. Low-signal events are trimmed first, and the terminal shows exactly what was dropped. Estimates are conservative, so real usage is usually lower.

| Output | Approx. tokens |
|---|---|
| Full handoff prompt | 700 to 1,450 |
| Timeline only (up to 15 events) | 250 to 450 |
| ASCII diagram (`--diagram`) | 600 to 1,000 |

The terminal prints an estimated token count after each copy. Estimates are approximate (`~`). Use `--budget` to keep the prompt small.

## How it works

| Layer | Needs parsing | Languages |
|---|---|---|
| Git signals: reverts, deletions, co-change, dependency diffs, branches | No | All |
| Comment scan: `TODO`/`FIXME`/`HACK` in added diff lines | No | All |
| Tree-sitter: stub detection, comment confirmation | Yes | Any language with a grammar |

If a file's language has no grammar, `radar` falls back to the first two layers and marks those findings as lower confidence.

## Offline by design

Everything runs locally. No network calls, no telemetry, no account. Nothing is sent anywhere unless you pass `--ai` with your own key. CI enforces this by running the test suite with network access disabled.

## Caching

Results are cached in `.git/radar-cache.json`, keyed on the HEAD commit plus the working-tree status. Repeat runs are instant, and uncommitted changes always invalidate the cache.

## Supported dependency manifests

`package.json`, `requirements.txt`, `pyproject.toml`, `go.mod`, `Cargo.toml`, `Gemfile`, `composer.json`, `pom.xml`, `build.gradle`, `pubspec.yaml`, `mix.exs`

## Limitations

- Decision archaeology reports what changed, not why. Conclusions are inferences.
- Test failures are read from existing artifacts (`.pytest_cache`, `junit.xml`, and similar) unless you pass `--run-tests`.
- Stub detection depends on Tree-sitter grammar coverage.
- Token counts are estimates, not exact.

## Contributing

Issues and PRs welcome. Run `pytest` before submitting.

## License

MIT
