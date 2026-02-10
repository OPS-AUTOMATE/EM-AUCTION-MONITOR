# Implementation Plan: Distributed Auction Intelligence System (DAIS)

## 1. Goal

Transition from a naive scraper to a state-aware monitoring engine that is stateless, scalable, and follows a strict protocol-first architecture.

## 2. Global Rules (MANDATORY)

* **No Invention**: Do not assume missing files or invent new tables.
* **Stateful Persistence**: Stateless components only, unless state is in DB.
* **Role Separation**: Scheduler decides *when*, Worker decides *what*, Adapter decides *how*.
* **Orthogonality**: No shared globals across engine components.
* **Atomic Operations**: Use database-level locking for concurrency safety.

## 3. Phased Execution Logic

### Phase 1: Database Finalization

* **Single Source of Truth**: Define the `auction_items` table with necessary monitoring fields (tier, lock, next_run).
* **Performance**: Optimize with indexes for the scheduler query (`next_fetch_at`, `locked_until`).
* **Security**: Ensure Supabase RLS compatibility.

### Phase 2: Engine Models

* **Pure Logic**: Define enums (FetchTier, Status, FetchMethod) and constants.
* **Deterministic**: No `now()` or side effects in models.

### Phase 3: Scheduler Validation

* **Authoritative**: Scheduler must determine eligibility for fetch.
* **Atomic Query**: Ensure queries target `next_fetch_at <= now()` with locking logic.

### Phase 4: Worker Loop

* **Deterministic Fetch**: Resolve adapter, execute exactly one fetch, and persist results.
* **Lock Management**: Deterministic release of locks on success or failure.
* **Backoff**: Implement failure handling at the manager/persistence layer.

### Phase 5: Adapter System

* **Contractual**: Standardize `.fetch()` entry point.
* **Hardened Factory**: Raise errors for unsupported site keys.

### Phase 6: Proxy Manager

* **Identity Mapping**: Deterministic `session_id` generation.
* **Orthogonality**: No scheduling or retry logic in proxy utilities.

### Phase 7: Integration Layer (db.py)

* **Abstraction**: Create a thin layer for DB operations (`fetch_due`, `lock_item`, `update_success`).
* **Independence**: Decouple the engine logic from Supabase SDK specifics.

### Phase 8: Orchestration (main.py)

* **Pipeline**: Wire Scheduler -> Worker.
* **Clean Exit**: Ensure monitoring passes end gracefully.

### Phase 9: Deployment Readiness

* **Portability**: Prepare `.env.example` and `requirements.txt`.
* **Stability**: Fix versions for core dependencies.

## 4. Hosting Strategy

* **Current**: Single instance for Frontend + Backend.
* **Growth**: Split infra only when load exceeds 5k concurrent items.
