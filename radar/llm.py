import json
from typing import Literal

import anthropic
import duckdb
import pyarrow as pa
from pydantic import BaseModel, ConfigDict, Field, model_validator

from radar.common import DATA, ROOT, config

CLASSIFY_MODEL = "claude-haiku-5-5"
SCORE_MODEL = "claude-sonnet-5-5"
FALLBACK_BETA = "server-side-fallback-2026-07-01"

Category = Literal[tuple(config("taxonomy")["categories"])]
ItemType = Literal[tuple(config("taxonomy")["item_types"])]
SiteTag = Literal[(*config("taxonomy")["site_tags"], "new-tag-candidate", "none")]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Classification(Strict):
    is_relevant: bool = Field(
        description="True only if useful to analytics/data engineers or AI-for-data "
        "practitioners. Spam, star-farmed repos, consumer AI gossip -> false."
    )
    category: Category
    primary_tag: SiteTag
    item_type: ItemType
    source_kind: Literal["primary", "secondary"] = Field(
        description="primary = official docs, release notes, specs, papers, the "
        "project's own repo; secondary = commentary, threads, newsletters."
    )
    topic_key: str = Field(
        description="2-5 word lowercase kebab-case label for the specific topic, "
        "reusable across items, e.g. 'dbt-fusion-engine', 'mcp-warehouse-servers'."
    )


class ClusterAssignment(Strict):
    topic_key: str
    cluster_key: str = Field(description="lowercase kebab-case, 2-5 words")
    cluster_label: str = Field(description="human-readable name, max 8 words")


class ClusterResult(Strict):
    assignments: list[ClusterAssignment]


class TopicScore(Strict):
    audience_relevance: int = Field(description="0-10")
    practical_applicability: int = Field(description="0-10")
    durability: int = Field(description="0-10")
    gap: int = Field(description="0-10")
    covered_by: str = Field(description="Existing post/backlog title or ''")
    verdict: Literal["Write now", "Watch", "Skip"]
    why_it_matters: str
    intended_reader: str
    reader_outcome: str = Field(description="Completes: 'the reader leaves able to...'")
    post_angle: str
    post_format: Literal["tutorial", "build log", "comparison", "opinion", "explainer"]
    example_scenario: str = Field(description="Fictional, non-German, non-retail")
    titles: list[str] = Field(description="2-3 alternatives")
    linkedin_hook: str
    primary_sources: list[str] = Field(description="URLs copied from the evidence")

    @model_validator(mode="after")
    def clamp(self):
        for f in ("audience_relevance", "practical_applicability", "durability", "gap"):
            setattr(self, f, max(0, min(10, getattr(self, f))))
        self.titles = self.titles[:3]
        return self


def json_schema(model: type[BaseModel]) -> dict:
    def strip(node):
        if isinstance(node, dict):
            for key in ("title", "minimum", "maximum", "minItems", "maxItems"):
                node.pop(key, None)
            for v in node.values():
                strip(v)
        elif isinstance(node, list):
            for v in node:
                strip(v)
        return node

    return {"type": "json_schema", "schema": strip(model.model_json_schema())}


def client() -> anthropic.Anthropic:
    return anthropic.Anthropic()


def first_text(message) -> str:
    return next(b.text for b in message.content if b.type == "text")


def call_structured(
    model_cls: type[BaseModel],
    system: list[dict],
    user: str,
    effort: str = "medium",
    max_tokens: int = 16000,
):
    msg = client().beta.messages.create(
        model=SCORE_MODEL,
        max_tokens=max_tokens,
        betas=[FALLBACK_BETA],
        fallbacks="default",
        system=system,
        messages=[{"role": "user", "content": user}],
        output_config={"effort": effort, "format": json_schema(model_cls)},
    )
    if msg.stop_reason == "refusal":
        raise RuntimeError(f"refused: {msg.stop_details}")
    if msg.stop_reason == "max_tokens":
        raise RuntimeError("hit max_tokens")
    return model_cls.model_validate(json.loads(first_text(msg))), msg.usage


def db(read_only: bool = True) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(str(DATA / "radar.duckdb"), read_only=read_only)
    con.execute(f"SET file_search_path = '{ROOT / 'dbt'}'")
    return con


CLASSIFIED_SCHEMA = pa.schema(
    [
        ("item_id", pa.string()),
        ("is_relevant", pa.bool_()),
        ("category", pa.string()),
        ("primary_tag", pa.string()),
        ("item_type", pa.string()),
        ("source_kind", pa.string()),
        ("topic_key", pa.string()),
        ("model", pa.string()),
        ("classified_at", pa.timestamp("us", tz="UTC")),
    ]
)

CLUSTER_SCHEMA = pa.schema(
    [
        ("topic_key", pa.string()),
        ("cluster_key", pa.string()),
        ("cluster_label", pa.string()),
        ("clustered_at", pa.timestamp("us", tz="UTC")),
    ]
)
