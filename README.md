# EVEL Võrgutööriistad

Eraldiseisev QGIS-i tööplugin EVEL andmemudeli võrguobjektide kiireks ja
topoloogiliselt korrektseks redigeerimiseks.

Plugin ei ole EVEL Generatori ega Kavitro plugina alammoodul. Arenduse lähtealus
on fail [docs/LAHTEULESANNE.md](docs/LAHTEULESANNE.md).

## Paigaldamine

Plugin vajab QGIS 3.40 või uuemat versiooni ja QGIS-i Pythoni keskkonnas
`psycopg2` moodulit. Avaldatud versiooni saab paigaldada QGIS-i pluginate
halduris kohandatud repositooriumist:

```text
https://github.com/KalverTammik/Kavitro_MapTools/releases/latest/download/plugins.xml
```

Arenduskeskkonnas peab lähtekataloogi nimi olema `EVEL_network_tools` ning see
peab asuma aktiivse QGIS-i profiili `python/plugins` kataloogis.

## Praegune seis

Praegune arendusversioon sisaldab:

- püsivat EVEL-i tööriistariba;
- EVEL-i tööriistariba, torutüübi menüü ja kõigi kohandatud dialoogide
  fikseeritud Kavitro-stiilis heledat kujundust; teemalülitit ei ole;
- **Lisa toru** rippmenüüd, mis kuvab projekti tegelikud vee- ja isevoolsete
  torude tüübid, aktiveerib valitud generaatori kihi ning käivitab vastava
  joonestamistöövoo;
- sama menüü valikut **Lisa toru koordinaatidega**, mis lubab valida torukihi
  ja sisendi koordinaatsüsteemi, sisestada algus- ja lõpp-punkti ning vajadusel
  täiendavad murdepunktid käsitsi või lõikelaualt;
- isevoolse kanali, sademeveetoru, ühisvoolse kanali ja drenaaži lisamist
  ühise heleda kolme sammuga EVEL-i torudialoogiga ning geomeetriast arvutatud
  `LENGTH_2D` väärtusega;
- vee- ja isevoolsete torude sisestamisel ühtset juhitud töövoogu
  **Toru põhiandmed → Kõrgused ja vool → Haldus ja kvaliteet**, mis loeb väljade nimetused,
  lookup-valikud, vaikeväärtused ja piirangud aktiivse projektikihi
  metaandmetest;
- kõigi toetatud vee- ja isevoolsete kanalisatsioonivõrkude uue toru
  võrguliigipõhiseid põhiandmete eelistusi; läbimõõdu tüüp on `De`, survevõrgul
  eelistatakse `PN10` ja isevoolsel torul `SN8`;
- eelistuste lahendamist lookup-valikute nimetuste järgi ning nende rakendamist
  ainult uue objekti tühjadele väljadele;
- ringjäikuse klassifikaatori valikuid **Määramata, SN8, SN16**, millest
  tavalisel isevoolsel reoveetorul on esmane valik `SN8`;
- tehniliste `MSLINK`, `NETWORK_ID`, `NETTYPE_ID`, `BEGIN_NODE_ID`,
  `END_NODE_ID` ja `LENGTH_2D` väljade lukustamist torudialoogis;
- vormita **Pööra suund** kaarditööriista, mis seab `NULL` või `0`
  `FLOWDIRECTION` väärtuse esimesel klõpsul väärtuseks `+1` ning pöörab
  määratud suuna järgmistel klõpsudel märgi vahetamisega vastupidiseks;
- torusuuna muudatuse kohest salvestamist ja plugina avatud
  redigeerimisseansi lõpetamist; kasutaja varem avatud redigeerimispuhvrit
  plugin vaikimisi ei kinnita;
- torusuuna salvestamisel ainult muudetud kihi renderduse värskendamist ilma
  kogu kaardilõuendi või projektidiagnostika uuesti käivitamiseta ning
  andmebaasioperatsiooni ajal kompaktse määramata kestusega edenemisvaate
  kuvamist;
- uue isevoolse toru `BEGIN_NODE_ID` ja `END_NODE_ID` väärtuste selgesõnalist
  tühjendamist, et vanema projektifaili ekslik vaikeväärtus ei rikuks
  kanalisatsioonisõlme võõrvõtit;
