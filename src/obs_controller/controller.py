import os
import time
import logging
import atexit
from functools import wraps
import win32com.client
import subprocess
import shutil
import configparser
import pythoncom

from pathlib import Path
from obswebsocket import obsws, requests

from .exceptions import OBSConnectionError, OBSProcessError, OBSWebSocketError

logger = logging.getLogger("obs_controller")

class OBSController:
    def __init__(self, password:str, port:str = 4455, host:str = "localhost", **kwargs):
        self.host = host
        self.port = port
        self.password = password
        self.ws = None
        self.process_name = "obs64.exe"
        self.replay_save_path = Path(kwargs.get("replay_path")) if kwargs.get("replay_path") else Path(os.path.expandvars(r"%USERPROFILE%/Videos"))
        self.cwd = Path(kwargs.get("obs_path") + "/bin/64bit") if kwargs.get("obs_path") else Path("C:/Program Files/obs-studio/bin/64bit")
        self.obs_profiles_path = Path(os.path.expandvars("%AppData%")) / "obs-studio" / "basic" / "profiles"
        self.obs_global_ini = Path(os.path.expandvars("%AppData%")) / "obs-studio" / "global.ini"
        self.module_profile_path = Path(__file__).parent / "profiles" / "obs_controller"
        self.max_folder_size = int(kwargs.get("max_folder_size", 1024*1024*1024*5)) # Default 5 GB
        self.timeout = kwargs.get("timeout", 300)
        self.process = None
        atexit.register(self.cleanup)
    
    
    def enable_websocket(self) -> bool:
        """
        Enables the OBS WebSocket server by modifying the global.ini configuration file.
        
        This method ensures that the OBS WebSocket server is enabled with the specified
        port and password by updating the relevant entries in the global.ini file. If the
        global.ini file does not exist or an error occurs during the update process, a
        RuntimeError is raised.
        
        Process:
            1. Verify the existence of the global.ini file.
            2. Read the file content with utf-8-sig encoding to handle BOM.
            3. Remove the BOM if present.
            4. Parse the configuration content.
            5. Update the WebSocket server settings.
            6. Write the updated configuration back to the global.ini file.
        
        Returns:
            bool: `True` if global.ini is successfully updated, `False` otherwise.

        Raises:
            RuntimeError: If an error occurs while attempting to read or write the global.ini file.
        """
        try:
            if not self.obs_global_ini.exists():
                logger.error("obs_controller was not able to locate the global.ini file")
                return False
                
            # Load the configuration from the predefined profile
            config = configparser.ConfigParser()
            config.optionxform = str # Preserve the case of keys
            with open(self.obs_global_ini, 'r', encoding='utf-8-sig') as f:
                content = f.read()
            
            if content.startswith("\ufeff"):
                content = content[1:]
            
            config.read_string(content)
            
            # Update WebSocket server settings in the configuration
            config["OBSWebSocket"]["ServerEnabled"] = "true"
            config["OBSWebSocket"]["ServerPort"] = str(self.port)
            config["OBSWebSocket"]["ServerPassword"] = str(self.password)
            
            # Write the updated configuration
            with open(self.obs_global_ini, 'w', encoding='utf-8-sig') as f:
                config.write(f, space_around_delimiters=False)
                
            logger.debug("Successfully updated the WebSocket server settings in global.ini")
        except Exception as e:
            logger.exception("Failed to update WebSocket server settings")
            raise RuntimeError(f"Failed to update WebSocket server settings: {e}") from e
        
        return True
    
    def require_connection(f):
        """
        Decorator that ensures a connection to the OBS WebSocket is established before calling the decorated method.
        
        This decorator checks if the OBS WebSocket connection is active by verifying the `is_connected` property.
        If there is no active connection, it raises an `OBSWebSocketError`. If the connection is active, it allows 
        the decorated method to proceed as normal.
        
        Args:
            f (function): The function to be decorated.
        
        Returns:
            function: The wrapped function with a connection check.
        
        Raises:
            OBSWebSocketError: If there is no active connection to the OBS WebSocket.
        """
        @wraps(f)
        def wrapped(self:'OBSController', *args, **kwargs):
            if not self.is_connected:
                raise OBSWebSocketError("Not connected to OBS WebSocket.")
            return f(self, *args, **kwargs)
        return wrapped

    def require_process_running(f):
        """
        Decorator that ensures the OBS process is running before calling the decorated method.
        
        This decorator checks if the OBS process is running by verifying the `is_process_running` property.
        If the process is not running, it raises an `OBSProcessError`. If the process is running, it allows 
        the decorated method to proceed as normal.
        
        Args:
            f (function): The function to be decorated.
        
        Returns:
            function: The wrapped function with a process running check.
        
        Raises:
            OBSProcessError: If the OBS process is not running.
        """
        @wraps(f)
        def wrapped(self:'OBSController', *args, **kwargs):
            if not self.is_process_running:
                raise OBSProcessError("OBS process is not running.")
            return f(self, *args, **kwargs)
        return wrapped
    
    
    def cleanup(self) -> None:
        """
        Safely disconnects from the OBS WebSocket and terminates the OBS process if running.
        
        This method is registered to be called at script termination using `atexit` to ensure that
        resources are properly freed. It attempts to disconnect from the OBS WebSocket if connected
        and terminates the OBS process if it is running. Any exceptions encountered during cleanup
        are logged.

        Raises:
            Exception: Logs any exceptions encountered during the cleanup process.
        """
        logger.debug("Starting cleanup process.")
        try:
            if self.ws and self.ws.ws.connected:
                self.ws.disconnect()
                logger.info("Successfully disconnected from OBS WebSocket.")
            else:
                logger.debug("No active OBS WebSocket connection to disconnect.")

            if self.process:
                self.process.terminate()
                logger.info("Successfully terminated the OBS process.")
            else:
                logger.debug("No OBS process was running to terminate.")
        except Exception:
            logger.exception("An error occurred during the cleanup process")
    
    
    def set_default_profile(self) -> None:
        """
        Sets the default OBS profile by copying the configuration from a predefined profile.
        
        This method reads the configuration from a predefined profile located in the module's
        directory, updates the file paths for output and recording to the configured replay save path,
        and copies this configuration to the OBS profiles directory. If a profile with the same name
        already exists in the destination, it is removed before copying the new profile.

        Steps:
            1. Read the configuration from the module's 'basic.ini' file.
            2. Update file paths in the configuration.
            3. Check if the destination profile directory exists; if so, remove it.
            4. Create the destination profile directory.
            5. Write the updated configuration to the destination directory.

        Raises:
            RuntimeError: If any error occurs during the process, a RuntimeError is raised with the
                        appropriate error message.
        """
        try:
            # Load the configuration from the predefined profile
            config = configparser.ConfigParser()
            config.optionxform = str # Preserve the case of keys
            config.read(self.module_profile_path / "basic.ini")
            
            # Update file paths in the configuration
            replay_path_str = str(self.replay_save_path.as_posix()) # Convert to POSIX so path is valid
            config["SimpleOutput"]["FilePath"] = replay_path_str
            config["AdvOut"]["RecFilePath"] = replay_path_str
            config["AdvOut"]["FFFilePath"] = replay_path_str
            
            # Define the destination path for the specific profile
            destination_path = self.obs_profiles_path / "obs_controller"

            # Check if the destination profile directory exists, remove it if it does
            if destination_path.exists():
                shutil.rmtree(destination_path)
                logger.info("Existing profile directory at %s has been removed.", destination_path)

            # Create the destination profile directory
            os.makedirs(str(destination_path), exist_ok=True)
            
            # Write the updated configuration to the destination directory
            with open(destination_path / "basic.ini", 'w') as f:
                config.write(f, space_around_delimiters=False)
                
            logger.info("Successfully copied default profile to %s", destination_path)
        except Exception as e:
            logger.exception("Failed to set the default profile")
            raise RuntimeError(f"Failed to set the default profile: {e}") from e
    
    
    def is_obs_installed(self) -> bool:
        """
        Checks if the OBS executable is located at the predefined path.

        This method verifies the existence of the OBS executable (`obs64.exe`) in the directory
        specified by `self.cwd`. This directory is typically the OBS installation path. The method
        returns `True` if the executable is found, indicating that OBS is installed, and `False` otherwise.

        Returns:
            bool: `True` if the OBS executable is found at the predefined path, `False` otherwise.
        """
        try:
            obs_installation_path = self.cwd / self.process_name
            if obs_installation_path.exists():
                return True
            return False
        except Exception:
            logger.exception("Error occurred while checking if obs is installed")
            return False
    
    
    def launch_obs(self) -> None:
        """
        Launches OBS studio if it's not already running.
                
        This method checks if the OBS process is already running. If not, it launches OBS Studio
        using the specified launch parameters. The method uses the `subprocess.Popen` function to
        start the OBS executable with various command-line arguments to ensure it starts in the
        desired state.
        
        Launch Parameters:
            --minimize-to-tray: Ensures OBS starts minimized to the system tray.
            --disable-updater: Disables the updater to maintain a consistent OBS version.
            --disable-shutdown-check: Prevents shutdown popups when restarting programmatically.
            --profile "obs_controller": Selects the "obs_controller" profile if it is available.
        
        Exceptions:
            If an error occurs while attempting to launch OBS, an exception is logged.
        """
        if self.is_process_running:
            logger.info("Process is already running!")
            return
        
        params = [
            '--minimize-to-tray',
            '--disable-updater',
            '--disable-shutdown-check',
            "--profile",
            "obs_controller"
        ]
            
        try:
            path = str(self.cwd / self.process_name)
            command = [path] + params
            self.process = subprocess.Popen(command, cwd=str(self.cwd))
        except Exception:
            logger.exception("Failed to start OBS:")
    
    
    def websocket_connection_health_check(self) -> bool:
        """
        Performs a health check for the OBS WebSocket server without affecting existing connections.
        
        This method attempts to establish a new connection to the OBS WebSocket server using the
        provided credentials (host, port, password). If the connection is successful, it logs the
        success and immediately disconnects. If any error occurs during the connection attempt, it logs
        the error and returns False.

        Returns:
            bool: `True` if the connection to the OBS WebSocket server is successful, `False` otherwise.
        """
        try:
            ws = obsws(self.host, self.port, self.password)
            ws.connect()
            logger.debug("Health check: Successfully connected to OBS WebSocket.")
            ws.disconnect()
            logger.debug("Health check: Disconnected successfully after health check.")
            return True
        except Exception:
            logger.exception("Health check failed")
            return False
    
    
    @property
    def is_connected(self) -> bool:
        """
        Checks if there is an active connection to the OBS WebSocket.

        This method tries to determine if the WebSocket connection is active by accessing
        the connected attribute of the WebSocket client. It handles any exceptions that
        might occur if the WebSocket object is not initialized or in an erroneous state.

        Returns:
            bool: `True` if connected, `False` otherwise.
        """
        try:
            # Check if self.ws is initialized and has a WebSocket connection established
            return getattr(self, "ws", None) is not None and self.ws.ws.connected
        except AttributeError:
            # This handles the case where self.ws or self.ws.ws does not exist
            logger.error("WebSocket client is not properly initialized.")
            return False
        except Exception:
            # General exception to catch any other unforeseen issues
            logger.exception("Error checking connection status")
            return False


    @require_process_running
    def connect(self) -> bool:
        """
        Attempts to connect to the OBS WebSocket.

        This method first checks if the OBS process is running. If OBS is not running, it logs an error and returns False.
        If OBS is running, it tries to establish a WebSocket connection using the configured host, port, and password.
        
        Returns:
            bool: `True` if the connection was successfully established, `False` otherwise.
        
        Raises:
            Exception: Logs any exceptions that occur during the connection attempt.
        """
        try:
            self.ws = obsws(self.host, self.port, self.password)
            self.ws.connect()
            logger.info("Connected to OBS WebSocket.")
            return True
        except Exception:
            logger.exception("Failed to connect to OBS WebSocket")
            return False


    def disconnect(self) -> bool:
        """
        Attempts to disconnect from the OBS WebSocket if currently connected.

        Returns:
            bool: `True` if the disconnection was successful, `False` otherwise.

        Raises:
            OBSConnectionError: If the disconnection attempt fails.
        """
        if self.ws is None:
            logger.info("No active connection to disconnect.")
            return False

        try:
            self.ws.disconnect()
            logger.info("Successfully disconnected from OBS WebSocket.")
            return True
        except Exception as e:
            logger.exception("Failed to disconnect from OBS WebSocket.")
            raise OBSConnectionError("Disconnection failed") from e
        finally:
            self.ws = None

    @property
    def is_process_running(self) -> bool:
        """
        Checks if a specific process is currently running on the system.

        This method iterates over all running processes and compares their names with the specified process name,
        ignoring any processes that are inaccessible due to permissions or are no longer active.

        Returns:
            bool: `True` if the specified process is found among active processes, `False` otherwise.

        """
        try:
            pythoncom.CoInitialize()
            process_name = self.process_name.lower()
            strComputer = "."
            objWMIService = win32com.client.Dispatch("WbemScripting.SWbemLocator")
            objSWbemServices = objWMIService.ConnectServer(strComputer,"root\cimv2")
            colItems = objSWbemServices.ExecQuery("SELECT * FROM Win32_Process WHERE Name = '{}'".format(process_name))
            return len(colItems) > 0
        except Exception:
            logger.exception("is_process_running encountered an unexpected error")
        finally:
            pythoncom.CoUninitialize()
            


    @require_connection
    def save_replay(self) -> bool:
        """
        Attempts to save the replay buffer to a file, verifying that a new file is created.

        Raises:
            NotConnectedException: If method is running without having an active connection.

        Returns:
            bool: `True` if the replay was saved successfully, `False` otherwise.
        """

        latest_file_before = self.get_latest_video()
        deadline = time.time() + self.timeout

        try:
            # Request to save the replay buffer
            self.ws.call(requests.SaveReplayBuffer())

            # Check for the creation of a new video file until timeout
            while time.time() <= deadline:
                latest_file_after = self.get_latest_video()
                if latest_file_before is None and latest_file_after:
                    # If no file was there before and now there is one, success!
                    logger.info("Replay saved to: %s", latest_file_after.get("path", ""))
                    return True
                elif latest_file_before and latest_file_after and latest_file_before['path'] != latest_file_after['path']:
                    # If there was a file before and a new file is different, success!
                    logger.info("Replay saved to: %s", latest_file_after.get("path", ""))
                    return True
                time.sleep(1)  # Delay to prevent high CPU load

            logger.warning("Failed to save replay: timeout reached without detecting a new file.")
            return False
        except Exception:
            logger.exception("Failed to save replay")
            return False
    
    
    @require_connection
    def start_replay_buffer(self) -> bool:
        """
        Attempts to start the replay buffer in OBS.

        Raises:
            NotConnectedException: If method is running without having an active connection.

        Returns:
            bool: `True` if the replay buffer was started successfully, `False` otherwise.
        """
        try:
            # Request to start the replay buffer
            self.ws.call(requests.StartReplayBuffer())

            logger.info("Replay buffer started successfully.")
            return True
        except Exception:
            logger.exception("Failed to start replay buffer")
            return False


    @require_connection
    def stop_replay_buffer(self) -> bool:
        """
        Attempts to stop the replay buffer in OBS.

        Raises:
            NotConnectedException: If method is running without having an active connection.

        Returns:
            bool: `True` if the replay buffer was stopped successfully, `False` otherwise.
        """
        try:
            # Request to stop the replay buffer
            self.ws.call(requests.StopReplayBuffer())

            logger.info("Replay buffer stopped successfully.")
            return True
        except Exception:
            logger.exception("Failed to stop replay buffer")
            return False
    
    
    def get_latest_video(self) -> dict[str, str|None]:
        """
        Retrieves the most recently modified MP4 video file from the designated save path.

        This method searches the directory specified by self.replay_save_path for MP4 files,
        identifies the most recent one based on its modification time, and returns detailed
        information about it, including its path and timestamps for creation, modification, and last access.

        Returns:
            dict: A dictionary containing details of the latest video file, such as its path, 
                modification time, creation time, and access time, or None if no video file is found or an error occurs.
        """
        try:
            # Find the latest video file based on modification time
            latest_video = max(self.replay_save_path.glob('*.mp4'), key=lambda p: p.stat().st_mtime, default=None)
            if not latest_video:
                logger.debug("No MP4 files found in the directory.")
                return None

            # Caching file stats to minimize file system interactions
            video_stats = latest_video.stat()

            # Convert timestamps format
            modification_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(video_stats.st_mtime))
            creation_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(video_stats.st_ctime))
            access_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(video_stats.st_atime))

            return {
                "path": str(latest_video),
                "modification_time": modification_time,
                "creation_time": creation_time,
                "access_time": access_time
            }
        except Exception:
            logger.exception("Error retrieving latest video")
            return None
    
    
    def check_and_manage_folder_size(self) -> None:
        """
        Checks the total size of video files in the designated directory and initiates cleanup
        if the size exceeds the configured maximum folder size.

        This method sums the sizes of all MP4 video files in the directory specified by
        self.replay_save_path. If this total exceeds self.max_folder_size, it calls the
        cleanup_videos method to delete the oldest files until the total size is within the limit.
        """
        total_size = sum(f.stat().st_size for f in self.replay_save_path.glob('*.mp4'))
        if total_size > self.max_folder_size:
            logger.info("Total folder size %s exceeds maximum of %s. Initiating cleanup.", total_size, self.max_folder_size)
            self.cleanup_videos()
        else:
            logger.info("Total folder size %s is within the limit of %s.", total_size, self.max_folder_size)


    def cleanup_videos(self) -> None:
        """
        Deletes the oldest MP4 video files in the directory until the total folder size
        is below the configured maximum limit.

        This method sorts the video files by creation time and sequentially removes the oldest file
        until the folder's total size meets the specified maximum size condition. Each deletion is
        logged, and errors during file deletion are caught and logged.
        """
        videos = sorted(self.replay_save_path.glob('*.mp4'), key=lambda f: f.stat().st_ctime)
        current_size = sum(f.stat().st_size for f in videos)

        while videos and current_size > self.max_folder_size:
            oldest_video = videos.pop(0)
            try:
                os.remove(oldest_video)
                removed_size = oldest_video.stat().st_size
                current_size -= removed_size
                logger.info("Deleted old video: %s (freed %s bytes)",oldest_video, removed_size)
            except Exception:
                logger.exception("Could not delete video %s", oldest_video)

    def get_obs_version(self) -> str:
        """
        Retrieves the version of the installed OBS Studio application.

        Returns:
            str: The version string of the installed OBS Studio application.
        """
        try:
            ws = obsws(self.host, self.port, self.password)
            ws.connect()
            return ws.call(requests.GetVersion()).getObsVersion()
        except Exception:
            logger.exception("Failed to retrieve OBS Studio version")
            return "Unknown"
        finally:
            try:
                ws.disconnect()
            except Exception:
                pass