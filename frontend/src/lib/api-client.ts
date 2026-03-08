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
}

export interface ClusterDetail extends Cluster {
  rca_title?: string;
  rca_hypothesis?: string;
  rca_steps?: string;
  rca_fix?: string;
  ai_analyzed?: boolean;
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
}

// Export singleton instance
export const apiClient = new APIClient();

// Export class for testing
export default APIClient;
