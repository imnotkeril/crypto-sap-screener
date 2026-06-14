"""
Database connection and session management
"""
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Enum, JSON, Date, UniqueConstraint, text, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.engine.url import make_url
from datetime import datetime
import enum
import os

from app.config import settings
import urllib.parse

# Set environment variable to ensure UTF-8 encoding for psycopg2 (PostgreSQL only)
if "postgres" in settings.DATABASE_URL.lower():
    os.environ.setdefault('PGCLIENTENCODING', 'UTF8')

# Encode database URL to handle special characters
def get_database_url():
    """Get database URL with proper encoding"""
    url = settings.DATABASE_URL
    # For SQLite, don't parse/reconstruct - urlparse can break the triple-slash format
    if url.lower().startswith("sqlite"):
        return url
    # For PostgreSQL and other backends, handle encoding
    try:
        # Convert to bytes and back to ensure proper encoding
        if isinstance(url, str):
            url_bytes = url.encode('utf-8')
            url = url_bytes.decode('utf-8')
        
        # Parse and reconstruct URL to handle encoding
        parsed = urllib.parse.urlparse(url)
        # Reconstruct with proper encoding
        encoded = urllib.parse.urlunparse(parsed)
        return encoded
    except Exception as e:
        import logging
        logging.warning(f"Error encoding database URL: {e}, using original URL")
        return url

# Flag to track if database is disabled due to encoding errors
_db_disabled = False

# Create database engine with connection pool settings
try:
    db_url = get_database_url()

    def _safe_url_parts(url_str: str) -> dict:
        try:
            u = make_url(url_str)
            return {
                "drivername": u.drivername,
                "username_present": bool(u.username),
                "host": u.host,
                "database": u.database,
            }
        except Exception as e:
            return {"parse_error": type(e).__name__, "raw": url_str}

    def _ensure_sqlite_parent_dir(url_str: str) -> None:
        """Ensure parent directory exists for sqlite file DBs."""
        try:
            url = make_url(url_str)
            if (url.drivername or "").startswith("sqlite"):
                db_path = url.database
                if not db_path or db_path == ":memory:":
                    return
                parent = os.path.dirname(db_path)
                if parent:
                    os.makedirs(parent, exist_ok=True)
        except Exception:
            # Best-effort only; engine creation will fail loudly if path is invalid.
            return
    
    # Ensure URL uses psycopg2 driver explicitly for PostgreSQL
    if "postgresql" in db_url.lower() and "psycopg2" not in db_url.lower():
        # Replace postgresql:// with postgresql+psycopg2://
        db_url = db_url.replace("postgresql://", "postgresql+psycopg2://", 1)
    
    # Connect args by backend
    connect_args = {}
    if db_url.lower().startswith("sqlite"):
        _ensure_sqlite_parent_dir(db_url)
        # SQLite needs this for multithreaded FastAPI usage.
        connect_args = {"check_same_thread": False}
    elif "postgresql" in db_url.lower() or "postgres" in db_url.lower():
        # PostgreSQL: ensure proper encoding is set and fail fast on connection
        # issues instead of hanging past the frontend's request timeout.
        connect_args = {"client_encoding": "UTF8", "connect_timeout": 5}
    
    # Create engine with explicit encoding handling
    engine = create_engine(
        db_url, 
        echo=False,
        pool_pre_ping=True,  # Verify connections before using
        pool_recycle=3600,   # Recycle connections after 1 hour
        connect_args=connect_args
    )
    
    # Test connection immediately to catch encoding errors early
    try:
        with engine.connect() as test_conn:
            test_conn.execute(text("SELECT 1"))
    except UnicodeDecodeError:
        # If encoding error occurs, disable database
        import logging
        logging.warning("Database disabled due to encoding error. Will work without DB.")
        engine = None
        SessionLocal = None
        _db_disabled = True
    except Exception:
        # Other connection errors are OK - DB might not be running
        pass
    
    if engine is not None:
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    else:
        SessionLocal = None
        
