# Changelog

All notable changes to this project are documented here. The file is generated
from Conventional Commits by [git-cliff](https://git-cliff.org) when a release is cut
with `make cut-release`.

## Unreleased

### Documentation

- Standard README structure and language framing (#7)
- Horizontal layered architecture diagram
- Compact horizontal architecture diagram

### Build and CI

- Run CodeQL on main and on a weekly schedule only

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

### Bench

- Add large-workload scale benchmark (#4)
