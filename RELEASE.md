# EVEL Võrgutööriistade väljalase

Plugin avaldatakse GitHub Release'i varana ja seda levitatakse QGIS-i kohandatud
pluginarepositooriumi kaudu. Väljalaske loob töövoog
`.github/workflows/qgis_release.yml`.

## Nähtavus

GitHubi repo peab olema avalik, et QGIS saaks `plugins.xml` faili ja ZIP-pakendi
ilma GitHubi autentimiseta alla laadida. Repo avalikuks muutmine teeb nähtavaks
ka kogu lähtekoodi ja git-ajaloo.

QGIS-i repositooriumi püsiv aadress on:

```text
https://github.com/KalverTammik/Kavitro_MapTools/releases/latest/download/plugins.xml
```

## Uue versiooni avaldamine

1. Käivita QGIS-i testid ja `python -m unittest tests.test_release_packaging -v`.
2. Uuenda `metadata.txt` versiooni ning commit'i muudatused `main` harusse.
3. Loo GitHubis uus Release ja tag kujul `vX.Y.Z`.
4. Lisa Release'i pealkiri ja kasutajale arusaadavad muudatuste märkmed.
5. Avalda Release ning oota töövoo `Release QGIS Plugin` lõppemist.
6. Kontrolli, et Release sisaldab `plugins.xml` faili ja
   `EVEL_network_tools.<versioon>.zip` pakendit.
7. Kontrolli paketti puhtas QGIS 3.40 või uuemas profiilis.

Töövoo võib käivitada ka käsitsi. Sellisel juhul tuleb sisestada versioon kujul
`0.12.2`; töövoog kasutab vaikimisi tagi `v0.12.2` ja loob puuduva Release'i.

## Pakendi sisu

`tools/build_release.py` koostab allow-list'i alusel minimaalse pakendi. Sellesse
kuuluvad plugina käituskood, metaandmed ja ikoon. Testid, arendusdokumendid,
lokaalsed andmebaasid, QGIS-i projektid, vahemälud ning ehitusväljund jäetakse
välja. Pakendaja muudab ainult release-kataloogis versiooni, stabiilsuslipu ja
muudatuste kirjelduse; arenduskataloogi `metadata.txt` jääb puutumata.

GitHubi automaatsed `Source code` arhiivid ei ole QGIS-i paigalduspakendid.

## Kohalik kontroll

```powershell
python -m unittest tests.test_release_packaging -v
python tools\build_release.py --version 0.12.2 `
  --output release_stage\EVEL_network_tools
```
