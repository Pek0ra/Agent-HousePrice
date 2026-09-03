from functools import lru_cache

from app.agents.mysql_agent import MysqlNaturalLanguageAgent
from app.config import settings


@lru_cache
def get_mysql_agent() -> MysqlNaturalLanguageAgent:
    return MysqlNaturalLanguageAgent(settings)
