!macro NSIS_HOOK_POSTINSTALL
  CopyFiles /SILENT "$INSTDIR\resources\package\windows\library.cmd" "$INSTDIR\library.cmd"
  CopyFiles /SILENT "$INSTDIR\resources\package\windows\library-mcp.cmd" "$INSTDIR\library-mcp.cmd"
  CopyFiles /SILENT "$INSTDIR\resources\package\windows\library-worker.cmd" "$INSTDIR\library-worker.cmd"
!macroend

!macro NSIS_HOOK_POSTUNINSTALL
  Delete "$INSTDIR\library.cmd"
  Delete "$INSTDIR\library-mcp.cmd"
  Delete "$INSTDIR\library-worker.cmd"
!macroend
