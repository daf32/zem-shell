## Summary

<!-- What changed and why. Link the roadmap item or issue if there is one. -->

## Notes for review

<!-- Risky spots, follow-ups, anything deliberately left out. -->

## Release

<!--
Every merge bumps the version and tags it. The branch name decides whether
that tag is also published:

  patch/ (and ci/, docs/, chore/, ...)  tag only, nothing published; the
                                        CHANGELOG entry stays under "Unreleased"
  minor/                                tag + release: GitHub and PyPI
  major/                                the same, named as a milestone

To ship something on its own, run the "Version bump" workflow by hand and
pick the bump; a hand-run always publishes.
-->

## Checklist

- [ ] `uv run pytest` passes locally
- [ ] `uv run ruff check .` is clean
- [ ] CHANGELOG.md updated under **Unreleased** (user-visible changes only)
- [ ] Docs updated if behaviour or configuration changed
