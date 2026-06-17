from sqlalchemy import Column, String, Integer, Float, DateTime, Enum, ForeignKey, Index
from sqlalchemy.orm import DeclarativeBase, relationship
from datetime import datetime
import uuid
import enum


class Base(DeclarativeBase):
    pass


class TokenState(str, enum.Enum):
    WAITING = "waiting"
    CALLED = "called"
    SERVING = "serving"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    NO_SHOW = "no_show"
    CANCELLED = "cancelled"
    DELAYED = "delayed"


class Organization(Base):
    __tablename__ = "organizations"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    queues = relationship("Queue", back_populates="organization", cascade="all, delete-orphan")


class Queue(Base):
    __tablename__ = "queues"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String, ForeignKey("organizations.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    daily_limit = Column(Integer, default=0)  # 0 means unlimited
    active = Column(Integer, default=1)
    is_accepting_tokens = Column(Integer, default=1) # 1=True, 0=False
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    organization = relationship("Organization", back_populates="queues")
    tokens = relationship("Token", back_populates="queue", cascade="all, delete-orphan")
    counters = relationship("Counter", back_populates="queue", cascade="all, delete-orphan")
    training_data = relationship("TrainingData", back_populates="queue", cascade="all, delete-orphan")
    date_statuses = relationship("QueueDateStatus", back_populates="queue", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index("ix_queue_organization_active", "organization_id", "active"),
    )


class Token(Base):
    __tablename__ = "tokens"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    queue_id = Column(String, ForeignKey("queues.id"), nullable=False, index=True)
    number = Column(Integer, nullable=False)  # E.g., 101, 102
    name = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    email = Column(String, nullable=True)
    state = Column(Enum(TokenState), default=TokenState.WAITING, nullable=False)
    service_date = Column(DateTime, nullable=False, index=True)
    secret_token = Column(String, nullable=False, index=True)  # UUID for session security
    verification_pin = Column(String, nullable=False)          # 4-digit PIN for counter
    joined_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    called_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    wait_time_minutes = Column(Float, nullable=True)  # Actual wait time after completion
    estimated_wait_minutes = Column(Float, nullable=True)  # ML prediction
    estimated_reporting_time = Column(String, nullable=True)  # e.g., "10:30 AM" – when user should arrive
    risk_status = Column(String, default="reliable")  # reliable, moderate_risk, high_risk
    requires_confirmation = Column(Integer, default=0) # 0=False, 1=True
    is_confirmed = Column(Integer, default=0) # 0=False, 1=True
    reminder_sent = Column(Integer, default=0) # 0=False, 1=True
    initial_queue_depth = Column(Integer, nullable=True) # Snapshotted at join time for ML
    priority_level = Column(Integer, default=0)           # 0=Normal, 100=High, 1000=Emergency
    
    queue = relationship("Queue", back_populates="tokens")
    
    __table_args__ = (
        Index("ix_token_queue_state", "queue_id", "state"),
        Index("ix_token_queue_joined", "queue_id", "joined_at"),
        Index("ix_token_state_joined", "state", "joined_at"),
    )


class Counter(Base):
    __tablename__ = "counters"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    queue_id = Column(String, ForeignKey("queues.id"), nullable=False, index=True)
    number = Column(Integer, nullable=False)  # Counter 1, Counter 2, etc.
    name = Column(String, nullable=True)
    operator_name = Column(String, nullable=True)
    current_token_id = Column(String, ForeignKey("tokens.id"), nullable=True)
    status = Column(String, default="idle")  # idle, serving, break
    created_at = Column(DateTime, default=datetime.utcnow)
    
    queue = relationship("Queue", back_populates="counters")
    
    __table_args__ = (
        Index("ix_counter_queue", "queue_id"),
    )


class TrainingData(Base):
    """Historical data for ML model training"""
    __tablename__ = "training_data"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    queue_id = Column(String, ForeignKey("queues.id"), nullable=False, index=True)
    hour_of_day = Column(Integer, nullable=False)  # 0-23
    day_of_week = Column(Integer, nullable=False)  # 0-6 (Monday-Sunday)
    queue_depth = Column(Integer, nullable=False)  # Number waiting at time of join
    wait_time_minutes = Column(Float, nullable=False)  # Actual wait time (minutes)
    recorded_at = Column(DateTime, default=datetime.utcnow)
    
    queue = relationship("Queue", back_populates="training_data")

    queue = relationship("Queue", back_populates="training_data")


class QueueDateStatus(Base):
    """Stores date-specific settings (like pause) for a queue"""
    __tablename__ = "queue_date_status"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    queue_id = Column(String, ForeignKey("queues.id"), nullable=False, index=True)
    service_date = Column(DateTime, nullable=False, index=True) # Midnight UTC
    is_accepting_tokens = Column(Integer, default=1) # 1=True, 0=False
    
    queue = relationship("Queue", back_populates="date_statuses")
    
    __table_args__ = (
        Index("ix_qds_queue_date", "queue_id", "service_date", unique=True),
    )
