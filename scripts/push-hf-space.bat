@echo off
REM Push PROSE-MEET app files to your Hugging Face Space (run from repo root).
REM Requires: git, and HF access token (https://huggingface.co/settings/tokens)

set SPACE_REPO=https://huggingface.co/spaces/Gayaththri/PROSE-MEET
set TMPDIR=%TEMP%\prose-meet-hf-space

echo.
echo PROSE-MEET - Hugging Face Space push
echo Space: %SPACE_REPO%
echo.

if exist "%TMPDIR%" rmdir /s /q "%TMPDIR%"
mkdir "%TMPDIR%"
cd /d "%TMPDIR%"

git clone %SPACE_REPO% .
if errorlevel 1 (
    echo.
    echo git clone failed. Create a token at https://huggingface.co/settings/tokens
    echo When prompted for password, paste the token ^(not your HF password^).
    exit /b 1
)

copy /Y "%~dp0deploy\huggingface\space-repo\Dockerfile" Dockerfile
copy /Y "%~dp0deploy\huggingface\space-repo\README.md" README.md

git add Dockerfile README.md
git status
git commit -m "Deploy PROSE-MEET full stack (UI + FastAPI + Whisper)"
git push

echo.
echo Done. Open https://huggingface.co/spaces/Gayaththri/PROSE-MEET
echo First build may take 10-20 minutes.
cd /d "%~dp0"
