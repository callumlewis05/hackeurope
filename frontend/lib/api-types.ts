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
