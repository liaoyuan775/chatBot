$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
$path = 'D:\AgentLearning\chatBot\tmp\refs_and_diagram.docx'
$doc = $word.Documents.Open($path)
foreach ($toc in $doc.TablesOfContents) { $toc.Update() }
$doc.Fields.Update() | Out-Null
$doc.Repaginate()
$doc.Save()
$doc.Close()
$word.Quit()
