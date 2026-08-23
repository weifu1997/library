@echo off
set "LIBRARY_PY_MODULE=library.worker"
call "%~dp0library.cmd" %*
exit /b %ERRORLEVEL%
