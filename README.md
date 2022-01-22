[![Quality Gate Status](https://sonarcloud.io/api/project_badges/measure?project=M4R774_bobweb2&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=M4R774_bobweb2)
[![Lines of Code](https://sonarcloud.io/api/project_badges/measure?project=M4R774_bobweb2&metric=ncloc)](https://sonarcloud.io/summary/new_code?id=M4R774_bobweb2)
[![Coverage](https://sonarcloud.io/api/project_badges/measure?project=M4R774_bobweb2&metric=coverage)](https://sonarcloud.io/summary/new_code?id=M4R774_bobweb2)
[![Technical Debt](https://sonarcloud.io/api/project_badges/measure?project=M4R774_bobweb2&metric=sqale_index)](https://sonarcloud.io/summary/new_code?id=M4R774_bobweb2)

[![Security Rating](https://sonarcloud.io/api/project_badges/measure?project=M4R774_bobweb2&metric=security_rating)](https://sonarcloud.io/summary/new_code?id=M4R774_bobweb2)
[![Reliability Rating](https://sonarcloud.io/api/project_badges/measure?project=M4R774_bobweb2&metric=reliability_rating)](https://sonarcloud.io/summary/new_code?id=M4R774_bobweb2)
[![Maintainability Rating](https://sonarcloud.io/api/project_badges/measure?project=M4R774_bobweb2&metric=sqale_rating)](https://sonarcloud.io/summary/new_code?id=M4R774_bobweb2)

# bobweb2

Bobweb on kaveriporukan oma chättibotti. 

Joka päivä henkilö joka sanoo ekana 1337 klo 1337 saa pisteen.

Tässä on nähty paljon vaivaa ja tehty tosi hieno CI/CD putki. 

Bottia ajetaan Raspberry Pi 2B:llä. 

Projekti on jaettu kahteen osioon: Bob ja Web. Bob on Telegram botin toteutus, Web on djangolla toteutettu webbisivu. 

"Only way to go fast is to go well" - Uncle Bob

## Miten ajetaan

### Vaatimukset: 
- Docker
- Docker Compose

### Vaiheet:

1. Luo settings.json tiedosto projektin juureen. Esimerkki validista asetustiedostosta: 
```
{
    "bot_token": "bottisi_token_tähän_sisään.Saat_sen_bot_fatherilta",
    "DJANGO_SECRET_KEY": "tähän_vaan_jotain_salaista_mössöä"
}
```
2. Luo db.sqlite3 tietokanta
```shell
cd web
python3 manage.py migrate
```

3. Mikäli Docker ja Docker Compose on asennettuna ja käynnissä, ja aiemmat vaiheet on suoritettu,
ajamalla deploy skripti botin pitäisi lähteä käyntiin. 

#### Linux
```sh
./deploy.sh
```
#### Windows
```batch
./deploy.bat
```