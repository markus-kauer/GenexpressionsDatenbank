import aiomysql
import os
from dotenv import load_dotenv

import warnings
# Suppress MySQL warnings (like "Table already exists")
warnings.filterwarnings("ignore", category=aiomysql.Warning)

class DatabaseConnectionManager:
    read_pool = None
    write_pool = None
    active_connections = 0

    @staticmethod
    async def init_pools():
        if DatabaseConnectionManager.read_pool is None:
            load_dotenv()
            DatabaseConnectionManager.read_pool = await aiomysql.create_pool(
                host=os.getenv('DB_HOST'),
                user=os.getenv('DB_USER'),
                password=os.getenv('DB_PASSWORD'),
                db=os.getenv('DB_DATABASE'),
                ssl=None,
                autocommit=True
            )

        if DatabaseConnectionManager.write_pool is None:
            load_dotenv()
            DatabaseConnectionManager.write_pool = await aiomysql.create_pool(
                host=os.getenv('DB_HOST'),
                user=os.getenv('DB_USER'),
                password=os.getenv('DB_PASSWORD'),
                db=os.getenv('DB_DATABASE'),
                ssl=None,
                autocommit=False  
            )

    @staticmethod
    async def get_read_connection():
        if DatabaseConnectionManager.read_pool is None:
            await DatabaseConnectionManager.init_pools()
        conn = await DatabaseConnectionManager.read_pool.acquire()
        await conn.query("SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED")
        DatabaseConnectionManager.active_connections += 1
        return conn

    @staticmethod
    async def get_write_connection():
        if DatabaseConnectionManager.write_pool is None:
            await DatabaseConnectionManager.init_pools()
        conn = await DatabaseConnectionManager.write_pool.acquire()
        await conn.query("SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED")
        DatabaseConnectionManager.active_connections += 1
        return conn

    @staticmethod
    async def release_connection(conn):
        if DatabaseConnectionManager.read_pool and conn in DatabaseConnectionManager.read_pool._used:
            DatabaseConnectionManager.read_pool.release(conn)
        elif DatabaseConnectionManager.write_pool and conn in DatabaseConnectionManager.write_pool._used:
            DatabaseConnectionManager.write_pool.release(conn)
        DatabaseConnectionManager.active_connections -= 1

    @staticmethod
    async def close_pools():
        if DatabaseConnectionManager.read_pool:
            DatabaseConnectionManager.read_pool.close()
            await DatabaseConnectionManager.read_pool.wait_closed()

        if DatabaseConnectionManager.write_pool:
            DatabaseConnectionManager.write_pool.close()
            await DatabaseConnectionManager.write_pool.wait_closed()

    @staticmethod
    async def ensure_connected():
        if DatabaseConnectionManager.read_pool is None or DatabaseConnectionManager.write_pool is None:
            await DatabaseConnectionManager.init_pools()

    @staticmethod
    async def create_tables():
        conn = await DatabaseConnectionManager.get_write_connection()
        cursor = await conn.cursor()
        try:
            # Create tissue_types Table
            await cursor.execute("""
                CREATE TABLE IF NOT EXISTS tissue_types (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    name VARCHAR(255) NOT NULL UNIQUE
                )
            """)

            # Create Platform Table
            await cursor.execute("""
                CREATE TABLE IF NOT EXISTS Platform (
                    id VARCHAR(255),
                    title TEXT,
                    geo_accession TEXT,
                    platform_organism TEXT,
                    platform_taxid TEXT,
                    platform_manufacturer TEXT,
                    platform_description TEXT,
                    platform_contact_email VARCHAR(255),
                    PRIMARY KEY (ID)
                )
            """)

            # Create GeneAnnotations Table
            await cursor.execute("""
                CREATE TABLE IF NOT EXISTS GeneAnnotations (
                    id VARCHAR(255),
                    platform_id VARCHAR(255),
                    gene_title TEXT,
                    gene_symbol TEXT,
                    entrez_gene_id TEXT,
                    refseq_transcript_id TEXT,
                    PRIMARY KEY (id, platform_id),
                    FOREIGN KEY (platform_id) REFERENCES Platform(id)
                )
            """)

            # Create Series Table
            await cursor.execute("""
                CREATE TABLE IF NOT EXISTS Series (
                    id VARCHAR(255),
                    platform_id VARCHAR(255),
                    title TEXT,
                    summary TEXT,
                    pubmed_id VARCHAR(255),
                    type TEXT,
                    bto_id TEXT NULL,
                    tissue_type TEXT NULL,
                    series_contact_email VARCHAR(255),
                    is_finished BOOLEAN DEFAULT FALSE,
                    PRIMARY KEY (id),
                    FOREIGN KEY (platform_id) REFERENCES Platform(id)
                )
            """)

            # Create Sample Table 
            await cursor.execute("""
                CREATE TABLE IF NOT EXISTS Sample (
                    id VARCHAR(255) PRIMARY KEY,
                    platform_id VARCHAR(255),
                    title TEXT,
                    type TEXT,
                    description TEXT,
                    sample_contact_email VARCHAR(255),
                    source_name_ch1 TEXT,
                    organism_ch1 TEXT,
                    taxid_ch1 TEXT,
                    characteristics_ch1 TEXT,
                    molecule_ch1 TEXT,
                    extract_protocol_ch1 TEXT,
                    label_ch1 TEXT,
                    label_protocol_ch1 TEXT,
                    hyb_protocol TEXT,
                    scan_protocol TEXT,
                    data_processing TEXT,
                    tissue_type_id INT NULL,  
                    FOREIGN KEY (platform_id) REFERENCES Platform(id),
                    FOREIGN KEY (tissue_type_id) REFERENCES tissue_types(id) ON DELETE SET NULL
                )
            """)

            # Create SampleSeries Table
            await cursor.execute("""
                CREATE TABLE IF NOT EXISTS SampleSeries (
                    sample_id VARCHAR(255),
                    series_id VARCHAR(255),
                    PRIMARY KEY (sample_id, series_id),
                    FOREIGN KEY (sample_id) REFERENCES Sample(id) ON DELETE CASCADE,
                    FOREIGN KEY (series_id) REFERENCES Series(id) ON DELETE CASCADE
                )
            """)
            
            # Create sample_groups Table
            await cursor.execute("""
                CREATE TABLE IF NOT EXISTS sample_groups (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    disease VARCHAR(255) NOT NULL,
                    subtype VARCHAR(255) NOT NULL,
                    UNIQUE KEY unique_disease_subtype (disease, subtype)  
                )
            """)

            # Create sample_group_assignments Table
            await cursor.execute("""
                CREATE TABLE IF NOT EXISTS sample_group_assignments (
                    sample_id VARCHAR(255) NOT NULL,
                    group_id INT NOT NULL,
                    PRIMARY KEY (sample_id, group_id),
                    FOREIGN KEY (sample_id) REFERENCES Sample(id) ON DELETE CASCADE,
                    FOREIGN KEY (group_id) REFERENCES sample_groups(id) ON DELETE CASCADE
                )
            """)

            # Create GenExpression Table with gene_symbol
            await cursor.execute("""
                CREATE TABLE IF NOT EXISTS GenExpression (
                    gene_symbol TEXT,
                    sample_id VARCHAR(255),
                    platform_id VARCHAR(255),
                    value FLOAT,
                    PRIMARY KEY (gene_symbol(255), sample_id),
                    FOREIGN KEY (sample_id) REFERENCES Sample(id) ON DELETE CASCADE,
                    FOREIGN KEY (platform_id) REFERENCES Platform(id)
                )
            """)
            
            # Create MicroarrayMeasurements Table
            await cursor.execute("""
                CREATE TABLE IF NOT EXISTS MicroarrayMeasurements (
                    id_ref VARCHAR(255),
                    sample_id VARCHAR(255),
                    platform_id VARCHAR(255),
                    value FLOAT,
                    abs_call VARCHAR(255) NULL,
                    detection_p_value FLOAT NULL,
                    PRIMARY KEY (id_ref, platform_id, sample_id),
                    FOREIGN KEY (id_ref, platform_id) REFERENCES GeneAnnotations(id, platform_id),
                    FOREIGN KEY (sample_id) REFERENCES Sample(id) ON DELETE CASCADE
                )
            """)
            
            # Create FileLocation Table
            await cursor.execute("""
                CREATE TABLE IF NOT EXISTS FileLocation (
                    series_id VARCHAR(255),
                    platform_id VARCHAR(255),
                    file_location TEXT
                )
            """)

            # Create ImportStatus Table
            await cursor.execute("""
                CREATE TABLE IF NOT EXISTS ImportStatus (
                    import_id VARCHAR(36) PRIMARY KEY,
                    gse_id VARCHAR(255),
                    finished BOOLEAN,
                    progress FLOAT,
                    imports TEXT
                )
            """)

            # Create User Table
            await cursor.execute("""
                CREATE TABLE IF NOT EXISTS User (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    role VARCHAR(255) NOT NULL DEFAULT 'user',
                    username VARCHAR(255) NOT NULL UNIQUE,
                    password_hash VARCHAR(255) NOT NULL,
                    email VARCHAR(255) NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Create ExportHistory Table
            await cursor.execute("""
                CREATE TABLE IF NOT EXISTS ExportHistory (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT NULL,
                    export_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    sample_list TEXT,
                    normalization_method VARCHAR(255),
                    scaling_method BOOLEAN DEFAULT FALSE,
                    FOREIGN KEY (user_id) REFERENCES User(id) ON DELETE CASCADE 
                )
            """)
            


            # Commit all changes
            await conn.commit()
            print("Tables created or verified successfully.")
        except aiomysql.Error as e:
            print(f"Error with creating tables: {e}")
            await conn.rollback()
        finally:
            await cursor.close()
            await DatabaseConnectionManager.release_connection(conn)
