You are a senior software architect. Your task is to read this entire project,
then produce two things: (1) a detailed system architecture, and (2) a 
phased implementation plan where every phase maps to its own git branch.

STEP 1 — READ EVERYTHING FIRST (do not skip any of these)
- Read SPEC.md (primary source of truth)
- Read ASSIGNMENT.md in full
- Read README.md if it exists
- Read the full directory tree
- Read requirements.txt / pyproject.toml / package.json
- Read ALL files in tests/ — understand exactly what must pass
- Read any existing source files
- Run `git log --oneline` to see current state
- Run `git branch -a` to see existing branches

STEP 2 — ANALYZE
From everything you read, determine:
- The full system component map (every piece that needs to be built)
- Dependencies between components (what must exist before what)
- The critical path (what blocks everything else if delayed)
- What the tests are actually asserting (reverse-engineer requirements)
- Natural groupings of work that can be developed and tested in isolation
- Realistic time estimates given the deadline

STEP 3 — GENERATE ARCHITECTURE.md
Write a file called ARCHITECTURE.md in the project root with the following 
sections. Be completely specific to THIS project. No generic content.

---

# System Architecture & Implementation Plan
> Total phases: <N>
> Branch strategy: one branch per phase, merged into main on completion

---

## PART 1: SYSTEM ARCHITECTURE

### 1.1 Architecture Style
- State the architecture pattern (e.g. pipeline, event-driven, layered, 
  microservices, agent loop, RAG, etc.)
- Why this pattern fits this specific problem
- Key trade-offs made

### 1.2 Component Map
List every component that will exist in the final system.
For each component write:

#### `ComponentName`
- **Responsibility:** one sentence, what it owns
- **Inputs:** what it receives
- **Outputs:** what it produces
- **Dependencies:** which other components it calls
- **External services:** any third-party API or library it uses
- **File location:** where it will live (e.g. `src/parser/parser.py`)

### 1.3 System Data Flow
Describe the full journey of a request/input through the system,
step by step, from entry point to final output.
Then draw it as an ASCII diagram showing all components and arrows.

Example format (replace with actual components):
[Input]
↓
[Component A] ──calls──→ [External API]
↓
[Component B]
↓
[Component C] ──writes──→ [Database/Store]
↓
[Output]

### 1.4 External Dependencies & Integrations
Table with columns:
Service/Library | Purpose | How it's used | Fallback if unavailable

### 1.5 Data Flow & State Management
- What data is persisted vs in-memory
- Data formats at each boundary (JSON, Pydantic models, raw strings, etc.)
- Where validation happens
- How state is passed between components

### 1.6 Error Propagation Map
Show how errors flow through the system:
- Where errors are caught
- Where they are logged
- Where they surface to the caller
- Which errors are retried vs failed fast

### 1.7 Project File & Folder Structure (Final State)
Show the COMPLETE expected file tree when the project is done.
Every file with a one-line comment on what it contains.

project-root/
├── src/
│   ├── module/
│   │   ├── file.py        # what this file does

---

## PART 2: PHASED IMPLEMENTATION PLAN

### Phasing Rules (follow these exactly):
- Phase 0 is always project setup and skeleton
- Phases are ordered by dependency: nothing in phase N requires 
  something built in phase N+1
- Each phase must be independently testable before moving on
- Each phase gets its own git branch named: phase/<phase-name>
- A phase is DONE only when its tests pass and it's merged to main
- No phase should take more than 1 day of focused work
- The final phase is always "submission-ready" cleanup

---

Now write one section per phase in this format:

---

### Phase <N>: <Phase Name>
**Branch:** `phase/<kebab-case-name>`
**Goal:** One sentence — what capability exists after this phase that 
          didn't exist before.
**Depends on:** Phase <X> (or "none" for Phase 0)
**Estimated time:** X hours

#### What gets built:
- Bullet list of every file created or modified in this phase
- Be specific: `src/ingestion/pdf_loader.py` — not just "the loader"

#### Implementation steps:
Numbered list of exact steps to execute in this phase, in order.
Each step should be small enough to be one commit.

#### Commits to make in this phase:
List every commit that should be made, in order:
1. `feat(scope): description` — what this commit contains
2. `test(scope): description` — what tests are added
3. `fix(scope): description` — any fixes made

