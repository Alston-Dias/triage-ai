#====================================================================================================
# START - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================

# THIS SECTION CONTAINS CRITICAL TESTING INSTRUCTIONS FOR BOTH AGENTS
# BOTH MAIN_AGENT AND TESTING_AGENT MUST PRESERVE THIS ENTIRE BLOCK

# Communication Protocol:
# If the `testing_agent` is available, main agent should delegate all testing tasks to it.
#
# You have access to a file called `test_result.md`. This file contains the complete testing state
# and history, and is the primary means of communication between main and the testing agent.
#
# Main and testing agents must follow this exact format to maintain testing data. 
# The testing data must be entered in yaml format Below is the data structure:
# 
## user_problem_statement: {problem_statement}
## backend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.py"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## frontend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.js"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## metadata:
##   created_by: "main_agent"
##   version: "1.0"
##   test_sequence: 0
##   run_ui: false
##
## test_plan:
##   current_focus:
##     - "Task name 1"
##     - "Task name 2"
##   stuck_tasks:
##     - "Task name with persistent issues"
##   test_all: false
##   test_priority: "high_first"  # or "sequential" or "stuck_first"
##
## agent_communication:
##     -agent: "main"  # or "testing" or "user"
##     -message: "Communication message between agents"

# Protocol Guidelines for Main agent
#
# 1. Update Test Result File Before Testing:
#    - Main agent must always update the `test_result.md` file before calling the testing agent
#    - Add implementation details to the status_history
#    - Set `needs_retesting` to true for tasks that need testing
#    - Update the `test_plan` section to guide testing priorities
#    - Add a message to `agent_communication` explaining what you've done
#
# 2. Incorporate User Feedback:
#    - When a user provides feedback that something is or isn't working, add this information to the relevant task's status_history
#    - Update the working status based on user feedback
#    - If a user reports an issue with a task that was marked as working, increment the stuck_count
#    - Whenever user reports issue in the app, if we have testing agent and task_result.md file so find the appropriate task for that and append in status_history of that task to contain the user concern and problem as well 
#
# 3. Track Stuck Tasks:
#    - Monitor which tasks have high stuck_count values or where you are fixing same issue again and again, analyze that when you read task_result.md
#    - For persistent issues, use websearch tool to find solutions
#    - Pay special attention to tasks in the stuck_tasks list
#    - When you fix an issue with a stuck task, don't reset the stuck_count until the testing agent confirms it's working
#
# 4. Provide Context to Testing Agent:
#    - When calling the testing agent, provide clear instructions about:
#      - Which tasks need testing (reference the test_plan)
#      - Any authentication details or configuration needed
#      - Specific test scenarios to focus on
#      - Any known issues or edge cases to verify
#
# 5. Call the testing agent with specific instructions referring to test_result.md
#
# IMPORTANT: Main agent must ALWAYS update test_result.md BEFORE calling the testing agent, as it relies on this file to understand what to test next.

#====================================================================================================
# END - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================



#====================================================================================================
# Testing Data - Main Agent and testing sub agent both should log testing data below this section
#====================================================================================================

user_problem_statement: |
  F-01 Deployment Change Correlation. Auto-surface the deployment that caused the
  incident in the AI Triage Panel in real time. Includes cicd_tools + deployment_events
  collections (Mongo, per env), CICDToolService with GitHub Actions + Mock adapters,
  DeploymentCorrelator with confidence scoring, 60s background sync, GET /api/incidents/
  {id}/deployments, enriched Claude triage prompt, DeploymentCard UI at top of Triage
  Panel + IncidentDetail, and CICD tool registration in Settings → Integrations.