except UnicodeDecodeError as e:
    import logging
    logging.error(f"Unicode decode error creating database engine: {e}")
    if hasattr(e, 'start'):
        logging.error(f"Error at position {e.start}, object: {e.object if hasattr(e, 'object') else 'N/A'}")
    engine = None
    SessionLocal = None
    _db_disabled = True
except Exception as e:
    import logging
    logging.warning(f"Could not create database engine: {e}")
    import traceback
    logging.debug(traceback.format_exc())
    engine = None
    SessionLocal = None

Base = declarative_base()


class PairStatus(str, enum.Enum):
    """Status of a trading pair"""
    ACTIVE = "active"
    INACTIVE = "inactive"


class ScreeningSession(Base):
    """Screening session metadata"""
    __tablename__ = "screening_sessions"
    
    id = Column(Integer, primary_key=True, index=True)
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    total_pairs_tested = Column(Integer, default=0)
    pairs_found = Column(Integer, default=0)
    config = Column(JSON, nullable=True)  # Screening parameters
    status = Column(String, default="running")  # running, completed, failed


class PairsScreeningResult(Base):
    """Results of pairs screening"""
    __tablename__ = "pairs_screening_results"
    
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, nullable=True)  # Link to screening session
    asset_a = Column(String, index=True)
    asset_b = Column(String, index=True)
    correlation = Column(Float)
    adf_pvalue = Column(Float)
    adf_statistic = Column(Float)
    beta = Column(Float)  # Hedge ratio
    alpha = Column(Float, nullable=True)  # Intercept
    spread_std = Column(Float)  # σ_ε
    hurst_exponent = Column(Float, nullable=True)
    screening_date = Column(DateTime, default=datetime.utcnow)
    lookback_days = Column(Integer)
    status = Column(String, default="active")
    
    # Additional metrics
    mean_spread = Column(Float, nullable=True)
    min_correlation_window = Column(Float, nullable=True)
    max_correlation_window = Column(Float, nullable=True)
    composite_score = Column(Float, nullable=True)
    current_zscore = Column(Float, nullable=True)


class PriceDataCache(Base):
    """Cached price data from exchanges"""
    __tablename__ = "price_data_cache"
    
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, index=True)
    date = Column(Date, index=True)
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)
    volume = Column(Float)
    
    __table_args__ = (
        UniqueConstraint('symbol', 'date', name='uq_symbol_date'),
    )


class IntradaySnapshot(Base):
    """Persisted intraday z-score snapshot for a pair (used for sparkline history)"""
    __tablename__ = "intraday_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    asset_a = Column(String, index=True)
    asset_b = Column(String, index=True)
    price_a = Column(Float)
    price_b = Column(Float)
    beta = Column(Float)
    spread = Column(Float)
    zscore = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class Alert(Base):
    """Alert configuration for Z-Score monitoring"""
    __tablename__ = "alerts"
    
    id = Column(Integer, primary_key=True, index=True)
    pair_id = Column(Integer, index=True)
    asset_a = Column(String)
    asset_b = Column(String)
    threshold_high = Column(Float, nullable=True)  # Alert when Z-Score >= this
    threshold_low = Column(Float, nullable=True)  # Alert when Z-Score <= this
    enabled = Column(String, default="true")  # "true" or "false" as string for compatibility
    last_triggered = Column(DateTime, nullable=True)
    trigger_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


class BacktestSession(Base):
    """Backtest session"""
    __tablename__ = "backtest_sessions"
    
    id = Column(Integer, primary_key=True, index=True)
    asset_a = Column(String)
    asset_b = Column(String)
    strategy_type = Column(String)  # e.g., "zscore"
    entry_threshold = Column(Float)
    exit_threshold = Column(Float)
    initial_capital = Column(Float)
    start_date = Column(DateTime)
    end_date = Column(DateTime)
    request = Column(JSON, nullable=True)
    results = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class BacktestResult(Base):
    """Backtest results summary"""
    __tablename__ = "backtest_results"
    
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("backtest_sessions.id"), index=True)
    total_trades = Column(Integer)
    win_rate = Column(Float)
    total_return = Column(Float)
    sharpe_ratio = Column(Float)
    max_drawdown = Column(Float)
    profit_factor = Column(Float)
    final_capital = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)


