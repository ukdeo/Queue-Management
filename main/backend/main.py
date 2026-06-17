import fastapi
from typing import Optional
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
import os
import uuid
import random
from zoneinfo import ZoneInfo

from database import get_db, init_db
from models import (
    Organization, Queue, Token, Counter, TokenState, TrainingData, QueueDateStatus
)
from schemas import (
    OrganizationCreate, OrganizationResponse,
    QueueCreate, QueueUpdate, QueueResponse, QueueDetailResponse, QueueResetRequest,
    TokenCreate, TokenResponse, TokenSecureResponse, TokenStateUpdate, TokenPriorityUpdate, TokenListResponse,
    CounterCreate, CounterUpdate, CounterResponse,
    QueueStatsResponse, OperatorQueueResponse, QueueOverviewItem,
    HealthResponse, ImpactStatsResponse
)
from ml_engine import ml_engine
from sms_service import send_sms
import asyncio
from database import SessionLocal
from pydantic import BaseModel

async def run_reminder_loop():
    """Background task to send reminders when turn is near (1-2 hours)"""
    while True:
        await asyncio.sleep(60)  # Check every 1 minute
        try:
            db = SessionLocal()
            NPT = ZoneInfo("Asia/Kathmandu")
            now_npt = datetime.now(NPT)
            target_date = datetime(now_npt.year, now_npt.month, now_npt.day, 0, 0, 0)
            
            # Find WAITING tokens for today that haven't had a reminder
            waiting_tokens = db.query(Token).filter(
                Token.state == TokenState.WAITING,
                Token.reminder_sent == 0,
                Token.phone != None,
                Token.service_date == target_date
            ).all()
            
            for token in waiting_tokens:
                # Calculate tokens ahead
                tokens_ahead = db.query(Token).filter(
                    Token.queue_id == token.queue_id,
                    Token.state == TokenState.WAITING,
                    Token.service_date == token.service_date,
                    Token.joined_at < token.joined_at
                ).count()
                
                # Fetch queue for office context if needed, but we mainly need wait time
                est = ml_engine.predict(now_npt.hour, now_npt.weekday(), tokens_ahead)
                if est is None: est = tokens_ahead * 5 # Fallback
                
                # Proactive Alert: 60-120 minutes remaining
                if 60 <= est <= 120:
                    token.reminder_sent = 1
                    db.commit()
                    
                    msg = (
                        f"Hello {token.name or 'User'}, your Pālo turn #{token.number} is approaching (approx. {int(est)}m wait). "
                        f"Please arrive by {token.estimated_reporting_time}. "
                        f"Track live: https://palo.quest/t/{token.id}"
                    )
                    send_sms(token.phone, msg)
                    
        except Exception as e:
            print(f"Reminder loop error: {e}")
        finally:
            db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database on startup"""
    init_db()
    
    # Bootstrap default Organization and Queue if database is empty
    from database import SessionLocal
    db = SessionLocal()
    try:
        if db.query(Organization).count() == 0:
            default_org = Organization(id="default-org", name="Pālo Main Organization")
            db.add(default_org)
            default_queue = Queue(
                id="default-queue", 
                organization_id="default-org", 
                name="Main Registration Queue", 
                description="Default system queue"
            )
            db.add(default_queue)
            db.commit()
        
        asyncio.create_task(run_reminder_loop())

    finally:
        db.close()
        
    yield


app = FastAPI(title="Pālo Queue Management API", lifespan=lifespan)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# Health & Status
# ============================================================================

@app.get("/health", response_model=HealthResponse)
async def health(db: Session = fastapi.Depends(get_db)):
    """Health check endpoint"""
    try:
        db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception as e:
        db_status = f"error: {str(e)}"
    
    return HealthResponse(status="ok", database=db_status)

class IncomingSMS(BaseModel):
    phone: str
    message: str

@app.post("/webhooks/sms")
async def handle_incoming_sms(payload: IncomingSMS, db: Session = fastapi.Depends(get_db)):
    """Webhook for SMS provider (e.g. Twilio) to forward incoming replies"""
    msg = payload.message.strip().upper()
    
    if msg == "YES":
        # Find token that requires confirmation
        token = db.query(Token).filter(
            Token.phone == payload.phone,
            Token.state == TokenState.WAITING,
            Token.requires_confirmation == 1,
            Token.is_confirmed == 0
        ).first()
        
        if token:
            token.is_confirmed = 1
            db.commit()
            send_sms(payload.phone, "Thank you! Your Pālo appointment is now fully confirmed.")
            return {"status": "confirmed"}
        else:
            return {"status": "no pending confirmations"}
            
    return {"status": "ignored"}


# ============================================================================
# Organizations
# ============================================================================

@app.post("/organizations", response_model=OrganizationResponse)
async def create_organization(
    org: OrganizationCreate,
    db: Session = fastapi.Depends(get_db)
):
    """Create a new organization"""
    db_org = Organization(id=str(uuid.uuid4()), name=org.name)
    db.add(db_org)
    db.commit()
    db.refresh(db_org)
    return db_org


@app.get("/organizations/{org_id}", response_model=OrganizationResponse)
async def get_organization(org_id: str, db: Session = fastapi.Depends(get_db)):
    """Get organization by ID"""
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise fastapi.HTTPException(status_code=404, detail="Organization not found")
    return org


@app.get("/organizations", response_model=list[OrganizationResponse])
async def list_organizations(db: Session = fastapi.Depends(get_db)):
    """List all organizations"""
    return db.query(Organization).all()


@app.get("/organizations/{org_id}/impact", response_model=ImpactStatsResponse)
async def get_organization_impact(org_id: str, db: Session = fastapi.Depends(get_db)):
    """Get global impact stats for the entire platform"""
    # Get all completed tokens across the entire system
    completed_tokens = db.query(Token).filter(
        Token.state == TokenState.COMPLETED,
        Token.wait_time_minutes != None
    ).all()
    
    if not completed_tokens:
        return ImpactStatsResponse(users_served=0, hours_saved=0, wait_reduction_pct=0)
        
    users_served = len(completed_tokens)
    total_wait_minutes = sum(t.wait_time_minutes for t in completed_tokens)
    hours_saved = int(total_wait_minutes / 60)
    
    # Calculate Wait Reduction % compared to a 45-minute baseline physical wait
    avg_wait = total_wait_minutes / users_served
    baseline_minutes = 45.0
    
    if avg_wait < baseline_minutes:
        wait_reduction_pct = int(((baseline_minutes - avg_wait) / baseline_minutes) * 100)
    else:
        wait_reduction_pct = 0
        
    return ImpactStatsResponse(
        users_served=users_served,
        hours_saved=hours_saved,
        wait_reduction_pct=wait_reduction_pct
    )


# ============================================================================
# Queues
# ============================================================================

@app.post("/organizations/{org_id}/queues", response_model=QueueResponse)
async def create_queue(
    org_id: str,
    queue: QueueCreate,
    db: Session = fastapi.Depends(get_db)
):
    """Create a new queue"""
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise fastapi.HTTPException(status_code=404, detail="Organization not found")
    
    db_queue = Queue(
        id=str(uuid.uuid4()),
        organization_id=org_id,
        name=queue.name,
        description=queue.description,
        daily_limit=queue.daily_limit
    )
    db.add(db_queue)
    db.commit()
    db.refresh(db_queue)
    return db_queue


@app.delete("/queues/{queue_id}")
async def delete_queue(queue_id: str, db: Session = fastapi.Depends(get_db)):
    """Delete a queue and all its tokens"""
    queue = db.query(Queue).filter(Queue.id == queue_id).first()
    if not queue:
        raise fastapi.HTTPException(status_code=404, detail="Queue not found")
    
    db.delete(queue)
    db.commit()
    return {"status": "deleted", "queue_id": queue_id}


@app.get("/organizations/{org_id}/queues", response_model=list[QueueResponse])
async def list_queues(org_id: str, service_date: str = None, db: Session = fastapi.Depends(get_db)):
    """List all queues for an organization"""
    from datetime import date as date_type
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise fastapi.HTTPException(status_code=404, detail="Organization not found")
    
    queues = db.query(Queue).filter(Queue.organization_id == org_id).all()
    
    if service_date:
        try:
            svc = date_type.fromisoformat(service_date)
            target_date = datetime(svc.year, svc.month, svc.day, 0, 0, 0)
            
            for q in queues:
                date_status = db.query(QueueDateStatus).filter(
                    QueueDateStatus.queue_id == q.id,
                    QueueDateStatus.service_date == target_date
                ).first()
                if date_status:
                    q.is_accepting_tokens = date_status.is_accepting_tokens
        except ValueError:
            pass # Fallback to global if date is invalid

    return queues


@app.get("/organizations/{org_id}/overview", response_model=list[QueueOverviewItem])
async def get_org_overview(org_id: str, service_date: str = None, db: Session = fastapi.Depends(get_db)):
    """Get a summary overview of all queues (departments) for an organization on a given date."""
    from datetime import date as date_type
    from zoneinfo import ZoneInfo

    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise fastapi.HTTPException(status_code=404, detail="Organization not found")

    NPT = ZoneInfo("Asia/Kathmandu")
    if service_date:
        try:
            svc = date_type.fromisoformat(service_date)
        except ValueError:
            svc = datetime.now(NPT).date()
    else:
        svc = datetime.now(NPT).date()

    target_date = datetime(svc.year, svc.month, svc.day, 0, 0, 0)

    queues = db.query(Queue).filter(Queue.organization_id == org_id).all()
    result = []

    for q in queues:
        # Date-specific accepting status
        date_status = db.query(QueueDateStatus).filter(
            QueueDateStatus.queue_id == q.id,
            QueueDateStatus.service_date == target_date
        ).first()
        is_accepting = date_status.is_accepting_tokens if date_status else q.is_accepting_tokens

        total_waiting = db.query(Token).filter(
            Token.queue_id == q.id,
            Token.state == TokenState.WAITING,
            Token.service_date == target_date
        ).count()

        total_serving = db.query(Token).filter(
            Token.queue_id == q.id,
            Token.state == TokenState.SERVING,
            Token.service_date == target_date
        ).count()

        total_completed = db.query(Token).filter(
            Token.queue_id == q.id,
            Token.state == TokenState.COMPLETED,
            Token.service_date == target_date
        ).count()

        # Find next token with priority logic
        all_waiting = db.query(Token).filter(
            Token.queue_id == q.id,
            Token.state == TokenState.WAITING,
            Token.service_date == target_date
        ).all()
        
        now_utc = datetime.utcnow()
        for t in all_waiting:
            wait_time = (now_utc - t.joined_at).total_seconds() / 60
            t.temp_score = t.priority_level + wait_time
        
        all_waiting.sort(key=lambda x: (-x.temp_score, x.number))
        next_token = all_waiting[0] if all_waiting else None

        result.append(QueueOverviewItem(
            queue_id=q.id,
            queue_name=q.name,
            description=q.description,
            active=q.active,
            is_accepting_tokens=is_accepting,
            total_waiting=total_waiting,
            total_serving=total_serving,
            total_completed_today=total_completed,
            daily_limit=q.daily_limit or 0,
            next_token=next_token,
        ))

    return result


@app.get("/queues/{queue_id}", response_model=QueueResponse)
async def get_queue(queue_id: str, service_date: str = None, db: Session = fastapi.Depends(get_db)):
    """Get queue by ID"""
    from datetime import date as date_type
    queue = db.query(Queue).filter(Queue.id == queue_id).first()
    if not queue:
        raise fastapi.HTTPException(status_code=404, detail="Queue not found")
        
    if service_date:
        try:
            svc = date_type.fromisoformat(service_date)
            target_date = datetime(svc.year, svc.month, svc.day, 0, 0, 0)
            date_status = db.query(QueueDateStatus).filter(
                QueueDateStatus.queue_id == queue_id,
                QueueDateStatus.service_date == target_date
            ).first()
            if date_status:
                queue.is_accepting_tokens = date_status.is_accepting_tokens
        except ValueError:
            pass
            
    return queue


@app.patch("/queues/{queue_id}", response_model=QueueResponse)
async def update_queue(
    queue_id: str,
    queue_update: QueueUpdate,
    db: Session = fastapi.Depends(get_db)
):
    """Update queue"""
    queue = db.query(Queue).filter(Queue.id == queue_id).first()
    if not queue:
        raise fastapi.HTTPException(status_code=404, detail="Queue not found")
    
    if queue_update.name is not None:
        queue.name = queue_update.name
    if queue_update.description is not None:
        queue.description = queue_update.description
    if queue_update.active is not None:
        queue.active = queue_update.active
    if queue_update.daily_limit is not None:
        queue.daily_limit = queue_update.daily_limit
    if queue_update.is_accepting_tokens is not None:
        if queue_update.service_date:
            # Date-specific pause
            try:
                date_obj = datetime.strptime(queue_update.service_date, "%Y-%m-%d")
                # Ensure it's midnight UTC for consistency
                date_obj = date_obj.replace(hour=0, minute=0, second=0, microsecond=0)
                
                status = db.query(QueueDateStatus).filter(
                    QueueDateStatus.queue_id == queue_id,
                    QueueDateStatus.service_date == date_obj
                ).first()
                
                if not status:
                    status = QueueDateStatus(
                        queue_id=queue_id,
                        service_date=date_obj,
                        is_accepting_tokens=queue_update.is_accepting_tokens
                    )
                    db.add(status)
                else:
                    status.is_accepting_tokens = queue_update.is_accepting_tokens
            except ValueError:
                raise fastapi.HTTPException(status_code=400, detail="Invalid service_date format. Use YYYY-MM-DD")
        else:
            # Global pause
            queue.is_accepting_tokens = queue_update.is_accepting_tokens
    
    queue.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(queue)
    return queue


# ============================================================================
# Tokens (Queue Members)
# ============================================================================

@app.post("/queues/{queue_id}/tokens", response_model=TokenSecureResponse)
async def create_token(
    queue_id: str,
    token_data: TokenCreate,
    background_tasks: fastapi.BackgroundTasks,
    db: Session = fastapi.Depends(get_db)
):
    """Join a queue and get a token (office hours: 10 AM – 5 PM, daily reset from #1)"""
    import random
    import uuid
    from datetime import timedelta, date as date_type
    from zoneinfo import ZoneInfo

    queue = db.query(Queue).filter(Queue.id == queue_id).first()
    if not queue:
        raise fastapi.HTTPException(status_code=404, detail="Queue not found")

    # ── Parse service_date ──────────────────────────────────────────────────
    NPT = ZoneInfo("Asia/Kathmandu")
    now_npt = datetime.now(NPT)
    today_npt = now_npt.date()

    if token_data.service_date:
        try:
            svc_date = date_type.fromisoformat(token_data.service_date)
        except ValueError:
            raise fastapi.HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")
        if svc_date < today_npt:
            raise fastapi.HTTPException(status_code=400, detail="Cannot book tokens for past dates.")
    else:
        svc_date = today_npt

    # -- Date-specific pause check -------------------------------------------
    svc_date_midnight = datetime.combine(svc_date, datetime.min.time())
    date_status = db.query(QueueDateStatus).filter(
        QueueDateStatus.queue_id == queue_id,
        QueueDateStatus.service_date == svc_date_midnight
    ).first()
    
    is_accepting = date_status.is_accepting_tokens if date_status else queue.is_accepting_tokens
    
    if is_accepting == 0:
        raise fastapi.HTTPException(
            status_code=403,
            detail=f"Token generation for '{queue.name}' on {svc_date} is paused by administration."
        )

    # Store as UTC midnight for that Nepal date (NPT is UTC+5:45)
    # We store the date as a plain midnight datetime in UTC for consistency
    service_date = datetime(
        svc_date.year, svc_date.month, svc_date.day,
        0, 0, 0
    )

    # -- Daily limit check ---------------------------------------------------
    tokens_issued_for_date = db.query(Token).filter(
        Token.queue_id == queue_id,
        Token.service_date == service_date
    ).count()

    if queue.daily_limit > 0 and tokens_issued_for_date >= queue.daily_limit:
        raise fastapi.HTTPException(
            status_code=403,
            detail=f"INVALID: Token limit ({queue.daily_limit}) reached for {svc_date.strftime('%B %d, %Y')}."
        )

    # ── Cooldown: same phone cannot book twice in 24h for the same date ────
    if token_data.phone:
        existing = db.query(Token).filter(
            Token.phone == token_data.phone,
            Token.queue_id == queue_id,
            Token.service_date == service_date,
            Token.state.notin_([TokenState.CANCELLED, TokenState.NO_SHOW])
        ).first()
        if existing:
            raise fastapi.HTTPException(
                status_code=409,
                detail=f"You already have Token #{existing.number} booked for {svc_date.strftime('%B %d, %Y')}."
            )

    # ── Assign next token number (resets to 1 each day) ────────────────────
    # Synchronized across the entire organization as requested
    last_token = db.query(Token).join(Queue).filter(
        Queue.organization_id == queue.organization_id,
        Token.service_date == service_date
    ).order_by(Token.number.desc()).first()
    next_number = (last_token.number + 1) if last_token else 1

    # ── Compute estimated reporting time ────────────────────────────────────
    # Office: 10:00 AM to 5:00 PM = 420 minutes
    # Interval = 420 / daily_limit (or 5 min default if unlimited)
    OFFICE_START_HOUR = 10
    TOTAL_OFFICE_MINUTES = 420  # 7 hours
    if queue.daily_limit and queue.daily_limit > 0:
        interval_minutes = TOTAL_OFFICE_MINUTES / queue.daily_limit
    else:
        interval_minutes = 5  # Default 5-min slots when unlimited

    # Use current Nepal Time as the 'reported' (requested) time
    reporting_time_str = now_npt.strftime("%I:%M %p")

    # ── Risk scoring ────────────────────────────────────────────────────────
    risk_status = "reliable"
    requires_confirmation = 0
    if token_data.phone:
        history_tokens = db.query(Token).filter(
            Token.phone == token_data.phone,
            Token.state.in_([TokenState.COMPLETED, TokenState.NO_SHOW, TokenState.CANCELLED])
        ).all()
        total_history = len(history_tokens)
        if total_history >= 3:
            attended = sum(1 for t in history_tokens if t.state == TokenState.COMPLETED)
            score = attended / total_history
            if score > 0.8:
                risk_status = "reliable"
            elif score >= 0.5:
                risk_status = "moderate_risk"
            else:
                risk_status = "high_risk"
                requires_confirmation = 1

    # ── Create token ────────────────────────────────────────────────────────
    waiting_count = db.query(Token).filter(
        Token.queue_id == queue_id,
        Token.state == TokenState.WAITING,
        Token.service_date == service_date
    ).count()

    now_utc = datetime.utcnow()
    estimated_minutes = ml_engine.predict(now_utc.hour, now_utc.weekday(), waiting_count)

    db_token = Token(
        id=str(uuid.uuid4()),
        queue_id=queue_id,
        number=next_number,
        name=token_data.name,
        phone=token_data.phone,
        state=TokenState.WAITING,
        service_date=service_date,
        secret_token=str(uuid.uuid4()),
        verification_pin=str(random.randint(1000, 9999)),
        risk_status=risk_status,
        requires_confirmation=requires_confirmation,
        is_confirmed=0,
        estimated_wait_minutes=estimated_minutes,
        estimated_reporting_time=reporting_time_str,
        initial_queue_depth=waiting_count,
        priority_level=token_data.priority_level or 0
    )

    if token_data.phone:
        NPT = ZoneInfo("Asia/Kathmandu")
        joined_time_npt = now_utc.astimezone(NPT).strftime("%I:%M %p")
        msg = (
            f"Namaste {token_data.name or 'User'}! Your Pālo token for {queue.name} is #{db_token.number}. "
            f"Registered at {joined_time_npt}. Please report by {reporting_time_str}. "
            f"Track live: https://palo.quest/t/{db_token.id}"
        )
        if requires_confirmation == 1:
            msg += "\nACTION REQUIRED: Reply 'YES' to confirm your attendance."
        background_tasks.add_task(send_sms, token_data.phone, msg)

    db.add(db_token)
    db.commit()
    db.refresh(db_token)
    return db_token


@app.get("/queues/{queue_id}/tokens", response_model=TokenListResponse)
async def list_tokens(queue_id: str, service_date: str = None, db: Session = fastapi.Depends(get_db)):
    """List all tokens in a queue for a given date (YYYY-MM-DD). Defaults to today (Nepal time)."""
    from zoneinfo import ZoneInfo
    from datetime import date as date_type
    queue = db.query(Queue).filter(Queue.id == queue_id).first()
    if not queue:
        raise fastapi.HTTPException(status_code=404, detail="Queue not found")

    NPT = ZoneInfo("Asia/Kathmandu")
    if service_date:
        svc = date_type.fromisoformat(service_date)
    else:
        svc = datetime.now(NPT).date()
    target_date = datetime(svc.year, svc.month, svc.day, 0, 0, 0)

    tokens = db.query(Token).filter(
        Token.queue_id == queue_id,
        Token.service_date == target_date
    ).order_by(Token.number).all()

    waiting   = sum(1 for t in tokens if t.state == TokenState.WAITING)
    serving   = sum(1 for t in tokens if t.state == TokenState.SERVING)
    completed = sum(1 for t in tokens if t.state == TokenState.COMPLETED)

    return TokenListResponse(
        tokens=tokens,
        total=len(tokens),
        waiting=waiting,
        serving=serving,
        completed=completed
    )


@app.get("/tokens/{token_id}", response_model=TokenResponse)
async def get_token(
    token_id: str, 
    db: Session = fastapi.Depends(get_db),
    x_token_secret: Optional[str] = fastapi.Header(None)
):
    """Get token by ID (Masks sensitive data if secret is missing)"""
    token = db.query(Token).filter(Token.id == token_id).first()
    if not token:
        raise fastapi.HTTPException(status_code=404, detail="Token not found")
    
    # Simple masking logic
    if not x_token_secret or x_token_secret != token.secret_token:
        # Mask pin, phone and email for public viewing
        token.verification_pin = "****"
        if token.phone:
            token.phone = token.phone[:3] + "****" + token.phone[-2:] if len(token.phone) > 5 else "***"
        if token.email:
            parts = token.email.split("@")
            token.email = parts[0][:2] + "..." + "@" + parts[1] if len(parts) > 1 else "***"
            
    # Dynamically update the AI predicted wait time based on current position
    if token.state == TokenState.WAITING:
        tokens_ahead = db.query(Token).filter(
            Token.queue_id == token.queue_id,
            Token.service_date == token.service_date,
            Token.state == TokenState.WAITING,
            Token.joined_at < token.joined_at
        ).count()
        
        # If there are no users ahead, estimated wait is 0 (or almost your turn)
        if tokens_ahead == 0:
            token.estimated_wait_minutes = 0
        else:
            now = datetime.utcnow()
            est = ml_engine.predict(now.hour, now.weekday(), tokens_ahead)
            if est is None:
                # Fallback heuristic if ML not trained
                est = max(1, tokens_ahead * 8)
            token.estimated_wait_minutes = est
            
    return token


@app.patch("/tokens/{token_id}", response_model=TokenResponse)
async def update_token_state(
    token_id: str,
    state_update: TokenStateUpdate,
    background_tasks: fastapi.BackgroundTasks,
    db: Session = fastapi.Depends(get_db)
):
    """Update token state"""
    token = db.query(Token).filter(Token.id == token_id).first()
    if not token:
        raise fastapi.HTTPException(status_code=404, detail="Token not found")
    
    now = datetime.utcnow()
    
    # State transitions
    token.state = TokenState(state_update.state)
    
    if token.state == TokenState.CALLED:
        token.called_at = now
        if token.phone:
            msg = f"TOKEN ALERT: #{token.number}, your turn has arrived! Please proceed to the counter now. - Pālo Queue"
            background_tasks.add_task(send_sms, token.phone, msg)
    
    if token.state == TokenState.COMPLETED and not token.completed_at:
        token.completed_at = now
        if token.joined_at:
            wait_minutes = (now - token.joined_at).total_seconds() / 60
            token.wait_time_minutes = wait_minutes
            
            # Record training data
            training_record = TrainingData(
                id=str(uuid.uuid4()),
                queue_id=token.queue_id,
                hour_of_day=token.joined_at.hour,
                day_of_week=token.joined_at.weekday(),
                queue_depth=token.initial_queue_depth or 0,
                wait_time_minutes=wait_minutes
            )
            db.add(training_record)
    
    db.commit()
    db.refresh(token)
    return token


@app.patch("/tokens/{token_id}/priority", response_model=TokenResponse)
async def update_token_priority(
    token_id: str,
    priority_update: TokenPriorityUpdate,
    db: Session = fastapi.Depends(get_db)
):
    """Update token priority level (0=Normal, 100=High, 1000=Emergency)"""
    token = db.query(Token).filter(Token.id == token_id).first()
    if not token:
        raise fastapi.HTTPException(status_code=404, detail="Token not found")
    
    token.priority_level = priority_update.priority_level
    db.commit()
    db.refresh(token)
    return token


@app.post("/tokens/{token_id}/confirm", response_model=TokenResponse)
async def confirm_token(token_id: str, db: Session = fastapi.Depends(get_db)):
    """Confirm attendance for a high-risk token"""
    token = db.query(Token).filter(Token.id == token_id).first()
    if not token:
        raise fastapi.HTTPException(status_code=404, detail="Token not found")
    
    token.is_confirmed = 1
    db.commit()
    db.refresh(token)
    return token


# ============================================================================
# Counters
# ============================================================================

@app.post("/queues/{queue_id}/counters", response_model=CounterResponse)
async def create_counter(
    queue_id: str,
    counter: CounterCreate,
    db: Session = fastapi.Depends(get_db)
):
    """Create a counter"""
    queue = db.query(Queue).filter(Queue.id == queue_id).first()
    if not queue:
        raise fastapi.HTTPException(status_code=404, detail="Queue not found")
    
    db_counter = Counter(
        id=str(uuid.uuid4()),
        queue_id=queue_id,
        number=counter.number,
        name=counter.name,
        operator_name=counter.operator_name
    )
    db.add(db_counter)
    db.commit()
    db.refresh(db_counter)
    return db_counter


@app.get("/queues/{queue_id}/counters", response_model=list[CounterResponse])
async def list_counters(queue_id: str, db: Session = fastapi.Depends(get_db)):
    """List all counters for a queue"""
    queue = db.query(Queue).filter(Queue.id == queue_id).first()
    if not queue:
        raise fastapi.HTTPException(status_code=404, detail="Queue not found")
    
    counters = db.query(Counter).filter(Counter.queue_id == queue_id).all()
    return counters


@app.patch("/counters/{counter_id}", response_model=CounterResponse)
async def update_counter(
    counter_id: str,
    counter_update: CounterUpdate,
    db: Session = fastapi.Depends(get_db)
):
    """Update counter"""
    counter = db.query(Counter).filter(Counter.id == counter_id).first()
    if not counter:
        raise fastapi.HTTPException(status_code=404, detail="Counter not found")
    
    if counter_update.name:
        counter.name = counter_update.name
    if counter_update.operator_name:
        counter.operator_name = counter_update.operator_name
    if counter_update.status:
        counter.status = counter_update.status
    if counter_update.current_token_id:
        counter.current_token_id = counter_update.current_token_id
    
    db.commit()
    db.refresh(counter)
    return counter


# ============================================================================
# Dashboard & Analytics
# ============================================================================


@app.post("/queues/{queue_id}/reset")
async def reset_queue(queue_id: str, req: QueueResetRequest | None = None, db: Session = fastapi.Depends(get_db)):
    """Reset tokens for a specific queue and date. DANGER: Deletes records."""
    from zoneinfo import ZoneInfo
    from datetime import date as date_type
    
    NPT = ZoneInfo("Asia/Kathmandu")
    svc_date_str = req.service_date if (req and req.service_date) else datetime.now(NPT).strftime("%Y-%m-%d")
    svc = date_type.fromisoformat(svc_date_str)
    target_date = datetime(svc.year, svc.month, svc.day, 0, 0, 0)
    
    # Delete tokens for this queue and date
    deleted = db.query(Token).filter(
        Token.queue_id == queue_id,
        Token.service_date == target_date
    ).delete()
    
    db.commit()
    
    return {
        "status": "success",
        "deleted_count": deleted,
        "service_date": svc_date_str,
        "message": f"Successfully cleared {deleted} tokens for {svc_date_str}."
    }


@app.get("/queues/{queue_id}/stats", response_model=QueueStatsResponse)
async def get_queue_stats(queue_id: str, service_date: str = None, db: Session = fastapi.Depends(get_db)):
    """Get queue statistics for a given date (YYYY-MM-DD). Defaults to today (Nepal time)."""
    from zoneinfo import ZoneInfo
    from datetime import date as date_type
    queue = db.query(Queue).filter(Queue.id == queue_id).first()
    if not queue:
        raise fastapi.HTTPException(status_code=404, detail="Queue not found")

    NPT = ZoneInfo("Asia/Kathmandu")
    if service_date:
        svc = date_type.fromisoformat(service_date)
    else:
        svc = datetime.now(NPT).date()
    # Store/Compare as midnight naive to match create_token storage
    target_date = datetime(svc.year, svc.month, svc.day, 0, 0, 0)

    waiting = db.query(Token).filter(
        Token.queue_id == queue_id,
        Token.state == TokenState.WAITING,
        Token.service_date == target_date
    ).count()

    serving = db.query(Token).filter(
        Token.queue_id == queue_id,
        Token.state == TokenState.SERVING,
        Token.service_date == target_date
    ).count()

    completed = db.query(Token).filter(
        Token.queue_id == queue_id,
        Token.state == TokenState.COMPLETED,
        Token.service_date == target_date
    ).count()

    skipped = db.query(Token).filter(
        Token.queue_id == queue_id,
        Token.state.in_([TokenState.SKIPPED, TokenState.NO_SHOW]),
        Token.service_date == target_date
    ).count()

    total_issued = db.query(Token).filter(
        Token.queue_id == queue_id,
        Token.service_date == target_date
    ).count()

    counters = db.query(Counter).filter(Counter.queue_id == queue_id).all()
    active_counters = sum(1 for c in counters if c.status != "idle")

    completed_tokens = db.query(Token).filter(
        Token.queue_id == queue_id,
        Token.state == TokenState.COMPLETED,
        Token.wait_time_minutes != None
    ).all()
    avg_wait = None
    if completed_tokens:
        avg_wait = sum(t.wait_time_minutes for t in completed_tokens) / len(completed_tokens)

    # Get date-specific pause status
    date_status = db.query(QueueDateStatus).filter(
        QueueDateStatus.queue_id == queue_id,
        QueueDateStatus.service_date == target_date
    ).first()
    is_accepting = date_status.is_accepting_tokens if date_status else queue.is_accepting_tokens

    return QueueStatsResponse(
        queue_id=queue_id,
        queue_name=queue.name,
        total_waiting=waiting,
        total_serving=serving,
        total_completed_today=completed,
        total_skipped=skipped,
        total_issued=total_issued,
        avg_wait_time=avg_wait,
        counters_active=active_counters,
        counters_total=len(counters),
        is_accepting_tokens=is_accepting
    )


@app.get("/queues/{queue_id}/operator-view", response_model=OperatorQueueResponse)
async def get_operator_view(queue_id: str, service_date: str = None, db: Session = fastapi.Depends(get_db)):
    """Get queue data for operator dashboard for a given date (YYYY-MM-DD). Defaults to today (Nepal time)."""
    from zoneinfo import ZoneInfo
    from datetime import date as date_type
    queue = db.query(Queue).filter(Queue.id == queue_id).first()
    if not queue:
        raise fastapi.HTTPException(status_code=404, detail="Queue not found")

    NPT = ZoneInfo("Asia/Kathmandu")
    if service_date:
        svc = date_type.fromisoformat(service_date)
    else:
        svc = datetime.now(NPT).date()
    target_date = datetime(svc.year, svc.month, svc.day, 0, 0, 0)

    # Fetch both WAITING and DELAYED tokens
    all_candidates = db.query(Token).filter(
        Token.queue_id == queue_id,
        Token.state.in_([TokenState.WAITING, TokenState.DELAYED]),
        Token.service_date == target_date
    ).all()

    now_utc = datetime.utcnow()
    waiting_tokens = []
    delayed_queue = []
    
    for t in all_candidates:
        if t.state == TokenState.DELAYED:
            delayed_queue.append(t)
        else:
            # Dynamic Score = priority_level + minutes_waiting
            wait_time = (now_utc - t.joined_at).total_seconds() / 60
            # We don't store score in DB, just calculate for sorting
            t.temp_score = t.priority_level + wait_time
            waiting_tokens.append(t)

    # Sort waiting by dynamic score descending, secondary sort by token number
    waiting_tokens.sort(key=lambda x: (-x.temp_score, x.number))
    
    # Bucket separation
    emergency_queue = [t for t in waiting_tokens if t.priority_level >= 1000]
    priority_queue = [t for t in waiting_tokens if 100 <= t.priority_level < 1000]
    normal_queue = [t for t in waiting_tokens if t.priority_level < 100]

    serving = db.query(Token).filter(
        Token.queue_id == queue_id,
        Token.state == TokenState.SERVING,
        Token.service_date == target_date
    ).all()

    counters = db.query(Counter).filter(Counter.queue_id == queue_id).all()
    next_token = waiting_tokens[0] if waiting_tokens else None

    # Get date-specific pause status
    date_status = db.query(QueueDateStatus).filter(
        QueueDateStatus.queue_id == queue_id,
        QueueDateStatus.service_date == target_date
    ).first()
    is_accepting = date_status.is_accepting_tokens if date_status else queue.is_accepting_tokens

    return OperatorQueueResponse(
        queue_id=queue_id,
        queue_name=queue.name,
        waiting_tokens=waiting_tokens,
        serving_tokens=serving,
        emergency_queue=emergency_queue,
        priority_queue=priority_queue,
        normal_queue=normal_queue,
        delayed_queue=delayed_queue,
        counters=counters,
        next_token=next_token,
        is_accepting_tokens=is_accepting
    )


@app.post("/ml/train")
async def train_ml_model(db: Session = fastapi.Depends(get_db)):
    """Train ML model on historical data"""
    # Get all training data
    training_records = db.query(TrainingData).all()
    
    if len(training_records) < 10:
        raise fastapi.HTTPException(
            status_code=400,
            detail=f"Not enough training data ({len(training_records)} records). Need at least 10."
        )
    
    training_data = [
        {
            "hour_of_day": t.hour_of_day,
            "day_of_week": t.day_of_week,
            "queue_depth": t.queue_depth,
            "wait_time_minutes": t.wait_time_minutes
        }
        for t in training_records
    ]
    
    success = ml_engine.train(training_data)
    
    if not success:
        raise fastapi.HTTPException(status_code=500, detail="Training failed")
    
    return {
        "status": "success",
        "records_trained": len(training_data),
        "model_info": ml_engine.get_model_info()
    }


@app.get("/ml/model-info")
async def get_model_info():
    """Get ML model information"""
    return ml_engine.get_model_info()


# ============================================================================
# Cross-Device Token Lookup
# ============================================================================

class TokenLookupRequest(BaseModel):
    phone: str
    verification_pin: str


@app.post("/tokens/lookup")
async def lookup_token(
    req: TokenLookupRequest,
    db: Session = fastapi.Depends(get_db)
):
    """
    Allows a user to retrieve their active ticket from another device.
    Supply the phone number used at registration and the 4-digit verification
    PIN shown on the ticket. Returns token_id + secret_token so the frontend
    can restore a full verified session.
    """
    # Normalise phone (strip spaces/dashes for comparison)
    phone_clean = req.phone.strip()

    token = db.query(Token).filter(
        Token.phone == phone_clean,
        Token.verification_pin == req.verification_pin.strip(),
        Token.state.in_([
            TokenState.WAITING,
            TokenState.CALLED,
            TokenState.SERVING,
        ])
    ).order_by(Token.joined_at.desc()).first()

    if not token:
        raise fastapi.HTTPException(
            status_code=404,
            detail="No active ticket found for this phone number and PIN combination. "
                   "Make sure you entered the correct details."
        )

    return {
        "token_id": token.id,
        "secret_token": token.secret_token,
        "token_number": token.number,
        "name": token.name,
        "state": token.state,
    }


# ============================================================================
# ML Wait Time Prediction (Live)
# ============================================================================

@app.get("/queues/{queue_id}/predict")
async def predict_wait_time(queue_id: str, db: Session = fastapi.Depends(get_db)):
    """Predict estimated wait time for joining now based on current queue depth"""
    queue = db.query(Queue).filter(Queue.id == queue_id).first()
    if not queue:
        raise fastapi.HTTPException(status_code=404, detail="Queue not found")

    from zoneinfo import ZoneInfo
    NPT = ZoneInfo("Asia/Kathmandu")
    today_npt = datetime.now(NPT).date()
    target_date = datetime(today_npt.year, today_npt.month, today_npt.day, 0, 0, 0)

    waiting_count = db.query(Token).filter(
        Token.queue_id == queue_id,
        Token.state == TokenState.WAITING,
        Token.service_date == target_date
    ).count()

    now = datetime.utcnow()
    hour = now.hour
    day_of_week = now.weekday()

    if waiting_count == 0:
        prediction = 0
        source = "heuristic"
    else:
        prediction = ml_engine.predict(hour, day_of_week, waiting_count)
        # Fallback heuristic if model is not trained: 8 min per person
        if prediction is None:
            prediction = max(1, waiting_count * 8)
            source = "heuristic"
        else:
            source = "ml_model"

    return {
        "queue_id": queue_id,
        "current_waiting": waiting_count,
        "estimated_wait_minutes": round(prediction, 1),
        "source": source,
        "is_ml_trained": ml_engine.is_trained,
        "hour_of_day": hour,
        "day_of_week": day_of_week,
    }


@app.post("/ml/seed-data")
async def seed_training_data(db: Session = fastapi.Depends(get_db)):
    """Seed synthetic training data to bootstrap the ML model"""
    import random
    import math

    existing = db.query(TrainingData).count()
    if existing >= 50:
        return {"status": "already_seeded", "records": existing}

    records_to_add = []
    for _ in range(200):
        hour = random.randint(7, 18)
        day = random.randint(0, 6)
        depth = random.randint(0, 30)

        # Realistic wait time: higher at peak hours (9-11am, 2-4pm), less on weekends
        base_time = depth * 6.5
        peak_factor = 1.0
        if 9 <= hour <= 11 or 14 <= hour <= 16:
            peak_factor = 1.4
        elif hour < 9 or hour > 17:
            peak_factor = 0.6
        if day >= 5:  # weekend
            peak_factor *= 0.7
        noise = random.gauss(0, 2)
        wait_time = max(1, base_time * peak_factor + noise)

        records_to_add.append(TrainingData(
            id=str(uuid.uuid4()),
            queue_id=None,
            hour_of_day=hour,
            day_of_week=day,
            queue_depth=depth,
            wait_time_minutes=round(wait_time, 2)
        ))

    db.bulk_save_objects(records_to_add)
    db.commit()

    # Auto-train after seeding
    all_records = db.query(TrainingData).all()
    training_data = [
        {"hour_of_day": t.hour_of_day, "day_of_week": t.day_of_week,
         "queue_depth": t.queue_depth, "wait_time_minutes": t.wait_time_minutes}
        for t in all_records
    ]
    ml_engine.train(training_data)

    return {"status": "seeded_and_trained", "records_added": len(records_to_add), "model_info": ml_engine.get_model_info()}


# ============================================================================
# Admin Credentials Management
# ============================================================================

import json

CREDENTIALS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "admin_credentials.json")

