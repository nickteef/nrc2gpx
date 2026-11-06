# Changelog

## [1.0.0] - 2026-11-06

First public release. Verified working against the Nike API in November 2026.

### Added
- `list` command: table of runs with date, distance, duration, pace and GPS availability
- `export` command: export runs with GPS to GPX 1.1 (with elevation when available)
- Selection options: `--latest [N]`, `--since` / `--until`, `--pick` (interactive), `--id`
- Skips already exported files (`--overwrite` to replace them)
- `--raw` to save the raw activity JSON
- Clear error messages for expired tokens and changed endpoints
