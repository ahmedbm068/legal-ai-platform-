export const TOKEN_KEY = "admin_token";

export function getToken(): string | null {
    return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
    localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
    localStorage.removeItem(TOKEN_KEY);
}

const BASE = "/api";

async function request<T>(
    path: string,
    options: RequestInit = {}
): Promise<T> {
    const token = getToken();
    const headers: Record<string, string> = {
        "Content-Type": "application/json",
        ...(options.headers as Record<string, string>),
    };
    if (token) headers["Authorization"] = `Bearer ${token}`;

    const res = await fetch(`${BASE}${path}`, { ...options, headers });

    if (!res.ok) {
        let detail = `HTTP ${res.status}`;
        try {
            const body = await res.json();
            detail = body.detail ?? body.title ?? detail;
        } catch {
            // ignore parse errors
        }
        throw new Error(detail);
    }

    // 204 No Content
    if (res.status === 204) return undefined as unknown as T;
    return res.json() as Promise<T>;
}

// ─── Auth ─────────────────────────────────────────────────────────────────────

export interface LoginResponse {
    access_token: string;
    token_type: string;
}

export function apiLogin(email: string, password: string): Promise<LoginResponse> {
    return request<LoginResponse>("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
    });
}

export function apiGetMe(): Promise<AdminUser> {
    return request<AdminUser>("/auth/me");
}

// ─── Types ────────────────────────────────────────────────────────────────────

export interface AdminUser {
    id: number;
    name: string;
    email: string;
    role: string;
    tenant_id: number;
    created_at: string;
}

export interface AdminCase {
    id: number;
    title: string;
    status: string;
    jurisdiction_country: string;
    tenant_id: number;
    created_at: string;
}

export interface AdminDocument {
    id: number;
    filename: string;
    file_size: number;
    case_id: number | null;
    tenant_id: number;
    created_at: string;
}

export interface AuditLogEntry {
    id: number;
    tenant_id: number;
    user_id: number | null;
    method: string;
    path: string;
    status_code: number;
    duration_ms: number;
    created_at: string;
}

export interface SystemHealth {
    total_users: number;
    total_cases: number;
    total_documents: number;
    total_audit_entries: number;
}

// ─── Users ────────────────────────────────────────────────────────────────────

export function apiListUsers(): Promise<AdminUser[]> {
    return request<AdminUser[]>("/users/");
}

// ─── Cases ────────────────────────────────────────────────────────────────────

export function apiListCases(): Promise<AdminCase[]> {
    return request<AdminCase[]>("/cases/");
}

// ─── Audit Log ────────────────────────────────────────────────────────────────

export function apiListAuditLog(limit = 200): Promise<AuditLogEntry[]> {
    return request<AuditLogEntry[]>(`/admin/audit-log?limit=${limit}`);
}

// ─── System Health ────────────────────────────────────────────────────────────

export function apiSystemHealth(): Promise<SystemHealth> {
    return request<SystemHealth>("/admin/health");
}

// ─── Big Agent Catalog ────────────────────────────────────────────────────────

export interface BigAgent {
    name: string;
    tier: string;
    description: string;
    mini_agents_used: string[];
    intents_handled: string[];
    delegates_to: string[];
    ui_route: string | null;
    harvey_equivalent: string | null;
    legora_equivalent: string | null;
    last_24h_call_count: number | null;
}

export interface BigAgentCatalog {
    count: number;
    agents: BigAgent[];
}

export function apiListBigAgents(): Promise<BigAgentCatalog> {
    return request<BigAgentCatalog>("/admin/big-agents");
}

// ─── Copilot Trace ────────────────────────────────────────────────────────────

export interface CopilotTraceStage {
    name: string;
    status: string;
    detail?: string;
    metadata?: Record<string, unknown>;
}

export interface CopilotTrace {
    id: number;
    call_id: string;
    tenant_id: number | null;
    user_id: number | null;
    case_id: number | null;
    document_id: number | null;
    intent: string | null;
    big_agent: string | null;
    route: string | null;
    mode: string | null;
    effective_mode: string | null;
    verdict: string | null;
    confidence: string | null;
    used_fallback: boolean | null;
    error_count: number;
    duration_ms: number | null;
    mini_agents_used: string[];
    stages: CopilotTraceStage[];
    metadata: Record<string, unknown>;
    created_at: string | null;
}

export interface CopilotTraceList {
    count: number;
    traces: CopilotTrace[];
}

export function apiListCopilotTraces(params?: {
    limit?: number;
    big_agent?: string;
    verdict?: string;
}): Promise<CopilotTraceList> {
    const q = new URLSearchParams();
    if (params?.limit) q.set("limit", String(params.limit));
    if (params?.big_agent) q.set("big_agent", params.big_agent);
    if (params?.verdict) q.set("verdict", params.verdict);
    const qs = q.toString();
    return request<CopilotTraceList>(`/admin/copilot/traces${qs ? `?${qs}` : ""}`);
}

export function apiGetCopilotTrace(callId: string): Promise<CopilotTrace> {
    return request<CopilotTrace>(`/admin/copilot/trace/${encodeURIComponent(callId)}`);
}
