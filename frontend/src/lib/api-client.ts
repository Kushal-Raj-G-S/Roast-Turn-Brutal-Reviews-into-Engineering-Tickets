/**
 * Backend API Client
 * ==================
 * Client for communicating with FastAPI backend
 */

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export interface LoginCredentials {
  email: string;
  password: string;
}

export interface SignupData {
  email: string;
  password: string;
  full_name?: string;
}

export interface User {
  id: string;
  email: string;
  full_name?: string;
  avatar_url?: string;
  provider?: string;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  user: User;
}

export interface Upload {
  id: number;
  user_id: string;
  filename: string;
  file_size_bytes?: number;
  total_reviews?: number;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  error_message?: string;
  processed_reviews?: number;
  filtered_noise?: number;
  clusters_created?: number;
  ai_analyzed_count?: number;
  processing_time_ms?: number;
  processing_time_seconds?: number;
  created_at: string;
  completed_at?: string;
}

export interface UploadResponse {
  upload_id: number;
  status: string;
  message: string;
}

export interface Cluster {
  id: number;
  cluster_uuid: string;
  title: string;
  severity: 'critical' | 'high' | 'medium' | 'low';
  status: 'fresh_roast' | 'assigned' | 'in_progress' | 'resolved' | 'wont_fix';
  review_count?: number;
  assigned_to?: string;
  created_at: string;
  regression_detected?: boolean;
  regression_of_title?: string;
  regression_confidence?: number;
  regression_match_method?: 'keyword' | 'semantic' | 'keyword+semantic';
}

export interface AgentSimilarIssue {
  cluster_id: number;
  title: string;
  severity: string;
  status: string;
}

export interface AgentMetadata {
  likelihood: string;
  scope: string;
  suggested_severity: string;
  severity_reason: string;
  confidence: number;
  similar_issues: AgentSimilarIssue[];
  eval_scores?: {
    faithfulness: number;
    answer_relevancy: number;
    reasoning?: string | null;
  } | null;
  trace_id?: string;
  agent_steps: string[];
}

export interface ClusterDetail extends Cluster {
  rca_title?: string;
  rca_hypothesis?: string;
  rca_steps?: string;
  rca_fix?: string;
  ai_analyzed?: boolean;
  ai_metadata?: AgentMetadata | null;
  affected_versions?: string[];
  affected_devices?: string[];
  keywords?: string[];
  sample_reviews?: Array<{
    content: string;
    rating?: number;
    date?: string;
    version?: string;
    device?: string;
  }>;
  assigned_at?: string;
  updated_at?: string;
  resolved_at?: string;
  regression_resolved_at?: string;
  version_bisect?: {
    earliest_version: string | null;
    most_common_version: string;
    distinct_versions: number;
    version_counts: Record<string, number>;
  } | null;
}

export interface UserStatistics {
  total_reviews_analyzed: number;
  total_issues_found: number;
  total_issues_resolved: number;
  average_sentiment_score: number;
  rating_1_count: number;
  rating_2_count: number;
  rating_3_count: number;
  rating_4_count: number;
  rating_5_count: number;
  average_resolution_time_hours: number;
  last_analysis_at?: string;
}

export interface SeverityDistribution {
  critical: number;
  high: number;
  medium: number;
  low: number;
}

export interface StatusDistribution {
  fresh_roast: number;
  assigned: number;
  in_progress: number;
  resolved: number;
  wont_fix: number;
}

export interface RecentActivity {
  date: string;
  filename: string;
  reviews: number;
  clusters: number;
}

export interface AnalyticsData {
  user_statistics: UserStatistics;
  severity_distribution: SeverityDistribution;
  status_distribution: StatusDistribution;
  recent_activity: RecentActivity[];
  total_uploads: number;
}

class APIClient {
  private baseURL: string;
  private token: string | null = null;

  constructor(baseURL: string = API_BASE_URL) {
    this.baseURL = baseURL;
    // Load token from localStorage if available
    if (typeof window !== 'undefined') {
      this.token = localStorage.getItem('api_token');
    }
  }

  private getHeaders(includeAuth: boolean = false): HeadersInit {
    const headers: HeadersInit = {
      'Content-Type': 'application/json',
    };

    if (includeAuth && this.token) {
      headers['Authorization'] = `Bearer ${this.token}`;
    }

    return headers;
  }

  setToken(token: string) {
    this.token = token;
    if (typeof window !== 'undefined') {
      localStorage.setItem('api_token', token);
    }
  }

  clearToken() {
    this.token = null;
    if (typeof window !== 'undefined') {
      localStorage.removeItem('api_token');
    }
  }

