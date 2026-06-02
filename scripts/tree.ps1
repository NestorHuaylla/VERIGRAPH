Get-ChildItem -Recurse -Force |
  Where-Object { $_.FullName -notmatch "\\node_modules\\|\\.next\\|\\.venv\\" } |
  Select-Object FullName