class BacktestTrade(Base):
    """Individual backtest trade"""
    __tablename__ = "backtest_trades"
    
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("backtest_sessions.id"), index=True)
    entry_date = Column(DateTime)
    exit_date = Column(DateTime, nullable=True)
    entry_signal = Column(String)  # "long_spread" or "short_spread"
    entry_price_a = Column(Float)
    entry_price_b = Column(Float)
    exit_price_a = Column(Float, nullable=True)
    exit_price_b = Column(Float, nullable=True)
    entry_zscore = Column(Float)
    exit_zscore = Column(Float, nullable=True)
    pnl = Column(Float, nullable=True)
    pnl_pct = Column(Float, nullable=True)


class Position(Base):
    """Open trading position"""
    __tablename__ = "positions"
    
    id = Column(Integer, primary_key=True, index=True)
    pair_id = Column(Integer, index=True)
    asset_a = Column(String)
    asset_b = Column(String)
    side = Column(String)  # "long" or "short"
    quantity_a = Column(Float)
    quantity_b = Column(Float)
    entry_price_a = Column(Float)
    entry_price_b = Column(Float)
    beta = Column(Float)
    entry_zscore = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PositionUpdate(Base):
    """Position update history"""
    __tablename__ = "position_updates"
    
    id = Column(Integer, primary_key=True, index=True)
    position_id = Column(Integer, ForeignKey("positions.id"), index=True)
    current_price_a = Column(Float)
    current_price_b = Column(Float)
    pnl = Column(Float)
    timestamp = Column(DateTime, default=datetime.utcnow)


# Create all tables
def init_db():
    """Initialize database tables"""
    global _db_disabled
    
    if _db_disabled or engine is None:
        # Database is disabled or not available - skip initialization
        import logging
        logging.info("Skipping database initialization - database is disabled or not available")
        return
    
    try:
        # Test connection first
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        Base.metadata.create_all(bind=engine)
    except UnicodeDecodeError as e:
        # Handle encoding errors - disable database
        import logging
        logging.warning(f"Unicode decode error creating database tables: {e}")
        logging.warning("Database will be disabled. Application will work without database.")
        _db_disabled = True
        # Don't raise - allow app to continue without DB
    except Exception as e:
        # Log error but don't crash - database might not be available yet
        import logging
        logging.warning(f"Could not create database tables: {e}")
        # Don't raise - allow app to continue without DB


def get_db():
    """Dependency for getting database session"""
    global _db_disabled
    
    # If database is disabled due to encoding errors, skip all connection attempts
    if _db_disabled or SessionLocal is None:
        yield None
        return
    
    db = None
    try:
        db = SessionLocal()
        # Test connection with a simple query to catch encoding issues early
        try:
            # Use raw connection to avoid encoding issues
            result = db.execute(text("SELECT 1"))
            result.fetchone()
        except UnicodeDecodeError as encoding_error:
            # Handle encoding errors - disable database permanently
            if not _db_disabled:
                # Only log once when first detected
                import logging
                logger = logging.getLogger(__name__)
                logger.warning("Unicode decode error detected - database disabled. Application will work without database.")
            _db_disabled = True
            if db:
                try:
                    db.close()
                except:
                    pass
            yield None
            return
        except Exception as test_error:
            # If test query fails (e.g., connection refused), that's OK - DB might not be running
            # Silently return None without logging (to avoid spam in logs)
            if db:
                try:
                    db.close()
                except:
                    pass
            yield None
            return
        
        yield db
    except UnicodeDecodeError as e:
        # Handle encoding errors specifically
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Unicode decode error in database connection: {e}")
        if db:
            try:
                db.close()
            except:
                pass
        yield None
    except Exception as e:
        # Database connection error (e.g., connection refused)
        import logging
        logger = logging.getLogger(__name__)
        logger.debug(f"Database connection error: {e}")
        if db:
            try:
                db.close()
            except:
                pass
        yield None
    finally:
        if db:
            try:
                db.close()
            except:
                pass

