Repo-ready tree for Easy-Button-Real-Estate/distressed-lead-engine (nothing has been pushed).

  .gitattributes                                   keeps .bat CRLF and .command / .sh / .py LF in checkouts
  .github/workflows/dev-skill-clean-machine.yml    clean-machine CI
  development-opportunity-finder/                  the full kit, identical to the round-6 zip contents

Workflow triggers: workflow_dispatch; push to main, dev-skill/round5-clean-machine or dev-skill/round6-clean-machine;
push of a tag matching v*.
Jobs: build (zip once, SHA-256, both test suites in repo layout, uploads kit-zip and a release-style artifact named
development-opportunity-finder-<ref>-<sha7>); clean-machine (macos-latest + windows-latest x Python 3.10, 3.13,
3.14, 3.15 with allow-prereleases; negative cases, starter --check, both test suites, demo); windows-pymanager
(install manager with no runtime must print "Python install manager found but no Python installed. Run: py install
3.14", then py install 3.13 and the starter must find it; runs /which-python, /check and the demo, NOT the test
suites).

Suggested branch: dev-skill/round6-clean-machine.
After copying into the repo, keep the exec bit on the Mac starter:
  git add --chmod=+x development-opportunity-finder/start-mac.command
Then push the branch (or Actions > dev-skill-clean-machine > Run workflow).

CI has NOT run on the round-6 code. The last green run (r5/ci-proof.md) was on the round-5 commit and does not
cover the round-6 changes, the 3.15 matrix leg or the new pymanager no-runtime step. Rerun CI on the new commit.
