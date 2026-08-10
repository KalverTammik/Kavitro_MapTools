# Genereeritud veevõrgu kihtide tehniline selgitus

Staatus: EVEL Network Tools arenduse tehniline sisend
Koostatud: 21.07.2026
Ulatus: PostGIS-i veetorud ja veesõlmed

## 1. Dokumendi eesmärk

See dokument kirjeldab QGIS-i projekti sellisena, nagu EVEL-i mudeli
seadistamise töövoog selle praegu loob. See ei defineeri eraldi
konfiguratsioonisüsteemi ega paralleelset andmemudelit.

EVEL Network Tools peab töötama avatud QGIS-i projekti kihtide vastu. Projekt,
kihtide andmeallikad, väljad, vormid, vaikeväärtused ja relatsioonid on
tõeallikas. Kuvatavat kihinime võib kasutada kasutajaliideses, kuid mitte kihi
tehniliseks tuvastamiseks.

Praegune PostGIS-i projekt salvestab QGIS-i projekti omadustesse ka väljundi
versioonitunnused:

```text
EVEL/model_version = 1
EVEL/network_tools_contract_version = 1
```

Need on generaatori väljundi tunnused, mitte eraldi kasutaja seadistus. Plugin
võib nende abil toetatud projektiversiooni kontrollida, kuid peab vea korral
ikkagi nimetama konkreetse puuduva kihi, välja või seadistuse.

Lähteülesanne ja käesolev dokument täiendavad teineteist:

- [LAHTEULESANNE.md](LAHTEULESANNE.md) kirjeldab tööriista käitumist;
- käesolev dokument kirjeldab valmis projekti tehnilist ülesehitust.

## 2. Kasutaja valiku tähendus

Kasutaja valib, millised teemakihid QGIS-i projekti lisatakse. Tabeli olemasolu
andmebaasis ei tähenda, et vastav QGIS-i kiht on projektis kasutatav.

Veevõrgu tööriist vajab korraga:

1. redigeeritavat veetoru projektikihti;
2. filtreerimata veesõlmede baaskihti;
3. nende ühist PostGIS-i andmeühendust.

Kui üks neist puudub, peab **Lisa veetoru** olema keelatud ja diagnostika peab
nimetama puuduva kihi või omaduse. Tööriist ei lisa puuduvat projektikihti ega
loo puuduvat tabelit.

Praeguses väljundis lisatakse filtreerimata veesõlmede tehniline baaskiht siis,
kui valitud projektikomponentide hulgas on `SN_WATER_NODE` põhine komponent.
Üksnes veetoru teemakihi valimine ei lisa seda tugikihti QGIS-i projekti, kuigi
`SN_WATER_NODE` tabel võib andmebaasis sõltuvusena olemas olla.

## 3. Veetoru projektikiht

Tavalise vee teemakihi tegelik ülesehitus on järgmine:

| Omadus | Väärtus |
|---|---|
| Andmepakkuja | `postgres` |
| Skeem | `evel` |
| Tabel | `sn_water_duct` |
| Geomeetriaveerg | `GEOM` |
| Geomeetria | `LineString`, SRID `3301` |
| Alamfilter | `"NETWORK_ID" = 312` |
| `NETWORK_ID` vaikeväärtus | `312` |
| `NETTYPE_ID` vaikeväärtus | `308` |

Projektikiht kannab vähemalt järgmisi tehnilisi omadusi:

```text
evel_project_layer = true
evel_project_source = postgres
evel_project_schema = evel
evel_project_table = sn_water_duct
evel_topology_role = water_edge
evel_topology_node_network_id = 312
evel_topology_node_nettype_id = 308
```

Tuletõrjevee ja toorvee kihid kasutavad sama tabelit, kuid teisi filtreid ja
`NETWORK_ID` väärtusi. Seetõttu peab tööriist võtma uue sõlme võrguväärtused
aktiivse torukihi omadustest, mitte eeldama alati väärtust `312`.

### Uue toru põhiandmete eelistused

Uue objekti tühjade väljade korral kasutatakse järgmisi algvalikuid:

