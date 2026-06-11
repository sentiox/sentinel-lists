$ErrorActionPreference = "Stop"

[Console]::InputEncoding = [Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

function Write-Title {
    Clear-Host
    Write-Host "Помощник Sentinel Lists" -ForegroundColor Cyan
    Write-Host "Папка: $Root" -ForegroundColor DarkGray
    Write-Host ""
}

function Read-Choice($Prompt, [string[]]$Allowed) {
    while ($true) {
        $value = (Read-Host $Prompt).Trim()
        if ($Allowed -contains $value) { return $value }
        Write-Host "Неверный выбор. Можно: $($Allowed -join ', ')" -ForegroundColor Yellow
    }
}

function Get-RelativePath([string]$Path) {
    $rootPath = (Resolve-Path -LiteralPath $Root).Path.TrimEnd("\") + "\"
    $fullPath = (Resolve-Path -LiteralPath $Path).Path
    if ($fullPath.StartsWith($rootPath, [StringComparison]::OrdinalIgnoreCase)) {
        return $fullPath.Substring($rootPath.Length).Replace("\", "/")
    }
    return $fullPath.Replace("\", "/")
}

function Get-ListFiles {
    Get-ChildItem -Path `
        (Join-Path $Root "Services"), `
        (Join-Path $Root "Categories"), `
        (Join-Path $Root "Subnets\IPv4"), `
        (Join-Path $Root "Subnets\IPv6"), `
        (Join-Path $Root "Russia"), `
        (Join-Path $Root "Ukraine"), `
        (Join-Path $Root "src") `
        -File -Filter "*.lst" -ErrorAction SilentlyContinue |
        Sort-Object FullName
}

function Get-QuickTargets {
    @(
        @{ Label = "Telegram - домены"; Path = "Services\telegram.lst" },
        @{ Label = "Telegram - IPv4"; Path = "Subnets\IPv4\telegram.lst" },
        @{ Label = "Telegram - IPv6"; Path = "Subnets\IPv6\telegram.lst" },
        @{ Label = "Discord - домены"; Path = "Services\discord.lst" },
        @{ Label = "Discord - IPv4"; Path = "Subnets\IPv4\discord.lst" },
        @{ Label = "Discord - IPv6"; Path = "Subnets\IPv6\discord.lst" },
        @{ Label = "Instagram/Meta - домены"; Path = "Services\meta.lst" },
        @{ Label = "Instagram/Meta - IPv4"; Path = "Subnets\IPv4\meta.lst" },
        @{ Label = "YouTube - домены"; Path = "Services\youtube.lst" },
        @{ Label = "Google AI/ChatGPT - домены"; Path = "Services\google_ai.lst" },
        @{ Label = "Roblox - домены"; Path = "Services\roblox.lst" },
        @{ Label = "Roblox - IPv4"; Path = "Subnets\IPv4\roblox.lst" },
        @{ Label = "Россия внутри РФ - домены"; Path = "Russia\inside-raw.lst" },
        @{ Label = "Россия мимо РФ - домены"; Path = "Russia\outside-raw.lst" },
        @{ Label = "Украина внутри - домены"; Path = "Ukraine\inside-raw.lst" }
    ) | Where-Object { Test-Path -LiteralPath (Join-Path $Root $_.Path) }
}

function Select-ListFile {
    $quick = @(Get-QuickTargets)
    if ($quick.Count -gt 0) {
        Write-Host "Быстрый выбор:" -ForegroundColor Cyan
        for ($i = 0; $i -lt $quick.Count; $i++) {
            Write-Host ("  q{0}. {1} [{2}]" -f ($i + 1), $quick[$i].Label, $quick[$i].Path.Replace("\", "/"))
        }
        Write-Host "  m. Показать все списки"
        Write-Host ""

        while ($true) {
            $rawQuick = (Read-Host "Быстрый выбор или m").Trim().ToLowerInvariant()
            if ($rawQuick -eq "m" -or $rawQuick -eq "") { break }
            if ($rawQuick -match "^q?(\d+)$") {
                $index = [int]$Matches[1]
                if ($index -ge 1 -and $index -le $quick.Count) {
                    return (Join-Path $Root $quick[$index - 1].Path)
                }
            }
            Write-Host "Напиши q1, q2... или m." -ForegroundColor Yellow
        }
    }

    $files = @(Get-ListFiles)
    if ($files.Count -eq 0) {
        throw "Не найдены .lst файлы."
    }

    Write-Host "Выбери список:" -ForegroundColor Cyan
    for ($i = 0; $i -lt $files.Count; $i++) {
        Write-Host ("{0,3}. {1}" -f ($i + 1), (Get-RelativePath $files[$i].FullName))
    }
    Write-Host ""

    while ($true) {
        $raw = (Read-Host "Номер списка").Trim()
        $index = 0
        if ([int]::TryParse($raw, [ref]$index) -and $index -ge 1 -and $index -le $files.Count) {
            return $files[$index - 1].FullName
        }
        Write-Host "Нужно число от 1 до $($files.Count)." -ForegroundColor Yellow
    }
}

function Split-Items([string]$InputText) {
    $InputText -split "[\s,;]+" |
        ForEach-Object { $_.Trim().TrimEnd(".").ToLowerInvariant() } |
        Where-Object { $_ -ne "" -and -not $_.StartsWith("#") }
}

function Test-IPv4Cidr([string]$Value) {
    if ($Value -notmatch "^(\d{1,3}\.){3}\d{1,3}(/\d{1,2})?$") { return $false }
    $parts = $Value.Split("/")[0].Split(".")
    foreach ($part in $parts) {
        $n = [int]$part
        if ($n -lt 0 -or $n -gt 255) { return $false }
    }
    if ($Value.Contains("/")) {
        $mask = [int]($Value.Split("/")[1])
        if ($mask -lt 0 -or $mask -gt 32) { return $false }
    }
    return $true
}

function Test-IPv6Cidr([string]$Value) {
    $addr = $Value.Split("/")[0]
    $parsed = $null
    if (-not [Net.IPAddress]::TryParse($addr, [ref]$parsed)) { return $false }
    if ($parsed.AddressFamily -ne [Net.Sockets.AddressFamily]::InterNetworkV6) { return $false }
    if ($Value.Contains("/")) {
        $mask = 0
        if (-not [int]::TryParse($Value.Split("/")[1], [ref]$mask)) { return $false }
        if ($mask -lt 0 -or $mask -gt 128) { return $false }
    }
    return $true
}

function Test-Domain([string]$Value) {
    return $Value -match "^(?:\*\.)?(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9][a-z0-9-]{1,62}$"
}

function Test-ItemForFile([string]$File, [string]$Value) {
    $rel = Get-RelativePath $File
    if ($rel -like "Subnets/IPv4/*") { return Test-IPv4Cidr $Value }
    if ($rel -like "Subnets/IPv6/*") { return Test-IPv6Cidr $Value }
    return Test-Domain $Value
}

function Test-IPv4ListFile([string]$File) {
    return (Get-RelativePath $File) -like "Subnets/IPv4/*"
}

function ConvertTo-IPv4Number([string]$Address) {
    $parts = $Address.Split(".")
    return (([uint32]$parts[0] -shl 24) -bor ([uint32]$parts[1] -shl 16) -bor ([uint32]$parts[2] -shl 8) -bor [uint32]$parts[3])
}

function Get-IPv4Range([string]$Value) {
    $addr = $Value.Split("/")[0]
    $mask = 32
    if ($Value.Contains("/")) {
        $mask = [int]($Value.Split("/")[1])
    }

    $ip = ConvertTo-IPv4Number $addr
    if ($mask -eq 0) {
        $network = [uint32]0
        $broadcast = [uint32]4294967295
    } else {
        $maskBits = ([uint32]4294967295) -shl (32 - $mask)
        $network = $ip -band $maskBits
        $broadcast = $network -bor (-bnot $maskBits)
    }

    return @{ Start = [uint32]$network; End = [uint32]$broadcast; Mask = $mask }
}

function Find-IPv4Cover([string]$Ip, [string[]]$Existing) {
    $ipNum = ConvertTo-IPv4Number $Ip
    foreach ($line in $Existing) {
        if (-not (Test-IPv4Cidr $line)) { continue }
        $range = Get-IPv4Range $line
        if ($ipNum -ge $range.Start -and $ipNum -le $range.End) {
            return $line
        }
    }
    return $null
}

function Read-ItemsForFile([string]$File) {
    Write-Host ""
    Write-Host "Можно вставить одно или много значений. Пробел, запятая и новая строка подходят." -ForegroundColor DarkGray
    Write-Host "Пустая строка = закончить ввод." -ForegroundColor DarkGray
    $all = New-Object System.Collections.Generic.List[string]
    while ($true) {
        $line = Read-Host "Значение"
        if ([string]::IsNullOrWhiteSpace($line)) { break }
        foreach ($item in (Split-Items $line)) {
            if (Test-ItemForFile $File $item) {
                $all.Add($item)
            } else {
                Write-Host "Пропущено, формат не подходит для этого списка: $item" -ForegroundColor Yellow
            }
        }
    }
    return @($all | Select-Object -Unique)
}

function Read-ListContent([string]$File) {
    if (-not (Test-Path -LiteralPath $File)) { return @() }
    @(Get-Content -LiteralPath $File -Encoding UTF8 |
        ForEach-Object { $_.Trim() } |
        Where-Object { $_ -ne "" })
}

function Show-ListPreview([string]$File) {
    $content = @(Read-ListContent $File)
    Write-Host ""
    Write-Host "Текущий список: $(Get-RelativePath $File)" -ForegroundColor Cyan
    Write-Host "Строк: $($content.Count)" -ForegroundColor DarkGray

    if ($content.Count -eq 0) {
        Write-Host "Список пустой." -ForegroundColor Yellow
        return
    }

    if ($content.Count -le 120) {
        foreach ($line in $content) {
            Write-Host "  $line"
        }
        return
    }

    Write-Host "Первые 60:" -ForegroundColor DarkGray
    foreach ($line in ($content | Select-Object -First 60)) {
        Write-Host "  $line"
    }
    Write-Host "..." -ForegroundColor DarkGray
    Write-Host "Последние 30:" -ForegroundColor DarkGray
    foreach ($line in ($content | Select-Object -Last 30)) {
        Write-Host "  $line"
    }
    Write-Host "Список большой. Для точной проверки используй пункт 3 'Найти домен/IP'." -ForegroundColor Yellow
}

function Save-ListContent([string]$File, [string[]]$Lines) {
    $sorted = @($Lines |
        ForEach-Object { $_.Trim().ToLowerInvariant() } |
        Where-Object { $_ -ne "" } |
        Sort-Object -Unique)
    [IO.File]::WriteAllLines($File, $sorted, [Text.UTF8Encoding]::new($false))
}

function Save-ListContentPreserveOrder([string]$File, [string[]]$Lines) {
    $seen = @{}
    $ordered = New-Object System.Collections.Generic.List[string]
    foreach ($line in $Lines) {
        $value = $line.Trim().ToLowerInvariant()
        if ($value -eq "" -or $seen.ContainsKey($value)) { continue }
        $seen[$value] = $true
        $ordered.Add($value)
    }
    [IO.File]::WriteAllLines($File, @($ordered), [Text.UTF8Encoding]::new($false))
}

function Add-Items {
    Write-Title
    $file = Select-ListFile
    Show-ListPreview $file
    $items = @(Read-ItemsForFile $file)
    if ($items.Count -eq 0) {
        Write-Host "Нечего добавлять." -ForegroundColor Yellow
        return
    }

    $current = @(Read-ListContent $file)
    $prepared = New-Object System.Collections.Generic.List[string]
    $covered = 0
    $singleIps = 0

    foreach ($item in $items) {
        if (Test-IPv4ListFile $file) {
            $ipOnly = $item.Split("/")[0]
            if (-not $item.Contains("/")) {
                $cover = Find-IPv4Cover $ipOnly $current
                if ($cover) {
                    Write-Host "Уже покрыто подсетью: $item -> $cover" -ForegroundColor Yellow
                    $covered++
                    continue
                }
                $prepared.Add("$item/32")
                $singleIps++
                continue
            }
        }
        $prepared.Add($item)
    }

    if ($prepared.Count -eq 0) {
        Write-Host ""
        Write-Host "Список: $(Get-RelativePath $file)" -ForegroundColor Cyan
        Write-Host "Добавлено новых: 0" -ForegroundColor Green
        if ($covered -gt 0) {
            Write-Host "Уже были покрыты существующими подсетями: $covered" -ForegroundColor DarkGray
        }
        return
    }

    $before = $current.Count
    Save-ListContent $file ($current + @($prepared))
    $after = @(Read-ListContent $file).Count

    Write-Host ""
    Write-Host "Список: $(Get-RelativePath $file)" -ForegroundColor Cyan
    Write-Host "Добавлено новых: $($after - $before)" -ForegroundColor Green
    if ($singleIps -gt 0) {
        Write-Host "Одиночные IP сохранены как /32: $singleIps" -ForegroundColor DarkGray
    }
    if ($covered -gt 0) {
        Write-Host "Уже были покрыты существующими подсетями: $covered" -ForegroundColor DarkGray
    }
    Write-Host "Дубли пропущены: $($prepared.Count - ($after - $before))" -ForegroundColor DarkGray
}

function Remove-Items {
    Write-Title
    $file = Select-ListFile
    Show-ListPreview $file
    $items = @(Read-ItemsForFile $file)
    if ($items.Count -eq 0) {
        Write-Host "Нечего удалять." -ForegroundColor Yellow
        return
    }

    $remove = @{}
    foreach ($item in $items) { $remove[$item] = $true }
    $current = @(Read-ListContent $file)
    $next = @($current | Where-Object { -not $remove.ContainsKey($_.ToLowerInvariant()) })
    if ($current.Count -ne $next.Count) {
        Save-ListContentPreserveOrder $file $next
    }

    Write-Host ""
    Write-Host "Список: $(Get-RelativePath $file)" -ForegroundColor Cyan
    Write-Host "Удалено: $($current.Count - $next.Count)" -ForegroundColor Green
}

function Find-Item {
    Write-Title
    $items = @(Split-Items (Read-Host "Что найти"))
    if ($items.Count -eq 0) { return }
    $found = $false
    foreach ($file in Get-ListFiles) {
        $content = @(Read-ListContent $file)
        foreach ($item in $items) {
            if ($content -contains $item) {
                Write-Host "$(Get-RelativePath $file): $item" -ForegroundColor Green
                $found = $true
            }
        }
    }
    if (-not $found) {
        Write-Host "Не найдено." -ForegroundColor Yellow
    }
}

function Run-Convert {
    Write-Title
    if (-not (Test-Path -LiteralPath (Join-Path $Root "convert.py"))) {
        Write-Host "convert.py не найден." -ForegroundColor Yellow
        return
    }
    python .\convert.py
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Генерация завершена." -ForegroundColor Green
    } else {
        Write-Host "convert.py завершился с ошибкой: $LASTEXITCODE" -ForegroundColor Red
    }
}

function Invoke-Git {
    & git -c core.quotepath=false @args
}

function Show-GitDiff {
    Write-Title
    if (-not (Test-Path -LiteralPath (Join-Path $Root ".git"))) {
        Write-Host "В этой папке нет .git. Diff/push здесь недоступны." -ForegroundColor Yellow
        return
    }
    Write-Host "Статус Git:" -ForegroundColor Cyan
    Invoke-Git status --short
    Write-Host ""
    Write-Host "Подсказка: ?? = новый файл, M = изменённый файл, D = удалённый файл." -ForegroundColor DarkGray
    Write-Host ""
    Invoke-Git diff --stat
}

function Commit-And-Push {
    Write-Title
    if (-not (Test-Path -LiteralPath (Join-Path $Root ".git"))) {
        Write-Host "В этой папке нет .git. Для push открой настоящий репозиторий sentinel-lists." -ForegroundColor Yellow
        return
    }

    Invoke-Git status --short
    Write-Host ""
    $answer = Read-Host "Сделать commit и push? Напиши yes"
    if ($answer -ne "yes") {
        Write-Host "Отменено." -ForegroundColor Yellow
        return
    }

    $message = Read-Host "Сообщение коммита"
    if ([string]::IsNullOrWhiteSpace($message)) {
        $message = "Update domain lists"
    }

    Invoke-Git add .
    Invoke-Git commit -m $message
    if ($LASTEXITCODE -ne 0) { return }
    Invoke-Git push
}

while ($true) {
    Write-Title
    Write-Host "1. Добавить домен/IP"
    Write-Host "2. Удалить домен/IP"
    Write-Host "3. Найти домен/IP"
    Write-Host "4. Запустить convert.py"
    Write-Host "5. Git diff/status"
    Write-Host "6. Commit + push"
    Write-Host "0. Выход"
    Write-Host ""

    switch (Read-Choice "Выбор" @("1","2","3","4","5","6","0")) {
        "1" { Add-Items; Read-Host "Enter чтобы продолжить" | Out-Null }
        "2" { Remove-Items; Read-Host "Enter чтобы продолжить" | Out-Null }
        "3" { Find-Item; Read-Host "Enter чтобы продолжить" | Out-Null }
        "4" { Run-Convert; Read-Host "Enter чтобы продолжить" | Out-Null }
        "5" { Show-GitDiff; Read-Host "Enter чтобы продолжить" | Out-Null }
        "6" { Commit-And-Push; Read-Host "Enter чтобы продолжить" | Out-Null }
        "0" { break }
    }
}
