# Tasks: Distributed Auction Intelligence System

## Phase 0: Global Rules Verification

- [x] Verify stateless components requirement
- [x] Verify no shared globals across engine
- [x] Verify role separation (Scheduler/Worker/Adapter)

## Phase 1: Database Finalization

- [x] Finalize `database/schema.sql` with monitoring fields
- [x] Add indexes for `next_fetch_at` and `locked_until`
- [x] Ensure Supabase RLS compatibility

## Phase 2: Engine Models

- [x] Define `FetchTier` and `Status` enums in `engine/models.py`
- [x] Implement Tier -> Interval mapping (seconds only)
- [x] Remove side effects (no `now()` in models)

## Phase 3: Scheduler Validation

- [x] Verify atomic selection logic in `engine/scheduler.py`
- [x] Confirm no network calls in scheduler
- [x] Verify locking mechanism requirements

## Phase 4: Worker Loop Validation

- [x] Refactor `engine/worker.py` for statelessness
- [x] Resolve adapter via factory site_key
- [x] Ensure deterministic lock release
- [x] Inject DB interface for persistence

## Phase 5: Adapter System

- [x] Solidify `adapters/base_adapter.py` contract
- [x] Hardened `adapters/adapter_factory.py` with explicit registry
- [x] Setup `adapters/mock_adapter.py` for testing

## Phase 6: Proxy Manager

- [x] Sanity-check `utils/proxy_manager.py`
- [x] Ensure deterministic `session_id` mapping
- [x] Verify no scheduling logic in utility

## Phase 7: Supabase Integration Layer

- [x] Create `database/db.py` thin adapter
- [x] Implement `fetch_due_items` and `lock_item`
- [x] Implement `update_item_success` and `update_item_failure`

## Phase 8: Orchestration

- [x] Implement `main.py` entry point
- [x] Wire scheduler to worker batch execution
- [x] Ensure clean exit on completion

## Phase 9: Deployment Readiness

- [x] Create `requirements.txt` with locked versions
- [x] Create `env.example` with project credentials
- [x] Migrate Frontend UI to `auction_items` table
- [x] **COURSE CORRECTION**: Purged Generic heuristics and premature coupling
- [x] **COURSE CORRECTION**: Re-anchored to selector-agnostic Core Engine
- [x] Build Reference Adapter: `GsaAdapter` (JSON-first, no selectors)
- [x] Harden Registry: One site at a time (GSA Done)
- [ ] Harden Registry: Bidspotter (Ongoing)
