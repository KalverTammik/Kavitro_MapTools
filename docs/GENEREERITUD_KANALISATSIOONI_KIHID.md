# Genereeritud kanalisatsioonikihtide kasutamine

See dokument kirjeldab EVEL Võrgutööriistade praegust lepingut generaatoriga
loodud isevoolsete kanalisatsioonikihtide jaoks. Plugina lähtepunkt on valmis
QGIS-i projekt; eraldi kihiseadistust ei looda.

## Lisa toru valikud

**Lisa toru** on rippmenüü. Valiku tegemisel aktiveeritakse vastav
generaatori kiht ja käivitatakse QGIS-i joonestamistööriist.

| Valik | Tabel | NETWORK_ID | NETTYPE_ID |
|---|---|---:|---:|
| Isevoolne kanal | `sn_sewer_duct` | 315 | 309 |
| Isevoolsed torud | `sn_sewer_duct` | 316 | 309 |
| Ühisvoolne kanal | `sn_sewer_duct` | 318 | projekti vaikeväärtus |
| Drenaaž | `sn_sewer_duct` | 317 | projekti vaikeväärtus |

Survekanal, survetorud, vaakumkanal ja mahajäetud kanalitorud ei kuulu
isevoolsete torude valikusse.

Uue isevoolse toru puhul:

- geomeetria lisatakse kasutaja valitud projektikihti;
- `NETWORK_ID` ja olemasolu korral `NETTYPE_ID` tulevad kihi
  vaikeväärtustest;
- `LENGTH_2D` arvutatakse geomeetriast;
- avaneb vee- ja isevoolsetele torudele ühine heleda kujundusega EVEL-i
  torudialoog **Toru → Haldus ja kvaliteet → EPANET**; kõrgused, voolusuund
  ning asukoha ja kõrguse täpsus määratakse toruskeemil;
- toruskeem kasutab tegelikku geomeetriat, näitab lähedast võrku, voolu
  ilmakaart ning piisavate otsakõrguste korral pikiprofiili; kuni isevoolse
  toru sõlmed pole loodud, kuvatakse otspunktid ausalt olekuga **Sidumata**;
- väljade sidemed, lookup-valikud, vaikeväärtused ja piirangud loetakse
  aktiivse torukihi QGIS-i metaandmetest; kasutajale näidatavad sildid ning
  ikoonid tulevad plugina UI-konfiguratsioonist ja haldusväljad paigutuvad
  vastavalt saadaolevale laiusele ühte või kahte veergu;
- uue toru tühjade põhiandmete korral kasutatakse järgmisi
  võrguliigipõhiseid eelistusi:

| Võrk | Otstarve | Materjal | Mõõdu tüüp | Mõõt | Rõhuklass | Ringjäikus | Kuju |
|---|---|---|---|---:|---|---|---|
| Reovesi | Peatoru | PVC | De | 160 | PN10 | SN8 | Ümmargune |
| Sademevesi | Peatoru | PP | De | 315 | PN10 | SN8 | Ümmargune |
| Drenaaž | Peatoru | PP | De | 250 | PN10 | SN8 | Ümmargune |
| Ühisvoolne | Peatoru | PP | De | 315 | PN10 | SN8 | Ümmargune |

- eelistused lahendatakse lookup-valikute kuvatavate nimetuste järgi, mitte
  koodi salvestatud ID-dega; projektist või kasutajalt juba saadud väärtust ei
  kirjutata üle;
- generaatori `FIRMNESS_CLASS` referentsandmed sisaldavad valikuid
  **Määramata, SN8, SN16**; tavalisel isevoolsel torul eelistatakse `SN8` ja
  `SN16` jääb kasutatavaks kaitsetoru korral;
- läbimõõdud on sisestust kiirendavad lähte-eelistused, mitte
  hüdraulilise arvutuse tulemus; kasutaja peab projektipõhise mõõdu vajadusel
  muutma;
- `MSLINK`, `NETWORK_ID`, `NETTYPE_ID`, `BEGIN_NODE_ID`, `END_NODE_ID` ja
  `LENGTH_2D` on dialoogis lukustatud;
- dialoogist loobumisel pööratakse tagasi kogu pooleliolev toruoperatsioon ja
  objekt eemaldatakse redigeerimispuhvrist;
- `BEGIN_NODE_ID` ja `END_NODE_ID` jäävad kuni kaevu või muu
  kanalisatsioonisõlme lisamiseni tühjaks; plugin kirjutab need uue toru
  loomisel selgesõnaliselt tühjaks ka siis, kui vanemas QGIS-i projektis on
  väljadele ekslik vaikeväärtus jäänud.

