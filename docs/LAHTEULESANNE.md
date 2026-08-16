# EVEL Võrgutööriistade lähteülesanne

Staatus: arenduse lähtealus
Koostatud: 20.07.2026

## 1. Eesmärk

Luua eraldiseisev QGIS-i plugin, millega saab EVEL andmemudeli võrguobjekte
kiiresti ja topoloogiliselt korrektselt joonestada, muuta ning kontrollida.

Esimene terviklik kasutusjuht on veetoru lisamine nii, et kasutaja ei pea
`BEGIN_NODE_ID` ja `END_NODE_ID` väärtusi käsitsi valima. Plugin peab siduma
joone otsad veesõlmedega, looma vajadusel uued baassõlmed ning lahendama uue
haru ühendamise olemasoleva toru keskele.

## 2. Toodete vastutus

### EVEL Võrgutööriistad

- tuvastab avatud projektist EVEL-i võrgu põhi- ja sõlmekihid;
- juhib võrguobjektide joonestamist ja muutmist;
- täidab ning kontrollib objektide topoloogilisi viiteid;
- töötab QGIS-i avatud kihtide ja olemasoleva autentimise kaudu;
- ei loo andmebaasi, tabeleid, kasutajaid, rolle, vorme ega stiile.

### Kavitro QGIS-i plugin

- jääb Kavitro moodulite ja EVEL/Kavitro andmevahetuse tööriistaks;
- ei ole EVEL Võrgutööriistade käitussõltuvus;
- ei oma EVEL-i üldise võrgutopoloogia redigeerimise loogikat.

Plugin ei impordi Kavitro ega teiste QGIS-i pluginate Python-mooduleid.
Integratsioonileping on QGIS-i projekti ja kihtide metadata ning EVEL-i väljaskeem.

## 3. EVEL-i veevõrgu tähendus

Veevõrk koosneb servadest ja sõlmedest:

- `SN_WATER_DUCT` on joongeomeetriaga võrgu serv;
- `SN_WATER_NODE` on punktgeomeetriaga võrgusõlm;
- `SN_WATER_DUCT.BEGIN_NODE_ID` viitab `SN_WATER_NODE.MSLINK` väärtusele;
- `SN_WATER_DUCT.END_NODE_ID` viitab `SN_WATER_NODE.MSLINK` väärtusele.

Tööriista tõlgendus:

```text
BEGIN_NODE_ID = joone esimese tipu asukohas oleva sõlme MSLINK
END_NODE_ID   = joone viimase tipu asukohas oleva sõlme MSLINK
```

Algus ja lõpp kirjeldavad joone geomeetria suunda. Need ei tähenda tingimata
tegelikku veevoolu suunda. Hüdrauliline suund jääb eraldi välja
`FLOWDIRECTION` vastutuseks.

## 4. Projektileping

Selles dokumendis tähendab projektileping ainult avatud QGIS-i projekti
tehnilisi tunnuseid. See ei ole eraldi lepingufail ega kasutaja seadistus.
Genereeritud kihtide, vormide, vaikeväärtuste ja relatsioonide tegelik
ülesehitus on kirjeldatud failis
[GENEREERITUD_VEEVORGU_KIHID.md](GENEREERITUD_VEEVORGU_KIHID.md).

EVEL-i lõplikud projektikihid peavad olema tuvastatavad järgmiste omaduste järgi:

- `evel_project_layer`;
- `evel_project_table`;
- `evel_project_schema`;
- `evel_project_source`.

Praegune genereeritud PostGIS-i projekt sisaldab järgmisi omadusi:

### Projekti omadused

```text
EVEL/model_version = 1
EVEL/network_tools_contract_version = 1
```

### Veetoru kiht

```text
evel_project_layer = true
evel_project_table = sn_water_duct
evel_topology_role = water_edge
evel_topology_node_network_id = <selle torukihi NETWORK_ID>
evel_topology_node_nettype_id = <uue sõlme NETTYPE_ID>
```

Uue baassõlme `NETWORK_ID` ja `NETTYPE_ID` võetakse aktiivse torukihi nendest
metadata omadustest. Neid ei tuletata kuvatavast kihinimest ega filtreerimata
sõlmekihist. Näiteks tavalisel veetorukihil on väärtused vastavalt `312` ja
`308`.

Nõutavad väljad:

```text
MSLINK
NETWORK_ID
NETTYPE_ID
BEGIN_NODE_ID
END_NODE_ID
GEOM
LENGTH_2D
```

### Veesõlme baaskiht

```text
evel_project_layer = true
evel_project_table = sn_water_node
evel_topology_role = water_node
```

Nõutavad väljad:

```text
MSLINK
GEOM
NETWORK_ID
NETTYPE_ID
```

