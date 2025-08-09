import os
import shutil
import aiomysql
import time
from services.geo_data_handler import GEODataHandler

class GSEScanner:
    def __init__(self, db_manager):
        self.db_manager = db_manager

    async def ensure_connected(self):
        await self.db_manager.ensure_connected()

    async def scan_gse(self, gse_id=None):
        file_path = None
        locally_available = False
        if not gse_id:
            print("Missing required parameters.")
            return None

        try:
            await self.db_manager.ensure_connected()
            conn = await self.db_manager.get_read_connection()
            cursor = await conn.cursor()
            try:
                await cursor.execute("SELECT file_location FROM FileLocation WHERE series_id = %s", (gse_id,))
                result = await cursor.fetchone()
                if result:
                    file_path = result[0]
                    
                    if os.path.exists(file_path):
                        locally_available = True
                        print("Locally available", file_path)
                    else:
                        print("File not found, attempting to download:", file_path)
                        locally_available = False
                        file_path = None
                else:
                    print("No file path found in database, downloading data.")
                    locally_available = False

            finally:
                await cursor.close()
                await self.db_manager.release_connection(conn)

        except aiomysql.Error as e:
            print(f"Database error: {e}")
            return None

        if not locally_available:
            return await self.download_data(gse_id)
        else:
            if file_path.endswith(".soft.gz"):
                try:
                    return file_path
                except Exception as e:
                    print(f"Failed to load GSE data from file: {e}")
                    return None
            else:
                print("The file must be a .soft file.")
                return None

    async def download_data(self, gse_id):
        '''
        GEODataHandler.download_GEO_file(gse_id, destdir=destdir)
        downloadet die Datei, falls sie noch nicht vorhanden ist.
        Falls ein Ordner bereits existiert und leer ist, wird dieser gelöscht.
        Da die Methode von GEOParse damit nicht umgehen kann.
        '''
        
        destdir = "temp"
        
        # Edgecasebehandlung: Wenn der Ordner bereits existiert und leer ist, wird dieser gelöscht.
        gse_dir = os.path.join(destdir, gse_id)
        if os.path.exists(gse_dir):
            if not os.listdir(gse_dir):
                print("Der Ordner ist leer und wird gelöscht:", gse_dir)
                shutil.rmtree(gse_dir)
                while os.path.exists(gse_dir):
                    print("Warten auf das Löschen des Ordners:", gse_dir)
                    time.sleep(0.5)
            else:
                print("Der Ordner ist nicht leer und wird nicht gelöscht.")
        
        print("Scraping data from GEO...")
                
        soft_file_path = GEODataHandler.download_GEO_file(gse_id, destdir=destdir)
        gpl_id = GEODataHandler.extract_gpl_id(soft_file_path)
        
        if soft_file_path:
            try:
                await self.db_manager.ensure_connected()
                conn = await self.db_manager.get_write_connection()
                cursor = await conn.cursor()
                try:
                    await cursor.execute("""
                        INSERT INTO FileLocation (series_id, platform_id, file_location)
                        VALUES (%s, %s, %s)
                        ON DUPLICATE KEY UPDATE file_location = VALUES(file_location)
                    """, (gse_id,gpl_id,soft_file_path, ))
                    await conn.commit()
                    print("File path added to the database.")
                except aiomysql.Error as e:
                    print(f"Database error: {e}")
                    await conn.rollback()
                finally:
                    await cursor.close()
                    await self.db_manager.release_connection(conn)
            except aiomysql.Error as e:
                print(f"Database error: {e}")
                return None
        return soft_file_path


