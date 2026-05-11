import logging


class IgnoreWs404Filter(logging.Filter):
    def filter(self, record):
        msg = record.getMessage()
        if '/ws/' in msg and ('404' in msg or 'Not Found' in msg):
            return False
        return True