Projektis peab olema üks üheselt tuvastatav, filtreerimata veesõlmede baaskiht.
See võib olla QGIS-i kihipuus privaatne, sest kasutaja töötab edasi nähtavate
kaevude, sulgeseadmete, liitmike ja teiste detailkihtidega.

Kui veetoru- või filtreerimata veesõlmede baaskiht puudub, ei ole **Lisa
veetoru** kasutatav. Puuduvat kihti ei looda ega asendata tööriista käivitamisel.

### PostGIS-i redigeerimisleping

PostGIS-i projektis peavad olema täidetud järgmised tingimused:

- projekti tehingurežiim on `Automatic Transaction Groups`;
- projekt ja PostgreSQL-i andmepakkuja hindavad serveripoolseid vaikeväärtusi;
- `SN_WATER_DUCT` ja `SN_WATER_NODE` kasutavad sama andmebaasiühendust;
- `MSLINK` saadakse serveripoolsest `IDENTITY` või sequence vaikeväärtusest;
- `BEGIN_NODE_ID` ja `END_NODE_ID` võõrvõtmed viitavad
  `SN_WATER_NODE.MSLINK` väljale;
- võõrvõtmed on `DEFERRABLE INITIALLY DEFERRED`, uuendamisel kaskaadsed ja
  sõlme kustutamisel piiravad (`ON DELETE RESTRICT`).

Plugin kontrollib neid eeldusi enne redigeerimist ega muuda projekti
tehingurežiimi vaikides.

Vanemate projektide jaoks võib kasutada varutuvastust andmeallika skeemi,
tabeli ja nõutud väljade põhjal. Kui kandidaatkihte on mitu või tuvastus ei ole
üheselt kindel, peab plugin tööriista keelama ja näitama täpset põhjust. Kihi
kuvatav nimi ei ole usaldusväärne leping.

## 5. Esimene põhitööriist: Lisa veetoru

### 5.1 Käivitamise kontroll

Enne joonestamist kontrollitakse:

- EVEL projektilepingu olemasolu ja toetatud versiooni;
- veetoru- ja veesõlmekihi olemasolu ning kehtivust;
- nõutud väljade olemasolu;
- kihtide redigeeritavust ja kasutaja õigusi;
- sobivat geomeetriatüüpi ja CRS-i;
- seda, et kasutatav andmeallikas suudab muudatused salvestada.

### 5.2 Joonestamine

Plugin kasutab QGIS-i kaardilõuendit, snapping'ut ja Advanced Digitizing
võimalusi. Kasutaja joonistab toru tavapärase joone lisamise töövooga.

Mõlemale otsale rakendatakse sama lahendusreeglit:

1. **Olemasolev sõlm**: kasutatakse leitud sõlme `MSLINK` väärtust.
2. **Tühi asukoht**: luuakse uus `SN_WATER_NODE` baaskirje ja kasutatakse selle
   serveri või andmepakkuja genereeritud `MSLINK` väärtust.
3. **Olemasoleva toru segment**: luuakse ühendussõlm ning olemasolev toru
   jagatakse kaheks korrektsete algus- ja lõppsõlme viidetega servaks.
4. **Mitmeti tõlgendatav tulemus**: salvestamine peatatakse. Plugin ei vali
   vaikides ühte mitmest lähestikku paiknevast sõlmest.

Pärast geomeetria ja seoste ettevalmistamist täidetakse vähemalt:

- `BEGIN_NODE_ID`;
- `END_NODE_ID`;
- `LENGTH_2D` vastavalt joone pikkusele.

`LENGTH_2D` on tasapinnaline `length($geometry)` tulemus kihi CRS-i ühikutes.
EVEL-i veekihtide leping eeldab projitseeritud `EPSG:3301` CRS-i, mistõttu on
tulemus meetrites. Väärtus arvutatakse uuesti ka geomeetria muutmisel.

Seejärel avatakse ühine heleda kujundusega EVEL-i torudialoog:
**Toru → Haldus ja kvaliteet → EPANET**. Kõrgused, voolusuund ning asukoha ja
kõrguse täpsus määratakse toruskeemil. Sama dialoogi kasutatakse vee-
ja isevoolsete torude jaoks, kuid kuvatavad väljad ning valikud sõltuvad
aktiivsest torukihist.

Toruskeem on kontekstitundlik objekti eelvaade: aktiivne toru joonistatakse
tegeliku geomeetriaga, lähedane võrk jääb visuaalselt taustale, otspunktidel
kuvatakse sõlme seos ning voolusuunast arvutatakse ilmakaar ja asimuut.
Pikiprofiil kuvatakse ainult piisavate kõrgusandmete korral. Skeem ei loo
enda tarbeks dubleerivaid andmevälju ja peab töötama ka sidumata otspunktidega.

