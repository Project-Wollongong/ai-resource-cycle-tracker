from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Index,
    text,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Stock(Base):
    __tablename__ = "stocks"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(10), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    exchange: Mapped[str] = mapped_column(String(20), default="ASX", server_default="ASX")
    trading_currency: Mapped[str] = mapped_column(String(3), default="AUD", server_default="AUD")
    listing_status: Mapped[str] = mapped_column(String(20), default="Unknown", server_default="Unknown")
    sector: Mapped[str | None] = mapped_column(String(120), nullable=True)
    business_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    pilot_universe_member: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    identity_history: Mapped[list["StockIdentity"]] = relationship(
        back_populates="stock", order_by="StockIdentity.id", lazy="selectin"
    )
    commodity: Mapped[str] = mapped_column(String(30))  # gold/copper/lithium/uranium/rare_earth
    stage: Mapped[str] = mapped_column(String(20), default="explorer")  # explorer/developer
    resource_score_override: Mapped[float | None] = mapped_column(Float, nullable=True)
    risk_score_override: Mapped[float | None] = mapped_column(Float, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    price_bars: Mapped[list["PriceBar"]] = relationship(back_populates="stock", cascade="all, delete-orphan")
    announcements: Mapped[list["Announcement"]] = relationship(back_populates="stock", cascade="all, delete-orphan")
    signals: Mapped[list["Signal"]] = relationship(back_populates="stock", cascade="all, delete-orphan")
    project_links: Mapped[list["StockProject"]] = relationship(back_populates="stock", cascade="all, delete-orphan")


class StockIdentity(Base):
    """Names and exchange-scoped tickers; [valid_from, valid_to), NULL = unknown."""

    __tablename__ = "stock_identities"
    __table_args__ = (
        CheckConstraint("kind IN ('ticker', 'company_name', 'alias')", name="ck_stock_identity_kind"),
        CheckConstraint("valid_to IS NULL OR valid_from IS NULL OR valid_to > valid_from", name="ck_stock_identity_dates"),
        CheckConstraint("NOT is_current OR (valid_to IS NULL AND kind != 'alias')", name="ck_stock_identity_current"),
        CheckConstraint("kind != 'ticker' OR exchange IS NOT NULL", name="ck_stock_identity_exchange"),
        Index("uq_stock_identity_current", "stock_id", "kind", unique=True, sqlite_where=text("is_current = 1")),
        Index("ix_stock_identity_lookup", "normalized_value", "kind", "exchange"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    value: Mapped[str] = mapped_column(String(160))
    normalized_value: Mapped[str] = mapped_column(String(160))
    exchange: Mapped[str | None] = mapped_column(String(20), nullable=True)
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(String(120), default="manual")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    stock: Mapped[Stock] = relationship(back_populates="identity_history")


class ProjectIdentity(Base):
    __tablename__ = "project_identities"
    __table_args__ = (CheckConstraint("kind IN ('name', 'alias')", name="ck_project_identity_kind"), Index("ix_project_identity_lookup", "normalized_value", "kind"))

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    value: Mapped[str] = mapped_column(String(160))
    normalized_value: Mapped[str] = mapped_column(String(160), index=True)
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(String(120), default="manual")
    project: Mapped["Project"] = relationship(back_populates="identity_history")


class ProjectRelationship(Base):
    __tablename__ = "project_relationships"
    __table_args__ = (CheckConstraint("effective_to IS NULL OR effective_from IS NULL OR effective_to > effective_from", name="ck_project_relationship_dates"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    relationship_type: Mapped[str] = mapped_column(String(40), default="owner")
    ownership_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    operator_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    effective_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    source: Mapped[str] = mapped_column(String(120), default="manual")
    source_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_excerpt: Mapped[str] = mapped_column(Text, default="")
    project: Mapped["Project"] = relationship(back_populates="relationship_history")


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_key: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    commodity: Mapped[str | None] = mapped_column(String(30), nullable=True)
    region: Mapped[str | None] = mapped_column(String(120), nullable=True)
    jurisdiction: Mapped[str | None] = mapped_column(String(80), nullable=True)
    stage: Mapped[str | None] = mapped_column(String(40), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    stock_links: Mapped[list["StockProject"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    identity_history: Mapped[list[ProjectIdentity]] = relationship(back_populates="project", cascade="all, delete-orphan", order_by="ProjectIdentity.id")
    relationship_history: Mapped[list[ProjectRelationship]] = relationship(back_populates="project", cascade="all, delete-orphan", order_by="ProjectRelationship.id")
    asset_units: Mapped[list["AssetUnit"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    commodity_relationships: Mapped[list["CommodityRelationship"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    proposals: Mapped[list["AssetUnitProposal"]] = relationship(back_populates="project", cascade="all, delete-orphan")

    @property
    def relationships(self):
        return self.relationship_history

    @property
    def identities(self):
        return self.identity_history

    @property
    def commodities(self):
        return self.commodity_relationships


class AssetUnit(Base):
    __tablename__ = "asset_units"
    __table_args__ = (Index("ix_asset_unit_project", "project_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    parent_asset_unit_id: Mapped[int | None] = mapped_column(ForeignKey("asset_units.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    unit_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    country: Mapped[str | None] = mapped_column(String(80), nullable=True)
    region: Mapped[str | None] = mapped_column(String(120), nullable=True)
    commodity_override: Mapped[str | None] = mapped_column(String(80), nullable=True)
    ownership_override_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    operator_override: Mapped[str | None] = mapped_column(String(160), nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    project: Mapped[Project] = relationship(back_populates="asset_units")
    parent: Mapped["AssetUnit | None"] = relationship(remote_side="AssetUnit.id", back_populates="children")
    children: Mapped[list["AssetUnit"]] = relationship(back_populates="parent")
    identity_history: Mapped[list["AssetUnitIdentity"]] = relationship(back_populates="asset_unit", cascade="all, delete-orphan", order_by="AssetUnitIdentity.id")
    commodity_relationships: Mapped[list["CommodityRelationship"]] = relationship(back_populates="asset_unit", cascade="all, delete-orphan")

    @property
    def identities(self):
        return self.identity_history

    @property
    def commodities(self):
        return self.commodity_relationships


class AssetUnitIdentity(Base):
    __tablename__ = "asset_unit_identities"
    id: Mapped[int] = mapped_column(primary_key=True)
    asset_unit_id: Mapped[int] = mapped_column(ForeignKey("asset_units.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20), default="name")
    value: Mapped[str] = mapped_column(String(160))
    normalized_value: Mapped[str] = mapped_column(String(160), index=True)
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(String(120), default="manual")
    asset_unit: Mapped[AssetUnit] = relationship(back_populates="identity_history")


class AssetUnitProposal(Base):
    __tablename__ = "asset_unit_proposals"
    __table_args__ = (CheckConstraint("status IN ('pending', 'approved', 'rejected')", name="ck_asset_proposal_status"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    proposed_name: Mapped[str] = mapped_column(String(160))
    proposed_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    rationale: Mapped[str] = mapped_column(Text, default="")
    evidence_document_id: Mapped[int | None] = mapped_column(ForeignKey("evidence_documents.id"), nullable=True, index=True)
    source_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_excerpt: Mapped[str] = mapped_column(Text, default="")
    asset_unit_id: Mapped[int | None] = mapped_column(ForeignKey("asset_units.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    project: Mapped[Project] = relationship(back_populates="proposals")
    asset_unit: Mapped["AssetUnit | None"] = relationship()


class P01EntityProposal(Base):
    __tablename__ = "p01_entity_proposals"
    __table_args__ = (
        Index("uq_p01_pending_proposal_dedupe", "dedupe_key", unique=True, sqlite_where=text("status = 'pending'")),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), index=True)
    target_level: Mapped[str] = mapped_column(String(20), default="project")
    proposed_project_name: Mapped[str] = mapped_column(String(160))
    proposed_asset_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    proposed_asset_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    proposed_commodity: Mapped[str | None] = mapped_column(String(80), nullable=True)
    proposed_ownership_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    proposed_operator: Mapped[str | None] = mapped_column(String(160), nullable=True)
    source_type: Mapped[str] = mapped_column(String(40), default="manual")
    source_ref: Mapped[str] = mapped_column(String(200), default="")
    source_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_excerpt: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="pending")
    proposal_type: Mapped[str] = mapped_column(String(60), default="new_project_candidate", index=True)
    proposed_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    proposed_name_normalized: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    proposed_entity_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    proposed_parent_project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True, index=True)
    proposed_payload_json: Mapped[str] = mapped_column(Text, default="{}")
    source_p3_event_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    source_p3_fact_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    source_evidence_document_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    source_announcement_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    supporting_mentions_json: Mapped[str] = mapped_column(Text, default="[]")
    supporting_announcement_count: Mapped[int] = mapped_column(Integer, default=0)
    supporting_evidence_count: Mapped[int] = mapped_column(Integer, default=0)
    supporting_event_count: Mapped[int] = mapped_column(Integer, default=0)
    supporting_fact_count: Mapped[int] = mapped_column(Integer, default=0)
    source_pages_json: Mapped[str] = mapped_column(Text, default="[]")
    source_excerpts_json: Mapped[str] = mapped_column(Text, default="[]")
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_by: Mapped[str] = mapped_column(String(30), default="manual")
    dedupe_key: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    reviewer: Mapped[str | None] = mapped_column(String(120), nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    review_note: Mapped[str] = mapped_column(Text, default="")
    correction_json: Mapped[str] = mapped_column(Text, default="{}")
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True, index=True)
    asset_unit_id: Mapped[int | None] = mapped_column(ForeignKey("asset_units.id"), nullable=True, index=True)
    resulting_entity_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    resulting_entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    stock: Mapped[Stock] = relationship()
    parent_project: Mapped["Project | None"] = relationship(foreign_keys=[proposed_parent_project_id])
    reviews: Mapped[list["P01EntityProposalReview"]] = relationship(
        back_populates="proposal", cascade="all, delete-orphan", order_by="P01EntityProposalReview.id"
    )


class P01EntityProposalReview(Base):
    __tablename__ = "p01_entity_proposal_reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    proposal_id: Mapped[int] = mapped_column(ForeignKey("p01_entity_proposals.id"), index=True)
    action: Mapped[str] = mapped_column(String(30), index=True)
    before_json: Mapped[str] = mapped_column(Text, default="{}")
    after_json: Mapped[str] = mapped_column(Text, default="{}")
    reviewer: Mapped[str] = mapped_column(String(120))
    review_note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    proposal: Mapped[P01EntityProposal] = relationship(back_populates="reviews")


class CommodityRelationship(Base):
    __tablename__ = "commodity_relationships"
    __table_args__ = (
        CheckConstraint("(project_id IS NOT NULL) != (asset_unit_id IS NOT NULL)", name="ck_commodity_one_parent"),
        CheckConstraint("effective_to IS NULL OR effective_from IS NULL OR effective_to > effective_from", name="ck_commodity_relationship_dates"),
        Index("ix_commodity_relationship_history", "commodity", "project_id", "asset_unit_id", "effective_from"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True, index=True)
    asset_unit_id: Mapped[int | None] = mapped_column(ForeignKey("asset_units.id"), nullable=True, index=True)
    commodity: Mapped[str] = mapped_column(String(80))
    relationship_type: Mapped[str] = mapped_column(String(40), default="economic_exposure")
    is_economic: Mapped[bool] = mapped_column(Boolean, default=True)
    effective_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    source: Mapped[str] = mapped_column(String(120), default="manual")
    project: Mapped["Project | None"] = relationship(back_populates="commodity_relationships")
    asset_unit: Mapped["AssetUnit | None"] = relationship(back_populates="commodity_relationships")


class StockProject(Base):
    __tablename__ = "stock_projects"
    __table_args__ = (UniqueConstraint("stock_id", "project_id", name="uq_stock_project"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    relationship_type: Mapped[str] = mapped_column(String(40), default="owner")
    ownership_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    effective_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    stock: Mapped[Stock] = relationship(back_populates="project_links")
    project: Mapped[Project] = relationship(back_populates="stock_links")


class PriceBar(Base):
    __tablename__ = "price_bars"
    __table_args__ = (UniqueConstraint("stock_id", "date", name="uq_price_stock_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[int] = mapped_column(Integer)

    stock: Mapped[Stock] = relationship(back_populates="price_bars")


class CommodityBar(Base):
    """Daily closes for commodity proxies and the backtest benchmark instrument."""

    __tablename__ = "commodity_bars"
    __table_args__ = (UniqueConstraint("instrument", "date", name="uq_commodity_instrument_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    instrument: Mapped[str] = mapped_column(String(20), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    close: Mapped[float] = mapped_column(Float)


class InstrumentMapping(Base):
    __tablename__ = "instrument_mappings"
    __table_args__ = (UniqueConstraint("instrument_type", "provider", "source_symbol", name="uq_instrument_mapping_source"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    instrument_code: Mapped[str] = mapped_column(String(80), index=True)
    instrument_type: Mapped[str] = mapped_column(String(20), index=True)
    provider: Mapped[str] = mapped_column(String(80))
    source_symbol: Mapped[str] = mapped_column(String(80))
    currency: Mapped[str | None] = mapped_column(String(10), nullable=True)
    timezone: Mapped[str] = mapped_column(String(50), default="UTC")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class MarketDataPoint(Base):
    __tablename__ = "market_data_points"
    __table_args__ = (UniqueConstraint("instrument_code", "trading_date", name="uq_market_data_instrument_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    instrument_code: Mapped[str] = mapped_column(String(80), index=True)
    instrument_type: Mapped[str] = mapped_column(String(20), index=True)
    trading_date: Mapped[date] = mapped_column(Date, index=True)
    open: Mapped[float | None] = mapped_column(Float, nullable=True)
    high: Mapped[float | None] = mapped_column(Float, nullable=True)
    low: Mapped[float | None] = mapped_column(Float, nullable=True)
    close: Mapped[float | None] = mapped_column(Float, nullable=True)
    adjusted_close: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(10), nullable=True)
    source: Mapped[str] = mapped_column(String(80))
    source_symbol: Mapped[str] = mapped_column(String(80))
    is_adjusted: Mapped[str] = mapped_column(String(10), default="unknown")
    quality_status: Mapped[str] = mapped_column(String(30), default="ok", index=True)
    quality_flags_json: Mapped[str] = mapped_column(Text, default="[]")
    source_unit: Mapped[str | None] = mapped_column(String(30), nullable=True)
    standard_unit: Mapped[str | None] = mapped_column(String(30), nullable=True)


class Announcement(Base):
    __tablename__ = "announcements"
    __table_args__ = (UniqueConstraint("stock_id", "ann_id", name="uq_ann_stock_annid"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), index=True)
    ann_id: Mapped[str] = mapped_column(String(64))
    headline: Mapped[str] = mapped_column(Text)
    ann_date: Mapped[datetime] = mapped_column(DateTime, index=True)
    url: Mapped[str] = mapped_column(Text, default="")
    price_sensitive: Mapped[bool] = mapped_column(Boolean, default=False)
    ann_type: Mapped[str] = mapped_column(String(30), default="OTHER")
    type_score: Mapped[float] = mapped_column(Float, default=20.0)
    matched_keywords: Mapped[str] = mapped_column(Text, default="[]")  # JSON list
    raw_payload: Mapped[str] = mapped_column(Text, default="{}")  # raw source JSON, for traceability
    evidence_document_id: Mapped[int | None] = mapped_column(ForeignKey("evidence_documents.id"), nullable=True, index=True)
    ai_summary: Mapped[str | None] = mapped_column(Text, nullable=True)  # phase-2 AI analysis layer
    ai_metrics: Mapped[str | None] = mapped_column(Text, nullable=True)  # phase-2, JSON
    document_category: Mapped[str] = mapped_column(String(80), default="Other / Needs Review")
    official_header_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    official_subtype: Mapped[str | None] = mapped_column(String(120), nullable=True)
    standard_form: Mapped[str | None] = mapped_column(String(80), nullable=True)
    event_families_json: Mapped[str] = mapped_column(Text, default="[]")
    event_labels_json: Mapped[str] = mapped_column(Text, default="[]")
    revision_tags_json: Mapped[str] = mapped_column(Text, default="[]")
    classification_source: Mapped[str] = mapped_column(String(40), default="title_routing")
    classification_version: Mapped[str] = mapped_column(String(40), default="p03_family_v1")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    stock: Mapped[Stock] = relationship(back_populates="announcements")
    evidence_document: Mapped["EvidenceDocument | None"] = relationship(
        "EvidenceDocument", foreign_keys=[evidence_document_id], uselist=False
    )


class EvidenceDocument(Base):
    __tablename__ = "evidence_documents"
    __table_args__ = (UniqueConstraint("source_type", "source_id", name="uq_evidence_source"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int | None] = mapped_column(ForeignKey("stocks.id"), nullable=True, index=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True, index=True)
    announcement_id: Mapped[int | None] = mapped_column(ForeignKey("announcements.id"), nullable=True, index=True)
    source_type: Mapped[str] = mapped_column(String(40))
    source_id: Mapped[str] = mapped_column(String(120))
    title: Mapped[str] = mapped_column(Text, default="")
    document_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    url: Mapped[str] = mapped_column(Text, default="")
    raw_storage_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_text_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # P02 evidence lifecycle fields. Legacy storage/content columns remain for compatibility.
    source_url: Mapped[str] = mapped_column(Text, default="")
    local_original_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    local_raw_text_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_hash_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    downloaded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    text_extracted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    evidence_status: Mapped[str] = mapped_column(String(30), default="metadata_only", index=True)
    download_status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    text_status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    last_retry_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    duplicate_of_id: Mapped[int | None] = mapped_column(ForeignKey("evidence_documents.id"), nullable=True)
    historical_baseline: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    review_status: Mapped[str] = mapped_column(String(30), default="pending_review", index=True)
    imported_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class P3Fact(Base):
    __tablename__ = "p3_facts"

    id: Mapped[int] = mapped_column(primary_key=True)
    announcement_id: Mapped[int | None] = mapped_column(ForeignKey("announcements.id"), nullable=True, index=True)
    evidence_document_id: Mapped[int] = mapped_column(ForeignKey("evidence_documents.id"), index=True)
    p3_event_id: Mapped[int | None] = mapped_column(ForeignKey("p3_events.id"), nullable=True, index=True)
    parse_run_id: Mapped[int | None] = mapped_column(ForeignKey("p3_parse_runs.id"), nullable=True, index=True)
    stock_id: Mapped[int | None] = mapped_column(ForeignKey("stocks.id"), nullable=True, index=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True, index=True)
    asset_unit_id: Mapped[int | None] = mapped_column(ForeignKey("asset_units.id"), nullable=True, index=True)
    mapped_project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True, index=True)
    mapped_asset_unit_id: Mapped[int | None] = mapped_column(ForeignKey("asset_units.id"), nullable=True, index=True)
    project_mapping_id: Mapped[int | None] = mapped_column(ForeignKey("entity_mappings.id"), nullable=True, index=True)
    asset_unit_mapping_id: Mapped[int | None] = mapped_column(ForeignKey("entity_mappings.id"), nullable=True, index=True)
    project_mapping_status: Mapped[str] = mapped_column(String(30), default="unknown", index=True)
    asset_unit_mapping_status: Mapped[str] = mapped_column(String(30), default="unknown", index=True)
    fact_type: Mapped[str] = mapped_column(String(60), index=True)
    fact_family: Mapped[str] = mapped_column(String(10), default="OTHER", index=True)
    schema_name: Mapped[str] = mapped_column(String(80), default="generic")
    field_name: Mapped[str] = mapped_column(String(80), index=True)
    value_raw: Mapped[str] = mapped_column(Text, default="")
    value_numeric: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    value_json: Mapped[str] = mapped_column(Text)
    unit: Mapped[str | None] = mapped_column(String(30), nullable=True)
    unit_raw: Mapped[str | None] = mapped_column(String(60), nullable=True)
    unit_normalized: Mapped[str | None] = mapped_column(String(80), nullable=True)
    currency_raw: Mapped[str | None] = mapped_column(String(20), nullable=True)
    currency_normalized: Mapped[str | None] = mapped_column(String(20), nullable=True)
    quantity_type: Mapped[str] = mapped_column(String(30), default="text", index=True)
    period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    as_of_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="reported", index=True)
    project_attribution_status: Mapped[str] = mapped_column(String(30), default="unknown")
    source_section: Mapped[str] = mapped_column(String(40), default="body")
    source_page_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_page_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    extractor_name: Mapped[str] = mapped_column(String(80), default="deterministic_p3_fact_extractor")
    extractor_version: Mapped[str] = mapped_column(String(80), default="manual_v1")
    extraction_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    review_status: Mapped[str] = mapped_column(String(30), default="proposed", index=True)
    validity_status: Mapped[str] = mapped_column(String(40), default="current", index=True)
    validity_reason: Mapped[str] = mapped_column(Text, default="")
    validity_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    review_note: Mapped[str] = mapped_column(Text, default="")
    original_extraction_json: Mapped[str] = mapped_column(Text, default="{}")
    active_result: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    superseded_by_id: Mapped[int | None] = mapped_column(ForeignKey("p3_facts.id"), nullable=True, index=True)
    information_point_group_id: Mapped[int | None] = mapped_column(ForeignKey("p3_information_points.id"), nullable=True, index=True)
    information_point_type: Mapped[str | None] = mapped_column(String(60), nullable=True, index=True)
    parent_fact_id: Mapped[int | None] = mapped_column(ForeignKey("p3_facts.id"), nullable=True, index=True)
    display_order: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    event: Mapped["P3Event | None"] = relationship(foreign_keys=[p3_event_id])
    project: Mapped["Project | None"] = relationship(foreign_keys=[project_id])
    asset_unit: Mapped["AssetUnit | None"] = relationship(foreign_keys=[asset_unit_id])
    mapped_project: Mapped["Project | None"] = relationship(foreign_keys=[mapped_project_id])
    mapped_asset_unit: Mapped["AssetUnit | None"] = relationship(foreign_keys=[mapped_asset_unit_id])
    reviews: Mapped[list["P3FactReview"]] = relationship(
        back_populates="fact", cascade="all, delete-orphan", order_by="P3FactReview.id"
    )
    information_point_links: Mapped[list["P3InformationPointFact"]] = relationship(
        back_populates="fact", cascade="all, delete-orphan", order_by="P3InformationPointFact.display_order"
    )


class P3FactReview(Base):
    __tablename__ = "p3_fact_reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    p3_fact_id: Mapped[int] = mapped_column(ForeignKey("p3_facts.id"), index=True)
    action: Mapped[str] = mapped_column(String(20), index=True)
    before_json: Mapped[str] = mapped_column(Text, default="{}")
    after_json: Mapped[str] = mapped_column(Text, default="{}")
    reviewer: Mapped[str] = mapped_column(String(120))
    review_note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    fact: Mapped[P3Fact] = relationship(back_populates="reviews")


class P3InformationPoint(Base):
    """A source-grounded logical claim composed of one or more atomic P3Fact rows."""

    __tablename__ = "p3_information_points"
    __table_args__ = (UniqueConstraint("parse_run_id", "group_key", name="uq_p3_information_point_run_group"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("p3_events.id"), index=True)
    announcement_id: Mapped[int | None] = mapped_column(ForeignKey("announcements.id"), nullable=True, index=True)
    evidence_document_id: Mapped[int] = mapped_column(ForeignKey("evidence_documents.id"), index=True)
    parse_run_id: Mapped[int] = mapped_column(ForeignKey("p3_parse_runs.id"), index=True)
    stock_id: Mapped[int | None] = mapped_column(ForeignKey("stocks.id"), nullable=True, index=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True, index=True)
    asset_unit_id: Mapped[int | None] = mapped_column(ForeignKey("asset_units.id"), nullable=True, index=True)
    family: Mapped[str] = mapped_column(String(10), index=True)
    point_type: Mapped[str] = mapped_column(String(60), index=True)
    point_title: Mapped[str] = mapped_column(Text)
    group_key: Mapped[str] = mapped_column(String(64), index=True)
    fact_count: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(30), default="reported", index=True)
    source_section: Mapped[str] = mapped_column(String(40), default="body")
    source_page_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_page_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_excerpt: Mapped[str] = mapped_column(Text, default="")
    review_status: Mapped[str] = mapped_column(String(30), default="proposed", index=True)
    active_result: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    superseded_by_id: Mapped[int | None] = mapped_column(ForeignKey("p3_information_points.id"), nullable=True, index=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    event: Mapped["P3Event"] = relationship(foreign_keys=[event_id])
    project: Mapped["Project | None"] = relationship(foreign_keys=[project_id])
    asset_unit: Mapped["AssetUnit | None"] = relationship(foreign_keys=[asset_unit_id])
    fact_links: Mapped[list["P3InformationPointFact"]] = relationship(
        back_populates="information_point", cascade="all, delete-orphan", order_by="P3InformationPointFact.display_order"
    )


class P3InformationPointFact(Base):
    __tablename__ = "p3_information_point_facts"
    __table_args__ = (UniqueConstraint("information_point_id", "p3_fact_id", name="uq_p3_information_point_fact"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    information_point_id: Mapped[int] = mapped_column(ForeignKey("p3_information_points.id"), index=True)
    p3_fact_id: Mapped[int] = mapped_column(ForeignKey("p3_facts.id"), index=True)
    role: Mapped[str] = mapped_column(String(30), default="component")
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    information_point: Mapped[P3InformationPoint] = relationship(back_populates="fact_links")
    fact: Mapped[P3Fact] = relationship(back_populates="information_point_links")


class P3Statement(Base):
    __tablename__ = "p3_statements"

    id: Mapped[int] = mapped_column(primary_key=True)
    announcement_id: Mapped[int | None] = mapped_column(ForeignKey("announcements.id"), nullable=True, index=True)
    evidence_document_id: Mapped[int] = mapped_column(ForeignKey("evidence_documents.id"), index=True)
    p3_event_id: Mapped[int | None] = mapped_column(ForeignKey("p3_events.id"), nullable=True, index=True)
    parse_run_id: Mapped[int | None] = mapped_column(ForeignKey("p3_parse_runs.id"), nullable=True, index=True)
    stock_id: Mapped[int | None] = mapped_column(ForeignKey("stocks.id"), nullable=True, index=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True, index=True)
    asset_unit_id: Mapped[int | None] = mapped_column(ForeignKey("asset_units.id"), nullable=True, index=True)
    statement_type: Mapped[str] = mapped_column(String(60), index=True)
    statement_text: Mapped[str] = mapped_column(Text)
    source_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_excerpt: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    extractor_version: Mapped[str] = mapped_column(String(80), default="manual_v1")
    review_status: Mapped[str] = mapped_column(String(30), default="proposed", index=True)
    validity_status: Mapped[str] = mapped_column(String(40), default="current", index=True)
    validity_reason: Mapped[str] = mapped_column(Text, default="")
    validity_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class P3ParseRun(Base):
    __tablename__ = "p3_parse_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    evidence_document_id: Mapped[int] = mapped_column(ForeignKey("evidence_documents.id"), index=True)
    announcement_id: Mapped[int | None] = mapped_column(ForeignKey("announcements.id"), nullable=True, index=True)
    parser_name: Mapped[str] = mapped_column(String(80))
    parser_version: Mapped[str] = mapped_column(String(40))
    input_hash: Mapped[str] = mapped_column(String(64), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    source_scope: Mapped[str] = mapped_column(String(40), default="no_text")
    pages_examined_json: Mapped[str] = mapped_column(Text, default="[]")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_summary_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class P3Event(Base):
    __tablename__ = "p3_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    announcement_id: Mapped[int | None] = mapped_column(ForeignKey("announcements.id"), nullable=True, index=True)
    evidence_document_id: Mapped[int] = mapped_column(ForeignKey("evidence_documents.id"), index=True)
    parse_run_id: Mapped[int] = mapped_column(ForeignKey("p3_parse_runs.id"), index=True)
    stock_id: Mapped[int | None] = mapped_column(ForeignKey("stocks.id"), nullable=True, index=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True, index=True)
    asset_unit_id: Mapped[int | None] = mapped_column(ForeignKey("asset_units.id"), nullable=True, index=True)
    mapped_project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True, index=True)
    mapped_asset_unit_id: Mapped[int | None] = mapped_column(ForeignKey("asset_units.id"), nullable=True, index=True)
    project_mapping_id: Mapped[int | None] = mapped_column(ForeignKey("entity_mappings.id"), nullable=True, index=True)
    asset_unit_mapping_id: Mapped[int | None] = mapped_column(ForeignKey("entity_mappings.id"), nullable=True, index=True)
    project_mapping_status: Mapped[str] = mapped_column(String(30), default="unknown", index=True)
    asset_unit_mapping_status: Mapped[str] = mapped_column(String(30), default="unknown", index=True)
    event_type: Mapped[str] = mapped_column(String(60), default="OTHER_NEEDS_REVIEW")
    # event_family is retained as the P03-part-1 compatibility field.  New code
    # writes the same value to primary_family and exposes primary_family as the
    # authoritative P03 classification.
    event_family: Mapped[str] = mapped_column(String(10), default="OTHER")
    primary_family: Mapped[str] = mapped_column(String(10), default="OTHER", index=True)
    secondary_families_json: Mapped[str] = mapped_column(Text, default="[]")
    event_title: Mapped[str] = mapped_column(Text)
    event_status: Mapped[str] = mapped_column(String(30), default="proposed", index=True)
    classification_status: Mapped[str] = mapped_column(String(30), default="auto_classified", index=True)
    classification_source: Mapped[str] = mapped_column(String(40), default="summary")
    classification_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    revision_tags_json: Mapped[str] = mapped_column(Text, default="[]")
    classification_reason: Mapped[str] = mapped_column(Text, default="")
    reviewed_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    review_note: Mapped[str] = mapped_column(Text, default="")
    original_classification_json: Mapped[str] = mapped_column(Text, default="{}")
    active_result: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    validity_status: Mapped[str] = mapped_column(String(40), default="current", index=True)
    validity_reason: Mapped[str] = mapped_column(Text, default="")
    validity_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    source_section: Mapped[str] = mapped_column(String(40), default="body")
    source_page_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_page_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_excerpt: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    occurred_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    reported_on: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    project: Mapped["Project | None"] = relationship(foreign_keys=[project_id])
    asset_unit: Mapped["AssetUnit | None"] = relationship(foreign_keys=[asset_unit_id])
    mapped_project: Mapped["Project | None"] = relationship(foreign_keys=[mapped_project_id])
    mapped_asset_unit: Mapped["AssetUnit | None"] = relationship(foreign_keys=[mapped_asset_unit_id])
    classification_reviews: Mapped[list["P3EventClassificationReview"]] = relationship(
        back_populates="event", cascade="all, delete-orphan", order_by="P3EventClassificationReview.id"
    )

    @property
    def event_id(self) -> int:
        return self.id

    @property
    def source_page(self) -> int | None:
        return self.source_page_start

    @property
    def review_needed(self) -> bool:
        return self.classification_status == "review_needed" or self.event_status == "review_needed"


class P3VersionRelation(Base):
    """Auditable disclosure-version link; object rows are never deleted or overwritten."""

    __tablename__ = "p3_version_relations"
    __table_args__ = (
        CheckConstraint("predecessor_type IN ('event', 'fact', 'statement')", name="ck_p3_version_predecessor_type"),
        CheckConstraint("successor_type IS NULL OR successor_type IN ('event', 'fact', 'statement')", name="ck_p3_version_successor_type"),
        Index("ix_p3_version_predecessor", "predecessor_type", "predecessor_id"),
        Index("ix_p3_version_successor", "successor_type", "successor_id"),
        Index(
            "uq_p3_version_confirmed_effective_predecessor",
            "predecessor_type", "predecessor_id",
            unique=True,
            sqlite_where=text(
                "status = 'confirmed' AND relation_type IN "
                "('corrects','restates','revises','replaces','supersedes','withdraws','retracts')"
            ),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    predecessor_type: Mapped[str] = mapped_column(String(20), index=True)
    predecessor_id: Mapped[int] = mapped_column(Integer, index=True)
    successor_type: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    successor_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    relation_type: Mapped[str] = mapped_column(String(30), index=True)
    status: Mapped[str] = mapped_column(String(20), default="proposed", index=True)
    source_announcement_id: Mapped[int] = mapped_column(ForeignKey("announcements.id"), index=True)
    source_evidence_document_id: Mapped[int] = mapped_column(ForeignKey("evidence_documents.id"), index=True)
    source_page_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_page_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_excerpt: Mapped[str] = mapped_column(Text, default="")
    withdrawal_reason: Mapped[str] = mapped_column(Text, default="")
    detected_by: Mapped[str] = mapped_column(String(30), default="rule")
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    original_suggestion_json: Mapped[str] = mapped_column(Text, default="{}")
    reviewed_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    review_note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class P3VersionRelationChangeLog(Base):
    __tablename__ = "p3_version_relation_change_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    relation_id: Mapped[int] = mapped_column(ForeignKey("p3_version_relations.id"), index=True)
    action: Mapped[str] = mapped_column(String(30), index=True)
    before_json: Mapped[str] = mapped_column(Text, default="{}")
    after_json: Mapped[str] = mapped_column(Text, default="{}")
    reviewer: Mapped[str] = mapped_column(String(120))
    review_note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class EntityMention(Base):
    """One source occurrence of a P01 entity name in a P03 Event or Fact."""

    __tablename__ = "entity_mentions"
    __table_args__ = (
        CheckConstraint("mention_type IN ('stock', 'project', 'asset_unit', 'commodity')", name="ck_entity_mention_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    announcement_id: Mapped[int] = mapped_column(ForeignKey("announcements.id"), index=True)
    evidence_document_id: Mapped[int] = mapped_column(ForeignKey("evidence_documents.id"), index=True)
    parse_run_id: Mapped[int] = mapped_column(ForeignKey("p3_parse_runs.id"), index=True)
    p3_event_id: Mapped[int | None] = mapped_column(ForeignKey("p3_events.id"), nullable=True, index=True)
    p3_fact_id: Mapped[int | None] = mapped_column(ForeignKey("p3_facts.id"), nullable=True, index=True)
    mention_type: Mapped[str] = mapped_column(String(20), index=True)
    mention_text_raw: Mapped[str] = mapped_column(Text)
    mention_text_normalized: Mapped[str] = mapped_column(String(200), index=True)
    source_section: Mapped[str] = mapped_column(String(40), default="body")
    source_page_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_page_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_excerpt: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    mappings: Mapped[list["EntityMapping"]] = relationship(
        back_populates="mention", cascade="all, delete-orphan", order_by="EntityMapping.id"
    )


class EntityMapping(Base):
    """Auditable candidate or confirmed link from a mention to an approved P01 entity."""

    __tablename__ = "entity_mappings"
    __table_args__ = (
        CheckConstraint("matched_entity_type IN ('stock', 'project', 'asset_unit', 'commodity')", name="ck_entity_mapping_type"),
        Index(
            "uq_entity_mapping_confirmed_mention",
            "entity_mention_id",
            unique=True,
            sqlite_where=text("status = 'confirmed'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    entity_mention_id: Mapped[int] = mapped_column(ForeignKey("entity_mentions.id"), index=True)
    matched_entity_type: Mapped[str] = mapped_column(String(20), index=True)
    matched_entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    matched_alias_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    match_method: Mapped[str] = mapped_column(String(30), index=True)
    match_confidence: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(30), default="review_needed", index=True)
    stock_validation_result: Mapped[str] = mapped_column(String(80), default="not_applicable")
    parent_validation_result: Mapped[str] = mapped_column(String(80), default="not_applicable")
    matching_reason: Mapped[str] = mapped_column(Text, default="")
    candidate_parent_project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True, index=True)
    proposal_id: Mapped[int | None] = mapped_column(ForeignKey("p01_entity_proposals.id"), nullable=True, index=True)
    candidate_payload_json: Mapped[str] = mapped_column(Text, default="{}")
    reviewed_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    review_note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    mention: Mapped[EntityMention] = relationship(back_populates="mappings")


class EntityMappingChangeLog(Base):
    __tablename__ = "entity_mapping_change_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    entity_mention_id: Mapped[int] = mapped_column(ForeignKey("entity_mentions.id"), index=True)
    old_mapping_id: Mapped[int | None] = mapped_column(ForeignKey("entity_mappings.id"), nullable=True, index=True)
    new_mapping_id: Mapped[int | None] = mapped_column(ForeignKey("entity_mappings.id"), nullable=True, index=True)
    proposal_id: Mapped[int | None] = mapped_column(ForeignKey("p01_entity_proposals.id"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(30), index=True)
    before_json: Mapped[str] = mapped_column(Text, default="{}")
    after_json: Mapped[str] = mapped_column(Text, default="{}")
    reviewer: Mapped[str] = mapped_column(String(120))
    review_note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class P3EventClassificationReview(Base):
    __tablename__ = "p3_event_classification_reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    p3_event_id: Mapped[int] = mapped_column(ForeignKey("p3_events.id"), index=True)
    action: Mapped[str] = mapped_column(String(20), index=True)
    before_json: Mapped[str] = mapped_column(Text, default="{}")
    after_json: Mapped[str] = mapped_column(Text, default="{}")
    reviewer: Mapped[str] = mapped_column(String(120))
    review_note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    event: Mapped[P3Event] = relationship(back_populates="classification_reviews")


class P4Feature(Base):
    __tablename__ = "p4_features"

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int | None] = mapped_column(ForeignKey("stocks.id"), nullable=True, index=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True, index=True)
    evidence_document_id: Mapped[int | None] = mapped_column(ForeignKey("evidence_documents.id"), nullable=True, index=True)
    as_of_date: Mapped[date] = mapped_column(Date, index=True)
    feature_group: Mapped[str] = mapped_column(String(60), index=True)
    feature_name: Mapped[str] = mapped_column(String(80), index=True)
    value_json: Mapped[str] = mapped_column(Text)
    unit: Mapped[str | None] = mapped_column(String(30), nullable=True)
    input_refs_json: Mapped[str] = mapped_column(Text, default="[]")
    evidence_json: Mapped[str] = mapped_column(Text, default="{}")
    formula_version: Mapped[str] = mapped_column(String(80), default="manual_v1")
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ScoreSnapshot(Base):
    __tablename__ = "score_snapshots"
    __table_args__ = (UniqueConstraint("stock_id", "date", name="uq_score_stock_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    funding_score: Mapped[float] = mapped_column(Float)
    announcement_score: Mapped[float] = mapped_column(Float)
    resource_score: Mapped[float] = mapped_column(Float)
    commodity_score: Mapped[float] = mapped_column(Float)
    risk_score: Mapped[float] = mapped_column(Float)
    sentiment_score: Mapped[float] = mapped_column(Float, default=50.0)
    cycle_score: Mapped[float] = mapped_column(Float)
    label: Mapped[str] = mapped_column(String(20))
    components: Mapped[str] = mapped_column(Text, default="{}")  # JSON: per-sub-score explanation
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class HistoricalAnalysisSnapshot(Base):
    __tablename__ = "historical_analysis_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "stock_id",
            "as_of_date",
            "input_hash",
            name="uq_historical_snapshot_stock_asof_input",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), index=True)
    as_of_date: Mapped[date] = mapped_column(Date, index=True)
    as_of_cutoff: Mapped[datetime] = mapped_column(DateTime)
    market_data_as_of: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    run_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    mode: Mapped[str] = mapped_column(String(20), default="approximate")
    status: Mapped[str] = mapped_column(String(20), default="success")
    boundary_status: Mapped[str] = mapped_column(String(20), default="approximate")
    data_warnings: Mapped[str] = mapped_column(Text, default="[]")  # JSON list
    input_hash: Mapped[str] = mapped_column(String(64), index=True)
    input_summary: Mapped[str] = mapped_column(Text, default="{}")  # JSON
    funding_score: Mapped[float] = mapped_column(Float)
    announcement_score: Mapped[float] = mapped_column(Float)
    resource_score: Mapped[float] = mapped_column(Float)
    commodity_score: Mapped[float] = mapped_column(Float)
    risk_score: Mapped[float] = mapped_column(Float)
    sentiment_score: Mapped[float] = mapped_column(Float, default=50.0)
    cycle_score: Mapped[float] = mapped_column(Float)
    label: Mapped[str] = mapped_column(String(20))
    components: Mapped[str] = mapped_column(Text, default="{}")  # JSON
    ai_reason: Mapped[str] = mapped_column(Text, default="")
    config_snapshot: Mapped[str] = mapped_column(Text, default="{}")  # JSON
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class HistoricalAnalysisReturn(Base):
    __tablename__ = "historical_analysis_returns"
    __table_args__ = (
        UniqueConstraint(
            "snapshot_id",
            "horizon_days",
            name="uq_historical_return_snapshot_horizon",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("historical_analysis_snapshots.id"),
        index=True,
    )
    horizon_days: Mapped[int] = mapped_column(Integer)
    entry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    entry_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    exit_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    exit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    return_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    benchmark_return_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_drawdown_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(15), default="pending")
    filled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Signal(Base):
    __tablename__ = "signals"
    __table_args__ = (UniqueConstraint("stock_id", "date", "signal_type", name="uq_signal_stock_date_type"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    signal_type: Mapped[str] = mapped_column(String(30))
    source: Mapped[str] = mapped_column(String(10), default="live")  # live / replay
    label: Mapped[str | None] = mapped_column(String(20), nullable=True)  # NULL for replay
    reason: Mapped[str] = mapped_column(Text)
    evidence: Mapped[str] = mapped_column(Text, default="{}")  # JSON
    price_at_signal: Mapped[float] = mapped_column(Float)  # signal-day close, reference only
    cycle_score_at_signal: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Signals sharing an event_key come from one causal mechanism on one day
    # (a breakout already requires 1.5x volume, so it and the volume spike are
    # one price-action event seen twice). role marks which one represents it.
    event_key: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    role: Mapped[str] = mapped_column(String(10), default="primary")  # primary / secondary
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    stock: Mapped[Stock] = relationship(back_populates="signals")
    returns: Mapped[list["SignalReturn"]] = relationship(back_populates="signal", cascade="all, delete-orphan")


class AnalyticalSignal(Base):
    __tablename__ = "analytical_signals"

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), index=True)
    engine: Mapped[str] = mapped_column(String(30), index=True)  # fundamental/technical/sentiment/catalyst
    signal_date: Mapped[date] = mapped_column(Date, index=True)
    direction: Mapped[str] = mapped_column(String(20))
    magnitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    persistence: Mapped[str | None] = mapped_column(String(30), nullable=True)
    source_event_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    dependency_group: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    evidence_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    feature_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    key_drivers_json: Mapped[str] = mapped_column(Text, default="[]")
    key_risks_json: Mapped[str] = mapped_column(Text, default="[]")
    logic_version: Mapped[str] = mapped_column(String(80), default="manual_v1")
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class FusionRecord(Base):
    __tablename__ = "fusion_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), index=True)
    fusion_date: Mapped[date] = mapped_column(Date, index=True)
    opportunity_strength: Mapped[str] = mapped_column(String(30))
    confidence: Mapped[str | None] = mapped_column(String(20), nullable=True)
    signal_structure: Mapped[str | None] = mapped_column(String(40), nullable=True)
    evidence_independence: Mapped[str | None] = mapped_column(String(30), nullable=True)
    dominant_drivers_json: Mapped[str] = mapped_column(Text, default="[]")
    conflicts_json: Mapped[str] = mapped_column(Text, default="[]")
    blocking_conditions_json: Mapped[str] = mapped_column(Text, default="[]")
    overheating_risk: Mapped[str | None] = mapped_column(String(20), nullable=True)
    official_result: Mapped[str] = mapped_column(String(30))
    shadow_result: Mapped[str | None] = mapped_column(String(30), nullable=True)
    conflict_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    human_review_required: Mapped[bool] = mapped_column(Boolean, default=False)
    analytical_signal_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    rule_version: Mapped[str] = mapped_column(String(80), default="manual_v1")
    model_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AttentionState(Base):
    __tablename__ = "attention_states"

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), index=True)
    fusion_record_id: Mapped[int | None] = mapped_column(ForeignKey("fusion_records.id"), nullable=True, index=True)
    state_level: Mapped[str] = mapped_column(String(2), index=True)  # L0-L5
    state_label: Mapped[str] = mapped_column(String(40))
    previous_state_level: Mapped[str | None] = mapped_column(String(2), nullable=True)
    transition: Mapped[str] = mapped_column(String(20), default="hold")
    reason: Mapped[str] = mapped_column(Text, default="")
    manual_lock: Mapped[bool] = mapped_column(Boolean, default=False)
    manual_override: Mapped[bool] = mapped_column(Boolean, default=False)
    pinned_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    compute_profile: Mapped[str] = mapped_column(String(40), default="standard")
    alert_priority: Mapped[str] = mapped_column(String(30), default="dashboard")
    rule_version: Mapped[str] = mapped_column(String(80), default="manual_v1")
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    effective_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class TradeDecision(Base):
    __tablename__ = "trade_decisions"
    __table_args__ = (UniqueConstraint("stock_id", "decision_date", "rule_version", name="uq_trade_decision_stock_date_rule"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), index=True)
    fusion_record_id: Mapped[int | None] = mapped_column(ForeignKey("fusion_records.id"), nullable=True, index=True)
    attention_state_id: Mapped[int | None] = mapped_column(ForeignKey("attention_states.id"), nullable=True, index=True)
    decision_date: Mapped[date] = mapped_column(Date, index=True)
    decision: Mapped[str] = mapped_column(String(20))  # act/wait/pass
    action: Mapped[str] = mapped_column(String(30))  # none/starter_buy/buy
    conviction: Mapped[str] = mapped_column(String(20), default="low")
    reason: Mapped[str] = mapped_column(Text, default="")
    entry_logic: Mapped[str] = mapped_column(Text, default="")
    entry_range_json: Mapped[str] = mapped_column(Text, default="{}")
    position_size_json: Mapped[str] = mapped_column(Text, default="{}")
    add_trigger_json: Mapped[str] = mapped_column(Text, default="[]")
    invalidation_json: Mapped[str] = mapped_column(Text, default="[]")
    target_logic_json: Mapped[str] = mapped_column(Text, default="{}")
    key_risks_json: Mapped[str] = mapped_column(Text, default="[]")
    review_trigger_json: Mapped[str] = mapped_column(Text, default="[]")
    strategy_profile: Mapped[str] = mapped_column(String(40), default="balanced")
    rule_version: Mapped[str] = mapped_column(String(80), default="manual_v1")
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Position(Base):
    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), index=True)
    trade_decision_id: Mapped[int | None] = mapped_column(ForeignKey("trade_decisions.id"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)  # open/closed
    opened_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    entry_price: Mapped[float] = mapped_column(Float)
    quantity: Mapped[float] = mapped_column(Float)
    current_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    thesis_status: Mapped[str] = mapped_column(String(30), default="intact")
    catalyst_status: Mapped[str] = mapped_column(String(30), default="on_track")
    risk_status: Mapped[str] = mapped_column(String(30), default="normal")
    suggested_action: Mapped[str] = mapped_column(String(20), default="hold")
    price_stop: Mapped[float | None] = mapped_column(Float, nullable=True)
    thesis_stop_json: Mapped[str] = mapped_column(Text, default="[]")
    target_logic_json: Mapped[str] = mapped_column(Text, default="{}")
    original_thesis_json: Mapped[str] = mapped_column(Text, default="{}")
    thesis_delta_json: Mapped[str] = mapped_column(Text, default="{}")
    strategy_profile: Mapped[str] = mapped_column(String(40), default="balanced")
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    events: Mapped[list["PositionEvent"]] = relationship(back_populates="position", cascade="all, delete-orphan")


class PositionEvent(Base):
    __tablename__ = "position_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    position_id: Mapped[int] = mapped_column(ForeignKey("positions.id"), index=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), index=True)
    trade_decision_id: Mapped[int | None] = mapped_column(ForeignKey("trade_decisions.id"), nullable=True, index=True)
    event_time: Mapped[datetime] = mapped_column(DateTime, index=True)
    event_type: Mapped[str] = mapped_column(String(30), index=True)
    action: Mapped[str] = mapped_column(String(30), default="hold")
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    quantity_delta: Mapped[float | None] = mapped_column(Float, nullable=True)
    thesis_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    catalyst_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    risk_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    evidence_json: Mapped[str] = mapped_column(Text, default="{}")
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    position: Mapped[Position] = relationship(back_populates="events")


class TradeReview(Base):
    __tablename__ = "trade_reviews"
    __table_args__ = (UniqueConstraint("position_id", "review_version", name="uq_trade_review_position_version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    position_id: Mapped[int] = mapped_column(ForeignKey("positions.id"), index=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), index=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    closed_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    entry_price: Mapped[float] = mapped_column(Float)
    exit_price: Mapped[float] = mapped_column(Float)
    return_pct: Mapped[float] = mapped_column(Float)
    outcome_quality: Mapped[str] = mapped_column(String(30))
    decision_quality: Mapped[str] = mapped_column(String(30))
    thesis_review_json: Mapped[str] = mapped_column(Text, default="{}")
    signal_review_json: Mapped[str] = mapped_column(Text, default="{}")
    decision_review_json: Mapped[str] = mapped_column(Text, default="{}")
    position_management_review_json: Mapped[str] = mapped_column(Text, default="{}")
    outcome_attribution_json: Mapped[str] = mapped_column(Text, default="{}")
    state_transition_review_json: Mapped[str] = mapped_column(Text, default="{}")
    review_version: Mapped[str] = mapped_column(String(80), default="manual_v1")
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class StrategyLearningCandidate(Base):
    __tablename__ = "strategy_learning_candidates"

    id: Mapped[int] = mapped_column(primary_key=True)
    trade_review_id: Mapped[int] = mapped_column(ForeignKey("trade_reviews.id"), index=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), index=True)
    candidate_type: Mapped[str] = mapped_column(String(40), index=True)  # observation/hypothesis/change_candidate
    target_layer: Mapped[str] = mapped_column(String(20), index=True)  # P3-P9
    title: Mapped[str] = mapped_column(String(160))
    rationale: Mapped[str] = mapped_column(Text, default="")
    evidence_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(30), default="proposed", index=True)
    requires_backtest: Mapped[bool] = mapped_column(Boolean, default=True)
    requires_human_approval: Mapped[bool] = mapped_column(Boolean, default=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class SignalReturn(Base):
    __tablename__ = "signal_returns"
    __table_args__ = (UniqueConstraint("signal_id", "horizon_days", name="uq_return_signal_horizon"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    signal_id: Mapped[int] = mapped_column(ForeignKey("signals.id"), index=True)
    horizon_days: Mapped[int] = mapped_column(Integer)  # 5 / 20 / 60 / 120 trading days
    entry_price: Mapped[float | None] = mapped_column(Float, nullable=True)  # first close AFTER signal day
    return_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    benchmark_return_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(15), default="pending")  # pending/filled/unavailable
    filled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    signal: Mapped[Signal] = relationship(back_populates="returns")


class DailyReport(Base):
    __tablename__ = "daily_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    report_date: Mapped[date] = mapped_column(Date, unique=True, index=True)
    content_json: Mapped[str] = mapped_column(Text)
    content_text: Mapped[str] = mapped_column(Text)  # Telegram HTML
    pushed: Mapped[bool] = mapped_column(Boolean, default=False)
    pushed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    push_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AppConfig(Base):
    __tablename__ = "app_config"

    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[str] = mapped_column(Text)  # JSON
    description: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class AppConfigHistory(Base):
    __tablename__ = "app_config_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(60), index=True)
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    new_value: Mapped[str] = mapped_column(Text)  # JSON
    changed_by: Mapped[str] = mapped_column(String(60), default="system")
    source: Mapped[str] = mapped_column(String(60), default="api")
    changed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    trigger: Mapped[str] = mapped_column(String(20))  # scheduled/manual/cli/replay
    status: Mapped[str] = mapped_column(String(15), default="running")  # running/success/partial/failed
    stats_json: Mapped[str] = mapped_column(Text, default="{}")
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    pipeline_type: Mapped[str] = mapped_column(String(40), default="daily")
    provider: Mapped[str] = mapped_column(String(80), default="internal")
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    total_items: Mapped[int] = mapped_column(Integer, default=0)
    succeeded_items: Mapped[int] = mapped_column(Integer, default=0)
    skipped_items: Mapped[int] = mapped_column(Integer, default=0)
    failed_items: Mapped[int] = mapped_column(Integer, default=0)
    retry_of_run_id: Mapped[int | None] = mapped_column(ForeignKey("pipeline_runs.id"), nullable=True)
    configuration_snapshot_json: Mapped[str] = mapped_column(Text, default="{}")
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)


class PipelineRunItem(Base):
    __tablename__ = "pipeline_run_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("pipeline_runs.id"), index=True)
    stock_id: Mapped[int | None] = mapped_column(ForeignKey("stocks.id"), nullable=True, index=True)
    announcement_id: Mapped[int | None] = mapped_column(ForeignKey("announcements.id"), nullable=True, index=True)
    provider: Mapped[str] = mapped_column(String(80), default="internal")
    item_type: Mapped[str] = mapped_column(String(40), default="stock")
    status: Mapped[str] = mapped_column(String(20), index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=1)
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class BackfillRun(Base):
    """Administrator-scoped historical P02 -> P03 execution.

    Preview is deliberately read-only.  Its exact filters, configuration and
    candidate ids are persisted here only after the administrator confirms the
    preview and starts a run.
    """

    __tablename__ = "backfill_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    requested_by: Mapped[str] = mapped_column(String(120), default="admin")
    parser_version: Mapped[str] = mapped_column(String(80))
    pipeline_version: Mapped[str] = mapped_column(String(80), default="p02_p03_backfill_v1")
    filter_snapshot_json: Mapped[str] = mapped_column(Text, default="{}")
    configuration_snapshot_json: Mapped[str] = mapped_column(Text, default="{}")
    preview_token: Mapped[str] = mapped_column(String(64), index=True)
    total_announcements: Mapped[int] = mapped_column(Integer, default=0)
    succeeded_announcements: Mapped[int] = mapped_column(Integer, default=0)
    skipped_announcements: Mapped[int] = mapped_column(Integer, default=0)
    failed_announcements: Mapped[int] = mapped_column(Integer, default=0)
    partial_announcements: Mapped[int] = mapped_column(Integer, default=0)
    downloaded_files: Mapped[int] = mapped_column(Integer, default=0)
    extracted_texts: Mapped[int] = mapped_column(Integer, default=0)
    parsed_documents: Mapped[int] = mapped_column(Integer, default=0)
    created_events: Mapped[int] = mapped_column(Integer, default=0)
    created_facts: Mapped[int] = mapped_column(Integer, default=0)
    mapped_entities: Mapped[int] = mapped_column(Integer, default=0)
    review_needed_count: Mapped[int] = mapped_column(Integer, default=0)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_of_run_id: Mapped[int | None] = mapped_column(ForeignKey("backfill_runs.id"), nullable=True, index=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class BackfillRunItem(Base):
    __tablename__ = "backfill_run_items"
    __table_args__ = (UniqueConstraint("backfill_run_id", "announcement_id", name="uq_backfill_run_announcement"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    backfill_run_id: Mapped[int] = mapped_column(ForeignKey("backfill_runs.id"), index=True)
    announcement_id: Mapped[int] = mapped_column(ForeignKey("announcements.id"), index=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), index=True)
    evidence_document_id: Mapped[int | None] = mapped_column(ForeignKey("evidence_documents.id"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    stage: Mapped[str] = mapped_column(String(30), default="metadata", index=True)
    parser_version: Mapped[str] = mapped_column(String(80))
    input_hash: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_event_count: Mapped[int] = mapped_column(Integer, default=0)
    created_fact_count: Mapped[int] = mapped_column(Integer, default=0)
    mapped_count: Mapped[int] = mapped_column(Integer, default=0)
    review_needed_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class AnnouncementVersionRelation(Base):
    __tablename__ = "announcement_version_relations"
    __table_args__ = (UniqueConstraint("predecessor_announcement_id", "successor_announcement_id", name="uq_ann_version_pair"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    predecessor_announcement_id: Mapped[int] = mapped_column(ForeignKey("announcements.id"), index=True)
    successor_announcement_id: Mapped[int] = mapped_column(ForeignKey("announcements.id"), index=True)
    relation_type: Mapped[str] = mapped_column(String(30), default="related_to")
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending_review", index=True)
    source: Mapped[str] = mapped_column(String(80), default="rule_candidate")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    reviewed_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
