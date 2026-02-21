# HackEurope Agent Backend

AI guardian agent that protects neurodivergent users from impulsive or mistaken online actions. Built with **FastAPI** + **LangGraph** + **Qwen3-235B** (hosted on Crusoe Cloud) + **Supabase** (persistence).

A Chrome Extension captures user intent (e.g. booking a flight, adding items to cart) and sends it to this backend. The agent cross-references the action against calendar events, past bookings, purchase history, and spending patterns — then returns an empathetic intervention if risks are detected. Every analysis run and confirmed action is persisted to Supabase so future queries get smarter over time.

---

## Architecture

The project follows an **MVC-style architecture** with a **Strategy pattern** for domain-specific logic and a **Repository pattern** for database access:

```
backend/
├── src/
│   ├── main.py                          # FastAPI app init, CORS, router mounting
│   ├── config.py                        # LLM setup, env vars, cost constants
│   │
│   ├── models/                          # M — Data layer
│   │   ├── schemas.py                   # Pydantic request/response models
│   │   └── state.py                     # LangGraph AgentState TypedDict
│   │
│   ├── controllers/                     # C — HTTP layer
│   │   └── analyze_controller.py        # POST /api/analyze route handler
│   │
│   ├── db/                              # Repository layer — Supabase persistence
│   │   ├── client.py                    # Supabase client singleton
│   │   ├── flight_repo.py              # flight_bookings table queries & writes
│   │   ├── purchase_repo.py            # purchases table queries & writes
│   │   └── interaction_repo.py         # interactions table queries & writes
│   │
│   ├── domains/                         # Strategy pattern — domain-specific logic
│   │   ├── base.py                      # Abstract DomainHandler interface
│   │   ├── registry.py                  # Domain string → handler lookup
│   │   ├── flight.py                    # Skyscanner / flight booking handler
│   │   ├── shopping.py                  # Amazon / e-commerce handler
│   │   └── fallback.py                  # Generic handler for unknown domains
│   │
│   └── graph/                           # V — LangGraph pipeline (the "view" of the AI)
│       ├── nodes.py                     # Domain-agnostic node functions
│       └── builder.py                   # Graph wiring and compilation
│
├── pyproject.toml
└── .env                                 # CRUSOE_API_KEY, SUPABASE_URL, SUPABASE_KEY (not committed)
```

### How It Works

```
Chrome Extension
       │
       ▼
  POST /api/analyze
       │
       ▼
┌─────────────────┐
│  Context Router  │ ── Determines which data sources are needed
└────────┬────────┘      (rule-based, no LLM call)
         │ fans out (parallel)
   ┌─────┼──────────────┐
   ▼     ▼              ▼
Calendar Bank    Purchase History
Fetcher  Fetcher      Fetcher
(±3 day  (Supabase:   (Supabase:
window)  flight_      similar items,
         bookings)    category matches)
   │     │              │
   └─────┼──────────────┘
         │ fans in
         ▼
┌─────────────────┐
│     Audit       │ ── LLM cross-references intent vs. context
└────────┬────────┘    (conflicts, fatigue, double-booking,
         │              impulse buys, budget concerns)
    risks found?
    ┌────┴────┐
    ▼         ▼
Drafting   (skip)
    │         │
    └────┬────┘
         ▼
┌─────────────────┐
│   Economics      │ ── Compute cost, money saved, platform fee
└────────┬────────┘
         ▼
┌─────────────────┐
│    Storage       │ ── Persist booking/purchase + interaction
└────────┬────────┘    to Supabase for future queries
         │
         ▼
   JSON Response
```

### Adding a New Domain

1. Create `src/domains/your_domain.py`
2. Subclass `DomainHandler` and implement all abstract methods:
   - `context_requirements()` — which data sources to fetch
   - `get_mock_calendar_events()` / `get_mock_bank_transactions()` / `get_mock_purchase_history()` — data fetching (DB-backed with mock fallback)
   - `build_audit_prompt()` / `build_drafting_prompt()` — LLM prompts
   - `extract_item_price()` / `extract_hour_of_day()` — economics helpers
   - `store()` — persist confirmed actions to Supabase
3. Call `register_domain("yourdomain.com", YourHandler())` at module level
4. Import the module in `src/domains/registry.py`'s `_bootstrap()` function

That's it — the graph, nodes, and controller are fully domain-agnostic.

---

## Supported Domains

### Flight Booking — `skyscanner.net` / `skyscanner.com`

**Data sources checked:**
- Calendar events ±3 days around each flight leg (outbound + return)
- Existing flight bookings from Supabase near the same dates (±3 day window)
- Previous flights to the same destination (last 6 months)