- aktiivse `water_edge` torukihi tuvastamist;
- filtreerimata `water_node` tugikihi tuvastamist;
- projekti versiooni, metadata, väljade, geomeetria, CRS-i, vaikeväärtuste,
  PostGIS-i andmepakkuja ja automaatse tehingugrupi käivitusdiagnostikat;
- olekuikooni, mille kaudu kuvatakse esimene konkreetne takistus;
- aktiivset **Lisa toru** kaarditööriista, mis kasutab QGIS-i tavapärast
  kaardil joonestamist ja avab seejärel ühtse EVEL-i torudialoogi;
- eraldi püsivat **Vaata/muuda toru** kaarditööriista, mis tuvastab klõpsu
  lähedal toetatud vee- või kanalisatsioonitoru, laseb kattuvate kandidaatide
  korral kasutajal toru valida ning avab olemasoleva objekti samas EVEL-i
  torudialoogis;
- olemasoleva toru atribuudimuudatuste koondamist üheks tühistatavaks käsuks;
  vormist loobumisel pööratakse ainult selle dialoogi muudatused tagasi ning
  `MSLINK`, võrgu- ja sõlme-ID-d, pikkus ja geomeetria jäävad lukustatuks;
- kirjutusõiguseta torukihi avamist sama dialoogi vaaterežiimis;
- toru otste sidumist ühe võimaliku olemasoleva sõlmega või uue filtreerimata
  `sn_water_node` baassõlme loomist;
- olemasoleva toru algus- või lõpp-punktist jätkamisel puuduva baassõlme
  loomist ning vana toruotsa viite täitmist sama operatsiooni osana;
- olemasoleva toru sisemisest lõigust haru alustamisel ühendussõlme loomist,
  vana toru jagamist kaheks ja mõlema osa topoloogiliste viidete arvutamist;
- poolitatud toru mõlemal osal QGIS-i väljapoolituse reeglite järgi atribuutide
  säilitamist, kusjuures uue osa `MSLINK` saadakse serveripoolselt;
- toru, uute sõlmede ning tehniliste `BEGIN_NODE_ID`, `END_NODE_ID` ja
  `LENGTH_2D` väärtuste lisamist ühe tagasipööratava redigeerimisoperatsioonina;
- vormist loobumisel kogu poolelioleva toru-sõlme operatsiooni tühistamist;
- eraldi visuaalset **Hüdrant** kaarditööriista, millega saab muuta
  olemasoleva hüdrandi andmeid, lisada `sn_fire_plug` detaili olemasolevale
  veesõlmele või luua uue hüdrandisõlme veetorule;
- veetoru sisemusse hüdrandi lisamisel toru poolitamist, uue
  `sn_water_node` baassõlme ja ühe `sn_fire_plug` detailkirje loomist samas
  andmebaasitehingus;
- hüdrandi liigi, alamtüübi, paiknemise, tootja, tarnetoru läbimõõdu,
  ühendusstandardi, nimi- ja mõõdetud tootlikkuse ning mõõtmisandmete
  muutmist generaatori lookup-väljadega heledas kolme vahelehega vormis;
- hüdrandiga seotud sõlme tähise, inventarinumbri, kasutusoleku,
  seisukorraklassi, paigaldusaasta ja märkuste haldamist samas vormis;
- eraldi **Liitumispunkt** kaarditööriista, millega saab olemasolevat
  `CONSUMER_POINT` kirjet vaadata ja muuta või luua uue liitumispunkti
  olemasolevale vee- või kanalisatsioonisõlmele;
- vee-, reovee- ja sademeveeseose üheselt valimist olukorras, kus klõpsu
  lähedal on mitu võimalikku sõlme või sama `sn_sewer_node` võib tähistada
  reovee- või sademeveeliitumist;
- liitumispunkti põhiandmete, EVEL-i klassifikaatorite, võrgusõlmeviidete,
  omaniku, arve saaja, klienditunnuste ja märkuste muutmist heledas nelja
  vahelehega vormis; tehniline ID ja geomeetria täidetakse automaatselt;
- liitumispunkti teenusetunnuste `WATER_JUNCTION`, `SEWER_JUNCTION` ja
  `STORM_WATER_JUNCTION` arvutamist vastavate sõlmeviidete järgi ning
  salvestamise järel plugina avatud redigeerimisseansi lõpetamist;
