You are a senior software engineer and technical lead. Your task is to analyze 
this entire project repository and generate a comprehensive SPEC.md file.

Do the following steps IN ORDER:

STEP 1 — READ EVERYTHING FIRST
- Read ASSIGNMENT.md in full (this is the most important file)
- Read README.md if it exists
- Scan the full directory tree (all folders and files)
- Read requirements.txt / pyproject.toml / package.json (whatever exists)
- Read all files inside tests/ folder
- Read .env.example if it exists
- Read any existing source files in src/ or root-level .py files
- Run `git log --oneline` to check current commit history

STEP 2 — ANALYZE AND INFER
From everything you read, extract and infer:
- The core problem being solved
- All required features (explicit and implied)
- All APIs, tools, or agent actions that need to be built
- Input/output contracts for every endpoint or callable
- All constraints (language, libraries, deadlines, rules)
- Edge cases and failure modes
- What the pytest tests expect to pass
- Acceptance criteria implied by the assignment

STEP 3 — GENERATE SPEC.md
Write a file called SPEC.md in the project root with ALL of the following 
sections. Do not skip any section. Be specific to THIS project, not generic.

---

# Project Specification
> Generated: <today's date and time>  
> Deadline: <extract from ASSIGNMENT.md>  
> Repo: <current folder name>

---

## 1. Problem Statement
- What problem this system solves (2–4 sentences, specific)
- Who consumes this system (users, other services, evaluators)
- Why it matters in the context of the assignment

## 2. Functional Requirements
Break into three tiers:
### P0 — Must Have (assignment will fail without these)
### P1 — Should Have (expected for a good submission)
### P2 — Nice to Have (bonus, if time permits)
Each item as a checkbox: - [ ] requirement

## 3. Non-Functional Requirements
- Latency / performance expectations
- Reliability (retries, fallbacks)
- Security (no hardcoded secrets, .env usage)
- Logging and observability
- Code quality (type hints, docstrings, linting)

## 4. System Architecture
- List every component and its responsibility
- Describe data flow between components in plain English
- List all external services/APIs being called
- Draw a simple ASCII diagram of the architecture

## 5. API Contract (for every endpoint, agent tool, or callable)
For EACH one, write:
### `METHOD /route` or `function_name()`
- Description
- Input schema (with types and whether required)
- Output schema (with types)
- Auth mechanism
- Example request and response

## 6. Data Models / Schemas
For every major data structure:
- Field name | Type | Required | Description table
- Validation rules

## 7. Constraints
- Hard rules from ASSIGNMENT.md (copy them in explicitly)
- Tech stack constraints
- What is NOT allowed
- Deadline: exact date and time from assignment

## 8. Edge Cases & Error Handling
A table with columns: Scenario | Expected Behavior | Error Code / Exit
Cover at minimum:
- Empty or null inputs
- API timeouts and failures
- Malformed data
- Missing environment variables
- Rate limits
- Inputs exceeding context/token limits

## 9. Acceptance Criteria
- [ ] One checkbox per condition that must be true for a passing submission
- Map these directly to the test files you found in tests/
- Include the exact pytest command that must pass

## 10. Test Plan
### Unit Tests — list what needs unit coverage
### Integration Tests — list end-to-end scenarios
### How to run:
```bash
pytest tests/ -v
pytest tests/ -v --cov=src --cov-report=term-missing
```

## 11. Incremental Git Commit Strategy
This is CRITICAL — a single-dump commit history is disqualifying.

### Planned Commit Phases
Write a phase-by-phase table:
Phase | What gets committed | Example commit message

Use conventional commits format:
feat | fix | test | docs | refactor | chore | perf

### Rules I will follow:
- [ ] Commit after every logical unit (function, module, test, fix)
- [ ] Never commit with messages like "final", "done", "wip", "update"  
- [ ] Commit tests alongside or immediately after the feature they test
- [ ] Never commit secrets or .env files
- [ ] .gitignore must be committed in the very first commit

### Suggested first 10 commits for this project:
List the first 10 commits I should make, in order, specific to this project.

## 12. Environment Setup & Running the Project
```bash
# Full setup instructions from scratch
```
### Required Environment Variables table:
Variable | Description | Required | Example value

## 13. File & Folder Structure
Show the expected final structure as a tree, with a one-line comment 
on what each file/folder is responsible for.

## 14. Defence Video Plan (≤ 10 minutes)
Timestamp breakdown of what to show and say:
- 0:00–1:00 ...
- 1:00–3:00 ...
(make it specific to what this project actually does)

## 15. Submission Checklist
Every single thing that must be done before submitting:
- [ ] Tests pass: `pytest tests/ -v`
- [ ] No hardcoded secrets
- [ ] Incremental git history
- [ ] README has setup instructions
- [ ] Defence video ≤ 10 min and link is public/accessible
- [ ] Google Form submitted before deadline
- [ ] (add any project-specific ones)

## 16. Risks & Mitigations
| Risk | Likelihood | Impact | Mitigation |
List the top 5–8 real risks for this specific project.

## 17. Open Questions & Assumptions
- List anything ambiguous from the assignment with your assumed resolution
- Flag anything that needs clarification (check the Discord)

---

IMPORTANT RULES FOR GENERATION:
- Every section must be specific to THIS project. No generic placeholder text.
- Extract the actual deadline, actual tech stack, actual test names.
- If something is not in the assignment, make a reasonable inference and 
  mark it as [ASSUMED].
- After writing SPEC.md, print a summary of: how many sections written, 
  what files you read, and any assumptions you made.
- Do not ask for confirmation. Read, analyze, and generate in one shot.

