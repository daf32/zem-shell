import logging as _logging

# Default to a NullHandler so library use doesn't emit "No handlers found"
# warnings; `main.main()` opts into stderr output via `AXONIX_LOG_ENABLED`.
_logging.getLogger("axonix").addHandler(_logging.NullHandler())
