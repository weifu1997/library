@echo off
set "LIBRARY_PY_MODULE=library.mcp_server"
call "%~dp0library.cmd" %*
exit /b %ERRORLEVEL%