| Võrk | Otstarve | Materjal | Mõõdu tüüp | Mõõt | Rõhuklass | Ringjäikus |
|---|---|---|---|---:|---|---|
| Vesi | Tarbijatoru | PE | De | 32 | PN10 | Määramata |
| Tuletõrjevesi | Peatoru | PE | De | 110 | PN10 | Määramata |
| Toorvesi | Peatoru | PE | De | 110 | PN10 | Määramata |

Eelistused lahendatakse projektikihi lookup-valikute kuvatavate nimetuste
järgi. Olemasoleva objekti ega juba täidetud välja väärtust ei kirjutata üle.
Läbimõõt on sisestust kiirendav lähte-eelistus, mitte hüdraulilise arvutuse
tulemus.

### Nõutavad toruväljad

Vähemalt järgmised väljad peavad olema olemas:

```text
MSLINK
NETWORK_ID
NETTYPE_ID
BEGIN_NODE_ID
END_NODE_ID
LENGTH_2D
GEOM
```

- `MSLINK` on PostGIS-is serveripoolne `IDENTITY` primaarvõti;
- `BEGIN_NODE_ID` viitab `sn_water_node.MSLINK` väärtusele;
- `END_NODE_ID` viitab `sn_water_node.MSLINK` väärtusele;
- mõlemad sõlmeviited on andmebaasis `DEFERRABLE INITIALLY DEFERRED`
  võõrvõtmed;
- `LENGTH_2D` QGIS-i vaikeavaldis on `length($geometry)` ja see rakendub ka
  geomeetria muutmisel;
- `MSLINK` ja `LENGTH_2D` on atribuudivormis kirjutuskaitstud.

`LENGTH_2D` tulemus on EPSG:3301 puhul meetrites. Võrgutööriist ei tohi arvutada
primaarvõtit ega asendada serveripoolset vaikeväärtust.

## 4. Veesõlmede filtreerimata baaskiht

Tehnilise baaskihi ülesehitus:

| Omadus | Väärtus |
|---|---|
| Andmepakkuja | `postgres` |
| Skeem | `evel` |
| Tabel | `sn_water_node` |
| Geomeetriaveerg | `GEOM` |
| Geomeetria | `Point`, SRID `3301` |
| Alamfilter | puudub |
| Kihipuus nähtav | ei |

Kihi tehnilised omadused:

```text
evel_project_layer = true
evel_project_support_layer = true
evel_topology_support_layer = true
evel_project_source = postgres
evel_project_schema = evel
evel_project_table = sn_water_node
evel_topology_role = water_node
```

Tööriist kasutab seda kihti kõigi olemasolevate sõlmede leidmiseks ja uute
baassõlmede loomiseks. Nähtavaid kihte `Kaevud`, `Sulgeseadmed`, `Liitmikud` ja
`Muud veesõlmed` ei tohi selleks kasutada, sest need on detailtabelite kaudu
filtreeritud vaated samale `sn_water_node` tabelile.

### Nõutavad sõlmeväljad

```text
MSLINK
NETWORK_ID
NETTYPE_ID
GEOM
```

- `MSLINK` on PostGIS-is serveripoolne `IDENTITY` primaarvõti;
- uue sõlme `NETWORK_ID` ja `NETTYPE_ID` saadakse aktiivse torukihi
  `evel_topology_node_*` omadustest;
- geomeetria lisatakse `GEOM` veergu;
- genereeritud `MSLINK` tuleb lugeda tagasi QGIS-i andmepakkujalt.

## 5. Nähtavad sõlmekihid ja detailtabelid

Veesõlmede teemagrupi kihid kasutavad ühist `sn_water_node` baastabelit ja
eraldi mittegeomeetrilisi detailtabeleid:

