# obs_controller

A Python module to control OBS Studio, including launching the application, managing profiles, handling replay buffers, and connecting to the OBS WebSocket API.

## Features

- **Launch OBS Studio**: Start OBS if it is not already running.
- **Manage Profiles**: Set a default profile for OBS.
- **Enable WebSocket**: Enable WebSocket with the specified port and password.
- **WebSocket Connection**: Connect and communicate with OBS through its WebSocket API.
- **Replay Buffer Management**: Start, stop, and save replay buffers.
- **Video Management**: Check the latest video, manage folder size, and clean up old videos.

## First Time Setup

To use this module effectively, follow these setup steps:

1. **Add Source Display Capture**: 
   - Open OBS Studio.
   - In the `Sources` panel, click the `+` button and select `Display Capture`.
   - Configure the display capture as needed and click `OK`.


## Installation

```bash
pip install git+https://github.com/mathiascn/obs_controller.git
```

## Usage

Here’s a basic example of how to use the `OBSController` class:

```python
import logging
from obs_controller import OBSController

logging.basicConfig(level=logging.INFO)

obs = OBSController(password='your_websocket_password')

# Check if OBS is installed
if obs.is_obs_installed():
    logging.info("OBS is installed.")

# Enable WebSocket server
obs.enable_websocket()

# Launch OBS
obs.launch_obs()

# Connect to OBS WebSocket
if obs.connect():
    logging.info("Connected to OBS WebSocket.")

# Start the replay buffer
if obs.start_replay_buffer():
    logging.info("Replay buffer started.")

# Save the replay buffer
if obs.save_replay():
    logging.info("Replay saved.")

# Stop the replay buffer
if obs.stop_replay_buffer():
    logging.info("Replay buffer stopped.")

# Disconnect from OBS WebSocket
obs.disconnect()

# Cleanup on exit
obs.cleanup()
```

## Methods

#### `enable_websocket(self)`
Enables the OBS WebSocket server by modifying the global.ini configuration file.

#### `require_connection(f)`
Decorator to ensure a connection to the OBS WebSocket is established before calling the decorated method.

#### `require_process_running(f)`
Decorator to ensure the OBS process is running before calling the decorated method.

#### `cleanup(self) -> None`
Safely disconnects from the OBS WebSocket and terminates the OBS process if running.

#### `set_default_profile(self) -> None`
Sets the default OBS profile by copying the configuration from a predefined profile.

#### `is_obs_installed(self) -> bool`
Checks if the OBS executable is located at the predefined path.

#### `launch_obs(self) -> None`
Launches OBS studio if it's not already running.

#### `websocket_connection_health_check(self) -> bool`
Performs a health check for the OBS WebSocket server without affecting existing connections.

#### `is_connected(self) -> bool`
Checks if there is an active connection to the OBS WebSocket.

#### `connect(self) -> bool`
Attempts to connect to the OBS WebSocket.

#### `disconnect(self) -> bool`
Attempts to disconnect from the OBS WebSocket if currently connected.

#### `is_process_running(self) -> bool`
Checks if a specific process is currently running on the system.

#### `save_replay(self) -> bool`
Attempts to save the replay buffer to a file, verifying that a new file is created.

#### `start_replay_buffer(self) -> bool`
Attempts to start the replay buffer in OBS.

#### `stop_replay_buffer(self) -> bool`
Attempts to stop the replay buffer in OBS.

#### `get_latest_video(self) -> dict[str, str|None]`
Retrieves the most recently modified MP4 video file from the designated save path.

#### `check_and_manage_folder_size(self) -> None`
Checks the total size of video files in the designated directory and initiates cleanup if the size exceeds the configured maximum folder size.

#### `cleanup_videos(self) -> None`
Deletes the oldest MP4 video files in the directory until the total folder size is below the configured maximum limit.

## Logging

The module uses Python's built-in `logging` library for logging various actions and errors. You can configure the logging level to control the verbosity of the logs.

## Planned features
- Record keyboard inputs and mouse clicks - https://github.com/univrsal/input-overlay
- Set default scene to display capture main monitor