## Kaevu andmemudel

Kanalisatsioonikaev koosneb kahest kirjest:

```text
sn_sewer_node.MSLINK
        ↑
sn_sewer_manhole.NODE_ID
```

Geomeetria ja üldandmed asuvad `sn_sewer_node` tabelis. Kaevu tüüp,
materjal, läbimõõt, ringjäikus, tõusutoru ja kaane omadused asuvad
`sn_sewer_manhole` detailtabelis.

Generaatori nähtav **Kaevud** kiht:

- kasutab baastabelit `sn_sewer_node`;
- filtreerib sõlmed `sn_sewer_manhole.NODE_ID` seose järgi;
- sisaldab redigeeritavat ja upsert-toega join'i detailkihiga
  **Kaevud detailandmed**;
- kuvab kaevu sümboloogia ja vormi, kuid ei ole plugina tehniline
  kirjutamiskiht.

Veevõrgu `EVEL veesõlmede baaskiht` lahendusega analoogselt peab generaator
lisama kanalisatsioonile privaatse tehnilise baaskihi:

- tabel `sn_sewer_node`;
- kohandatud omadus `evel_topology_role=sewer_node`;
- puuduv alamfilter ja puuduvad join'id;
- punktgeomeetria ning muutmis- ja lisamisõigus;
- sama PostGIS-i ühendus ja automaatne tehingugrupp nagu toru- ja
  detailkihtidel.

Praeguses testprojektis selline kirjutatav baaskiht puudub:
**Kanalisatsiooni sõlmed – ülevaade** on join'ita, kuid kirjutuskaitstud.
Ühilduvuslahendusena loob plugin projekti sessiooniks olemasoleva PostGIS-i
allika põhjal privaatse, filtrita ja join'ita
**EVEL kanalisatsioonisõlmede baaskihi**. Kiht lisatakse projekti registrisse,
kuid mitte kihtide puusse. Uus `sn_sewer_node` kirje luuakse selle kaudu;
`sn_sewer_manhole`, `sn_sewer_branch` või `sn_sewer_pumping_station` detail
luuakse eraldi detailkihis ning nähtavat **Kaevud**, **Liitmikud** või
**Pumplad** kihti kasutatakse ainult tulemuse kuvamiseks. Generaatori järgmine
versioon peab looma sama baaskihi püsivalt.
Pärast edukat kirjutamist aktiveerib plugin loodud detailile vastava nähtava
**Kaevud** või **Liitmikud** kihi ja värskendab kaardivaate. Enne tööriista
käivitamist aktiivne olnud kiht ei määra kunagi kirjutamise sihttabelit.

## Kanalisatsioonipumpla

Pumpla ei ole kaevu liik ega kaevukella detail. Tööriistaribal on selleks
eraldi **Pumpla** tööriist ja eraldi mitme vahelehega sisestusaken.
Sisestusaken kasutab mängulist interaktiivset läbilõikevaadet: skeemi pumpla
rajatis, üksikpumbad, juhtkilp, alus/asukoht ja torustik on klõpsatavad
moodulid, mis avavad vastava parameetrite sammu. Põhinavigatsioon on üks
neljaosaline, võrdse laiusega ja kaherealine sammuriba
**Pumbad → Juhtimine → Rajatis ja asukoht → Torud**; skeemi rajatise ja
aluse/asukoha märgised avavad sama kolmanda sammu.

„Rajatis ja asukoht” vorm on rühmitatud identifitseerimise, klassifikatsiooni,
hüdrauliliste näitajate, tehniliste kõrguste ning asukoha plokkideks. Elemendi,
põhja ja maapinna kõrgus ning katastritunnus asuvad samal kaardil.
Olemasolev aadressiseose ID säilitatakse muutmisel, kuid seda
generaatoris ei kuvata. Välja silt paikneb välja kohal ja
sisestusvälja kõrgus on vähemalt 36 pikslit. Skeemi ja vormi vaikimisi
laiussuhe on ligikaudu 36/64 ning skeemi saab väiksemal ekraanil täielikult
ahendada. Peitmise nupp paikneb skeemi ülemises paremas nurgas; peidetud
skeemi taastamise nupp kuvatakse vormiala ülaservas. Vormi kohal ei
dubleerita aktiivse sammu nimetust, sest see on sammuribal juba nähtav.
Kohustuslikud
väljad on tähistatud. Pumpla nimi on redigeeritava pealkirjana ülemises alas;
samal real paremal kuvatakse ainult võrgu nimetus, mitte võrgu- ja sõlme-ID-sid
ega toruühenduste arvu. Määramata lookup-väärtus ei lähe
täidetud valikuna arvesse. Jätkamisnupp jääb kasutatavaks ning valideerib
klõpsamisel aktiivse sammu, kuvab puuduva või vigase välja juures selge teate
ja viib fookuse esimesele parandamist vajavale väljale. Viimasel sammul muutub
põhitegevus nupuks **Loo pumpla** või **Salvesta pumpla**.