- aktiivset visuaalset **Konfigureeri sõlm** kaarditööriista, mis loeb valitud
  baassõlme toruharud, kuvab need tegelike lokaalsete suundade järgi, pakub
  harude arvu põhjal keskse liitmiku tüüpi ning võimaldab haru ja sellele
  lisatava komponendi valida otse interaktiivselt skeemilt;
- sulgeseadme kauguse muutmist piki toru lohistades;
- visuaalse konfiguraatori komponendipaletti eristatavate vektorikoonide,
  tekstinimetuste ja ligipääsetavusvihjetega;
- valitud keskse liitmiku tüübikohast kujutamist skeemil tegelike
  toruharude suundades ning skeemi infot korranud kokkuvõttekasti eemaldamist;
- iga skeemiharu otsas toru ID, haru pikkuse ning generaatori
  `ValueRelation`-väljadest loetud läbimõõdu tüübi, läbimõõdu, materjali ja
  rõhuklassi kuvamist loetavate nimetustena;
- haru infokaartide paigutamist torujoonest väljapoole koos viitejoone ja
  kaartide omavahelise kattumise vältimisega;
- `FLOWDIRECTION` põhise voolusuuna kuvamist toruharul: `+1` järgib joone
  `BEGIN_NODE_ID → END_NODE_ID` suunda, `-1` näitab vastassuunda ning
  `0`/`NULL` kuvatakse määramata kahepoolse märgina;
- keskse sõlme märkimist kaevus paiknevaks sama `SN_WATER_NODE` baassõlmega
  seotud `SN_WATER_MANHOLE` detailkirje kaudu;
- kaevu liigi, materjali, läbimõõdu, ringjäikuse, tõusutoru, ankurdus- ja
  tasandusplaadi ning kaane tüübi, materjali, kuju, läbimõõdu, kandevõime ja
  soojustuse muutmist generaatori lookup-valikutega kahel kompaktsel vahelehel;
- kaevu kujutamist visuaalsel sõlmeskeemil kahe kontsentrilise ringina ning
  kaevu detaili lisamist, muutmist või eemaldamist samas tagasipööratavas
  redigeerimisoperatsioonis liitmiku ja sulgeseadmetega;
- keskse sõlme rajatise valimist generaatori projektis saadaolevate
  `SN_WATER_PUMPING_STATION` variantide seast: veevõrgupumpla,
  veetöötlusjaam või puurkaev/veeallikas;
- rajatise valikute piiramist sõlme `NETWORK_ID` järgi ning tehniliste
  `ROLE_ID` ja `WATER_TYPE_ID` väärtuste automaatset täitmist projektikihi
  vaikeväärtustest;
- rajatise materjali, tootlikkuse, survetõusu, registri- ja passiandmete,
  puurkaevu sügavuse, veeallika, kaugjuhtimise, signalisatsiooni,
  sanitaarkaitse, manteltoru ja elukaare kuupäevade muutmist;
- rajatise tüübi kujutamist visuaalse konfiguraatori kesksõlmel ning selle
  detailkirje lisamist, tüübi vahetamist või eemaldamist liitmiku,
  sulgeseadmete ja kaevuga samas tagasipööratavas operatsioonis;
- keskse `sn_water_branch` detaili loomist või tüübi muutmist ning valitud
  harudele eraldi `sn_water_valve` sõlmede loomist kasutaja määratud kaugusel;
- keskse liitmiku valikute piiramist tegeliku toruharude arvu järgi: otsakork
  ühele, kaheharulised liitmikud kahele, kolmik ja sadul kolmele ning nelik neljale
  harule; sama reeglit kontrollib enne kirjutamist ka writer;
- sulgeseadme `TYPE_AQUA_ID` kasutuskoha (liini/kinnistu) ja `TYPE_ID`
  tehnilise tüübi valimist generaatori lookup-väärtustest;
- sulgeseadme lisamisel olemasoleva toru poolitamist nii, et liitmik,
  sulgeseadmete baassõlmed, detailkirjed ja toruosad moodustavad ühe
  tagasipööratava redigeerimisoperatsiooni;
- sulgeseadme paigutamist kuni 0,30 m kaugusele kesksest sõlmest ning
  olemasoleva sulgeseadme kauguse hilisemat muutmist koos mõlema külgneva
  toruosa geomeetria ja pikkuse ümberarvutamisega;
- mõlema sõlmekonfiguraatori rakendamisel modaalse edenemisakna kuvamist koos
  tegelike tööetappide, toruharude tegevuste ja edenemisribaga;
