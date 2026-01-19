"""Simple logging utility for the shell."""
import sys
from enum import Enum
from typing import Optional


class LogLevel(Enum):
    """Log levels."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class Logger:
    """Simple logger for shell operations."""
    
    def __init__(self, level: LogLevel = LogLevel.WARNING, enabled: bool = True):
        self.level = level
        self.enabled = enabled
    
    def _should_log(self, level: LogLevel) -> bool:
        """Check if message should be logged."""
        if not self.enabled:
            return False
        
        levels = [LogLevel.DEBUG, LogLevel.INFO, LogLevel.WARNING, LogLevel.ERROR]
        return levels.index(level) >= levels.index(self.level)
    
    def _log(self, level: LogLevel, message: str):
        """Internal logging method."""
        if self._should_log(level):
            prefix = f"[{level.value}]"
            sys.stderr.write(f"{prefix} {message}\n")
    
    def debug(self, message: str):
        """Log debug message."""
        self._log(LogLevel.DEBUG, message)
    
    def info(self, message: str):
        """Log info message."""
        self._log(LogLevel.INFO, message)
    
    def warning(self, message: str):
        """Log warning message."""
        self._log(LogLevel.WARNING, message)
    
    def error(self, message: str):
        """Log error message."""
        self._log(LogLevel.ERROR, message)


# Default logger instance
_default_logger: Optional[Logger] = None


def get_logger() -> Logger:
    """Get the default logger instance."""
    global _default_logger
    if _default_logger is None:
        # Check environment variable for log level
        import os
        log_level = os.getenv("AXONIX_LOG_LEVEL", "WARNING").upper()
        try:
            level = LogLevel[log_level]
        except KeyError:
            level = LogLevel.WARNING
        
        enabled = os.getenv("AXONIX_LOG_ENABLED", "false").lower() == "true"
        _default_logger = Logger(level=level, enabled=enabled)
    
    return _default_logger
