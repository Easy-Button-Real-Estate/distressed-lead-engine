Repo-ready tree for Easy-Button-Real-Estate/distressed-lead-engine (nothing has been pushed).

  .gitattributes                                   keeps .bat CRLF and .command / .sh / .py LF in checkouts
  .github/workflows/dev-skill-clean-machine.yml    clean-machine CI (workflow_dispatch + push on its branch)
  development-opportunity-finder/                  the full kit, identical to the round-5 zip contents

Suggested branch: dev-skill/round5-clean-machine (the workflow's push trigger names this branch).
After copying into the repo, keep the exec bit on the Mac starter:
  git add --chmod=+x development-opportunity-finder/start-mac.command
Then run the workflow (Actions > dev-skill-clean-machine > Run workflow) or push the branch.
