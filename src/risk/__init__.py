from datetime import datetime, timedelta
from typing import Optional

from src.config import Settings
from src.database import Database
from src.utils.logger import logger


class RiskManager:
    def __init__(self, settings: Settings, db: Database) -> None:
        self.settings = settings
        self.db = db
        self.daily_loss_start: Optional[datetime] = None
        self._halted = False

    async def check(self) -> bool:
        if self._halted:
            logger.warning("Trading halted by risk manager")
            return False

        if self.settings.max_daily_loss > 0:
            daily_pnl = self.db.get_daily_pnl()
            if daily_pnl <= -self.settings.max_daily_loss:
                logger.warning(
                    "Daily loss limit reached: $%.2f / $%.2f",
                    daily_pnl, self.settings.max_daily_loss,
                )
                self._halted = True
                return False

        if self.settings.max_consecutive_losses > 0:
            cons = self.db.get_consecutive_losses()
            if cons >= self.settings.max_consecutive_losses:
                logger.warning(
                    "Consecutive loss limit reached: %d / %d",
                    cons, self.settings.max_consecutive_losses,
                )
                self._halted = True
                return False

        return True

    def reset_daily(self) -> None:
        self._halted = False
