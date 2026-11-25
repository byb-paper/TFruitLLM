$ErrorActionPreference = 'Stop'

$species = @(
    @{ key = 'pineapple'; scientificName = 'Ananas comosus' },
    @{ key = 'passionfruit'; scientificName = 'Passiflora edulis' },
    @{ key = 'avocado'; scientificName = 'Persea americana' },
    @{ key = 'sugarapple'; scientificName = 'Annona squamosa' },
    @{ key = 'guava'; scientificName = 'Psidium guajava' },
    @{ key = 'rambutan'; scientificName = 'Nephelium lappaceum' },
    @{ key = 'wampee'; scientificName = 'Clausena lansium' },
    @{ key = 'dragonfruit'; scientificName = 'Selenicereus undatus' },
    @{ key = 'litchi'; scientificName = 'Litchi chinensis' },
    @{ key = 'durian'; scientificName = 'Durio zibethinus' },
    @{ key = 'longan'; scientificName = 'Dimocarpus longan' },
    @{ key = 'mango'; scientificName = 'Mangifera indica' },
    @{ key = 'cashew'; scientificName = 'Anacardium occidentale' }
)

$result = [ordered]@{
    updated = (Get-Date -Format 'yyyy-MM-dd')
    source = 'NGDC Genome Warehouse public search API'
    species = @()
}

foreach ($item in $species) {
    $query = [uri]::EscapeDataString("$($item.scientificName)[Scientific name]")
    $url = "https://ngdc.cncb.ac.cn/gwh/gwhSearch/api?query_box=$query&exclude_unreleased=true&page=1&length=200&sort_by=&sort_order=ASC"
    $response = (Invoke-WebRequest -UseBasicParsing -Uri $url).Content | ConvertFrom-Json
    $records = @($response.data | Where-Object { $_.attrs.source -eq 'Direct submission' } | ForEach-Object {
        $download = ''
        if ($_.attrs.download -match "href='([^']+)'") { $download = $Matches[1] }
        [ordered]@{
            accession = $_.id
            assemblyName = $_.title
            scientificName = $_.attrs.scientific_name
            level = $_.attrs.assembly_level
            cultivar = $_.attrs.biosample_cultivar_breed
            releaseDate = $_.attrs.release_date
            repository = 'NGDC Genome Warehouse'
            recordUrl = $_.url
            downloadUrl = $download
            sourceType = 'Direct submission'
        }
    } | Sort-Object { $_.accession })

    $result.species += [ordered]@{
        key = $item.key
        scientificName = $item.scientificName
        records = $records
    }
    Write-Host "$($item.scientificName): $($records.Count) direct GWH assemblies"
    Start-Sleep -Milliseconds 250
}

$output = Join-Path $PSScriptRoot '..\..\dist\data\external-genomes.json'
$result | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $output -Encoding utf8
Write-Host "Updated $output"