- liitmiku ja sulgeseadme sümboli pöördenurga arvutamist torude lokaalsetest
  suundadest ning selle kirjutamist baassõlme `PNT_ROTATION` väljale
  lähima täiskraadina;
- aktiivset kanalisatsiooni **Kaev / põlv** kaarditööriista, mis lubab klõpsata
  olemasoleval kanalisatsioonisõlmel, samas punktis paiknevatel toruotstel,
  toru murdepunktil või toru sisemisel lõigul;
- analoogset kaevukella skeemi torude tegelike omavaheliste suundade,
  läbimõõtude, materjalide, sõlmepoolsete kõrguste ja `FLOWDIRECTION`
  voolunooltega;
- kanalisatsiooni kaevukella nurkade arvutamist päripäeva väljavoolust:
  referentstoru nurk on `0°` ning mitme väljuva toru korral valitakse
  referentsiks väikseima sõlmepoolse kõrgusega väljuv toru;
- väljuvate, sisenevate ja määramata voolusuunaga torude eristamist tabelis
  ning referentstoru automaatset uuendamist torukõrguse muutmisel;
- `sn_sewer_node` baassõlme ja `sn_sewer_manhole` detaili loomist või
  muutmist ning kaevu liigi, materjali, läbimõõdu, ringjäikuse, tõusutoru,
  kõrguste ja kaane parameetrite muutmist;
- kaevu või põlve/ühenduskoha valimist samas generaatoris; põlv kirjutatakse
  EVEL-i praeguse lookup-mudeli ametliku `sn_sewer_branch` tüübi
  **Ühenduskoht** alla;
- toru sisemisele lõigule või olemasolevale murdepunktile sõlme lisamisel
  toru poolitamist, mõlema toruosa sõlmeviidete, eraldi sõlmepoolsete
  kõrguste ja `LENGTH_2D` väärtuste arvutamist ühe tagasipööratava
  operatsioonina;
- mitme samas punktis lõppeva toru ning toru sisemise lõigu ja sellesse
  suubuva haru tuvastamist ühe tervikliku sõlmena, ilma torude vahel
  vaikivat valikut tegemata;
- PostGIS-i `IDENTITY` võtmete turvalist reserveerimist andmebaasi jadast
  kanalisatsioonisõlmele, kaevu- ja liitmikudetailile ning poolitatud toru
  uuele osale, et QGIS 3.40 ei saadaks uue objekti võtmeväljale `NULL`;
- redigeeritava join'i kaudu juba tekkinud poolelioleva kaevu- või
  liitmikudetaili puuduva `ID` parandamist enne detaili salvestamist;
- kanalisatsioonisõlme geomeetria kirjutamist join'ita tehnilisse
  `sn_sewer_node` baaskihti ning nähtava „Kaevud” kihi kasutamist ainult
  esituskihina; kui generaatori projektis eraldi kirjutatavat baaskihti pole,
  loob plugin sessiooniks privaatse filtrita baaskihi;
- eduka salvestamise järel loodud detailile vastava nähtava „Kaevud” või
  „Liitmikud” kihi aktiveerimist ja kaardivaate viivitamatut värskendamist,
  sõltumata enne tööriista käivitamist aktiivne olnud kihist;
- eraldi kanalisatsiooni **Pumpla** kaarditööriista ja sisestusakent, mis ei
  käsitle pumplat kaevu liigina ning lubab pumpla luua reovee-, sademevee- või
  drenaažitorule või olemasolevale sõlmele;
- mängulist interaktiivset pumpla läbilõikevaadet, kus pumpla rajatis,
  üksikpumbad, juhtkilp, asukoht ja torustik toimivad klõpsatavate moodulitena
  ning avavad vastava parameetriploki;
- ühtset nelja sammuga töövoogu
  **Pumbad → Juhtimine → Rajatis ja asukoht → Torud**,
  mille võrdse laiusega kaherealine sammuriba näitab täitmise seisu ning mille
  tegevusnupud muutuvad konteksti järgi;
- 36/64 proportsiooniga tööala, 36-piksliseid sisestusvälju, väljade kohal
  paiknevaid silte ja vajadusel täielikult ahendatavat pumpla skeemi; peitmise
  nupp paikneb skeemi ülemises paremas nurgas ning peidetud skeemi taastamise
  nupp vormiala ülaservas;
