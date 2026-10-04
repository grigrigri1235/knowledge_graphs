# Git Submodule Fix Plan

## Objective
Resolve the embedded git repository warning by converting the `handbook` clone into a regular directory within our project.

## Micro-Steps for Sequential Execution
1. **Part 1:** Run `git rm --cached handbook` to remove the embedded repository link from the staging area (output to `git_rm.log`).
2. **Part 2:** Run `rm -rf handbook/.git` to remove its internal git tracking, turning it into a normal folder.
3. **Part 3:** Run `git add handbook/` and `git add .` to stage the actual files (output to `git_add_fixed.log`).
4. **Part 4:** Run `git commit -m "Fix handbook embedding and upload updates"` (output to `git_commit.log`).
