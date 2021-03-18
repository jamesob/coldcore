# Cutting a release

1. Update CHANGELOG, commit
1. Update `main:__VERSION__`
1. Run `./bin/compile`.
1. Commit
1. Run `./bin/make_release`
1. Commit, push
1. Run `cp sigs/latest-version.asc ~/mnt/img/sigs/`