- ülemises alas otse redigeeritavat pumpla nime ja ainult kasutajale vajalikku
  võrgu nimetust; tehnilisi võrgu- ja sõlme-ID-sid seal ei dubleerita;
- kohustuslike väljade selget valideerimist ning rühmitatud
  identifitseerimise, klassifikatsiooni, hüdraulika,
  tehniliste kõrguste, automaatika, elektri ja asukoha plokke; elemendi,
  põhja ja maapinna kõrgus ning katastritunnus kuuluvad ühisele „Rajatis ja
  asukoht” kaardile; olemasolev aadressiseose ID säilitatakse
  muutmisel, kuid seda generaatoris ei kuvata;
- jätkamisnupu kaudu sammu valideerimist, esimesele puuduvale väljale
  fokuseerimist ning kohustuslike „Määramata” lookup-valikute käsitlemist
  täitmata valikuna;
- katastritunnuse vorminguhoiatust, keritavat ja ekraani suurusega kohanevat
  paigutust ning sisestusväljade ligipääsetavaid nimetusi ja seoseid;
- nullitavaid parameetripõhiste vahemike, sammude ja täpsustega arvuvälju,
  mis valivad fookuses senise väärtuse automaatselt, ning negatiivsete
  absoluutkõrguste säilitamist;
- pumpla andmetundliku illustratiivse skeemi reaalajas uuendamist valitud
  liigi, materjali, tootlikkuse, projekteeritud rõhutõusu, elektrivõimsuse,
  juhitavuse, UI-s hallatavate pumpade arvu ning tegelike toruühenduste ja
  voolusuundade järgi; pumpade arv ei mõjuta QGIS-i kaardisümbolit;
- üksikpumpade lisamist, kopeerimist, muutmist ja eemaldamist eraldi
  **Pumbad** sammus `sn_sewer_pump` mudeli järgi; pumbatabel avatakse
  sessiooniks privaatse mittesruumilise kihina, mis ei ilmu QGIS-i kihipuusse;
- pumba sisendi ja väljundi DN-mõõdu valimist EVEL-i
  `SW_DUCT_DIAMETER` standardkataloogist;
- üksikpumba tootlikkuse, tõstekõrguse, võimsuse, nimivoolu ja nimipinge
  sisestamist lihtsates kerimisnoolteta arvutekstiväljades, mis aktsepteerivad
  nii koma kui punkti;
- kompaktset toruühenduste tabelit ilma horisontaalse kerimiseta ning
  üheselt nimetatud sõlmepoolsete torupõhja kõrguste muutmist;
- writer'i töö ajal etapilist edenemisvaadet ja vea korral vormisisendi
  säilitamist koos veabänneri ning uuesti proovimise võimalusega;
- salvestamata muudatuste kinnitust dialoogi tühistamisel, sulgemisel või
  klahviga `Esc`;
- pumpla liigi, rolli, korpuse materjali, tähise/nime, maksimaalse tootlikkuse
  `Qmax`, projekteeritud rõhutõusu `Δp`, elektrikoguvõimsuse, peakaitsme
  läbilaskevõime, juhitavuse, katastritunnuse ja kõrguste
  muutmist koos vastavate ühikutega generaatori
  `sn_sewer_pumping_station` mudeli järgi;
- pumpla loomisel toru poolitamist või toruotste ühendamist, tehnilise
  `sn_sewer_node` baassõlme, `sn_sewer_pumping_station` detaili ja seotud
  `sn_sewer_pump` kirjete haldamist ning nähtava „Pumplad” kihi aktiveerimist
  ühe tagasipööratava operatsioonina;
- mälukihtide unit-testid ja generaatoriga loodud projekti kirjutuskaitstud
  integratsioonitest.

## EVEL-i kontrollpaketi import

Tööriistariba **Impordi** avab kontrollitud GeoPackage'i importeri. Nupp
aktiveerub ainult siis, kui avatud projektis on kõik üheksa vajalikku
`evel` skeemi sihttabelit ning need kasutavad sama PostgreSQL-i ühendust.

Töövoog:

1. ava EVEL Generatoriga loodud sihtprojekt;
2. vajuta **Impordi** ja vali kliendilt tagasi saadud kontrollpaketi `.gpkg`;
3. kontrolli objektide arve ja hoiatusi;
4. käivita kohustuslik **Kontrolli SQL-importi**;
5. pärast edukat tagasipööratud proovi vajuta **Impordi andmed**.

