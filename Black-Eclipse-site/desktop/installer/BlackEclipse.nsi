; Black Eclipse — per-user installer.
;
; Why per-user: the application resolves `python/harness` and its `.black-eclipse`
; runtime locks from `process.cwd()` (see docs/desktop-app-plan.md §6). That means
; the install directory MUST be writable by the user who runs it. Program Files is
; not, so a per-user install is a correctness requirement, not a convenience.
;
; User data lives in %LOCALAPPDATA%\BlackEclipse\data (BE_DATA_DIR, set by the
; bootstrap) and is deliberately NOT removed on uninstall.

Unicode true
!include "MUI2.nsh"
!include "FileFunc.nsh"
!include "LogicLib.nsh"

!ifndef APP_VERSION
  !define APP_VERSION "0.0.0"
!endif
!ifndef SRCDIR
  !define SRCDIR "..\..\dist\BlackEclipse"
!endif
!ifndef OUTFILE
  !define OUTFILE "..\..\dist\BlackEclipse-Setup.exe"
!endif
!ifndef PACKSDIR
  !define PACKSDIR "..\..\dist\packs"
!endif

Name "Black Eclipse"
OutFile "${OUTFILE}"
InstallDir "$LOCALAPPDATA\Programs\BlackEclipse"
InstallDirRegKey HKCU "Software\BlackEclipse" "InstallDir"
RequestExecutionLevel user
BrandingText "Black Eclipse ${APP_VERSION}"

VIProductVersion "${APP_VERSION}.0"
VIAddVersionKey "ProductName" "Black Eclipse"
VIAddVersionKey "FileVersion" "${APP_VERSION}"
VIAddVersionKey "ProductVersion" "${APP_VERSION}"
VIAddVersionKey "FileDescription" "Black Eclipse installer"
VIAddVersionKey "LegalCopyright" "MIT License"

SetCompressor /SOLID lzma
SetCompressorDictSize 64

!define MUI_ABORTWARNING
!define MUI_WELCOMEPAGE_TITLE "Black Eclipse ${APP_VERSION}"
!define MUI_WELCOMEPAGE_TEXT "This installs Black Eclipse for the current user only — no administrator rights, no Node.js, no Python and no other prerequisites.$\r$\n$\r$\nYour data is kept in %LOCALAPPDATA%\BlackEclipse\data and is not removed if you uninstall."
!define MUI_FINISHPAGE_RUN "$INSTDIR\Black Eclipse.exe"
!define MUI_FINISHPAGE_RUN_TEXT "Open Black Eclipse now"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"

Section "Black Eclipse" SecMain
  SetOutPath "$INSTDIR"
  ; Replace the payload atomically enough: remove the old application tree first
  ; so removed files from a previous version cannot linger. NEVER touch the data
  ; directory, which is a sibling of $INSTDIR, not inside it.
  RMDir /r "$INSTDIR\app"
  RMDir /r "$INSTDIR\runtime"
  File /r "${SRCDIR}\*.*"

  WriteRegStr HKCU "Software\BlackEclipse" "InstallDir" "$INSTDIR"
  WriteRegStr HKCU "Software\BlackEclipse" "Version" "${APP_VERSION}"

  ; Add/Remove Programs entry (per-user hive).
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\BlackEclipse" "DisplayName" "Black Eclipse"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\BlackEclipse" "DisplayVersion" "${APP_VERSION}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\BlackEclipse" "Publisher" "BlackEclipse"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\BlackEclipse" "DisplayIcon" "$INSTDIR\Black Eclipse.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\BlackEclipse" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\BlackEclipse" "QuietUninstallString" '"$INSTDIR\Uninstall.exe" /S'
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\BlackEclipse" "NoModify" 1
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\BlackEclipse" "NoRepair" 1
  
  ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
  IntFmt $0 "0x%08X" $0
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\BlackEclipse" "EstimatedSize" "$0"

  WriteUninstaller "$INSTDIR\Uninstall.exe"

  ; The app is a WebView2 host: without the runtime it opens a message box and
  ; exits, which reads as "the installer is broken". Check before finishing and
  ; install the Evergreen runtime when it is missing.
  Call EnsureWebView2

!ifdef FULL
  ; Offline edition: include whichever optional packs were built for this
  ; platform. The list is generated at build time (a pack such as winsdk has no
  ; Linux wheel), so NSIS does not hard-code it.
  SetOutPath "$INSTDIR\app\scripts\vendor\python\Lib\site-packages"
  !include "${PACKSINCLUDE}"
