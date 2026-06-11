from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from polyberg.config import repo_path
from polyberg.loaders import LoaderError, parse_model, prefer_local_overlay
from polyberg.models import MarketRegistry, Side, StrictModel

Action = Literal["BUY", "SELL"]
Purpose = Literal["cash_rebuild", "derisk", "runner"]


class Rung(StrictModel):
    price: float = Field(gt=0, lt=1)
    shares: float = Field(gt=0)


class Tags(StrictModel):
    purpose: Purpose | None = None
    notes: str | None = None


class Ladder(StrictModel):
    market_id: str
    outcome: Side
    action: Action
    rungs: list[Rung] = Field(min_length=1)
    tags: Tags | None = None

    @model_validator(mode="after")
    def no_duplicate_rung_prices(self) -> Ladder:
        prices = [r.price for r in self.rungs]
        seen: set[float] = set()
        duplicates: list[float] = []
        for p in prices:
            if p in seen:
                duplicates.append(p)
            seen.add(p)
        if duplicates:
            raise ValueError(
                f"duplicate rung prices in {self.market_id}/{self.outcome}/{self.action}: "
                + ", ".join(str(p) for p in duplicates)
            )
        return self


class MatchingConfig(StrictModel):
    price_tolerance: float = Field(default=0.0005, ge=0)
    shares_tolerance: float = Field(default=1.0, ge=0)


class TargetLadders(StrictModel):
    schema_version: str = "1"
    matching: MatchingConfig = Field(default_factory=MatchingConfig)
    ladders: list[Ladder] = Field(default_factory=list)


def _validate_against_registry(targets: TargetLadders, registry: MarketRegistry) -> None:
    registry_by_id = {m.market_id: m for m in registry.markets}
    errors: list[str] = []
    for ladder in targets.ladders:
        market = registry_by_id.get(ladder.market_id)
        if market is None:
            errors.append(f"unknown market_id in ladder: {ladder.market_id!r}")
            continue
        token_id = market.yes_token_id if ladder.outcome == "YES" else market.no_token_id
        if not token_id:
            field = "yes_token_id" if ladder.outcome == "YES" else "no_token_id"
            errors.append(
                f"missing {field} for {ladder.market_id}/{ladder.outcome} — "
                "add the token ID to the registry before creating a ladder"
            )
    if errors:
        raise LoaderError(
            "target_ladders validation failed:\n"
            + "\n".join(f"  - {e}" for e in errors)
        )


def load_target_ladders(
    path: Path | None = None,
    registry: MarketRegistry | None = None,
) -> TargetLadders:
    target_path = prefer_local_overlay(path or repo_path("live", "target_ladders.yaml"))
    targets = parse_model(TargetLadders, target_path)
    if registry is not None:
        _validate_against_registry(targets, registry)
    return targets