Importer:

- aktsepteerib ainult `EVEL kliendi kontrollpakett` tüüpi paketti;
- kontrollib paketi lokaalseid ID-sid, geomeetriaid, EPSG:3301
  koordinaatsüsteemi ja sõlmeviiteid;
- kontrollib sihttabeleid, serveripoolseid IDENTITY võtmeid,
  kirjutusõigusi, välju, SRID-d ja `SN_CONSTANT` lookup-väärtusi;
- omistab uued serveri ID-d ning teisendab kõik paketi kohalikud
  `NODE_ID`, `BEGIN_NODE_ID` ja `END_NODE_ID` viited;
- lisab sõlmed, detailkirjed ja torud ühe PostgreSQL-i tehinguna;
- katkestamisel või vea korral pöörab kogu tehingu tagasi;
- blokeerib sama võrgu täpselt kattuvate torugeomeetriate kordusimpordi;
- ei salvesta ega kuva projekti andmebaasiühenduse parooli.

Importer on teadlikult ainult lisav: olemasolevaid EVEL-i kirjeid ei muudeta
ega kustutata. Enne importi peavad sama andmebaasi QGIS-i
redigeerimispuhvrid olema salvestatud või tühistatud.

Tööriistariba eraldi **Tühjenda** tööriist on mõeldud kontrollitud
testandmebaasi puhastamiseks. See:

- kuvab enne toimingut kõigi üheksa impordi sihttabeli kirjete arvud;
- leiab ja kuvab sihttabelite sõlmedest sõltuvad sama `evel` skeemi
  detailtabelid ning kaasab need kontrollitud puhastusse;
- kontrollib skeemiväliseid võõrvõtme seoseid ega kasuta vaikivat `CASCADE`
  kustutamist;
- nõuab kõigepealt tagasipööratavat SQL-kontrolli;
- nõuab tegelikul kustutamisel kinnitusteksti `TÜHJENDA` ja teist kinnitust;
- kustutab sõltuvad detailid, torud ja baassõlmed võõrvõtmetest arvutatud
  järjekorras ühe tehinguna;
- ei kustuta `SN_CONSTANT` klassifikaatoreid ega nulli serveri IDENTITY
  jadasid.

Kui ühe sama detailtabeli mitu sama `NODE_ID` kirjet on kõigi sisuliste
atribuutide poolest täpsed duplikaadid, jätab importer mälupildis alles
väiksema ID-ga kirje ja kuvab väljajäetud detailide ID-d hoiatusena.
Kontrollpaketi faili ennast ei muudeta. Kui sama sõlme detailide atribuudid
erinevad, blokeeritakse SQL-import endiselt, sest selline vastuolu vajab
sisulist otsust või eraldi baassõlmede loomist.

GeoPackage'i üheosalised `MultiLineString` ja `MultiPoint` geomeetriad
teisendatakse importimise mälupildis vastavalt `LineString` ja `Point`
geomeetriaks, sest EVEL-i sihttabelid kasutavad üheosalisi geomeetriatüüpe.
Ka siin jääb lähtefail muutmata. Kahe või enama eraldiseisva osaga geomeetria
blokeeritakse, sest selle automaatne liitmine ei oleks üheselt määratud.

**Lisa toru** aktiveerub, kui projektis leidub vähemalt üks eduka
käivitusdiagnostikaga toetatud torukiht. Iga menüüvalik kontrollitakse eraldi
ning mittesobiv kiht jääb koos põhjusega keelatuks. Mitme võimaliku sõlme või
poolitatava toru korral salvestamine peatatakse ja tööriist ei tee vaikivat
valikut. Veetoru poolitamiskohas luuakse praegu ainult `sn_water_node`
baassõlm; võimaliku `sn_water_branch` detailkirje automaatne klassifitseerimine
ootab sisulist otsust. **Kontrolli** ja **Paranda** on seni teadlikult
keelatud.

Koordinaadisisestus toetab kihi CRS-i, projekti CRS-i ja WGS84 koordinaate.
Sisend teisendatakse enne salvestamist valitud torukihi CRS-i. X ja Y võib
sisestada punkti või komaga kümnendmurruna; lõikelaualt asetamisel sobivad
tabulaatori, tühiku või semikooloniga eraldatud koordinaadipaarid. Veetoru
otspunktide topoloogiakontroll kasutab koordinaadisisestusel fikseeritud täpsust
ega sõltu kaardi hetke suurendusastmest.