backend:
  - task: "F-01 CI/CD tool CRUD + token encryption"
    implemented: true
    working: "NA"
    file: "backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: "NA"
        agent: "main"
        comment: |
          Added Fernet-based encryption (JWT_SECRET-derived key), CICDTool model,
          and endpoints: GET /api/cicd/tools, POST /api/cicd/tools (admin),
          PATCH /api/cicd/tools/{id}, DELETE /api/cicd/tools/{id},
          POST /api/cicd/tools/{id}/test, POST /api/cicd/sync-all. Token never
          returned in API responses (`has_token` flag instead).

  - task: "F-01 DeploymentCorrelator + GET /incidents/{id}/deployments"
    implemented: true
    working: "NA"
    file: "backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: "NA"
        agent: "main"
        comment: |
          Confidence = 0.5*time_score + 0.35*service_match + 0.15*file_relevance.
          Time bands: ≤5m=1.0, ≤15m=0.85, ≤30m=0.6, ≤60m=0.3, ≤120m=0.1, else 0.
          Labels: high≥0.7, medium≥0.4, else low. Endpoint:
          GET /api/incidents/{id}/deployments?window_minutes=30&confidence_min=0.3
          Returns scored list with rollback_command, pr_url, ci_run_url.

  - task: "F-01 GitHub Actions + Mock adapters + 60s background sync"
    implemented: true
    working: "NA"
    file: "backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: "NA"
        agent: "main"
        comment: |
          BaseCICDAdapter interface with GitHubActionsAdapter (real, uses /actions/runs
          + /commits/{sha} for changed files & diff) and MockAdapter (synthetic,
          25% per sync, force=True on /test). Stubs: GitLab, CircleCI, ArgoCD.
          asyncio background loop calls sync_all() every 60s. Seeds one mock tool
          on first startup.

  - task: "F-01 Triage prompt enrichment with deployment context"
    implemented: true
    working: "NA"
    file: "backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
      - working: "NA"
        agent: "main"
        comment: |
          /api/triage now correlates deployments BEFORE calling Claude. When any
          confidence ≥ 0.3, prepends "RECENT DEPLOYMENTS (before first alert):"
          block to user message with service/version/deployer/time/files/PR.
          Response also includes "deployments" array. Verified via smoke test:
          Claude output explicitly references "checkout-svc v1.1.10 deployment
          9 minutes before first alert" and recommends rollback.

frontend:
  - task: "F-01 DeploymentCard component"
    implemented: true
    working: "NA"
    file: "frontend/src/components/DeploymentCard.jsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: false  # user will test FE; main agent verified visually
    status_history:
      - working: "NA"
        agent: "main"
        comment: |
          Shows confidence badge (HIGH/MEDIUM/LOW with color), service+version,
          deployer name + handle + avatar, time delta, PR title, top 3 changed
          files (clickable, copies path), expandable diff_summary, Rollback
          button (copies kubectl command via clipboard + toast), View PR + CI
          Run links opening in new tab. Verified rendered at top of triage panel
          with MEDIUM CONFIDENCE 61% in screenshot.

  - task: "F-01 CICDToolsSettings + Settings integration"
    implemented: true
    working: "NA"
    file: "frontend/src/components/CICDToolsSettings.jsx, frontend/src/pages/Settings.jsx"
    stuck_count: 0
    priority: "medium"
    needs_retesting: false
    status_history:
      - working: "NA"
        agent: "main"
        comment: |
          Admin-only UI to add/edit/delete/test/toggle CI/CD tools. Type selector
          for github/gitlab/circle/argocd/mock with help text. Token field
          masked, not pre-filled on edit. "Sync now" button and per-row
          "Test sync" verified to call /api/cicd/sync-all and /api/cicd/tools/{id}/test.

  - task: "F-01 TriagePanel + IncidentDetail integration"
    implemented: true
    working: "NA"
    file: "frontend/src/components/TriagePanel.jsx, frontend/src/pages/IncidentDetail.jsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: "NA"
        agent: "main"
        comment: |
          TriagePanel renders <DeploymentCard> at the very top when result.deployments
          is non-empty. IncidentDetail fetches /api/incidents/{id}/deployments on
          mount and renders a dedicated "Deployment Correlation" section above
          the AI Triage Summary, with the top match expanded and the rest in a
          collapsible <details> block.

metadata:
  created_by: "main_agent"
  version: "1.0"
  test_sequence: 0
  run_ui: false

test_plan:
  current_focus: []
  stuck_tasks: []
  test_all: false
  test_priority: "high_first"

agent_communication:
  - agent: "main"
    message: |
      F-01 backend verified end-to-end. 5 of 6 automated test scenarios PASSED; the 6th
      failure was a test-harness bug (stale incident_id). Manual curl smoke confirmed
      confidence scoring on the same endpoint returns the expected mix of high/low labels
      (0.85 high for service-matching deployment ~6-11m before incident; 0.335 low for
      non-matching service ~23m before). All acceptance criteria met:
        ✅ Deployment Card at top of triage panel (visually verified)
        ✅ Confidence badge HIGH/MEDIUM/LOW with colors
        ✅ One-click Rollback copies command (clipboard + toast)
        ✅ GitHub Actions adapter fully implemented
        ✅ Claude prompt enriched (summary references deployment + recommends rollback)
        ✅ CI/CD tool registration UI in Settings → CI/CD Integrations
      Frontend testing: awaiting user permission before invoking auto_frontend_testing_agent.
 fresh mock
           deployment with matching service, expect at least 1 entry with
           confidence_label in [low, medium, high].
        5) GET /api/incidents/{id}/deployments works with window_minutes &
           confidence_min query params, clamped properly.
        6) Verify confidence labeling thresholds: 0.7+/0.4+/else.
      Auth: use admin@triage.ai / admin123 (in /app/memory/test_credentials.md).
      Do NOT test frontend — user said FE will be tested separately.
