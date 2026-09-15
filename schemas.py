# schemas.py
from __future__ import annotations
from typing import List, Optional, Literal
from pydantic import BaseModel, Field


Color = Literal["blue", "green", "orange", "red", "purple"]
BlockType = Literal["list", "paragraphs"]
Criticality = Literal["high", "medium", "low"]


class Meta(BaseModel):
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    report_type: str = "weekly"


class Metric(BaseModel):
    id: str
    label: str
    value: float | int | str
    unit: Optional[str] = None
    sub: Optional[str] = None
    color: Color = "blue"
    icon: Optional[str] = None
    anchor: Optional[str] = None


class Item(BaseModel):
    text: str
    strong: Optional[str] = None


class Block(BaseModel):
    id: str
    icon: Optional[str] = None
    title: str
    type: BlockType = "paragraphs"
    items: List[Item] = Field(default_factory=list)


class Section(BaseModel):
    id: str
    num: int
    icon: Optional[str] = None
    title: str
    blocks: List[Block] = Field(default_factory=list)


class SmiCard(BaseModel):
    title: str
    desc: Optional[str] = None
    link: Optional[str] = None
    reaction: Optional[str] = None


class SmiGroup(BaseModel):
    criticality: Criticality
    label: str
    cards: List[SmiCard] = Field(default_factory=list)


class Smi(BaseModel):
    digest_period: Optional[str] = None
    groups: List[SmiGroup] = Field(default_factory=list)


class Report(BaseModel):
    meta: Meta
    metrics: List[Metric] = Field(default_factory=list)
    sections: List[Section] = Field(default_factory=list)
    smi: Optional[Smi] = None