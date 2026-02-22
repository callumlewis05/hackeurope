"""
Backfill script to populate categories and mistake_types for existing interactions.
Uses the configured LLM to classify interactions that have risk factors but no classification.
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

# Add backend root to sys.path
current_file = Path(__file__).resolve()
backend_root = current_file.parent.parent
sys.path.append(str(backend_root))

from dotenv import load_dotenv
from sqlalchemy import (
    select as sa_select,  # ✅ FIX 1: use native SA select for selectinload
)
from sqlalchemy.orm import selectinload
from sqlmodel import select

from src.config import llm
from src.db import (
    Category,
    Interaction,
    MistakeType,
    get_session,
)
from src.graph import _extract_text, _parse_json_response

load_dotenv()

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def classify_interaction(interaction: Interaction) -> tuple[list[str], list[str]]:
    """Classify a single interaction using the LLM."""
    domain = interaction.domain
    intent = interaction.intent_data
    risks = interaction.risk_factors

    if not risks:
        return [], []

    prompt = f"""You are an AI classifier for a neurodivergent support agent.

Interaction Context:
Domain: {domain}
Intent: {intent}

Identified Risks:
{risks}

Task:
1. Classify the interaction into one or more of these CATEGORIES:
   [electronics, travel, groceries, clothing, other]

2. Classify the risks into one or more of these MISTAKE TYPES:
   [double booking, impulse spending, date mixup, conflicting event, other]

Output JSON ONLY:
{{
  "categories": ["string"],
  "mistake_types": ["string"]
}}
"""

    if llm is None:
        logger.warning("No LLM configured, skipping classification.")
        return [], []

    try:
        response = await llm.ainvoke(prompt)
        text = _extract_text(response.content)
        data = _parse_json_response(text)
        return data.get("categories", []), data.get("mistake_types", [])
    except Exception as e:
        logger.error(f"LLM classification failed for interaction {interaction.id}: {e}")
        return [], []


def get_or_create_category(session, name: str, cache: dict[str, Category]) -> Category:
    if name in cache:
        return cache[name]
    cat = session.exec(select(Category).where(Category.name == name)).first()
    if not cat:
        cat = Category(name=name)
        session.add(cat)
        session.flush()
        session.refresh(cat)
    cache[name] = cat
    return cat


def get_or_create_mistake_type(
    session, name: str, cache: dict[str, MistakeType]
) -> MistakeType:
    if name in cache:
        return cache[name]
    mt = session.exec(select(MistakeType).where(MistakeType.name == name)).first()
    if not mt:
        mt = MistakeType(name=name)
        session.add(mt)
        session.flush()
        session.refresh(mt)
    cache[name] = mt
    return mt


async def main():
    logger.info("Starting backfill for categories and mistake types...")

    if not llm:
        logger.error("LLM not configured. Cannot proceed with backfill.")
        return

    updated_count = 0
    skipped_count = 0
    error_count = 0

    # ✅ FIX 2: Fetch only IDs in the first session, then process each
    # interaction in its own isolated session. This prevents a single
    # rollback from poisoning the entire session and causing
    # DetachedInstanceError on subsequent iterations.
    with get_session() as session:
        all_ids = session.exec(select(Interaction.id)).all()

    logger.info(f"Found {len(all_ids)} total interactions to inspect.")

    # Per-interaction caches survive across sessions (name -> id lookup)
    category_cache: dict[str, Category] = {}
    mistake_cache: dict[str, MistakeType] = {}

    for i, interaction_id in enumerate(all_ids):
        try:
            # ✅ FIX 3: Each interaction gets its own session so a failure/
            # rollback on one never affects another.
            with get_session() as session:
                # ✅ FIX 4: Use session.execute() + scalars() so selectinload
                # options are honoured. SQLModel's session.exec() does not
                # reliably propagate loader options in all versions.
                result = session.execute(
                    sa_select(Interaction)
                    .where(Interaction.id == interaction_id)
                    .options(selectinload(Interaction.categories))
                    .options(selectinload(Interaction.mistake_types))
                )
                interaction = result.scalars().first()

                if interaction is None:
                    logger.warning(f"Interaction {interaction_id} not found, skipping.")
                    skipped_count += 1
                    continue

                # Skip if no risks
                if not interaction.risk_factors:
                    skipped_count += 1
                    continue

                # Skip if already classified
                if interaction.categories or interaction.mistake_types:
                    skipped_count += 1
                    continue

                logger.info(
                    f"[{i + 1}/{len(all_ids)}] Backfilling interaction {interaction.id}..."
                )

                # Classify via LLM
                cats, mistakes = await classify_interaction(interaction)

                if not cats and not mistakes:
                    logger.warning(
                        f"  -> No classifications returned for {interaction.id}"
                    )
                    skipped_count += 1
                    continue

                logger.info(f"  -> Cats: {cats}, Mistakes: {mistakes}")

                # Link categories
                for c_name in cats:
                    c_obj = get_or_create_category(session, c_name, category_cache)
                    if c_obj not in interaction.categories:
                        interaction.categories.append(c_obj)

                # Link mistake types
                for m_name in mistakes:
                    m_obj = get_or_create_mistake_type(session, m_name, mistake_cache)
                    if m_obj not in interaction.mistake_types:
                        interaction.mistake_types.append(m_obj)

                session.add(interaction)
                # ✅ FIX 5: No manual session.commit() here — get_session()
                # commits automatically on clean exit of the `with` block.

                updated_count += 1

            # Rate-limit LLM calls outside the session (no DB lock held during sleep)
            await asyncio.sleep(0.2)

        except Exception as e:
            logger.exception(f"Error processing interaction {interaction_id}: {e}")
            error_count += 1
            # ✅ FIX 6: No manual session.rollback() — the `with get_session()`
            # block already rolls back on any unhandled exception before re-raising.
            # Since we catch here, the session was already cleaned up on exit.

    logger.info("Backfill complete.")
    logger.info(f"Updated:  {updated_count}")
    logger.info(f"Skipped:  {skipped_count}")
    logger.info(f"Errors:   {error_count}")


if __name__ == "__main__":
    asyncio.run(main())
