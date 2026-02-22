export interface UserProfileResponse {
  id: string;
  email: string;
  name: string;
  avatar_url: string;
  created_at: string;
}

export interface CalendarResponse {
  id: string;
  user_id: string;
  name: string;
  ical_url: string;
  created_at: string;
}

export interface ApiValidationError {
  detail: Array<{
    loc: Array<string | number>;
    msg: string;
    type: string;
    input?: unknown;
    ctx?: Record<string, unknown>;
  }>;
}

export interface InterventionResponse {
  id: string;
  domain: string;
  title: string;
  intent_type: string;
  intent_data: Record<string, unknown>;
  risk_factors: string[];
  intervention_message: string;
  was_intervened: boolean;
  compute_cost: number;
  feedback: boolean; // true if blocked, false if allowed
  money_saved: number;
  platform_fee: number;
  hour_of_day: number;
  analyzed_at: string;
}

export interface InterventionListResponse {
  items: InterventionResponse[];
  total: number;
  limit: number;
  offset: number;
}

export interface InterventionDomainStatsResponse {
  domain: string;
  total: number;
  intervened: number;
  money_saved: number;
}

export interface InterventionStatsResponse {
  total_analyses: number;
  total_interventions: number;
  total_money_saved: number;
  total_compute_cost: number;
  total_platform_fees: number;
  by_domain: InterventionDomainStatsResponse[];
}

export interface EmailStatusResponse {
  connected: boolean;
  provider: string | null;
  email_address: string | null;
  has_refresh_token: boolean;
  connected_at: string | null;
}
