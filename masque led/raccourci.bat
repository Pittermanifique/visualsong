@echo off
set "TargetPath=%~dp0beat.bat"
set "ShortcutPath=%USERPROFILE%\Desktop\MonScript.lnk"

powershell -command "$s=(New-Object -COM WScript.Shell).CreateShortcut('%ShortcutPath%');$s.TargetPath='%TargetPath%';$s.Save()"