**Risks detected:**
- Schedule conflicts (calendar events overlapping with flights, including airport travel time)
- Double bookings (already booked a flight to the same destination around the same dates)
- Fatigue / exhaustion (arriving late then early commitment, red-eye + work, short turnarounds)
- Too-early / too-late flights (departures before 06:00, arrivals after 23:00)
- Wasted money (already paid for a similar trip covering overlapping dates)

**Stored after analysis:**
- Each flight leg (outbound + return) → `flight_bookings` table
- Full interaction record → `interactions` table

**Example payload:**

```json
{
  "user_id": "demo_user",
  "domain": "skyscanner.net",
  "intent": {
    "type": "flight_booking",
    "outbound": {
      "airline": "Ryanair",
      "flight_number": "FR5271",
      "departure_date": "2026-04-25",
      "departure_time": "14:15",
      "departure_airport": "MAN Manchester",
      "arrival_time": "17:35",
      "arrival_airport": "BCN Barcelona",
      "duration": "2h 20m",
      "stops": "Direct"
    },
    "return": {
      "airline": "Ryanair",
      "flight_number": "FR6597",
      "departure_date": "2026-04-29",
      "departure_time": "12:35",
      "departure_airport": "BCN Barcelona",
      "arrival_time": "14:10",
      "arrival_airport": "MAN Manchester",
      "duration": "2h 35m",
      "stops": "Direct"
    },
    "selected_price": {
      "amount": 38,
      "currency": "GBP",
      "provider": "Ryanair"
    }
  }
}
```

### Shopping / E-Commerce — `amazon.co.uk` / `amazon.com`

**Data sources checked:**
- Recent purchases from Supabase (last 90 days)
- Similar items by name keywords and category (last 365 days)
- Category-level purchase counts (impulse pattern detection, last 180 days)
- 30-day spending totals (budget concern analysis)

**Risks detected:**
- Duplicate purchases (already own the same or very similar item)
- Impulse buying (multiple purchases in same category in short window, late-night shopping)
- Unnecessary upgrades (previous-gen version already owned, e.g. XM4 → XM5)
- Budget concerns (cart total high relative to recent 30-day spending)

**Stored after analysis:**
- Each item in cart → `purchases` table
- Full interaction record → `interactions` table

**Example payload:**

```json
{
  "user_id": "demo_user",
  "domain": "amazon.co.uk",
  "intent": {
    "type": "product_purchase",
    "items": [
      {
        "name": "Sony WH-1000XM5 Noise Cancelling Headphones",
        "price": 279.99,
        "currency": "GBP",
        "quantity": 1,
        "category": "Electronics",
        "url": "https://amazon.co.uk/dp/B0BSHWBGYS"
      }
    ],
    "cart_total": {
      "amount": 279.99,
      "currency": "GBP"
    },
    "delivery": {
      "method": "Prime Next Day",
      "estimated_date": "2026-04-26"
    }
  }
}
```

---

## API Reference

### `POST /api/analyze`

Analyze a user intent and return a risk assessment.

**Request body:** See example payloads above.

**Response:**

```json
{
  "is_safe": false,
  "intervention_message": "🎧 Heads up — you already own the XM4 headphones and recently bought another pair of noise-cancelling cans. Maybe sleep on this one?",
  "risk_factors": [
    "User already owns Sony WH-1000XM4 headphones purchased on 2026-03-10",
    "User purchased Anker Soundcore Life Q35 headphones just 3 weeks ago"
  ],
  "domain": "amazon.co.uk",
  "economics": {
    "compute_cost": 0.000225,
    "money_saved": 279.99,
    "platform_fee": 2.0,
    "hour_of_day": 23
  }
}
```

### `GET /health`

Liveness probe.

```json
{
  "status": "HackEurope LangGraph Engine Online"
}
```

---