Tehnilised arvuväljad on nullitavad ning kasutavad parameetripõhiseid
vahemikke, samme ja komakohtade arvu. Tühi väärtus ei vaja tehnilist
asendusväärtust `-1` ning lubatud negatiivsed absoluutkõrgused säilivad
väärtusena. Ühikud kuvatakse väljade juures (`l/s`, `bar`, `kW`, `A`, `m`).
Katastritunnuse ebatõenäoline vorming annab kasutajale hoiatuse, kuid ei
asenda andmebaasi sisulist kontrolli. Parempoolne vormiala on keritav ja
kohandub väiksema akna ning Windowsi suurendatud kuvaskaalaga. Väljade sildid
on seotud vastavate sisestusväljadega ning toru kõrgusväljadele antakse
kirjeldavad ligipääsetavuse nimetused.

Illustratsioon on plugina enda skaleeruv vektorskeem ega sõltu välisest
pildifailist. See uuendab valitud liigi, korpuse materjali, tootlikkuse
`Qmax`, projekteeritud rõhutõusu `Δp`, elektrivõimsuse ja juhtimise liigi
kõrval ka pumpla UI-s hallatavate pumpade ning tegelike toruühenduste arvu ja
voolusuundi. Pumpade arv mõjutab ainult dialoogi illustratsiooni, mitte QGIS-i
kaardisümbolit. Torude sammus
kasutatakse kompaktset ilma horisontaalse kerimiseta ühenduste tabelit;
muudetav kõrgus on nimetatud üheselt **Sõlmepoolne toru põhja kõrgus**.
Skeemi peitmisel ja taastamisel säilib kasutaja viimati valitud paneelilaius.

Loomise või salvestamise ajal kuvatakse writer'i tegelikke tööetappe ja
edenemist. Kirjutusvea korral jääb dialoog avatuks, kogu kasutaja sisend
säilib ning veabänner võimaldab pärast vea parandamist sama toimingut uuesti
proovida. Dialoog suletakse alles eduka kirjutamise järel. Sisestatud või
muudetud andmetega dialoogi tühistamisel, sulgemisel või klahviga `Esc`
küsitakse salvestamata muudatuste kohta kinnitust.

Pumpla koosneb kahest põhikirjest ja nullist või mitmest pumbakirjest:

```text
sn_sewer_node.MSLINK
        ↑
sn_sewer_pumping_station.NODE_ID

sn_sewer_pumping_station.ID
        ↑
sn_sewer_pump.PSTATION_ID (0…n)
```

Generaatori nähtav **Pumplad** kiht kasutab `sn_sewer_node` geomeetriat,
filtreerib sõlmed `sn_sewer_pumping_station.NODE_ID` seose järgi ning kuvab
projektis määratud pumpla sümboloogia. Plugin kirjutab geomeetria tehnilisse
filtrita baaskihti ja pumpla väärtused eraldi **Pumplad detailandmed** kihti.
Üksikpumbad loetakse ja kirjutatakse `sn_sewer_pump` tabelisse
`PSTATION_ID` kaudu. Plugin avab selle tabeli sessiooniks privaatse
mittesruumilise tehnilise kihina, lisab kihi QGIS-i automaatsesse
tehingugruppi, kuid ei lisa seda kihipuusse ega kaardile.

Pumpla saab luua järgmistes torukontekstides:

| Kontekst | NETWORK_ID |
|---|---:|
| Reovesi | 315 |
| Sademevesi | 316 |
| Drenaaž | 317 |

Kontekst päritakse valitud torult või olemasolevalt sõlmelt. Seda ei valita
pumpla vormis käsitsi. Ühisvoolse kanali `NETWORK_ID=318` ei ole praeguse
kokkuleppe järgi pumplatööriistas lubatud.

Eraldi pumplaaken muudab järgmisi `sn_sewer_pumping_station` välju:

- `TYPE_AQUA_ID`, `ROLE_ID`, `MATERIAL_ID` ja `CONTROL_ID` generaatori
  lookup-valikutega;
- `NAME`, `PRODUCTIVITY`, `PRESSURE_INCREASE`, `POWER_CONSUMPTION` ja
  `EL_MAX_CURRENT`;
