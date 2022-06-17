[![Quality gate](https://github.com/M4R774/bobweb2/actions/workflows/quality_gate.yml/badge.svg)](https://github.com/M4R774/bobweb2/actions/workflows/quality_gate.yml)
[![Lines of Code](https://sonarcloud.io/api/project_badges/measure?project=M4R774_bobweb2&metric=ncloc)](https://sonarcloud.io/summary/new_code?id=M4R774_bobweb2)
[![Coverage](https://sonarcloud.io/api/project_badges/measure?project=M4R774_bobweb2&metric=coverage)](https://sonarcloud.io/summary/new_code?id=M4R774_bobweb2)
[![Technical Debt](https://sonarcloud.io/api/project_badges/measure?project=M4R774_bobweb2&metric=sqale_index)](https://sonarcloud.io/summary/new_code?id=M4R774_bobweb2)

[![Security Rating](https://sonarcloud.io/api/project_badges/measure?project=M4R774_bobweb2&metric=security_rating)](https://sonarcloud.io/summary/new_code?id=M4R774_bobweb2)
[![Reliability Rating](https://sonarcloud.io/api/project_badges/measure?project=M4R774_bobweb2&metric=reliability_rating)](https://sonarcloud.io/summary/new_code?id=M4R774_bobweb2)
[![Maintainability Rating](https://sonarcloud.io/api/project_badges/measure?project=M4R774_bobweb2&metric=sqale_rating)](https://sonarcloud.io/summary/new_code?id=M4R774_bobweb2)

# bobweb2

Bobweb on erään kaveriporukan oma chättibotti. 

Joka päivä henkilö joka sanoo ekana 1337 klo 1337 saa pisteen. Lisäksi, kerran viikossa on mahdollista ansaita ylennys mergeämällä muutos tämän repon main haaraan. 

Tässä on nähty paljon vaivaa ja tehty tosi hieno CI/CD putki. 

Bottia ajetaan Raspberry Pi 2B:llä. 

Projekti on jaettu kahteen osioon: Bob ja Web. Bob on Telegram botin toteutus, Web on djangolla toteutettu webbisivu. 

"Only way to go fast is to go well" - Uncle Bob

## Ominaisuudet

Telegram botti sisältää pitkän listan erilaisia kivoja ominaisuuksia. Suurin osa näistä ominaisuuksista on nähtävissä /help komennolla (WIP)
Tällä hetkellä ainakin nämä ominaisuudet löytyvät: 
- `/ruoka` tai '.ruoka' - Palauttaa satunnaisen ruokareseptin
- `/space` tai '.space' - Palauttaa tiedon seuraavasta SpaceX:n raketin laukaisusta
- `/sää` Helsinki tai '.sää Helsinki' - Palauttaa syötteenä annetun kaupungin sään
- `/käyttäjät` tai '.käyttäjät' - Antaa listan keskustelun käyttäjistä, heidän arvostaan ja kunniasta 1337-pelissä sekä lähetettyjen viestien määrän tietyn hetken jälkeen
- `/aika` tai '.aika' - Antaa tämän hetken kellonajan sekunnin sadasosan tarkkuudella
- `1337` - Antaa pelaajalle pisteen tai "ylennyksen", jos kello on 13:37 ja kukaan muu ei ole ehtinyt sanoa 1337
- `/kuulutus on` tai '.kuulutus on' - kytkee "kuulutukset" päälle. Bob esimerkiksi kuuluttaa aina uusimmat gitin commit viestit käynnistyessään. 
- `/ruoka`
- `jotain tekstiä .vai jotain tekstiä .vai jotain tekstiä` - Arpoo satunnaisesti 2 - n vaihtoehdon välillä, kun ne on eroteltu avainsanalla **".vai"**

## Paikallinen kehitysympäristö

"Mummo-ohjeet", miten Bobista saa kopion käyntiin omalle koneelle tai miten esimerkiksi yksikkötestit ajetaan. 

### Esivaatimukset:

Seuraavat ohjelmat tulee olla asennettuna:
- **Git**
- **Docker**
- **Docker Compose**
- **Python (vähintään 3.10)**
- **Pip3**
- (valinnainen, mutta suositeltu) **PyCharm**

### Botin ajaminen paikallisesti:

-2. Asenna **Git, Docker, Docker Compose, Python 3.10 tai uudempi, Pip3, PyCharm ja venv.** 
-1. Aseta julkinen SSH-avain Githubin asetuksista kloonaamista varten
0. Kloonaa repository omalle koneellesi

```sh
git clone git@github.com:M4R774/bobweb2.git
```

1. Jos et käytä PyCharmia, joudut myös asentamaan riippuvuudet manuaalisesti ja luomaan
virtuaaliympäristön eli venvin. Jos käytät PyCharmia, nämä hoituvat parilla klikkauksella.

```sh
# Asenna käytetyt kirjastot
cd bobweb2
pip install -r requirements.txt
```

2. Luo https://t.me/botfather avulla uusi botti ja kopioi botin token
2. Lisää tarvittavat ympäristömuuttujat, kuten bot token (joudut katsomaan koodista mitä muuttujia tarvitaan tai lukemaan error viestit kun botti ei lähde käyntiin tai kun kaikki omaisuudet ei toimi).
3. Luo db.sqlite3 tietokanta

```sh
cd web
python3 manage.py migrate
```

Projekti on nyt valmis ajettavaksi. 

4. Mikäli Docker ja Docker Compose on asennettuna ja käynnissä, ja aiemmat vaiheet on suoritettu,
ajamalla deploy skripti botin pitäisi lähteä käyntiin. 

```sh
./deploy.sh
```

### Yksikkötestien ajaminen

Jos haluat ajaa bottia suoraan omalla koneella ja ajaa yksikkötestejä:

```sh
# Botin testit
cd bob
python -m unittest

# Webbisivun testit
cd ../web
python manage.py test
```

### Muutoksia tietokantaan

Tietokanta on Djangon hallinnoima. Näin ollen tietokannan ylläpitoon pätee Djangon perus workflow, joka on dokumentoitu täällä tarkemmin: https://docs.djangoproject.com/en/4.0/topics/migrations 

Aina kun tietomalliin tulee muutoksia, eli esim. tietokantaan tulee lisää sarakkeita, sarakkeita poistuu tai sarakkeen nimi muuttuu, tulee tietokanta "migroida". 

```
# Muutoksia tietokantaan
cd ../web

# Luo migraatiotiedostot
python manage.py makemigrations

# Lisää migraatiotiedostot versionhallintaan
git add .

# Migroi paikallinen tietokanta
python manage.py migrate
```
