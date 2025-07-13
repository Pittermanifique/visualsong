@echo off
set "TargetPath=%~dp0beat\beat.bat"
set "IconPath=%~dp0beat\icone.ico"  :: chemin vers ton icône .ico
set "ShortcutPath=%USERPROFILE%\Desktop\beat.lnk"

powershell -command "$s=(New-Object -COM WScript.Shell).CreateShortcut('%ShortcutPath%');$s.TargetPath='%TargetPath%';$s.IconLocation='%IconPath%';$s.Save()"