#### Tests to write / pass:
- List every test function that must pass before this phase is closed
- Include the test file path and test function name if inferrable

#### Definition of Done:
- [ ] Specific checkbox conditions that must all be true
- [ ] Relevant pytest command that proves this phase works:
      `pytest tests/path/test_file.py -v`
- [ ] Branch merged into main via: `git merge phase/<name>`

#### Git commands to execute at end of phase:
```bash
git add .
git commit -m "chore(phase-N): phase complete, all tests passing"
git checkout main
git merge phase/<phase-name>
git push origin main
git checkout -b phase/<next-phase-name>
```

---

(Repeat the above block for every phase)

---

## PART 3: MASTER TIMELINE

### 3.1 Phase Schedule
Given today's date and the deadline, build a recommended schedule:

| Phase | Branch | Est. Hours | Start | End | Status |
|-------|--------|------------|-------|-----|--------|
| 0 | phase/setup | Xh | Day 1 HH:MM | Day 1 HH:MM | ⬜ Not started |

Use these status icons:
⬜ Not started | 🔄 In progress | ✅ Complete | 🚨 Blocked

### 3.2 Critical Path
Identify the 3–5 steps that, if delayed, will blow the deadline.
For each: why it's on the critical path and how to mitigate the risk.

### 3.3 Time Buffers
- Where buffer time is built in
- What gets cut first if behind schedule (P2 features)
- Minimum viable submission (what must exist to not be disqualified)

---

## PART 4: GIT BRANCH STRATEGY (COMPLETE)

### Branch Map

main
├── phase/0-setup              ← merged first
├── phase/1-<name>             ← merged second
├── phase/2-<name>
├── ...
└── phase/N-submission-ready   ← final merge before submit

### Full Git Workflow
```bash
# Starting the project
git checkout main
git pull origin main

# Starting each phase
git checkout -b phase/<phase-name>

# During a phase (commit often, after each logical unit)
git add <specific files>
git commit -m "feat(scope): description"

# Finishing a phase
git checkout main
git merge phase/<phase-name>
git push origin main
git tag phase-<N>-complete
git checkout -b phase/<next-phase-name>
```

### Commit Message Reference

feat(scope):     new capability added
fix(scope):      bug fixed
test(scope):     tests added or updated
docs(scope):     documentation updated
refactor(scope): code restructured, no behavior change
chore(scope):    setup, config, dependencies
perf(scope):     performance improvement

### What NEVER goes in git
- .env files (secrets)
- __pycache__/ 
- Any file with an API key or password
- Large binary or model files (add to .gitignore immediately in Phase 0)

---

## PART 5: PRE-SUBMISSION CHECKLIST

### Code Quality
- [ ] `pytest tests/ -v` — zero failures
- [ ] No hardcoded secrets anywhere in codebase
- [ ] All environment variables documented in .env.example
- [ ] Type hints present on all public functions
- [ ] No dead code or commented-out blocks left in

### Git History
- [ ] At least <N> commits (one per implementation step minimum)
- [ ] No commit messages like "final", "done", "wip", "asdf", "update"
- [ ] All phase branches merged into main
- [ ] `git log --oneline` tells a clear story of development

### Documentation
- [ ] README has: what it does, setup steps, how to run, how to test
- [ ] SPEC.md exists
- [ ] ARCHITECTURE.md exists (this file)

### Submission
- [ ] Defence video recorded and ≤ 10 minutes
- [ ] Video link is publicly accessible (not private/unlisted-only)
- [ ] Google Form submitted before deadline
- [ ] Only ONE form submission made

---

GENERATION RULES:
- Every phase, every component, every file path must be specific to 
  THIS project. Read the tests to know exactly what needs to exist.
- If the tests import `from src.X import Y` — that file must appear 
  in the architecture and in the correct phase.
- Mark any inference you make as [ASSUMED] so I can verify it.
- Phase 0 must always set up .gitignore, virtual env, folder skeleton,
  and install dependencies — nothing else.
- The last phase must always be named "submission-ready" and contain
  only cleanup, final testing, README polish, and video prep.
- After writing ARCHITECTURE.md, print a summary:
  total phases, total estimated hours, critical path items,
  and the first git command I should run right now.
- Do not ask for confirmation. Read everything, then generate.