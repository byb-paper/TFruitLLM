$ErrorActionPreference = 'Stop'

$species = @(
    @{ key = 'pineapple'; commonName = 'Pineapple'; scientificName = 'Ananas comosus'; taxid = 4615 },
    @{ key = 'passionfruit'; commonName = 'Passion fruit'; scientificName = 'Passiflora edulis'; taxid = 78168 },
    @{ key = 'avocado'; commonName = 'Avocado'; scientificName = 'Persea americana'; taxid = 3435 },
    @{ key = 'sugarapple'; commonName = 'Sugar apple'; scientificName = 'Annona squamosa'; taxid = 301693 },
    @{ key = 'guava'; commonName = 'Guava'; scientificName = 'Psidium guajava'; taxid = 120290 },
    @{ key = 'rambutan'; commonName = 'Rambutan'; scientificName = 'Nephelium lappaceum'; taxid = 151071 },
    @{ key = 'wampee'; commonName = 'Wampee'; scientificName = 'Clausena lansium'; taxid = 159037 },
    @{ key = 'dragonfruit'; commonName = 'Dragon fruit'; scientificName = 'Selenicereus undatus'; taxid = 176265 },
    @{ key = 'litchi'; commonName = 'Litchi'; scientificName = 'Litchi chinensis'; taxid = 151069 },
    @{ key = 'durian'; commonName = 'Durian'; scientificName = 'Durio zibethinus'; taxid = 66656 },
    @{ key = 'longan'; commonName = 'Longan'; scientificName = 'Dimocarpus longan'; taxid = 128017 },
    @{ key = 'mango'; commonName = 'Mango'; scientificName = 'Mangifera indica'; taxid = 29780 },
    @{ key = 'cashew'; commonName = 'Cashew'; scientificName = 'Anacardium occidentale'; taxid = 171929 }
)

$result = [ordered]@{
    updated = (Get-Date -Format 'yyyy-MM-dd')
    source = 'NCBI Datasets Genome API'
    modelGenomePolicy = [ordered]@{
        type = 'no-single-fixed-assembly'
        en = 'TropicalfruitLLM v1.0 was fine-tuned from literature, QA and omics evidence. Its model weights are not built from, or bound to, one unified genome FASTA assembly.'
        zh = 'TropicalfruitLLM v1.0 基于文献、问答与多组学证据微调，模型权重并非由某一个统一的基因组 FASTA 组装构建，也不绑定单一参考基因组版本。'
    }
    species = @()
}

foreach ($item in $species) {
    $url = "https://api.ncbi.nlm.nih.gov/datasets/v2alpha/genome/taxon/$($item.taxid)/dataset_report?page_size=1000"
    $response = Invoke-RestMethod -Uri $url -Headers @{ Accept = 'application/json' }
    $assemblies = @($response.reports | ForEach-Object {
        $infra = $_.organism.infraspecific_names
        $cultivarParts = @()
        if ($infra.cultivar) { $cultivarParts += "cultivar=$($infra.cultivar)" }
        if ($infra.ecotype) { $cultivarParts += "ecotype=$($infra.ecotype)" }
        [ordered]@{
            accession = $_.accession
            organism = $_.organism.organism_name
            cultivar = ($cultivarParts -join '; ')
            isolate = [string]$infra.isolate
            level = $_.assembly_info.assembly_level
            assemblyName = $_.assembly_info.assembly_name
            bioproject = $_.assembly_info.bioproject_accession
            releaseDate = $_.assembly_info.release_date
            status = $_.assembly_info.assembly_status
            submitter = $_.assembly_info.submitter
            ncbiUrl = "https://www.ncbi.nlm.nih.gov/datasets/genome/$($_.accession)/"
            downloadUrl = "https://www.ncbi.nlm.nih.gov/datasets/genome/$($_.accession)/"
        }
    } | Sort-Object { $_.accession })

    $result.species += [ordered]@{
        key = $item.key
        commonName = $item.commonName
        scientificName = $item.scientificName
        taxid = $item.taxid
        assemblies = $assemblies
    }
    Write-Host "$($item.scientificName): $($assemblies.Count) assemblies"
    Start-Sleep -Milliseconds 350
}

$output = Join-Path $PSScriptRoot '..\..\dist\data\genomes.json'
$result | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $output -Encoding utf8
Write-Host "Updated $output"