| Nähtav kiht | Detailtabel | Baasvaikeväärtused | Detaili vaikeväärtused |
|---|---|---|---|
| Kaevud | `sn_water_manhole` | `NETWORK_ID=312`, `NETTYPE_ID=308` | `TYPE_ID=570` |
| Sulgeseadmed | `sn_water_valve` | `NETWORK_ID=312`, `NETTYPE_ID=308` | `TYPE_AQUA_ID=589`, `TYPE_ID=591`, `VALVE_HAND=598` |
| Liitmikud | `sn_water_branch` | `NETWORK_ID=312`, `NETTYPE_ID=308` | `TYPE_AQUA_ID=522`, `TYPE_ID=532` |
| Muud veesõlmed | `sn_water_other_node` | `NETWORK_ID=312`, `NETTYPE_ID=308` | `TYPE_AQUA_ID=574`, `TYPE_ID=577` |
| Hüdrandid | `sn_fire_plug` | `NETWORK_ID=313`, `NETTYPE_ID=308` | `TYPE_AQUA_ID=159`, `PLUG_TYPE_ID=160`, `LOCATION_ID=154` |

Iga nähtava kihi alamfilter piirab baaskihi objektid vastava detailtabeli
`NODE_ID` väärtustega. Näiteks `Liitmikud` kuvab ainult need `sn_water_node`
kirjed, mille `MSLINK` esineb tabelis `sn_water_branch.NODE_ID`.

Detailkiht lisatakse projekti tehnilise kihina ilma kihipuus kuvamata. QGIS-i
projektis luuakse:

- relatsioon `detail.NODE_ID -> sn_water_node.MSLINK`;
- redigeeritav join ilma väljanime prefiksita;
- `upsert on edit`;
- kaskaadne kustutamine;
- dünaamiline atribuudivorm.

Andmebaasis on `NODE_ID` unikaalne ühe detailtabeli piires ja sellel on
võõrvõti `sn_water_node.MSLINK` väljale. Detailkirje `ID` on serveripoolne
`IDENTITY` primaarvõti.

### Hüdrandi lisamine ja haldamine

Hüdrant kasutab sama sõlme-detaili mudelit:

```text
sn_fire_plug.NODE_ID -> sn_water_node.MSLINK
```

Tööriist võib lisada detaili olemasolevale veesõlmele või luua uue
`sn_water_node` baassõlme. Veetoru sisemisel lõigul lisamisel poolitatakse
toru ning uus sõlm, mõlemad toruosad ja `sn_fire_plug` detail salvestatakse
ühes automaatses tehingugrupis. Uue hüdrandisõlme võrgu vaikeväärtused
loetakse nähtavalt `Hüdrandid` kihilt; olemasoleva sõlme võrguvälju tööriist
ei kirjuta üle.

Hüdrandi vorm muudab detailvälju `TYPE_AQUA_ID`, `PLUG_TYPE_ID`,
`LOCATION_ID`, `MANUFACTURER`, `DUCT_SIZE`, `CAPACITY`,
`MEASURED_CAPACITY`, `MEASURE_DATE`, `MEASURE_NR` ja
`CONNECTION_STANDARD` ning valitud baassõlme põhilisi haldusvälju.
Tehnilised `ID`, `NODE_ID`, `MSLINK`, `NETWORK_ID` ja `NETTYPE_ID`
täidetakse automaatselt ning neid kasutaja vormis ei muuda.

### Kaevu detail sõlmekonfiguraatoris

Sõlmekonfiguraatori valik **Sõlm asub kaevus** tähendab ühe
`sn_water_manhole` detailkirje olemasolu:

```text
sn_water_manhole.NODE_ID -> sn_water_node.MSLINK
```

Kaev ei asenda keskse sõlme liitmiku- ega harude sulgeseadmete detaile. Samal
baassõlmel võivad olla korraga kaevu ja liitmiku detailkirjed.
Konfiguraator muudab järgmisi kasutajavälju:

```text
TYPE_ID
MATERIAL_ID
DIAMETER_TYPE_ID
DIAMETER_ID
FIRMNESS_CLASS_ID
ANCHOR_PLATE
LOAD_LEVELING_PLATE
LID_TYPE_ID
LID_MATERIAL_ID
LID_SHAPE_ID
LID_DIAMETER_ID
LID_CAPACITY_ID
LID_INSULATION
ACCESS_DUCT_DIAM
```