- `PARCEL_NR` ja `ADDRESS_ID`;
- baassõlme tähist ning elemendi, põhja ja maapinna kõrgust;
- pumplaga ühendatud isevoolsete torude sõlmepoolseid kõrgusi.

**Pumbad** samm loeb ja muudab iga `sn_sewer_pump` kirje välju:

- `TYPE_ID` rühmast `SW_PUMP_TYPE` ja `INSTALL_METHOD_ID` rühmast
  `PUMP_INSTALL_METHOD`;
- `MANUFACTURER`, `MARK` ja `INSTALL_DATE`;
- `PRODUCTIVITY`, `PUMP_HEAD`, `POWER_W` ning `RUNNING_TIME`;
- `IN_DIAMETER`, `OUT_DIAMETER`, `ENGINE_CURRENT` ja `ENGINE_VOLTAGE`;
- `REMARKS`.

Pumba `TYPE_ID` on lisatud pumbal kohustuslik. Pumpade arv saadakse seotud
kirjete arvust; pumpla tabelisse eraldi `PUMP_COUNT` väärtust ei kirjutata.
UI lubab pumpasid lisada, kopeerida, muuta ja eemaldada. Uue pumpla puhul
reserveeritakse esmalt `sn_sewer_pumping_station.ID`, seejärel kasutatakse
sama väärtust pumbakirjete `PSTATION_ID` väljal.

`IN_DIAMETER` ja `OUT_DIAMETER` on mudelis arvulised DN-väljad. UI ei luba
neisse vabalt suvalist mõõtu kirjutada, vaid koostab valikud EVEL-i
`SW_DUCT_DIAMETER` standardkataloogist. Varem salvestatud kataloogiväline
väärtus kuvatakse muutmisel eraldi olemasoleva väärtusena, et vältida
andmekadu. Kõik nullitavad arvuväljad märgivad fookuses oleva väärtuse
automaatselt, mistõttu uus sisestus asendab kohe `—` või senise arvu.
Üksikpumba tootlikkus, tõstekõrgus, võimsus, mootori nimivool ja nimipinge
kasutavad ilma kerimisnoolteta tekstivälju. Need väljad lubavad nii koma kui
punktiga kümnendarve ning valivad fookuses senise teksti automaatselt.

Uue pumpla baassõlme `NETTYPE_ID` on generaatori Pumplad kihi järgi `308`.
Toru sisemisel lõigul või murdepunktil pumpla loomine kasutab sama kontrollitud
torupoolituse mehhanismi nagu kaevukell. Olemasolevale kaevu- või
liitmikudetailiga sõlmele pumplat vaikimisi ei lisata, sest pumpla on eraldi
sõlmeobjekt. Pärast edukat rakendamist aktiveeritakse nähtav **Pumplad** kiht.

## Kanalisatsioonisõlme generaator

Tööriistariba **Kaev / põlv** aktiveerib kaardil punktivaliku. Sama
kaevukella-laadne sõlmeskeem võimaldab kirjeldada keskse elemendina kas kaevu
või põlve/ühenduskoha.

EVEL-i praeguses `SW_BRANCH_TYPE` lookup-rühmas puudub eraldi **Põlv**
väärtus. Seetõttu salvestab tööriist kasutajaliideses valitud põlve ametliku
`sn_sewer_branch.TYPE_AQUA_ID` väärtusena **Ühenduskoht** (praeguses
generaatoriprojektis ID `395`). Alamtüüp tuleb `SW_BRANCH_TYPE_SUB`
lookup-rühmast.

### Klõps olemasoleval sõlmel

Tööriist loeb:

- `sn_sewer_node` geomeetria, tähise ja väljad `Z_COORD1`, `Z_COORD2`,
  `Z_COORD3`;
- olemasoleva `sn_sewer_manhole` detaili;
- kõik toetatud isevoolsed torud, mille `BEGIN_NODE_ID` või `END_NODE_ID`
  viitab valitud sõlmele;
- iga toru sõlmepoolse kõrguse vastavalt väljast `BEGIN_Z_COORD` või
  `END_Z_COORD`.

### Klõps ühisel sõlmpunktil või toruotstel

Kui samas punktis lõpeb mitu toru, käsitletakse neid ühe sõlmena. Olemasolevat
ühist `BEGIN_NODE_ID`/`END_NODE_ID` viidet kasutatakse; puuduva viite korral
luuakse üks uus `sn_sewer_node` ning kõigi toruotste viited täidetakse sama
ID-ga. Kasutaja valiku järgi luuakse kas `sn_sewer_manhole` kaevudetail või
`sn_sewer_branch` ühenduskoha detail.

