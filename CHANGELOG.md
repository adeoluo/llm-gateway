# Changelog

All notable changes to this project are documented here. The file is generated
from Conventional Commits by [git-cliff](https://git-cliff.org) when a release is cut
with `make cut-release`.

## [0.2.1] 2026-11-08

### Bug fixes

- Report the released version and keep version strings in step on release (#8)

### Documentation

- Remove authorship statements from docs and scripts
- Recorded demos of more commands, with their vhs tapes (#3)
- Recorded demos of the HTTP service and more commands (#4)
- Describe the supply chain accurately (#5)
- Complete citation metadata and bump it on release (#7)

### Maintenance

- Latest toolchain and CI versions (#6)

## [0.2.0] 2026-11-02

### Features

- Go reverse proxy with the gateway rules (gateway-proxy) (#2)

### Documentation

- Standard README structure and language framing (#7)
- Horizontal layered architecture diagram
- Compact horizontal architecture diagram
- Recorded terminal demo of a real run, with its vhs tape (#1)

### Build and CI

- Run CodeQL on main and on a weekly schedule only

### Maintenance

- Add release automation, AGENTS.md, llms.txt and contributor docs
- Classify squash merges in the changelog by the commits they contain

## [0.1.0] 2026-11-02

### Features

- Implement language-model safety gateway (#1)
- Add retry/failover, per-tenant isolation, and concurrency-safe metrics (#5)

### Documentation

- Clarify that headline metrics come from the offline provider (#3)
- Remove em dashes from documentation (#6)

### Maintenance

- Initialize repository with license and overview
- Remove Dependabot configuration
