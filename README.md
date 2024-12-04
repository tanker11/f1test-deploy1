# Deploy teszt az eredeti (lokális docker-compose) projekthez

## Deploy Github Actions-sel, Web Application-ként

Azure Portálon:

f1test-deploy1 nevű Application Service Plan-t létrehozunk
Aztán Web Appot is létrehozunk, itt pl választunk egy olcsót (B1), Python kód alappal, adatbázis nem kell
engedélyezzük a Continuous Deploymentet, hozzákötjük a GitHub accounthoz.

A backup könyvtárból felülírjuk az ettől létrejövő github/workflow fájlt, mert az már elő van készítve a létrehozáshoz.