Ka T-kujuline olukord lahendatakse ühe sõlmena: läbiv toru poolitatakse ning
samas kohas lõppev harutoru seotakse loodud sõlmega.

### Klõps toru sisemisel lõigul või murdepunktil

Ühe operatsiooni käigus:

1. luuakse uus `sn_sewer_node`;
2. luuakse kasutaja valikul `sn_sewer_manhole` või `sn_sewer_branch` detail;
3. olemasolev toru poolitatakse klõpsukohas;
4. esimese osa `END_NODE_ID` ja teise osa `BEGIN_NODE_ID` seotakse uue
   sõlmega;
5. kummalegi toruosale saab anda eraldi sõlmepoolse kõrguse;
6. mõlema osa `LENGTH_2D` arvutatakse uuesti;
7. uue toruosa `MSLINK` saadakse serverist.

Olemasoleval murdepunktil klõpsates säilib murdepunkti täpne koordinaat. See
muudetakse topoloogiliseks sõlmeks, mistõttu ei jää detail lihtsalt joone
sisemise tipu külge ilma toru sõlmeviideteta.

Kaevukella nurk arvutatakse päripäeva referents-väljavoolust:

- toru on väljuv, kui `FLOWDIRECTION` näitab sõlmest eemale;
- ühe väljuva toru korral on see `0°` referents;
- mitme väljuva toru korral on referents väikseima sõlmepoolse
  `BEGIN_Z_COORD`/`END_Z_COORD` väärtusega ehk madalaim väljuv toru;
- teiste torude nurgad arvutatakse päripäeva referentstoru tegelikust
  kaardisuunast;
- skeem pööratakse referentstoru järgi ning `N` näitab sellel tegelikku
  põhjasuunda;
- torukõrguse muutmisel hinnatakse mitme väljavoolu referents kohe ümber;
- kui `FLOWDIRECTION` ei määra ühtegi väljavoolu, kuvatakse selge hoiatus ja
  nurgad jäävad ajutiselt põhjasuunast arvutatuks.

See reegel kuulub ainult isevoolse kanalisatsiooni kaevukellale. Veevõrgu
visuaalse sõlmekonfiguraatori torusuundade ja pöördenurkade loogikat see ei
muuda. Mitme eri asukohaga võimaliku sõlme või toru korral tööriist ei tee
vaikivat valikut.

## Tehing ja tagasipööre

Sõlme, kaevu-, liitmiku- või pumpladetaili, pumpla pumbakirjete, kõigi ühises
punktis olevate toruotste, toru poolituse, sõlmeviidete ja kõrguste muutmine
kuulub ühte QGIS-i redigeerimisoperatsiooni. Projekti PostGIS-kihid peavad
kasutama automaatseid tehingugruppe ja serveripoolseid vaikeväärtusi.
Muudatused jäävad QGIS-i redigeerimispuhvrisse ning salvestatakse või
tühistatakse QGIS-i tavapäraste käskudega.

QGIS 3.40 PostGIS-i andmepakkuja ei tagasta nende kihtide `IDENTITY` võtme
vaikeavaldist. Kui võtmeväli jätta QGIS-is tühjaks, lisab andmepakkuja päringusse
seetõttu otsese `NULL` väärtuse ning PostgreSQL ei rakenda `IDENTITY` generaatorit.
Plugin reserveerib enne objekti lisamist võtme tabeli enda jadast
`nextval(pg_get_serial_sequence(...))` abil ja kirjutab saadud täisarvu
`sn_sewer_node.MSLINK`, `sn_sewer_manhole.ID`, `sn_sewer_branch.ID`,
`sn_sewer_pumping_station.ID`, `sn_sewer_pump.ID` või poolitatud
`sn_sewer_duct.MSLINK` väljale. `nextval` on samaaegsete kasutajate
korral turvaline. Objekti lisamine jääb endiselt QGIS-i tehingusse; tühistamisel
võib ID-jadasse jääda kasutamata number, mis on PostgreSQL-i jadade tavapärane
käitumine ega tähenda poolikut objekti.

Kui generaatori redigeeritav join või varasem pooleliolev redigeerimiskäsk on
loonud detailipuhvrisse juba rea, millel on `NODE_ID` ja `TYPE_ID`, kuid puudub
`ID`, ei käsitleta seda valmis andmebaasikirjena. Plugin reserveerib sellisele
pooleliolevale `sn_sewer_manhole` või `sn_sewer_branch` detailile enne väljade
uuendamist samuti serveri jadast võtme. See väldib olukorda, kus QGIS püüab
salvestada olemasolevaks peetud detaili kujul `(NULL, NODE_ID, TYPE_ID, ...)`.
