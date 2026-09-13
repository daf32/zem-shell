## Summary

<!-- What changed and why. Link the roadmap item or issue if there is one. -->

## Notes for review

<!-- Risky spots, follow-ups, anything deliberately left out. -->

## Release

<!--
Branch name decides the release on merge:

  patch/ (and ci/, docs/, chore/, ...)  merge it, no release; the CHANGELOG
                                        entry waits under "Unreleased"
  minor/                                release what has accumulated
  major/                                a milestone: "version 1", "version 2"

To ship something on its own, run the "Version bump" workflow by hand and
pick the bump.
-->

## Checklist

- [ ] `uv run pytest` passes locally
- [ ] `uv run ruff check .` is clean
- [ ] CHANGELOG.md updated under **Unreleased** (user-visible changes only)
- [ ] Docs updated if behaviour or configuration changed
