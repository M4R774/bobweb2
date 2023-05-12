[![Quality gate](https://github.com/M4R774/bobweb2/actions/workflows/quality_gate.yml/badge.svg)](https://github.com/M4R774/bobweb2/actions/workflows/quality_gate.yml)
[![Lines of Code](https://sonarcloud.io/api/project_badges/measure?project=M4R774_bobweb2&metric=ncloc)](https://sonarcloud.io/summary/new_code?id=M4R774_bobweb2)
[![Coverage](https://sonarcloud.io/api/project_badges/measure?project=M4R774_bobweb2&metric=coverage)](https://sonarcloud.io/summary/new_code?id=M4R774_bobweb2)
[![Technical Debt](https://sonarcloud.io/api/project_badges/measure?project=M4R774_bobweb2&metric=sqale_index)](https://sonarcloud.io/summary/new_code?id=M4R774_bobweb2)

[![Security Rating](https://sonarcloud.io/api/project_badges/measure?project=M4R774_bobweb2&metric=security_rating)](https://sonarcloud.io/summary/new_code?id=M4R774_bobweb2)
[![Reliability Rating](https://sonarcloud.io/api/project_badges/measure?project=M4R774_bobweb2&metric=reliability_rating)](https://sonarcloud.io/summary/new_code?id=M4R774_bobweb2)
[![Maintainability Rating](https://sonarcloud.io/api/project_badges/measure?project=M4R774_bobweb2&metric=sqale_rating)](https://sonarcloud.io/summary/new_code?id=M4R774_bobweb2)

# bobweb2

Bobweb on erään kaveriporukan oma chättibotti. 

Joka päivä henkilö joka sanoo ekana 1337 klo 1337 saa pisteen. Lisäksi, kerran
viikossa on mahdollista ansaita ylennys mergeämällä muutos tämän repon main
haaraan. 

Tässä on nähty paljon vaivaa ja tehty tosi hieno CI/CD putki. 

Bottia ajetaan Raspberry Pi 2B:llä. 

Projekti on jaettu kahteen osioon: Bob ja Web. Bob on Telegram botin toteutus,
Web on djangolla toteutettu webbisivu. 

"Only way to go fast is to go well" - Uncle Bob

## Ominaisuudet

Telegram botti sisältää pitkän listan erilaisia kivoja ominaisuuksia. Suurin
osa näistä ominaisuuksista on nähtävissä `/help` komennolla (WIP)
Tällä hetkellä ainakin nämä ominaisuudet löytyvät: 
- `/sähkö` - näyttää kuluvan päivän pörssisähkön hintatilastot
- `/ruoka` - Palauttaa satunnaisen ruokareseptin
- `/space` - Palauttaa tiedon seuraavasta avaruusraketin
laukaisusta
- `/sää [kaupunki]` - Palauttaa syötteenä annetun kaupungin
sään
- `/käyttäjät` - Antaa listan keskustelun käyttäjistä, heidän
arvostaan ja kunniasta 1337-pelissä sekä lähetettyjen viestien määrän tietyn
hetken jälkeen
- `/aika` - Antaa tämän hetken kellonajan sekunnin sadasosan
tarkkuudella
- `1337` - Antaa pelaajalle pisteen tai "ylennyksen", jos kello on 13:37 ja
kukaan muu ei ole ehtinyt sanoa 1337
- `/asetukset` voit säätää botin komentoja ja toimintoja päälle tai pois. Kuulutuksilla tarkoitetaan toimintoa, missä Bob mm.
kuuluttaa uusimman gitin commit viestin käynnistyessään. 
- `/ruoka`
- `jotain tekstiä .vai jotain tekstiä .vai jotain tekstiä` - Arpoo
satunnaisesti 2 - n vaihtoehdon välillä, kun ne on eroteltu avainsanalla 
**".vai"**
- `/kunta` generoi satunnaisen kunnan
- `/kysymys` - Päivän kysymykseen liittyvien toimintojen hallinta
- `/epicgames` - hakee tiedon kysymyshetkellä epic games storessa ilmaiseksi jaossa olevista peleistä.
- `/huoneilma` - Näyttää sisälämpötilan ja ilmankosteuden "serverihuoneessa"
- `/gpt [prompt]` generoi vastauksen annettuun kysymykseen. Generointi vie n. 30-60 sekuntia.
- `/dallemini [prompt]` generoi kuvan annetulla promptilla ja lähettää sen vastauksena. Käyttää Dallemini-mallia generointiin.
- `/dalle [prompt]` generoi kuvan annetulla promptilla ja lähettää sen vastauksena. Käyttää Dall-e 2 mallia generointiin.
- `/tekstitä` tekstittää komennon kohteena olevan viestin sisältämän median puheen tekstiksi. Esimerkiksi ääniviestiin vastatessa tällä komennolla botti tekstittää kyseisen ääniviestin sisällön

Muita ominaisuuksia:
- Botti ylläpitää "päivän kysymys" -peliä. Pelissä yksi käyttäjä esittää päivän aikana kysymyksen, johon muut ryhmäläiset vastaavat. Voittaja ilmoitetaan vapaamuotoisesti, jolloin voittanut käyttäjä voi esittää seuraavana päivänä seuraavan päivän kysymyksen. Botti pitää kirjaa näistä kysymyksistä, vastauksista ja voitoista, jos chattiin on luotu päivän kysymyksen kausi. Pelin pääsee aloittamaan päivän kysymyksen valikon kautta komennolla '/kysymys'
- Joka torstai klo 18.05 botti hakee tiedon Epic Games Storen ilmaiseksi jaossa olevista peleistä ja ilmoittaa niistä kaikkiin ryhmiin, joissa omainaisuus on kytketty päälle.

## Paikallinen kehitysympäristö

"Mummo-ohjeet", miten Bobista saa kopion käyntiin omalle koneelle tai miten 
esimerkiksi yksikkötestit ajetaan. 

### Esivaatimukset:
Sovellusta voi ajaa joko paikallisesti asennetuilla ohjelmilla tai Docker-kontissa. Suositeltu kehitysympäristö on PyCharm, josta löytyy myös ilmainen community edition.

Asennettujen sovellusten vaatimukset
- **Git**
- **Paikallinen ajo:**
  - **Python (vähintään 3.10)**
  - **Pip3**
  - **ffmpeg** (ei pakollinen)
    - Ääni- ja videomedian manipulointiin käytetty sovellus, jonka avulla osa komennoista käsittelee ääni- ja videomediaa. Tarvitaan vain '/tekstitä'-komennon käyttämiseen
- **Kontissa ajo:**
  - **Docker**
  - **Docker Compose**
- **Muita ei paikollisia**
  - **PyCharm** Community Edition (ilmainen) tai Ultimate

### Botin ajaminen paikallisesti:

1. Asenna **Git, Docker, Docker Compose, Python 3.10 tai uudempi, Pip3, PyCharm
ja venv.** 
2. Aseta julkinen SSH-avain Githubin asetuksista kloonaamista varten
3. Kloonaa repository omalle koneellesi

```sh
git clone git@github.com:M4R774/bobweb2.git
```

4. Jos et käytä PyCharmia, joudut myös asentamaan riippuvuudet manuaalisesti ja
luomaan virtuaaliympäristön eli venvin. Jos käytät PyCharmia, nämä hoituvat
parilla klikkauksella.

```sh
# Asenna käytetyt kirjastot
cd bobweb2
pip install -r requirements.txt
```

5. Luo https://t.me/botfather avulla uusi botti ja kopioi botin token
6. Lisää tarvittavat ympäristömuuttujat, kuten bot token, OPEN_WEATHER_API_KEY ja OPENAI_API_KEY
(joudut katsomaan koodista mitä muuttujia tarvitaan tai lukemaan error viestit
kun botti ei lähde käyntiin tai kun kaikki omaisuudet ei toimi).
7. Luo db.sqlite3 tietokanta

```sh
python bobweb/web/manage.py migrate
```

Projekti on nyt valmis ajettavaksi.

4. Mikäli Docker ja Docker Compose on asennettuna ja käynnissä, ja aiemmat
vaiheet on suoritettu, ajamalla deploy skripti botin pitäisi lähteä käyntiin.

```sh
./dev-deploy.sh
```
Tai Windows-koneella komentoriviltä
```
.\dev-deploy.bat
```

### Yksikkötestien ajaminen

Jos haluat ajaa botin testejä paikallisesti komentoriviltä, onnistuu se alla
olevilla komennoilla. Jos käytössäsi on PyCharm Ultimate, voit ajaa testejä myös suoraan PyCharmin
käyttöliittymästä valitsemalla ajokonfiguraatioksi jonkin testiajon tai klikkaamalla editorin marginaalissa testiluokan/-metodin vieressä olevaa nuolta. Community Editionilla testejä ajettaessa on käytössä Pythonin oletus testiajaja, jolloin paikalliseen tietokantaan jää testiajoista testeissä luotua dataa.

```sh
# Botin testit
python bobweb/web/manage.py test bobweb/bob

# Webbisivun testit
python bobweb/web/manage.py test bobweb/web
```

### Muutoksia tietokantaan

Tietokanta on Djangon hallinnoima. Näin ollen tietokannan ylläpitoon pätee
Djangon perus workflow, joka on dokumentoitu täällä tarkemmin:
https://docs.djangoproject.com/en/4.0/topics/migrations

Aina kun tietomalliin tulee muutoksia, eli esim. tietokantaan tulee lisää
sarakkeita, sarakkeita poistuu tai sarakkeen nimi muuttuu, tulee tietokanta
"migroida". Alta löytyy komentorivikomennot tämän toimenpiteen tekemiseksi.

```sh
# Luo migraatiotiedostot
python bobweb/web/manage.py makemigrations

# Lisää migraatiotiedostot versionhallintaan
git add .

# Migroi paikallinen tietokanta
python bobweb/web/manage.py migrate
```
Jos huomaat puutteita migraatiossa tai teet lisää muutoksia tietomalliin, on
mielekästä *lopuksi* tiivistää kaikki samaan kokonaisuuteen liittyvät muutokset
yhteen migraatioon, ettei jokaiselle pienelle muutokselle tule turhaan omaa
migraatiotansa. Migraatioiden tiivistäminen onnistuu poistamalla kaikkia
kehityshaarassa lisätyt migraatiotiedostot migraatio-kansiosta ja ajamalla
komento
``` sh
# Migratoi paikallisen kannan taaksepäin aiempaan versioon
python bobweb/web/manage.py migrate bobapp XXXX
# missä XXXX on viimeisin migraatio ennen nykyisiä muutoksia.
# Tämän jälkeen kun ajaa jälleen
python bobweb/web/manage.py makemigrations
python bobweb/web/manage.py migrate
# Niin luodaan 1 migraatio kaikille muutoksille ja tietokanta migratoidaan jälleen siihen versioon.
# HUOM! Migraatioissa kulkeminen taaksepäin voi aiheuttaa tiedon menetystä paikallisessa tietokannassa.
# Esim jos olet luonut uuden taulun ja lisännyt sinne jo tietoa, lisäämis-migraation poistaminen
# ja uudelleenluominen aiheuttaa kyseisen taulun sisällön katoamisen
```

### Muutoksia riippuvuuksiin

Jos teit muutoksia esimerkiksi Dockerfile-tiedostoon, voit vielä varmistaa
muutostesi toimivuuden paikallisesti alla olevalla komennolla. Tietokoneesi
arkkitehtuuri (x86_64) poikkeaa Raspberry Pi:n arkkitehtuurista (armv7l)
mikä vaikuttaa riippuvuuksien asentamiseen.

```sh
docker build --platform linux/armhf . -t bob-armhf --progress=plain --no-cache
```

### Uuden komennon luominen

Luo uusi moduuli ja sinne luokka joka perii ChatCommand luokan. Esim moduuli (tiedosto) `uusi_komento_command.py` ja siellä luokka:
```python
class UusiKomento(ChatCommand):
    def __init__(self):
        super().__init__(
            name='uusiKomento',
            regex=regex_simple_command('uusiKomento'),
            help_text_short=('uusiKomento', 'tähän pari sanaa enemmän')
        )

    def handle_update(self, update: Update, context: CallbackContext = None):
        update.message.reply_text('Hei, tämä on uusi komento')

    def is_enabled_in(self, chat):
        return True  # Tähän ehto, että komento on käytössä kyseisessä chatissä.
```

Tämän jälkeen lisää komento moduulin `command_service.py` metodiin `create_all_but_help_command()`. Tämän jälkeen komento on käytettävissä normaalisti.