Visuaalne konfiguraator käsitleb keskset liitmikku ja iga haru sulgeseadet
eraldi võrguobjektina. See vastab mudelile, kus ühel baassõlmel saab olla üks
`sn_water_branch` ja üks `sn_water_valve` detailkirje ning detailtabelites pole
haru või pordi tunnust. Olemasoleva naabersõlme sulgeseadme tüüpi ja kaugust
saab muuta;
sulgeseadme eemaldamine koos kahe toruosa taasliitmisega lisatakse hiljem.

Kui plugin käivitas torukihtide redigeerimise ise, kinnitab **Loo toru** või
**Salvesta muudatused** või **Salvesta hüdrant** kogu toru-sõlme tehingu
andmebaasi ja lõpetab seotud
kihtide redigeerimisrežiimi. Dialoogist loobumine pöörab operatsiooni tagasi
ning lõpetab plugina avatud redigeerimisseansi. Kui kiht oli enne tööriista
käivitamist juba kasutaja poolt redigeerimisel, ei kinnita plugin varasemaid
muudatusi vaikides: uus muudatus jäetakse samasse puhvrisse ja kasutajat
teavitatakse.

Isevoolsete kihtide ja sõlmegeneraatori täpne projektileping on kirjeldatud failis
[docs/GENEREERITUD_KANALISATSIOONI_KIHID.md](docs/GENEREERITUD_KANALISATSIOONI_KIHID.md).

## Testimine

Teste käitatakse QGIS-i Pythoniga pluginate kausta vanemkataloogist. Päris
projekti integratsioonitest kasutab keskkonnamuutujat `EVEL_TEST_PROJECT`.
Importeri reaalandmete testid kasutavad muutujaid `EVEL_IMPORT_TEST_PROJECT` ja
`EVEL_IMPORT_TEST_PACKAGE`. Andmebaasi ühenduvust vajavad testid käivitatakse
ainult siis, kui lisaks on `EVEL_RUN_DB_TESTS=1`. Puuduvate failide või lubadeta
jäetakse vastavad testid vahele.

PowerShelli näide:

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
$env:EVEL_TEST_PROJECT = 'C:\tee\genereeritud-projekt.qgz'
$env:EVEL_IMPORT_TEST_PROJECT = 'C:\tee\importeri-testprojekt.qgz'
$env:EVEL_IMPORT_TEST_PACKAGE = 'C:\tee\kontrollpakett.gpkg'
& 'C:\Program Files\QGIS 3.40.13\bin\python-qgis-ltr.bat' `
  -m unittest discover -s EVEL_network_tools/tests -t . -v
```

Release-pakenduse kiire kontroll ei vaja QGIS-i:

```powershell
python -m unittest tests.test_release_packaging -v
python tools\build_release.py --version 0.12.2 `
  --output release_stage\EVEL_network_tools
```

Väljalaske tegemise täpne protsess on kirjeldatud failis [RELEASE.md](RELEASE.md).

## Kolmandate osapoolte ressursid

Plugina visioonikontseptsiooni üldise kasutajaliidese ikoonid pärinevad
[Icons8](https://icons8.com/) Windows 11 Color ja Windows 11 Outline seeriatest.
Allikate loend ja kasutusteave paiknevad failides
`resources/icons/actions/SOURCES.icons8.txt` ning
`resources/icons/actions/LICENSE.icons8.txt`. Need kontseptsiooniikoonid tuleb
enne avalikku tootepaketti asendada tellitud originaalsete ikoonidega. Neid ei
kasutata kaardikihtide sümboloogias ega kihipõhiste ikoonide asendamiseks.

## Ikoonide haldus

Kasutajaliidese ikoonid asuvad kataloogis `resources/icons/actions`. Keskne
semantiline mapping ja kõik `ICON_*` konstandid asuvad failis
`ui/icon_catalog.py`. Näiteks kõigi salvestamisnuppude ikooni vahetamiseks
piisab faili `save.png` asendamisest. Kui tegevus peab kasutama teist faili,
muuda `ICON_FILES` mapping'ut. Uue tegevuse lisamisel lisa PNG- või SVG-fail,
uus `ICON_*` konstant ja selle kirje samasse mapping'usse. Nii saab hiljem
tellitud ikoonikomplektile üle minna ainult faile ja mapping'ut vahetades.
