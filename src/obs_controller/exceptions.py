class OBSConnectionError(Exception):
    """Exception raised when there's an issue with connecting to OBS."""
    pass

class OBSReplayError(Exception):
    """Exception raised when saving or managing replay buffers fails."""
    pass

class OBSVideoError(Exception):
    """Exception raised when video file management fails."""
    pass

class OBSWebSocketError(Exception):
    """General exceptions related to OBS WebSocket interactions."""
    pass

class OBSProcessError(Exception):
    """Exception raised when there is an error with the OBS process check."""
    pass