  // Authentication endpoints
  async signup(data: SignupData): Promise<TokenResponse> {
    const response = await fetch(`${this.baseURL}/auth/signup`, {
      method: 'POST',
      headers: this.getHeaders(),
      body: JSON.stringify(data),
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Signup failed');
    }

    const result: TokenResponse = await response.json();
    this.setToken(result.access_token);
    return result;
  }

  async login(credentials: LoginCredentials): Promise<TokenResponse> {
    const response = await fetch(`${this.baseURL}/auth/login`, {
      method: 'POST',
      headers: this.getHeaders(),
      body: JSON.stringify(credentials),
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Login failed');
    }

    const result: TokenResponse = await response.json();
    this.setToken(result.access_token);
    return result;
  }

  async getCurrentUser(): Promise<User> {
    const response = await fetch(`${this.baseURL}/auth/me`, {
      headers: this.getHeaders(true),
    });

    if (!response.ok) {
      throw new Error('Failed to get current user');
    }

    return response.json();
  }

  async logout(): Promise<void> {
    try {
      await fetch(`${this.baseURL}/auth/logout`, {
        method: 'POST',
        headers: this.getHeaders(true),
      });
    } finally {
      this.clearToken();
    }
  }

  // Upload endpoints
  async uploadCSV(file: File): Promise<UploadResponse> {
    const formData = new FormData();
    formData.append('file', file);

    const response = await fetch(`${this.baseURL}/upload`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${this.token}`,
      },
      body: formData,
    });

    if (!response.ok) {
      const errorData = await response.json();
      // For 402 errors, pass detailed error info
      if (response.status === 402 && typeof errorData.detail === 'object') {
        const err: any = new Error(errorData.detail.message || 'Upload limit reached');
        err.code = errorData.detail.code;
        err.details = errorData.detail;
        err.status = 402;
        throw err;
      }
      throw new Error(errorData.detail || 'Upload failed');
    }

    return response.json();
  }

  async getUploads(): Promise<Upload[]> {
    const response = await fetch(`${this.baseURL}/uploads`, {
      headers: this.getHeaders(true),
    });

    if (!response.ok) {
      throw new Error('Failed to get uploads');
    }

    return response.json();
  }

  async getUploadProgress(uploadId: number): Promise<any> {
    const response = await fetch(`${this.baseURL}/uploads/${uploadId}/progress`, {
      headers: this.getHeaders(true),
    });

    if (!response.ok) {
      throw new Error('Failed to get progress');
    }

    return response.json();
  }

  async getUploadClusters(uploadId: number): Promise<Cluster[]> {
    const response = await fetch(`${this.baseURL}/uploads/${uploadId}/clusters`, {
      headers: this.getHeaders(true),
    });

    if (!response.ok) {
      throw new Error('Failed to get clusters');
    }

    return response.json();
  }

  async getCluster(clusterId: number): Promise<ClusterDetail> {
    const response = await fetch(`${this.baseURL}/clusters/${clusterId}`, {
      headers: this.getHeaders(true),
    });

    if (!response.ok) {
      throw new Error('Failed to get cluster details');
    }

    return response.json();
  }

  // Ad-hoc prompt experimentation — ephemeral, nothing here is persisted.
  // `payload.model` is a style persona, not a real model swap (see backend
  // playground_run docstring) — `model_used` in the response is the real
  // model that actually ran, `persona_used` is what you picked.
  async runPlayground(
    clusterId: number,
    payload: { prompt: string; model?: string; temperature?: number; max_tokens?: number }
  ): Promise<{ output: string; model_used: string; persona_used: string | null; temperature_used: number }> {
    const response = await fetch(`${this.baseURL}/clusters/${clusterId}/playground`, {
      method: 'POST',
      headers: this.getHeaders(true),
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || 'Playground run failed');
    }

    return response.json();
  }

  // Analytics endpoint
  async getAnalytics(): Promise<AnalyticsData> {
    const response = await fetch(`${this.baseURL}/analytics`, {
      headers: this.getHeaders(true),
    });

    if (!response.ok) {
      throw new Error('Failed to get analytics');
    }

    return response.json();
  }

  // Health check
  async healthCheck(): Promise<{ status: string; version: string }> {
    const response = await fetch(`${this.baseURL}/health`);
    return response.json();
  }

  // ── Proactive alerting settings ──────────────────────────────────────
  async getAlertSettings(): Promise<{
    alert_webhook_url: string | null;
    alerts_enabled: boolean;
    email_alerts_enabled: boolean;
    weekly_digest_enabled: boolean;
  }> {
    const response = await fetch(`${this.baseURL}/settings/alerts`, {
      headers: this.getHeaders(true),
    });
    if (!response.ok) throw new Error('Failed to load alert settings');
    return response.json();
  }

  async updateAlertSettings(payload: {
    alert_webhook_url?: string | null;
    alerts_enabled?: boolean;
    email_alerts_enabled?: boolean;
    weekly_digest_enabled?: boolean;
  }): Promise<{
    alert_webhook_url: string | null;
    alerts_enabled: boolean;
    email_alerts_enabled: boolean;
    weekly_digest_enabled: boolean;
  }> {
    const response = await fetch(`${this.baseURL}/settings/alerts`, {
      method: 'PUT',
      headers: this.getHeaders(true),
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || 'Failed to save alert settings');
    }
    return response.json();
  }

  async testAlertWebhook(): Promise<{ status: string }> {
    const response = await fetch(`${this.baseURL}/settings/alerts/test`, {
      method: 'POST',
      headers: this.getHeaders(true),
    });
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || 'Test alert failed');
    }
    return response.json();
  }

  async testAlertEmail(): Promise<{ status: string }> {
    const response = await fetch(`${this.baseURL}/settings/alerts/test-email`, {
      method: 'POST',
      headers: this.getHeaders(true),
    });
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || 'Test email failed');
    }
    return response.json();
  }

  // ── Browser push notifications (Web Push, self-hosted VAPID) ────────
  async subscribePush(subscription: PushSubscriptionJSON): Promise<{ status: string }> {
    const response = await fetch(`${this.baseURL}/push/subscribe`, {
      method: 'POST',
      headers: this.getHeaders(true),
      body: JSON.stringify(subscription),
    });
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || 'Failed to save push subscription');
    }
    return response.json();
  }

  async unsubscribePush(endpoint: string): Promise<{ status: string }> {
    const response = await fetch(`${this.baseURL}/push/unsubscribe`, {
      method: 'POST',
      headers: this.getHeaders(true),
      body: JSON.stringify({ endpoint }),
    });
    if (!response.ok) throw new Error('Failed to remove push subscription');
    return response.json();
  }

  async getPushStatus(): Promise<{ subscribed_devices: number }> {
    const response = await fetch(`${this.baseURL}/push/status`, {
      headers: this.getHeaders(true),
    });
    if (!response.ok) throw new Error('Failed to load push status');
    return response.json();
  }

  async testPush(): Promise<{ status: string; devices: number }> {
    const response = await fetch(`${this.baseURL}/push/test`, {
      method: 'POST',
      headers: this.getHeaders(true),
    });
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || 'Test push failed');
    }
    return response.json();
  }

  // ── Fix verification / triage / cross-platform ──────────────────────
  async getTriageQueue(uploadId: number): Promise<{ upload_id: number; clusters: any[] }> {
    const response = await fetch(`${this.baseURL}/uploads/${uploadId}/triage-queue`, {
      headers: this.getHeaders(true),
    });
    if (!response.ok) throw new Error('Failed to load triage queue');
    return response.json();
  }

  async getCrossPlatformMatches(uploadId: number): Promise<{ upload_id: number; matches: any[] }> {
    const response = await fetch(`${this.baseURL}/uploads/${uploadId}/cross-platform-matches`, {
      headers: this.getHeaders(true),
    });
    if (!response.ok) throw new Error('Failed to load cross-platform matches');
    return response.json();
  }

  // ── Cluster status (resolve / reopen / assign) ───────────────────────
  async updateClusterStatus(
    clusterId: number,
    status: 'fresh_roast' | 'assigned' | 'in_progress' | 'resolved' | 'wont_fix'
  ): Promise<{ id: number; status: string; resolved_at: string | null }> {
    const response = await fetch(`${this.baseURL}/clusters/${clusterId}/status`, {
      method: 'PATCH',
      headers: this.getHeaders(true),
      body: JSON.stringify({ status }),
    });
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || 'Failed to update cluster status');
    }
    return response.json();
  }

  // ── Auto-generated repro test stub ───────────────────────────────────
  async generateTestStub(clusterId: number): Promise<{ cluster_id: number; code: string }> {
    const response = await fetch(`${this.baseURL}/clusters/${clusterId}/test-stub`, {
      method: 'POST',
      headers: this.getHeaders(true),
    });
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || 'Test stub generation failed');
    }
    return response.json();
  }
}

// Export singleton instance
export const apiClient = new APIClient();

// Export class for testing
export default APIClient;
