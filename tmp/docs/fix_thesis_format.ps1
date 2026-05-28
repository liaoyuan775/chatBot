$ErrorActionPreference = 'Stop'

$root = 'D:\AgentLearning\chatBot'
$docPath = Get-ChildItem -Path (Join-Path $root 'output\doc') -Filter '*.docx' |
    Where-Object { -not $_.Name.StartsWith('~$') } |
    Sort-Object Length -Descending |
    Select-Object -First 1 -ExpandProperty FullName

if (-not $docPath) {
    throw 'No docx found in output\doc.'
}

function Get-ParagraphText($paragraph) {
    return $paragraph.Range.Text.Replace([char]13, '').Replace([char]7, '').Replace([char]11, '').Replace([char]12, '')
}

function Set-RangeFont($range, [string]$eastAsia, [string]$asciiFont, [double]$sizePt, [bool]$bold) {
    $range.Font.NameFarEast = $eastAsia
    $range.Font.NameAscii = $asciiFont
    $range.Font.NameOther = $asciiFont
    $range.Font.Size = $sizePt
    $range.Font.Bold = $(if ($bold) { -1 } else { 0 })
}

function Set-ParagraphFormat($paragraph, [int]$alignment, [double]$beforePt, [double]$afterPt, [int]$lineRule, [double]$lineSpacing, [double]$firstIndentPt, [double]$leftIndentPt) {
    $fmt = $paragraph.Format
    $fmt.Alignment = $alignment
    $fmt.SpaceBefore = $beforePt
    $fmt.SpaceAfter = $afterPt
    $fmt.LineSpacingRule = $lineRule
    $fmt.LineSpacing = $lineSpacing
    $fmt.FirstLineIndent = $firstIndentPt
    $fmt.LeftIndent = $leftIndentPt
}

function Replace-ParagraphSubstring($doc, [int]$paragraphIndex, [string]$source, [string]$target) {
    if ($paragraphIndex -gt $doc.Paragraphs.Count) {
        return
    }
    $paragraph = $doc.Paragraphs.Item($paragraphIndex)
    $text = Get-ParagraphText $paragraph
    if (-not $text.Contains($source)) {
        return
    }
    $range = $doc.Range($paragraph.Range.Start, $paragraph.Range.End - 1)
    $range.Text = $text.Replace($source, $target)
}

function Format-CenteredTitle($paragraph, [string]$eastAsiaFont, [string]$asciiFont, [double]$sizePt) {
    Set-ParagraphFormat $paragraph 1 24 18 0 12 0 0
    Set-RangeFont $paragraph.Range $eastAsiaFont $asciiFont $sizePt $true
}

function Format-Heading2($paragraph) {
    Set-ParagraphFormat $paragraph 0 12 6 0 12 0 0
    Set-RangeFont $paragraph.Range 'SimHei' 'Times New Roman' 15 $true
}

function Format-Heading3($paragraph) {
    Set-ParagraphFormat $paragraph 0 12 6 0 12 0 0
    Set-RangeFont $paragraph.Range 'SimHei' 'Times New Roman' 14 $true
}

function Format-Caption($paragraph) {
    Set-ParagraphFormat $paragraph 1 0 0 4 18 0 0
    Set-RangeFont $paragraph.Range 'SimSun' 'Times New Roman' 10.5 $false
}

function Format-Reference($paragraph, [double]$leftIndentPt) {
    Set-ParagraphFormat $paragraph 3 0 0 4 18 (-1 * $leftIndentPt) $leftIndentPt
    Set-RangeFont $paragraph.Range 'SimSun' 'Times New Roman' 12 $false
}

function Normalize-CnKeywords($doc, [int]$paragraphIndex, [int]$labelLength) {
    if ($paragraphIndex -gt $doc.Paragraphs.Count) {
        return
    }
    $paragraph = $doc.Paragraphs.Item($paragraphIndex)
    Set-ParagraphFormat $paragraph 0 0 0 4 18 0 0
    $full = $doc.Range($paragraph.Range.Start, $paragraph.Range.End - 1)
    Set-RangeFont $full 'SimSun' 'Times New Roman' 12 $false
    $label = $doc.Range($paragraph.Range.Start, $paragraph.Range.Start + $labelLength)
    Set-RangeFont $label 'SimHei' 'Times New Roman' 12 $true
}

function Normalize-EnKeywords($doc, [int]$paragraphIndex, [int]$labelLength) {
    if ($paragraphIndex -gt $doc.Paragraphs.Count) {
        return
    }
    $paragraph = $doc.Paragraphs.Item($paragraphIndex)
    Set-ParagraphFormat $paragraph 0 0 0 4 18 0 0
    $full = $doc.Range($paragraph.Range.Start, $paragraph.Range.End - 1)
    Set-RangeFont $full 'Times New Roman' 'Times New Roman' 12 $false
    $label = $doc.Range($paragraph.Range.Start, $paragraph.Range.Start + $labelLength)
    Set-RangeFont $label 'Times New Roman' 'Times New Roman' 12 $true
}

$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0

