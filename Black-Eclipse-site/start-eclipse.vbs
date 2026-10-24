' Black Eclipse desktop launcher.
' Double-click (or a desktop shortcut to this file) to start the production
' site behind the local hostname proxy. The Node launcher runs with a HIDDEN
' console: the app stops itself when its tab closes, and the boot/stop log is
' written to .black-eclipse/desktop-launch.log instead of a window.
Set fso = CreateObject("Scripting.FileSystemObject")
root = fso.GetParentFolderName(WScript.ScriptFullName)
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = root
sh.Run "node """ & root & "\scripts\start-desktop.js""", 0, False
