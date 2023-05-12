# PyCharm Ultimate version asetusten valmistelu

Käy asettamassa PyCharmiin Django-asetukset. Ne löydät asetukset-valikosta polusta _Languages & Frameworkds > Django_. Aseta seuraavasti:

| Asetus                          | Selite                                                              |
|---------------------------------|---------------------------------------------------------------------|
| _Enable Django Support_         | ☑ (valittu)                                                         |
| _Django project root_           | Tähän polku projektin juuri-kansioon (_bobweb2_-kansio)             |
| _Settings_                      | Tähän polku settings.py moduuliin, eli `bobweb\web\web\settings.py` |
| _Do not use Django test runner_ | ☐ (tyhjä)                                                           |
| _Manage script_                 | Polku manage.py moduuliin, eli `bobweb\web\manage.py`               |

Näiden asettamisen jälkeen samassa ikkunassa olevasta napista _Show Structure_ pitäisi aueta pieni ali-ikkuna, jossa näkyy mm. kohdan _applications_ alla kohta _bobweb.web.bobapp_. 

Nämä asetukset mahdollistavat monen toimenpiteen ajamisen ilman komentoriviä suoraan PyCharmin käyttöliittymän kautta. Esim testi-moduulissa yksittäisen testitapauksen voi ajaa marginaalissa sen otsikon vieressä olevasta nuolesta niin, että PyCharm osaa käyttää Djangon testien ajajaa.