## Setup

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager
- A [Supabase](https://supabase.com) project

### Install

```bash
cd backend
uv sync
```

### Environment Variables

Create a `.env` file in the `backend/` directory:

```env
# Required
CRUSOE_API_KEY=your_crusoe_api_key_here
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_supabase_anon_or_service_key

# Optional overrides
LLM_BASE_URL=https://hackeurope.crusoecloud.com/v1/
LLM_MODEL=NVFP4/Qwen3-235B-A22B-Instruct-2507-FP4
CORS_ORIGINS=*
COST_PER_MILLION_TOKENS=0.15
ESTIMATED_TOKENS_PER_RUN=1500
PLATFORM_FEE=2.00
```

### Database Setup

Run the following SQL in your Supabase SQL Editor to create the required tables:

```sql
-- ============================================================
-- 1. Flight Bookings
-- ============================================================
create table if not exists flight_bookings (
    id                uuid primary key default gen_random_uuid(),
    user_id           text not null,
    airline           text,
    flight_number     text,
    departure_date    date not null,
    departure_time    time,
    departure_airport text,
    arrival_time      time,
    arrival_airport   text,
    destination       text,
    price_amount      numeric(10,2),
    price_currency    text default 'GBP',
    leg               text check (leg in ('outbound', 'return')),
    trip_id           uuid,
    booked_at         timestamptz default now()
);

create index if not exists idx_flight_bookings_user
    on flight_bookings (user_id);
create index if not exists idx_flight_bookings_dates
    on flight_bookings (user_id, departure_date);

-- ============================================================
-- 2. Purchases
-- ============================================================
create table if not exists purchases (
    id              uuid primary key default gen_random_uuid(),
    user_id         text not null,
    item_name       text not null,
    category        text,
    price           numeric(10,2),
    currency        text default 'GBP',
    quantity        integer default 1,
    domain          text,
    product_url     text,
    returned        boolean default false,
    purchased_at    timestamptz default now()
);

create index if not exists idx_purchases_user
    on purchases (user_id);
create index if not exists idx_purchases_user_category
    on purchases (user_id, category);
create index if not exists idx_purchases_user_date
    on purchases (user_id, purchased_at);

-- ============================================================
-- 3. Interactions (audit trail)
-- ============================================================
create table if not exists interactions (
    id                      uuid primary key default gen_random_uuid(),
    user_id                 text not null,
    domain                  text not null,
    intent_type             text,
    intent_data             jsonb not null,
    risk_factors            jsonb default '[]'::jsonb,
    intervention_message    text,
    was_intervened          boolean default false,
    compute_cost            numeric(10,6),
    money_saved             numeric(10,2),
    platform_fee            numeric(10,2),
    hour_of_day             smallint,
    analyzed_at             timestamptz default now()
);

create index if not exists idx_interactions_user
    on interactions (user_id);
create index if not exists idx_interactions_user_domain
    on interactions (user_id, domain);
create index if not exists idx_interactions_analyzed
    on interactions (analyzed_at);
```

### Run

```bash
uv run uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

### Test with cURL

**Flight booking (Skyscanner):**

```bash
curl -X POST http://localhost:8000/api/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "demo_user",
    "domain": "skyscanner.net",
    "intent": {
      "type": "flight_booking",
      "outbound": {
        "airline": "Ryanair",
        "flight_number": "FR5271",
        "departure_date": "2026-04-25",
        "departure_time": "14:15",
        "departure_airport": "MAN Manchester",
        "arrival_time": "17:35",
        "arrival_airport": "BCN Barcelona"
      },
      "selected_price": {"amount": 38, "currency": "GBP"}
    }
  }'
```

**Shopping (Amazon):**

```bash
curl -X POST http://localhost:8000/api/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "demo_user",
    "domain": "amazon.co.uk",
    "intent": {
      "type": "product_purchase",
      "items": [
        {
          "name": "Sony WH-1000XM5 Noise Cancelling Headphones",
          "price": 279.99,
          "currency": "GBP",
          "quantity": 1,
          "category": "Electronics"
        }
      ],
      "cart_total": {"amount": 279.99, "currency": "GBP"}
    }
  }'
```

---

## Requirements Checklist

| # | Requirement | Status | Implementation |
|---|-------------|--------|----------------|
| 1 | Look at current website (shopping, travel) | ✅ | Domain registry resolves handler from `domain` field |
| 2 | Get data of selected options at checkout | ✅ | Flexible `intent` payload accepted as `Dict[str, Any]` |
| 3 | Flights: calendar ±3 days around each leg | ✅ | `FlightDomainHandler._calendar_date_range()` computes window, filters events |
| 4 | Warn of conflicts, fatigue, too-early/too-late | ✅ | Audit prompt explicitly checks all 5 risk categories including fatigue and timing |
| 5 | Look at DB for similar flights / double booking | ✅ | `flight_repo.get_flights_near_dates()` + `get_flights_to_destination()` |
| 6 | Store booked flights into DB for future | ✅ | `storage_node` → `handler.store()` → `flight_repo.store_flight_booking()` |
| 7 | Shopping: purchase history / similar items from DB | ✅ | `purchase_repo.find_similar_items()` + `get_purchases_by_category()` + `get_spending_total()` |
| 8 | Warn about impulse purchase / double buying | ✅ | Audit prompt checks duplicates, impulse patterns, upgrades, and budget |
| 9 | Store bought items / interactions in DB | ✅ | `storage_node` → `handler.store()` → `purchase_repo.store_purchase()` + `interaction_repo.store_interaction()` |

---

## Tech Stack

| Component          | Technology                              |
| ------------------ | --------------------------------------- |
| Framework          | FastAPI                                 |
| AI Orchestration   | LangGraph                               |
| LLM                | Qwen3-235B-A22B (Crusoe Cloud)          |
| Database           | Supabase (PostgreSQL)                   |
| Validation         | Pydantic v2                             |
| Package Manager    | uv                                      |