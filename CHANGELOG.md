# Changelog

## Unreleased

- A lockfile that pins `lockstep-evidence` itself is checked like any other package instead of reported as not installed.

## 0.4.0 - 2026-10-02

- `--image` checks a container image without installing anything into it.
- SBOM input.
- The probe no longer reads packages from the working directory.

## 0.3.0 - 2026-09-27

- Read `uv.lock` directly.
- `--python` checks another interpreter.

## 0.2.0 - 2026-09-26

- `lockstep verify` re-hashes installed files against `RECORD`.
- `pylock.toml` and `Pipfile.lock`.
- Environment markers.

## 0.1.1 - 2026-09-26

- Versions compared per PEP 440; pip itself is no longer reported as drift.

## 0.1.0 - 2026-09-10

- First release.
