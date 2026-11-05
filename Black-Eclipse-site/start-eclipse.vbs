' Black Eclipse desktop launcher.
' Double-click (or a desktop shortcut to this file) to start the production
' site behind the local hostname proxy. The Node launcher runs with a HIDDEN
' console: the app stops itself when its tab closes, and the boot/stop log is
' written to .black-eclipse/desktop-launch.log instead of a window.
'
' Reliability notes:
'   * The launcher shows a progress page (loopback, opened by the launcher)
'     within a fraction of a second, so a cold build or a failed boot is never
'     a silent no-op.
'   * `node` is looked up on PATH, then in the two standard install locations,
'     so a shortcut works even when the shell that starts it has a lean PATH.
'   * If no Node.js can be found, tell the user with a dialog instead of
'     failing invisibly.
Option Explicit

Dim fso, sh, root, nodeExe, cmd, rc
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")

root = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = root

Function FileExists(p)
  FileExists = (Len(p) > 0) And fso.FileExists(p)
End Function

nodeExe = ""
If FileExists(sh.ExpandEnvironmentStrings("%ProgramFiles%\nodejs\node.exe")) Then
  nodeExe = sh.ExpandEnvironmentStrings("%ProgramFiles%\nodejs\node.exe")
ElseIf FileExists(sh.ExpandEnvironmentStrings("%LOCALAPPDATA%\Programs\nodejs\node.exe")) Then
  nodeExe = sh.ExpandEnvironmentStrings("%LOCALAPPDATA%\Programs\nodejs\node.exe")
Else
  ' Fall back to PATH. `where` tells us whether the name resolves at all.
  On Error Resume Next
  rc = sh.Run("cmd /c where node >nul 2>nul", 0, True)
  On Error GoTo 0
  If rc = 0 Then nodeExe = "node"
End If

If Len(nodeExe) = 0 Then
  MsgBox "Black Eclipse needs Node.js (version 20 or newer), but it was not found." & vbCrLf & vbCrLf & _
         "Install it from https://nodejs.org, then double-click this icon again.", _
         vbCritical, "Black Eclipse"
  WScript.Quit 1
End If

cmd = """" & nodeExe & """ """ & root & "\scripts\start-desktop.js"""

On Error Resume Next
sh.Run cmd, 0, False
If Err.Number <> 0 Then
  MsgBox "Black Eclipse could not start its launcher." & vbCrLf & vbCrLf & _
         "Error: " & Err.Description & vbCrLf & vbCrLf & _
         "Log: " & root & "\.black-eclipse\desktop-launch.log", _
         vbCritical, "Black Eclipse"
End If
On Error GoTo 0
