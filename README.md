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

> "Only way to go fast is to go well" - Uncle Bob

## Ominaisuudet

Telegram botti sisältää pitkän listan erilaisia kivoja ominaisuuksia. Suurin osa näistä ominaisuuksista on nähtävissä /help komennolla (WIP)
Tällä hetkellä ainakin nämä ominaisuudet löytyvät: 
- `/space` tai '.space' - palauttaa tiedon seuraavasta SpaceX:n raketin laukaisusta
- `/sää` Helsinki tai '.sää Helsinki' - Palauttaa syötteenä annetun kaupungin sään
- `/käyttäjät` tai `.käyttäjät` - Antaa listan keskustelun käyttäjistä, heidän arvostaan ja kunniasta 1337-pelissä sekä lähetettyjen viestien määrän tietyn hetken jälkeen
- '/aika' tai '.aika' - Antaa tämän hetken kellonajan sekunnin sadasosan tarkkuudella
- `1337` - Kavattaa pelaajan arvoa tai kunniaa, jos kello on 13:37 ja kukaan muu ei ole ehtinyt sanoa 1337
- `/kuulutus on` tai `.kuulutus on` - kytkee "kuulutukset" päälle. Bob esimerkiksi kuuluttaa aina uusimmat gitin commit viestit käynnistyessään.
- `/kuulutus off` tai `.kuulutus off` - kytkee "kuulutukset" pois päältä.

## 1337-peli

Pelaajilla on päivittäin mahdollisuus voittaa piste kommentoimalla "1337" kellon ollessa 13:37 (UTC+2). Ensimmäinen oikeaan aikaan kommentoinut palkitaan pisteellä ja muut kommentoijat menettävät pisteen. Samoin pisteen menettää jos kommentoidessaan "1337" kello ei ole 13:37 (UTC+2).

Kerran viikossa pelaajilla on mahdollisuus ansaita piste yhdistämällä muutos tämän repositorion main-haaraan.

Pisteet nostattavat pelaajan **arvoa**. Pelaajalla voi olla minimissään 0 pistettä ja enimmmillään 37 pistettä. Enimmäispistemäärän täyttyessä pelaajan **kunnia** nousee yhden pykälän ja pisteidenlasku aloitetaan alusta. **Kunnialla** ei ole ylärajaa.

### WIP

Pisteet toimivat chatin sisäisenä valuuttana joita pelaajat voivat käyttää uhkapelaamiseen.

## Miten ajetaan

### Vaatimukset:

- Docker
- Docker Compose

### Vaiheet:

1. Luo settings.json tiedosto projektin juureen. Esimerkki validista asetustiedostosta: 
```sh
{
    "bot_token": "bottisi_token_tähän_sisään.Saat_sen_bot_fatherilta",
    "DJANGO_SECRET_KEY": "tähän_vaan_jotain_salaista_mössöä"
}
```
2. Luo db.sqlite3 tietokanta
```sh
cd web
python3 manage.py migrate
```

3. Mikäli Docker ja Docker Compose on asennettuna ja käynnissä, ja aiemmat vaiheet on suoritettu,
ajamalla deploy skripti botin pitäisi lähteä käyntiin. 

#### Linux

```sh
./deploy.sh
```

##### Paikallinen kehitysympäristö

Jos haluat ajaa bottia suoraan omalla koneella tai esimerkiksi ajaa yksikkötestejä:

```sh
# For local development:
# install python3.10
# install pip:
curl -sS https://bootstrap.pypa.io/get-pip.py | python3.10
alias pip='/home/<user>/.local/bin/pip3.10'
pip install -r requirements.txt

# Testit
cd bob
python -m unittest

cd ../web
python manage.py test
```