try {
    $doc = $word.Documents.Open($docPath, $false, $false)

    $doc.Sections.Item(1).PageSetup.TopMargin = $word.CentimetersToPoints(2.8)
    $doc.Sections.Item(1).PageSetup.BottomMargin = $word.CentimetersToPoints(2.5)
    $doc.Sections.Item(1).PageSetup.LeftMargin = $word.CentimetersToPoints(2.5)
    $doc.Sections.Item(1).PageSetup.RightMargin = $word.CentimetersToPoints(2.5)

    for ($s = 2; $s -le $doc.Sections.Count; $s++) {
        $sec = $doc.Sections.Item($s)
        $sec.PageSetup.TopMargin = $word.CentimetersToPoints(2.5)
        $sec.PageSetup.BottomMargin = $word.CentimetersToPoints(2.5)
        $sec.PageSetup.LeftMargin = $word.CentimetersToPoints(2.5)
        $sec.PageSetup.RightMargin = $word.CentimetersToPoints(2.5)

        $header = $sec.Headers.Item(1).Range
        Set-RangeFont $header 'SimSun' 'Times New Roman' 14 $false
        $header.ParagraphFormat.Alignment = 1

        $footer = $sec.Footers.Item(1).Range
        Set-RangeFont $footer 'SimSun' 'Times New Roman' 10.5 $false
        $footer.ParagraphFormat.Alignment = 1
    }

    foreach ($styleName in 'TOC 1', 'TOC 2', 'TOC 3') {
        $style = $doc.Styles.Item($styleName)
        $style.Font.NameFarEast = 'SimSun'
        $style.Font.NameAscii = 'Times New Roman'
        $style.Font.NameOther = 'Times New Roman'
        $style.Font.Size = 12
        $style.Font.Bold = 0
        $style.ParagraphFormat.Alignment = 0
        $style.ParagraphFormat.SpaceBefore = 0
        $style.ParagraphFormat.SpaceAfter = 0
        $style.ParagraphFormat.LineSpacingRule = 4
        $style.ParagraphFormat.LineSpacing = 18
        $style.ParagraphFormat.FirstLineIndent = 0
    }
    $doc.Styles.Item('TOC 1').ParagraphFormat.LeftIndent = 0
    $doc.Styles.Item('TOC 2').ParagraphFormat.LeftIndent = 24
    $doc.Styles.Item('TOC 3').ParagraphFormat.LeftIndent = 48

    $refIndent = $word.CentimetersToPoints(0.74)

    Format-CenteredTitle $doc.Paragraphs.Item(51) 'SimHei' 'Times New Roman' 18
    Format-CenteredTitle $doc.Paragraphs.Item(57) 'Times New Roman' 'Times New Roman' 18
    Format-CenteredTitle $doc.Paragraphs.Item(64) 'SimHei' 'Times New Roman' 18
    Normalize-CnKeywords $doc 56 5
    Normalize-EnKeywords $doc 62 10

    foreach ($chapterIndex in 146, 192, 244, 375, 455, 591, 756, 769, 781, 786) {
        if ($chapterIndex -le $doc.Paragraphs.Count) {
            $paragraph = $doc.Paragraphs.Item($chapterIndex)
            Format-CenteredTitle $paragraph 'SimHei' 'Times New Roman' 18
            $paragraph.Format.PageBreakBefore = -1
        }
    }

    for ($i = 1; $i -le $doc.Paragraphs.Count; $i++) {
        $paragraph = $doc.Paragraphs.Item($i)
        $page = $paragraph.Range.Information(3)
        $text = (Get-ParagraphText $paragraph).Trim()
        if ($page -lt 8 -or $text -eq '') {
            continue
        }

        if ($text -match '^\d+\.\d+\.\d+\s') {
            Format-Heading3 $paragraph
            continue
        }

        if ($text -match '^\d+\.\d+\s') {
            Format-Heading2 $paragraph
            continue
        }

        if ($text -match '^\u56FE\d+-\d+\s' -or $text -match '^\u8868\d+-\d+\s') {
            Format-Caption $paragraph
            continue
        }

        if ($text -match '^\[\d+\]') {
            Format-Reference $paragraph $refIndent
            continue
        }
    }

    Replace-ParagraphSubstring $doc 470 '5-4' '5-1'
    Replace-ParagraphSubstring $doc 472 '5-4' '5-1'
    Replace-ParagraphSubstring $doc 477 '5-1' '5-2'
    Replace-ParagraphSubstring $doc 479 '5-1' '5-2'
    Replace-ParagraphSubstring $doc 495 '5-2' '5-3'
    Replace-ParagraphSubstring $doc 497 '5-2' '5-3'
    Replace-ParagraphSubstring $doc 498 '5-3' '5-4'
    Replace-ParagraphSubstring $doc 500 '5-3' '5-4'
    Replace-ParagraphSubstring $doc 559 '5-10' '5-9'
    Replace-ParagraphSubstring $doc 562 '5-10' '5-9'
    Replace-ParagraphSubstring $doc 566 '5-9' '5-10'
    Replace-ParagraphSubstring $doc 568 '5-9' '5-10'

    for ($i = $doc.Paragraphs.Count; $i -ge 1; $i--) {
        $paragraph = $doc.Paragraphs.Item($i)
        $raw = $paragraph.Range.Text.Replace([char]13, '')
        if ($raw -eq [string][char]12) {
            $paragraph.Range.Delete() | Out-Null
        }
    }

    if ($doc.TablesOfContents.Count -gt 0) {
        for ($i = 1; $i -le $doc.TablesOfContents.Count; $i++) {
            $doc.TablesOfContents.Item($i).Update()
        }
    }

    $doc.Fields.Update() | Out-Null
    $doc.Repaginate()
    $doc.Save()
    Write-Output $docPath
} finally {
    if ($doc -ne $null) {
        $doc.Close()
    }
    $word.Quit()
}