!endif

  ; Start Menu
  CreateDirectory "$SMPROGRAMS\Black Eclipse"
  CreateShortCut "$SMPROGRAMS\Black Eclipse\Black Eclipse.lnk" "$INSTDIR\Black Eclipse.exe" "" "$INSTDIR\Black Eclipse.exe" 0
  CreateShortCut "$SMPROGRAMS\Black Eclipse\Uninstall Black Eclipse.lnk" "$INSTDIR\Uninstall.exe"

  ; Desktop shortcut, but never overwrite one the user already arranged.
  IfFileExists "$DESKTOP\Black Eclipse.lnk" +2 0
  CreateShortCut "$DESKTOP\Black Eclipse.lnk" "$INSTDIR\Black Eclipse.exe" "" "$INSTDIR\Black Eclipse.exe" 0
SectionEnd

; --- WebView2 -----------------------------------------------------------------
; The runtime registers its version under one of three roots (per-machine 32/64
; and per-user). Any of them means it is available to this user.
!macro WV2_READ out
  ReadRegStr ${out} HKLM "SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}" "pv"
  ${If} ${out} == ""
    ReadRegStr ${out} HKLM "SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}" "pv"
  ${EndIf}
  ${If} ${out} == ""
    ReadRegStr ${out} HKCU "Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}" "pv"
  ${EndIf}
!macroend

Function EnsureWebView2
  !insertmacro WV2_READ $0
  ${If} $0 != ""
    DetailPrint "WebView2 runtime already present ($0)"
    Return
  ${EndIf}

  DetailPrint "WebView2 runtime not found - installing the Evergreen runtime..."

!ifdef WEBVIEW2_BOOTSTRAPPER
  InitPluginsDir
  File "/oname=$PLUGINSDIR\MicrosoftEdgeWebview2Setup.exe" "${WEBVIEW2_BOOTSTRAPPER}"
  ExecWait '"$PLUGINSDIR\MicrosoftEdgeWebview2Setup.exe" /silent /install' $1
  DetailPrint "WebView2 bootstrapper finished with exit code $1"
!else
  DetailPrint "No WebView2 bootstrapper was bundled in this build."
!endif

  !insertmacro WV2_READ $0
  ${If} $0 != ""
    DetailPrint "WebView2 runtime is now available ($0)"
    Return
  ${EndIf}

  ; Still missing: explain precisely and let the user decide. Silently finishing
  ; would leave an app that cannot open, which is worse than a clear message.
  MessageBox MB_YESNO|MB_ICONEXCLAMATION \
    "Black Eclipse needs the Microsoft Edge WebView2 Runtime, and it could not be installed automatically.$\r$\n$\r$\nThis usually means there is no internet connection right now, or the installer was blocked by policy.$\r$\n$\r$\nInstall it manually from:$\r$\nhttps://developer.microsoft.com/microsoft-edge/webview2/$\r$\n$\r$\nBlack Eclipse is installed already. Without the runtime it will not open.$\r$\n$\r$\nContinue anyway?" \
    IDYES wv2_continue
  Abort "Installation paused: install the WebView2 Runtime, then start Black Eclipse again."
  wv2_continue:
  DetailPrint "Continuing without WebView2 - the app will ask for it on launch."
FunctionEnd

Section "Uninstall"  ; Stop a running instance so files are not locked.
  nsExec::Exec 'taskkill /IM "Black Eclipse.exe" /F'

  Delete "$SMPROGRAMS\Black Eclipse\Black Eclipse.lnk"
  Delete "$SMPROGRAMS\Black Eclipse\Uninstall Black Eclipse.lnk"
  RMDir "$SMPROGRAMS\Black Eclipse"
  Delete "$DESKTOP\Black Eclipse.lnk"

  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\BlackEclipse"
  DeleteRegKey HKCU "Software\BlackEclipse"

  RMDir /r "$INSTDIR\app"
  RMDir /r "$INSTDIR\runtime"
  Delete "$INSTDIR\Black Eclipse.exe"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"

  ; Deliberately NOT deleted: "$LOCALAPPDATA\BlackEclipse\data"
  ; Reinstalling keeps the user's database, journals and settings.
SectionEnd
