' Black Eclipse desktop launcher.
' Double-click (or a desktop shortcut to this file) to start the production
' site behind the local hostname proxy, showing boot progress in a console
' window. The window closes itself when the app tab is closed, or when this
' window is closed (which stops the server).
Set fso = CreateObject("Scripting.FileSystemObject")
root = fso.GetParentFolderName(WScript.ScriptFullName)
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = root
sh.Run "node """ & root & "\scripts\start-desktop.js""", 1, False