Detaili lisamine, muutmine või eemaldamine peab kuuluma liitmiku ja
sulgeseadmetega samasse QGIS-i redigeerimisoperatsiooni. Puuduva
`sn_water_manhole` detailkihi või selle tehingugruppi mittekuulumise korral
peab sõlmekonfiguraatori käivitusdiagnostika nimetama konkreetse takistuse.

### Veevõrgu rajatis sõlmekonfiguraatoris

Veevõrgupumpla, veetöötlusjaam ning puurkaev/veeallikas kasutavad sama
mittegeomeetrilist detailtabelit:

```text
sn_water_pumping_station.NODE_ID -> sn_water_node.MSLINK
```

Genereeritud projektis eristatakse rajatise variante sõlme võrgu ning
detailkihi vaikeväärtuste kombinatsiooniga:

| Rajatis | `NETWORK_ID` | `ROLE_ID` | `WATER_TYPE_ID` |
|---|---:|---:|---:|
| Veevõrgupumpla | 312 | 370 | 378 |
| Veetöötlusjaam | 312 | 369 | 376 |
| Puurkaevud ja veeallikad | 314 | 369 | 376 |

Plugin tuvastab variandid projektis loodud `NODE_ID -> MSLINK` relatsiooni,
detailkihi `evel_component_name` omaduse ning kihtide vaikeväärtuste kaudu.
Kuvatavaid kihinimesid ei kasutata andmekihi tehniliseks leidmiseks.

Ühel sõlmel saab olla üks `sn_water_pumping_station` detailkirje. Rajatise
tüübid on seetõttu vastastikku välistavad, kuid rajatis võib samal baassõlmel
eksisteerida koos liitmiku ja kaevu detailidega. Konfiguraator muudab järgmisi
kasutajavälju:

```text
MATERIAL_ID
PRODUCTIVITY
PRESSURE_INCREASE
P_REG_CODE
P_PASPORT_NR
P_DEPTH
WATER_SOURCE_ID
WIPEOUT_DATE
RENEWAL_DATE
IS_CONTROLLED
IS_SIGNALISATION
PROTECTION_ZONE
MANTLE_DIAM
```

`NODE_ID`, `ROLE_ID` ja `WATER_TYPE_ID` määrab plugin automaatselt. Lisamine,
tüübi vahetamine ja eemaldamine kuuluvad ülejäänud sõlmekomponentidega samasse
QGIS-i redigeerimisoperatsiooni.

## 6. Vormid

Veetoru lisamisel kasutatakse ühise heleda kujundusega kolme sammuga EVEL-i
torudialoogi: **Toru põhiandmed → Kõrgused ja vool → Haldus ja kvaliteet**. Dialoog loeb
väljade aliased, lookup-valikud, vaikeväärtused ja piirangud aktiivse veetoru
projektikihi QGIS-i metaandmetest. Lookup-väärtusi ega muid projektipõhiseid
valikuid ei kirjutata plugina koodi sisse.

Tehnilised väljad `MSLINK`, `NETWORK_ID`, `NETTYPE_ID`, `BEGIN_NODE_ID`,
`END_NODE_ID` ja `LENGTH_2D` on dialoogis lukustatud. Dialoogist loobumine
pöörab tagasi kogu poolelioleva toru-sõlme operatsiooni, kaasa arvatud loodud
sõlmed ja olemasoleva toru poolitamise.

Sõlmekomponentide kihid kasutavad projektiga seotud `.ui` vorme. Vormi asukohta
tuleb lugeda `QgsEditFormConfig` kaudu; failinime või kuvatavat vormipealkirja
ei tohi tööriista koodi sisse kirjutada.

Komponentvormi puhul on QGIS-i kihil lisaks omadus:

```text
evel_form_ui = <tegelik UI faili nimi>
```

Vormide põhimõtted:

- süsteemiväljad ja geomeetriaveerg on peidetud ning kirjutuskaitstud;
- PostGIS-i primaarvõtmel puudub QGIS-i `maximum(...) + 1` vaikeavaldis;
- detailvormis on `MSLINK`, detaili `ID` ja `NODE_ID` tehnilised väljad
  peidetud ning kirjutuskaitstud;
