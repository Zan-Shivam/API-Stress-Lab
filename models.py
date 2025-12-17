from sqlalchemy import Column, Integer, String, DateTime, Text
from sqlalchemy.sql import func

from database import Base

class TestRun(Base):
    __tablename__ = "test_runs"

    id = Column(Integer, primary_key=True, index=True)

    url = Column(String, nullable=False)
    method = Column(String, nullable=False)
    total_requests = Column(Integer, nullable=False)
    concurrency = Column(Integer, nullable=False)
    label = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    #storing as a text rn
    metrics_json = Column(Text, nullable=False)
