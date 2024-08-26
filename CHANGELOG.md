# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog],
and this project adheres to [Semantic Versioning].


## [1.1.2] - 2024-05-27

### Fixed

- Fixed initialization of com libraries before dispatching WbemScripting, in `is_process_running` method. They are not always initialized by default.

## [1.1.1] - 2024-05-18

### Fixed

- Added missing requirement `pywin32==306` to `requirements.txt` and pyproject.toml
- Set `replay_path_str `to posix path in `obscontroller.py` to fix windows path issue

## [1.1.0] - 2024-05-16

### Added

- Added api for getting the OBS studio version: `get_obs_version`

### Fixed

- Use lazy % formatting on logging.
- Use exception logging on exceptions.

## [1.0.0] - 2024-05-15

- Initial release

<!-- Links -->
[keep a changelog]: https://keepachangelog.com/en/1.0.0/
[semantic versioning]: https://semver.org/spec/v2.0.0.html

<!-- Versions -->
[1.1.2]: https://github.com/mathiascn/obs_controller/tags/1.1.2