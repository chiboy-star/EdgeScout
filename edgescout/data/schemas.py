"""
Data schemas and type validation for EdgeScout.
"""
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import date


class MatchRecord(BaseModel):
    match_id: str
    league_code: str
    league_name: Optional[str] = None
    season: str
    match_date: str
    match_time: Optional[str] = None
    home_team: str
    away_team: str
    fthg: Optional[int] = None
    ftag: Optional[int] = None
    ftr: Optional[str] = None
    hthg: Optional[int] = None
    htag: Optional[int] = None
    htr: Optional[str] = None


class OddsRecord(BaseModel):
    match_id: str
    b365_h: Optional[float] = None
    b365_d: Optional[float] = None
    b365_a: Optional[float] = None
    ps_h: Optional[float] = None
    ps_d: Optional[float] = None
    ps_a: Optional[float] = None
    b365_ch: Optional[float] = None
    b365_cd: Optional[float] = None
    b365_ca: Optional[float] = None
    ps_ch: Optional[float] = None
    ps_cd: Optional[float] = None
    ps_ca: Optional[float] = None