- valikloendid kasutavad peidetud `sn_constant` lookup-kihti;
- võrgutööriist peab pärast geomeetria ja tehniliste viidete ettevalmistamist
  avama veetoru ühise EVEL-i torudialoogi.

## 7. Projekti redigeerimisrežiim

PostGIS-i projektis kasutatakse:

```text
Qgis.TransactionMode.AutomaticGroups
Qgis.ProjectFlag.EvaluateDefaultValuesOnProviderSide = true
```

Ka PostgreSQL-i kihtide andmepakkujal on serveripoolsete vaikeväärtuste
hindamine sisse lülitatud. See võimaldab lugeda `IDENTITY` väärtuse pärast
sõlme lisamist ja kasutada seda toru `BEGIN_NODE_ID` või `END_NODE_ID` väljal.

Võrgutööriist peab enne töö alustamist kontrollima vähemalt:

- mõlemad kihid on PostGIS-i kihid ja redigeeritavad;
- mõlemad kuuluvad sama andmeühenduse automaatsesse tehingugruppi;
- projekt hindab andmepakkuja vaikeväärtusi;
- vajalikud väljad ja geomeetriatüübid on olemas;
- torukihil on uue sõlme `NETWORK_ID` ja `NETTYPE_ID` määratud.

Tööriist ei muuda neid projektiseadeid vaikides.

## 8. `SN_WATER_BRANCH` otsus

Praegune projekt käsitleb `sn_water_branch` tabelit `Liitmikud` nähtava kihi
detailtabelina. Detailkirje tähendus on:

```text
sn_water_branch.NODE_ID -> sn_water_node.MSLINK
```

Toru keskele ühendamiseks on kaks tehniliselt võimalikku tulemust:

1. luua ainult `sn_water_node` baassõlm;
2. luua baassõlm ja sellele `sn_water_branch` detailkirje.

Seda valikut ei lahendata uue metadata poliitikaga. Enne rakendamist tuleb
kontrollida päris genereeritud projektis `Liitmikud` vormi, stiili ja
andmesisestuse käitumist ning kinnitada EVEL-i sisuline reegel. Kuni otsus pole
tehtud, peab topoloogiamootor oskama baassõlme luua, kuid detailkirje loomine
peab jääma eraldi ja selgelt testitavaks operatsiooniks.

## 9. Arendaja soovituslik käivitusdiagnostika

**Lisa veetoru** võib aktiveeruda ainult siis, kui:

1. leidub täpselt üks sobiv aktiivne `water_edge` kiht;
2. leidub täpselt üks filtreerimata `water_node` tugikiht;
3. mõlemal kihil on oodatud PostGIS-i tabel ja geomeetria;
4. torukihil on vajalikud tehnilised väljad ning sõlme vaikeväärtused;
5. sõlmekihil on `MSLINK`, `NETWORK_ID`, `NETTYPE_ID` ja `GEOM`;
6. tehingu- ja provideripoolsed vaikeväärtused on kasutatavad;
7. kasutajal on mõlema tabeli muutmisõigus.

Kui kontroll ebaõnnestub, tuleb tööriist keelata ja näidata konkreetset põhjust.
Kihi kuvatav nimi ei ole piisav tuvastustunnus.

## 10. Kontroll päris projektifailiga

Käesolev kirjeldus põhineb generaatori praegusel rakendusel. Enne esimese
joonestamisfunktsiooni lõpetamist tuleb üks generaatoriga salvestatud `.qgz` või
`.qgs` projekt lisada arenduse testnäidiseks ja kontrollida selles:

- toru- ja tugikihi andmeallika URI-d;
- tegelikud custom property väärtused;
- `subsetString()` väärtused;
- vormide failiteed;
- QGIS-i relatsioonid ja join'id;
- provideripoolsed vaikeväärtused;
- uue sõlme serveripoolse `MSLINK` tagastus;
- `Liitmikud` detailkirje loomise tegelik kasutusvoog.

Kui projektifail ja käesolev kirjeldus erinevad, on salvestatud projekt koos
andmebaasi tegeliku skeemiga vea leidmise tõeallikas ning erinevus tuleb esmalt
parandada projekti loomise protsessis.
