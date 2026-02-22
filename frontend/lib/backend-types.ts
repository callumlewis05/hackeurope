export type Uuid = string;
export type IsoTimestamp = string;
export type IsoDate = string;
export type IsoTime = string;

export type JsonPrimitive = string | number | boolean | null;
export type JsonValue = JsonPrimitive | { [key: string]: JsonValue } | JsonValue[];

export interface UserCalendarRow {
  id: Uuid;
  user_id: Uuid;
  name: string;
  ical_url: string;
  created_at: IsoTimestamp;
}

export interface IntentAnalysisRow {
  id: Uuid;
  user_id: Uuid;
  domain: string;
  intent_type: string;
  intent_data: JsonValue;
  risk_factors: JsonValue;
  intervention_message: string;
  was_intervened: boolean;
  compute_cost: number;
  money_saved: number;
  platform_fee: number;
  hour_of_day: number;
  analyzed_at: IsoTimestamp;
}

export interface PurchaseRow {
  id: Uuid;
  user_id: Uuid;
  item_name: string;
  category: string;
  price: number;
  currency: string;
  quantity: number;
  domain: string;
  product_url: string;
  returned: boolean;
  purchased_at: IsoTimestamp;
}

export interface ProfileRow {
  id: Uuid;
  email: string;
  name: string;
  avatar_url: string;
  created_at: IsoTimestamp;
}

export interface FlightBookingRow {
  id: Uuid;
  user_id: Uuid;
  airline: string;
  flight_number: string;
  departure_date: IsoDate;
  departure_time: IsoTime;
  departure_airport: string;
  arrival_time: IsoTime;
  arrival_airport: string;
  destination: string;
  price_amount: number;
  price_currency: string;
  leg: string;
  trip_id: Uuid;
  booked_at: IsoTimestamp;
}

export interface UserRow {
  id: Uuid;
  email: string;
  name: string;
  avatar_url: string;
  created_at: IsoTimestamp;
}

// Two table keys are inferred from the column sets in your schema paste.
export type BackendTableRows = {
  user_calendars: UserCalendarRow;
  intent_analyses: IntentAnalysisRow;
  purchases: PurchaseRow;
  profiles: ProfileRow;
  flight_bookings: FlightBookingRow;
  users: UserRow;
};

export type BackendRow = BackendTableRows[keyof BackendTableRows];