Dialoog ei dubleeri generaatori andmemudelit. Väljade sidumine, lookup-valikud,
vaikeväärtused ja piirangud loetakse aktiivse kihi QGIS-i metaandmetest;
kasutajale näidatavad eestikeelsed nimetused ning semantilised ikoonid on
plugina keskses UI-konfiguratsioonis. Toru põhiandmed ja EPANET on
üheveerulised, haldus- ning täpsemad andmed paigutuvad laias vaates kahte ja
kitsas vaates automaatselt ühte veergu. Väärtusepõhine väljalaiuse piirang
säilib paigutuse muutumisel.
Uue toru tühjade põhiandmete korral rakendatakse võrguliigipõhist
eelistusprofiili. Veevõrkudes kasutatakse `De`, `PN10` ja ringjäikust
`SN16`; isevoolsetes võrkudes `De`, `PN10`, `SN8` ning ümmargust kuju.
Kõigi uute torude paiknemine on `Maa-alune`, asukoha täpsus `10 cm` ja
kõrguse täpsus `2 cm`.
Täpne otstarve, materjal ja läbimõõt sõltuvad aktiivse kihi `NETWORK_ID` ning
`NETTYPE_ID` väärtusest ja on kirjeldatud genereeritud vee- ja
kanalisatsioonikihtide dokumentides. Eelistused lahendatakse lookup-valikute
nimetuste järgi ning neid ei rakendata olemasolevale objektile ega väljale,
millel on väärtus juba olemas. Läbimõõt on töövoo algväärtus, mitte
hüdrauliline projekteerimisotsus.
Tehnilised väljad `MSLINK`, `NETWORK_ID`, `NETTYPE_ID`, `BEGIN_NODE_ID`,
`END_NODE_ID` ja `LENGTH_2D` on kasutajale lukustatud. Dialoogist loobumisel
pööratakse tagasi kogu pooleliolev toru-sõlme operatsioon, sealhulgas loodud
sõlmed ja olemasoleva toru poolitamine.

### 5.3 Toru keskele ühendamine

Olemasoleva serva `A -> B` keskele loodud sõlme `J` korral peab tulemus olema:

```text
A -> J
J -> B
J -> C   uus haru
```

Olemasoleva toru tehnilised ja haldusatribuudid säilitatakse mõlemal tekkinud
osal vastavalt QGIS-i poolitusreeglitele. Topoloogilised viited arvutatakse
eraldi ning neid ei kopeerita pimesi.

## 6. Esimese versiooni tööriistad

1. **Lisa veetoru**: loob toru, sõlmed ja vajalikud viited.
2. **Pööra toru suund**: pöörab geomeetria ning vahetab omavahel
   `BEGIN_NODE_ID` ja `END_NODE_ID`.
3. **Kontrolli veevõrku**: leiab puuduvad, vastuolulised ja mitmeti
   tõlgendatavad sõlmeseosed.
4. **Paranda valitud toru seosed**: arvutab valitud toru viited selle
   lõpp-punktide ja olemasolevate sõlmede põhjal uuesti.

Tööriistad kuvatakse kompaktsel EVEL-i tööriistaribal. Tegevused on mitte-EVEL
projektis või puuduva kihilepingu korral mitteaktiivsed ning kuvavad põhjuse.

## 7. Andmetervikluse reeglid

- toru esimene tipp peab ruumiliselt kattuma viidatud algussõlmega;
- toru viimane tipp peab ruumiliselt kattuma viidatud lõppsõlmega;
- viidatud sõlmed peavad andmeallikas olemas olema;
- ühe asukoha juurde ei looda põhjendamatult dubleerivaid baassõlmi;
- toru keskele loodud ühendus peab jagama olemasoleva serva;
- sama sõlme kasutamine mõlemas otsas on lubatud ainult teadlikult toetatud
  suletud geomeetria korral;
- `BEGIN_NODE_ID` ja `END_NODE_ID` on tavavormis peidetud või kirjutuskaitstud;
- geomeetria muutmisel tuleb sõlmeseosed uuesti valideerida;
- joone suuna pööramisel tuleb sõlme-ID väärtused alati vahetada.

Snapping'u ekraanitolerants aitab kasutajal punkti valida, kuid andmete
salvestamisel peab geomeetria lõpp-punkt kasutama täpselt lahendatud sõlme
koordinaati. Lähedus üksi ei tähenda püsivat võrguühendust.

## 8. Salvestamine, ID-d ja samaaegne kasutus

- primaarvõtmeid ei arvutata kujul `maximum(ID) + 1`;
- PostGIS-is kasutatakse serveripoolset `IDENTITY` või sequence vaikeväärtust;
- tööriist kasutab ainult QGIS-i kihtide redigeerimisliidest ja avatud projekti
  andmeühendust;
- sõlmed lisatakse enne neid viitavaid torusid ning genereeritud ID loetakse
  andmepakkujalt;