def _load_credentials() -> dict:
    if os.path.exists(CREDENTIALS_FILE):
        try:
            with open(CREDENTIALS_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"pin": "1234"}

def _save_credentials(creds: dict):
    with open(CREDENTIALS_FILE, "w") as f:
        json.dump(creds, f)


@app.get("/admin/credentials")
async def get_admin_pin():
    """Return the current admin PIN (used by frontend to validate login)"""
    creds = _load_credentials()
    return {"pin": creds.get("pin", "1234")}


class ChangePasswordRequest(fastapi.BaseModel if False else object):
    pass

from pydantic import BaseModel as _BaseModel

class ChangePasswordRequest(_BaseModel):
    current_pin: str
    new_pin: str


@app.post("/admin/change-password")
async def change_admin_password(req: ChangePasswordRequest):
    """Change the admin PIN"""
    creds = _load_credentials()
    if req.current_pin != creds.get("pin", "1234"):
        raise fastapi.HTTPException(status_code=403, detail="Current PIN is incorrect.")
    if len(req.new_pin) < 4:
        raise fastapi.HTTPException(status_code=400, detail="New PIN must be at least 4 digits.")
    if not req.new_pin.isdigit():
        raise fastapi.HTTPException(status_code=400, detail="PIN must contain only digits.")
    creds["pin"] = req.new_pin
    _save_credentials(creds)
    return {"status": "success", "message": "PIN updated successfully."}

