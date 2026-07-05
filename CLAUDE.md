# Project instructions for Claude

## Git is READ-ONLY for Claude (VERY IMPORTANT)

The user handles all git write operations themselves. Claude must NEVER:
commit, push, pull, stash, merge, rebase, tag, or switch/create/rename
branches — no state-changing git command of any kind.

Read-only git commands (`status`, `log`, `diff`, `show`, `blame`) are fine.

When work is ready to be committed, say so and suggest a commit message;
the user will do the rest.
