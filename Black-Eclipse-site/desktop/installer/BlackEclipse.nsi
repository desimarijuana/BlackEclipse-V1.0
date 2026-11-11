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

Section "Uninstall"
  ; Stop a running instance so files are not locked.
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
