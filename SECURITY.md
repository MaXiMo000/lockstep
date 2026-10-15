# Security

## Reporting a problem

Report vulnerabilities privately through GitHub: **Security -> Report a
vulnerability** on this repository. Please do not open a public issue for
anything exploitable. You will get an acknowledgement within 72 hours.

## What lockstep handles

- **Read-only.** `check` reads package metadata and `verify` re-hashes
  installed files against each package's `RECORD`. Nothing is modified.
- **No network access.** `--image` runs a short-lived container from an image
  you already have, with a stdlib-only probe; nothing is installed into it.

## Supply chain

- GitHub Actions are pinned to full commit SHAs.
- Releases publish to PyPI through trusted publishing (OIDC); no long-lived
  token is stored in the repository.
