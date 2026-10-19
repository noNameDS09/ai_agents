"""Seed reference data (jurisdictions, license types) into the database."""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from compliance.models.organization import Jurisdiction
from agent_api.database import async_session, engine, Base as AgentBase
from compliance.models import ComplianceBase
from compliance.models.organization import Jurisdiction as CJurisdiction


async def seed():
    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(AgentBase.metadata.create_all)
        await conn.run_sync(ComplianceBase.metadata.create_all)

    async with async_session() as session:
        # Seed jurisdictions
        jurisdictions = [
            ("US-CA", "California", "US", "money_transmitter", "https://dfpi.ca.gov/"),
            ("US-NY", "New York", "US", "money_transmitter", "https://dfs.ny.gov/"),
            ("US-TX", "Texas", "US", "money_transmitter", "https://www.sml.texas.gov/"),
            ("US-FL", "Florida", "US", "money_transmitter", "https://flofr.gov/"),
            ("US-IL", "Illinois", "US", "money_transmitter", "https://idfpr.illinois.gov/"),
            ("US-FEDERAL", "Federal (US)", "US", "money_transmitter", "https://www.fincen.gov/"),
        ]
        for code, name, country, regime, url in jurisdictions:
            existing = await session.execute(
                __import__("sqlalchemy").select(CJurisdiction).where(CJurisdiction.code == code)
            )
            if existing.scalar_one_or_none() is None:
                session.add(CJurisdiction(code=code, name=name, country=country, regime=regime, regulator_url=url))
        await session.commit()
        print(f"Seeded {len(jurisdictions)} jurisdictions")


if __name__ == "__main__":
    asyncio.run(seed())