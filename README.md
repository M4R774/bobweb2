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

## CI/CD

Projektissa on käytössä GitHub Actions ja Sonar Cloud quality gate. Pull requestin ja jokaisen siihen kohdistuvan puskun
yhteydessä suoritetaan:

- projektin Docker-imagen buildaus ja tarkistus, että se lähtee käyntiin odotetusti
- kaikkien testien ajaminen
- Sonar Cloud laatuanalyysi

Kun main-haaraan pusketaan muutoksia tapahtuu sekä koko projektin Sonar laatuanalyysi, että automaattinen muutosten
deployaaminen tuotantoon. Deployaamisessa buildataan projektista valmiit docker imaget alustoille [amd64, armv7] ja
näistä pusketaan imaget [DockerHubiin](https://hub.docker.com/r/latemus/bobweb2/tags). Tuotantoympäristö tarkistaa
uusimman version viiden minuutin välein ja uudelleenkäynnistää botin uusimmalla versiolla mikäli sellainen on
saatavilla.

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
- `/asetukset` voit säätää botin komentoja ja toimintoja päälle tai pois. Kuulutuksilla tarkoitetaan toimintoa, missä
  Bob mm.
  kuuluttaa uusimman gitin commit viestin käynnistyessään.
- `/ruoka`
- `jotain tekstiä .vai jotain tekstiä .vai jotain tekstiä` - Arpoo
  satunnaisesti 2 - n vaihtoehdon välillä, kun ne on eroteltu avainsanalla '.vai'
- `/kunta` generoi satunnaisen kunnan
- `/kysymys` - Päivän kysymykseen liittyvien toimintojen hallinta
- `/twitch [kanava]` - Näyttää kanavan sen hetkisen striimin tiedot. Päivittää tietoja niin kauan kun kanavan striimi on päällä
- `/epicgames` - hakee tiedon kysymyshetkellä epic games storessa ilmaiseksi jaossa olevista peleistä.
- `/huoneilma` - Näyttää sisälämpötilan ja ilmankosteuden "serverihuoneessa"
- `/gpt [prompt]` generoi vastauksen annettuun kysymykseen. Generointi vie n. 30-60 sekuntia.
- `/dallemini [prompt]` generoi kuvan annetulla promptilla ja lähettää sen vastauksena. Käyttää Dallemini-mallia
  generointiin.
- `/dalle [prompt]` generoi kuvan annetulla promptilla ja lähettää sen vastauksena. Käyttää Dall-e 2 mallia
  generointiin.
- `/tekstitä` tekstittää komennon kohteena olevan viestin sisältämän median puheen tekstiksi. Esimerkiksi ääniviestiin
  vastatessa tällä komennolla botti tekstittää kyseisen ääniviestin sisällön
- `/lausu` lausuu komennon kohteena olevan viestin ääneen. Botti palauttaa ääniviestin.

Muita ominaisuuksia:

- Botti ylläpitää "päivän kysymys" -peliä. Pelissä yksi käyttäjä esittää päivän aikana kysymyksen, johon muut
  ryhmäläiset vastaavat. Voittaja ilmoitetaan vapaamuotoisesti, jolloin voittanut käyttäjä voi esittää seuraavana
  päivänä seuraavan päivän kysymyksen. Botti pitää kirjaa näistä kysymyksistä, vastauksista ja voitoista, jos chattiin
  on luotu päivän kysymyksen kausi. Pelin pääsee aloittamaan päivän kysymyksen valikon kautta komennolla '/kysymys'
- Botti hakee päivittäin tiedon uusista Epic Games Storen ilmaiseksi jaossa olevista peleistä ja ilmoittaa niistä
  kaikkiin ryhmiin, joissa omainaisuus on kytketty päälle.

## Paikallinen kehitysympäristö

"Mummo-ohjeet", miten Bobista saa kopion käyntiin omalle koneelle tai miten
esimerkiksi yksikkötestit ajetaan.

### Esivaatimukset:

Sovellusta voi ajaa joko paikallisesti asennetuilla ohjelmilla tai Docker-kontissa. Suositeltu kehitysympäristö on
**PyCharm**, josta löytyy myös ilmainen community edition.

Asennettujen sovellusten vaatimukset

- **Git**
- **Paikallinen ajo** (kts. seuraava kohta)
    - **Python (vähintään 3.10)**
    - **Pip3**
- **Kontissa ajo** (kts. seuraava kohta)
    - **Docker**
    - **Docker Compose**
- **Muita ei-paikollisia**
    - **PyCharm** Community Edition (ilmainen) tai Ultimate
        - Ultimate version suositellut asetukset alempana kohdassa `PyCharm Ultimate version suositellut asetukset`    
    - **ffmpeg**
        - Ääni- ja videomedian manipulointiin käytetty ohjelma, jonka avulla osa komennoista käsittelee ääni- ja
          videomediaa
        - Tarvitaan '/tekstita' ja '/twitch' komentojen käyttöön paikallisessa ajossa
    - **Firefox-selain**
        - Tarvitaan vain "/kunt"-komennon käyttöön paikallisessa ajossa

### Botin ajaminen omalla tietokoneella:

Botin ajamiseen paikallisesti on 2 vaihtoehtoa. Vaihtoehto 1 on käyttää paikallista ympäristöä, missä python ja botin
käyttämät riippuvuudet on asennettu levylle käyttäjän käyttöjärjestelmän tiedostohierarkiaan. Vaihtoehto 2 on käyttää
Docker-kontteja, jolloin kaikki bottiin liittyvä asennus tehdään eristetyn kontin sisällä. Molemmissa on omat hyvät ja
huonot puolensa. Lähtökohtaisesti on helpompi ajaa bottia paikallisesti, mutta Docker konttien käyttö eristää bottiin
liittyvät asiat omaan konttiinsa, jolloin muut asennetut python versiot tai kirjastot eivät aiheuta ongelmia.

Koska tietokanta luodaan Djangon migraatioilla, tarvii Docker-konttien vaihtoehdossa valmistella projekti osittain
paikallista suoritusta varten.

#### Yhteiset vaiheet
1. Asenna **Git, PyCharm, Python 3.10 tai uudempi, Pip3 ja venv**
2. Aseta julkinen SSH-avain Githubin asetuksista profiiliisi. Tätä ei tarvita projektin kloonaamiseen, vaan muutosten 
   puskemiseen. Ohjeet tähän löytyy [Githubin omasta oppaasta](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/adding-a-new-ssh-key-to-your-github-account)
3. Kloonaa repository omalle koneellesi
    - ```sh
      git clone git@github.com:M4R774/bobweb2.git
      ```
4. Jos et käytä PyCharmia, joudut myös asentamaan riippuvuudet manuaalisesti ja
   luomaan virtuaaliympäristön eli venvin. Jos käytät PyCharmia, nämä hoituvat
   parilla klikkauksella (PyCharm ehdottaa projektin lataamisen yhteydessä)
   - ```sh
     # Asenna käytetyt kirjastot
     cd bobweb2
     pip install -r requirements.txt
     ```
5. Luo https://t.me/botfather avulla uusi botti ja kopioi botin token talteen. Vaihtoehtoisesti pyydä toisen kehittäjän
   kehitysbotin tunnukset lainaan.
6. Lisää tarvittavat ympäristömuuttujat. Ympäristömuuttujia käytetään sellaisten tunnusten välittämiseen, mitä ei voida
   tallentaa versionhallintaa. Botin käyttämät ympäristömuuttujat löytyvät `bobweb/bob/config.py`. Ympäristömuuttujan
   voi lisätä myös `main.py` ajokonfiguraatioon jos ajat bottia paikallisesti. Dockeria käytettäessä tunnukset pitää
   olla lisättynä ympäristömuuttujiin
    - Pakollinen ympäristömuuttuja: `BOT_TOKEN` = Tähän asetettava jonkin BotFatherilla luodun botin tunnus. Muut
      ympäristömuuttujat ovat tarpeen vain osaan ominaisuuksia
   -  Windowsilla ympäristömuuttujan voi asettaa pysyvästi komennolla `setx {AVAIN} "{arvo}"`, missä {AVAIN} on 
      ympäristömuuttujan avain ja {arvo} on sen 
      arvo. Esim botin tokenin voi lisätä windowsin komentoriviltä `setx BOT_TOKEN 123ASD456FGH`, joss jälkimmäinen 
      merkkijono on todellinen tokeni
   - Linuxille löytyy ohjeet [tämän linkin takaa](https://pimylifeup.com/ubuntu-set-environment-variable/#setting-a-permanent-environment-variable-on-ubuntu-for-the-current-user)
7. Luo db.sqlite3 tietokanta komennolla:
    - ```sh
      python bobweb/web/manage.py migrate
      ```

#### Ajaminen paikallisesti ilman Dockeria
1. Etsi `bobweb/bob/main.py` ja sen sisältä rivi, joka sisältää `if __name__ == '__main__':`. Klikkaa sen vasemmalla 
   puolella marginaalissa olevaa nuolta (jos Pycharm) tai ajamalla komentoriviltä `python bobweb/bob/main.py` komennolla
      
#### Ajaminen Docker-kontissa
1. Asenna lisäksi **Docker** ja tee asennuksen jälkeiset toimenpiteet niin, että voi ajaa ilman sudo-oikeuksia (linux)
2. Mikäli Docker (tai Docker Desktop jos windows) on asennettuna (ja käynnissä), ja aiemmat
   vaiheet on suoritettu, voi konttiin liittyvän imagen buildauksen ja käynnistyksen aloittaa komennolla 
   `./deploy.dev.sh` (linux) tai `.\deploy.dev.bat` (windows). Ensimmäinen imagen build kestää joitakin minuutteja, jonka
   jälkeen myöhemmät buildit ovat nopeampia.

### Yksikkötestien ajaminen

Jos haluat ajaa botin testejä paikallisesti komentoriviltä, onnistuu se alla olevilla komennoilla. Jos käytössäsi on 
PyCharm Ultimate, ja olet määritellyt testiajajaksi Djangon oman testiajurin (kts. alempaa 
"PyCharm Ultimate version suositellut asetukset") voit ajaa testejä myös suoraan PyCharmin käyttöliittymästä 
valitsemalla ajokonfiguraatioksi jonkin testiajon tai klikkaamalla editorin marginaalissa testiluokan/-metodin vieressä 
olevaa nuolta. Community Editionilla testejä ajettaessa on käytössä Pythonin oletus testiajaja, jolloin paikalliseen 
tietokantaan jää testiajoista testeissä luotua dataa. Testejä voi ajaa Djangon ajurilla komentoiriviltä seuraavilla 
komennoilla ja tämä on suositeltavaa aina kun haluaa varmistaa, ettei paikallisesti tehdyt muutokset ole rikkoneet 
mitään.

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

Luo uusi moduuli ja sinne luokka joka perii ChatCommand luokan. Esim moduuli (tiedosto) `uusi_komento_command.py` ja
siellä luokka:

```python
class UusiKomento(ChatCommand):
    def __init__(self):
        super().__init__(
            name='uusiKomento',
            regex=regex_simple_command('uusiKomento'),
            help_text_short=('uusiKomento', 'tähän pari sanaa enemmän')
        )

    def is_enabled_in(self, chat):
        return True  # Tähän ehto, että komento on käytössä kyseisessä chatissä.

    async def handle_update(self, update: Update, context: CallbackContext = None):
        # tähän komennon varsinainen toteutus, eli kaikki mitä tapahtuu kun komento laukeaa
        await update.message.reply_text('Hei, tämä on uusi komento')


```

Tämän jälkeen lisää komento moduulin `command_service.py` metodiin `create_all_but_help_command()`. Tämän jälkeen
komento on käytettävissä normaalisti.

### PyCharm Ultimate version suositellut asetukset

Käy asettamassa PyCharmiin Django-asetukset. Ne löydät asetukset-valikosta polusta _Languages & Frameworkds > Django_.
Aseta seuraavasti:

| Asetus                          | Selite                                                              |
|---------------------------------|---------------------------------------------------------------------|
| _Enable Django Support_         | ☑ (valittu)                                                         |
| _Django project root_           | Tähän polku projektin juuri-kansioon (_bobweb2_-kansio)             |
| _Settings_                      | Tähän polku settings.py moduuliin, eli `bobweb\web\web\settings.py` |
| _Do not use Django test runner_ | ☐ (tyhjä)                                                           |
| _Manage script_                 | Polku manage.py moduuliin, eli `bobweb\web\manage.py`               |

Näiden asettamisen jälkeen samassa ikkunassa olevasta napista _Show Structure_ pitäisi aueta pieni ali-ikkuna, jossa
näkyy mm. kohdan _applications_ alla kohta _bobweb.web.bobapp_.

Nämä asetukset mahdollistavat monen toimenpiteen ajamisen ilman komentoriviä suoraan PyCharmin käyttöliittymän kautta.
Esim testi-moduulissa yksittäisen testitapauksen voi ajaa marginaalissa sen otsikon vieressä olevasta nuolesta niin,
että PyCharm osaa käyttää Djangon testien ajajaa.