- mitut kihti puudutav tegevus peab olema üks terviklik redigeerimiskäsk;
- vea või kasutajapoolse tühistamise korral ei tohi jääda osaliselt loodud
  sõlmi, poolikuid torusid ega katkiseid viiteid;
- PostGIS-i puhul nõutakse QGIS-i automaatset transaction group'i; teiste
  andmepakkujate terviklik salvestusviis kontrollitakse eraldi;
- mitme kasutaja korral peab andmebaas jääma võtmete ja võõrvõtmete lõplikuks
  tervikluse kontrollijaks.

Põhiloogika kirjutatakse QGIS-i `QgsVectorLayer` API vastu. PostGIS on esimene
reaalne testkeskkond, kuid otsest PostgreSQL SQL-i ei kasutata tavapärase
joonestamise ainsa teostusena. Nii jääb võimalikuks sama töövoo kasutamine
teiste toetatud redigeeritavate andmeallikatega.

## 9. Kasutajakogemus

- tööriist ei ava suurt haldusakent;
- kaardil kuvatakse snapping'u ja valitud lõpp-punkti selge olek;
- olemasolev sõlm, uus sõlm ja toru poolitamist nõudev asukoht peavad olema
  visuaalselt eristatavad;
- veateade peab nimetama konkreetse puuduva kihi, välja, õiguse või vastuolu;
- `Escape` tühistab aktiivse joonestamise ilma kõrvalmõjudeta;
- pärast edukat lisamist jääb kasutaja tavapärasesse QGIS-i töövoogu;
- hiljem võib lisada jätkurežiimi, kus järgmine toru algab eelmise toru
  lõppsõlmest.

## 10. Testimine

Automatiseeritud testid peavad katma vähemalt:

- EVEL kihi tuvastamise metadata ja väljade järgi;
- puuduva või mitmeti tõlgendatava kihilepingu;
- olemasoleva algus- ja lõppsõlme kasutamise;
- uue baassõlme loomise;
- olemasoleva toru korrektse poolitamise;
- joone pööramise koos ID-de vahetamisega;
- katkise seose tuvastamise;
- ebaõnnestunud mitmekihilise operatsiooni täieliku tagasipööramise;
- ID-de võtmise andmepakkuja vaikeväärtusest.

QGIS-i käsitsi smoke-testid tehakse arenduse PostGIS projektis järgmiste
juhtudega:

1. olemasolev sõlm -> olemasolev sõlm;
2. olemasolev sõlm -> uus sõlm;
3. uus sõlm -> uus sõlm;
4. olemasoleva toru keskelt algav haru;
5. toru geomeetria muutmine pärast loomist;
6. toru suuna pööramine;
7. tegevuse tühistamine igas vaheetapis;
8. kahe kasutaja järjestikused ja võimalusel samaaegsed lisamised.

## 11. Teostamise järjekord

1. Fikseerida ja valideerida EVEL-i projekti- ning kihimetadata leping.
2. Rakendada selles pluginas kihi tuvastus ja käivitamise diagnostika.
3. Rakendada veetoru joonestamine olemasolevate ning uute sõlmedega.
4. Rakendada olemasoleva toru poolitamine ja haru loomine.
5. Rakendada suuna pööramine, kontroll ja valitud toru parandamine.
6. Lisada automatiseeritud testid, kasutajajuhend ja QGIS-i smoke-testide
   kontrollnimekiri.

## 12. Vastuvõtukriteeriumid

Esimene arendusetapp on valmis, kui:

- plugin töötab ilma teiste QGIS-i pluginate aktiivse käitussõltuvuseta;
- EVEL-i projekt tuvastatakse ilma kuvatavaid kihinimesid kasutamata;
- kasutaja saab lisada veetoru ilma sõlme-ID väärtusi käsitsi sisestamata;
- tühja lõpp-punkti juurde tekib üks korrektne baassõlm;
- olemasoleva toru keskele ühendamine tekitab kolm õigesti seotud serva;
- suuna pööramine säilitab geomeetria ja viidete kooskõla;
- vigane või poolik mitmekihiline tegevus pööratakse täielikult tagasi;
- kontrolltööriist leiab vähemalt puuduva sõlme, vale viite ja geomeetriast
  eemal asuva viidatud sõlme;
- PostGIS-i testis saadakse kõik primaarvõtmed serveripoolselt.

## 13. Edasine ulatus

Pärast veevõrgu töövoo kinnitamist saab sama topoloogiateenust laiendada
kanalisatsiooni-, kaugkütte-, gaasi-, elektri- ja sidevõrkudele. Laiendamine ei
tohi muuta esimese versiooni veevõrgu lepingut ega tuua pluginasse Kavitro
veebirakenduse või andmebaasi haldusloogikat.
