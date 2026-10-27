@echo off
rem CARE-EW: double-click to set up and launch the web console for a demonstration.
rem Extra options are passed through, e.g.  START_DEMO.bat -Aoi NPL_chure   or   -InstallShortcut
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_demo.ps1" %*
