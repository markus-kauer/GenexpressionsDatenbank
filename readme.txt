
Package requirements:
    python 3.8.2
    https://marketplace.visualstudio.com/items?itemName=mtxr.sqltools
    https://marketplace.visualstudio.com/items?itemName=mtxr.sqltools-driver-mysql

    pip install GEOparse
    pip install mysql-connector-python      // um die Datenbank mit Python zu verbinden
    pip install -U python-dotenv             // um die .env Datei zu lesen
    pip install Flask
    pip install aiohttp aiomysql GEOparse
    pip install aiomysql
    pip install --upgrade pip
    pip install hypercorn
    pip install matplotlib
    pip install SPARQLWrapper
    pip install sparqlwrapper quart
    pip install quart-auth
    pip install PyJWT
    pip install pytest pytest-asyncio
    pip install scikit-learn


    Database Mysql:
    https://dev.mysql.com/downloads/file/?id=526927
    MySQL 8.4 Command Line Client --> Create Database genexpressionsdatenbank

scrape_data unter Windows mit gitbash:

    wget.exe (download) --> system32  + Umgebungsvariablen (PATH) 

    Befehl:
    ./scrape_data.sh -c GSE15960 -d /c/Users/Kmark/OneDrive/Desktop/Bachelorarbeit

    https://docs.python.org/3/library/subprocess.html

Dokumentation:

    https://git.rz.uni-augsburg.de/misit-bachelor/geneexpressiondb/-/wikis/Code-Examples

    https://git.rz.uni-augsburg.de/misit-bachelor/geneexpressiondb/-/wikis/Definitions

    https://git.rz.uni-augsburg.de/misit-bachelor/geneexpressiondb/-/wikis/SQL-Tables

Datei:
    GEODataloader.py    // Klasse zum Laden der Daten
    web_app.py         // Flask Web App
    scrape_data.sh      // Bash Script zum herunterladen und entpacken der Daten von GEO im .soft Format
    .env                // Umgebungsvariablen
    db_operations.py    // Klasse zum Verbinden und Schreiben in die Datenbank



Ausführung:
hypercorn -c hypercorn_config.py web_app:app