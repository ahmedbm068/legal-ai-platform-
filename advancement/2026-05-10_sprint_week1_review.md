# Sprint Week 1 Review — 2026-05-10

1. **Rate limiter**: Sliding-window rate limiter deployed on all backend API routes (Day 1–2).
2. **Frontend stabilization**: Fixed 6 type errors in lawyer app including CalendarEvent import, UiLanguage cast, and ImageDocumentBatch.processing_status → status (Days 2–3, 7).
3. **Admin + client-portal shells**: Bootstrapped full routed shells for admin (Day 4) and client-portal (Day 5) with error boundaries in all 3 apps.
4. **Toast notification system**: Unified toast context + container implemented across all 3 apps with per-app styling (Day 6).
5. **Prompt governance**: SHA-256 lock on AI prompts (PROMPT_LOCK.json) with eval gate policy; baseline eval snapshot at 20% pass rate documents target gaps for next sprint (Day 6).
