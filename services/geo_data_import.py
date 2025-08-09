import aiomysql
import uuid
import asyncio
import json
from services.geo_data_handler import GEODataHandler
from services.database_connection_manager import DatabaseConnectionManager

class GEODataImport:
    import_status = {}

    def __init__(self, db_manager):
        self.db_manager = db_manager

    async def check_sample_id_table(self, platform_id, series_id, file_path, gsm_ids=None):
        if gsm_ids is None:
            gsm_ids = GEODataHandler.extract_gsm_ids(file_path=file_path)

        if isinstance(gsm_ids, str):
            gsm_ids = gsm_ids.split(', ')

        query = """
            SELECT Sample.id
            FROM Sample
            JOIN SampleSeries ON Sample.id = SampleSeries.sample_id
            WHERE Sample.platform_id = %s AND SampleSeries.series_id = %s
        """

        conn = await self.db_manager.get_read_connection()
        cursor = await conn.cursor()
        try:
            await cursor.execute(query, (platform_id, series_id))
            existing_ids = {row[0] for row in await cursor.fetchall()}
        finally:
            await cursor.close()
            await self.db_manager.release_connection(conn)

        new_gsm_ids = [gsm_id for gsm_id in gsm_ids if gsm_id not in existing_ids]
        
        return new_gsm_ids

    async def check_gsm_id_table(self, file_path, gsm_ids=None):
        conn = await self.db_manager.get_read_connection()
        cursor = await conn.cursor()
        try:
            if gsm_ids is None:
                existing_ids = GEODataHandler.extract_gsm_ids(file_path=file_path)
                query = "SELECT sample_id FROM GenExpression"
                await cursor.execute(query)
                existing_ids_db = {row[0] for row in await cursor.fetchall()}
                new_gsm_ids = [gsm_id for gsm_id in existing_ids if gsm_id not in existing_ids_db]
            else:
                if isinstance(gsm_ids, str):
                    gsm_ids = gsm_ids.split(', ')
                placeholders = ', '.join(['%s'] * len(gsm_ids))
                query = f"SELECT sample_id FROM GenExpression WHERE sample_id IN ({placeholders})"
                await cursor.execute(query, tuple(gsm_ids))
                existing_ids = {row[0] for row in await cursor.fetchall()}
                new_gsm_ids = [gsm_id for gsm_id in gsm_ids if gsm_id not in existing_ids]
                print("GSM-ID-Table GSM-IDs to insert:", new_gsm_ids)
        finally:
            await cursor.close()
            await self.db_manager.release_connection(conn)

        return new_gsm_ids
    
    async def check_platform_exists(self, platform_id):
        conn = await self.db_manager.get_read_connection()
        cursor = await conn.cursor()
        try:
            await cursor.execute("SELECT COUNT(*) FROM Platform WHERE ID = %s", (platform_id,))
            count = (await cursor.fetchone())[0]
        finally:
            await cursor.close()
            await self.db_manager.release_connection(conn)
        return count > 0
    
    async def check_series_exists(self, gse_id):
        conn = await self.db_manager.get_read_connection()
        cursor = await conn.cursor()
        try:
            await cursor.execute("SELECT COUNT(*) FROM Series WHERE id = %s", (gse_id,))
            count = (await cursor.fetchone())[0]
        finally:
            await cursor.close()
            await self.db_manager.release_connection(conn)
        return count > 0

    async def update_progress(self, import_id, sample_id, status):
        conn = await self.db_manager.get_write_connection()
        cursor = await conn.cursor()
        try:
            await cursor.execute("SELECT imports FROM ImportStatus WHERE import_id = %s", (import_id,))
            result = await cursor.fetchone()
            if result:
                imports = json.loads(result[0])
                imports[sample_id] = status
                completed = sum(1 for status in imports.values() if status != "in progress")
                total = len(imports)
                progress = (completed / total) * 100
                finished = progress == 100
                await cursor.execute("""
                    UPDATE ImportStatus
                    SET finished = %s, progress = %s, imports = %s
                    WHERE import_id = %s
                """, (finished, progress, json.dumps(imports), import_id))
                await conn.commit()
        finally:
            await cursor.close()
            await self.db_manager.release_connection(conn)

    async def import_from_soft_file(self, file_path, platform_id, gse_id, gsm_ids=None, import_id=None, filter_p_value=False):
        GEODataImport.import_status[import_id] = {
            "finished": False,
            "progress": 1,
            "imports": {gsm_id: "in progress" for gsm_id in gsm_ids}
        }

        async def insert_platform():
            print("started importing platform data")
            conn = await self.db_manager.get_write_connection()
            cursor = await conn.cursor()
            try:
                platform_data = GEODataHandler.prepare_platform_data(file_path)
                await cursor.execute(
                    "INSERT INTO Platform (ID, Title, geo_accession, platform_organism, platform_taxid, platform_manufacturer, \
                    platform_description, platform_contact_email) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) \
                    ON DUPLICATE KEY UPDATE Title = VALUES(Title), geo_accession = VALUES(geo_accession), platform_organism = VALUES(platform_organism), \
                    platform_taxid = VALUES(platform_taxid), platform_manufacturer = VALUES(platform_manufacturer), platform_description = VALUES(platform_description), \
                    platform_contact_email = VALUES(platform_contact_email)",
                    (platform_data['platform_id'], platform_data['title'], platform_data['geo_accession'], platform_data['platform_organism'], platform_data['platform_taxid'], platform_data['platform_manufacturer'],
                    platform_data['platform_description'], platform_data['platform_contact_email'])
                )
                await conn.commit()
            except aiomysql.Error as e:
                await conn.rollback()
            finally:
                await cursor.close()
                await self.db_manager.release_connection(conn)

        async def insert_gene_annotations():
            conn = await self.db_manager.get_write_connection()
            cursor = await conn.cursor()
            try:
                gene_annotations_data = GEODataHandler.prepare_gene_annotations_data(file_path, platform_id)
                if gene_annotations_data:
                    await cursor.executemany(
                        "INSERT INTO GeneAnnotations (id, platform_id, gene_title, gene_symbol, entrez_gene_id, \
                        refseq_transcript_id) VALUES (%s, %s, %s, %s, %s, %s) \
                        ON DUPLICATE KEY UPDATE gene_title = VALUES(gene_title), gene_symbol = VALUES(gene_symbol), entrez_gene_id = VALUES(entrez_gene_id), \
                        refseq_transcript_id = VALUES(refseq_transcript_id)",
                        gene_annotations_data
                    )
                await conn.commit()
            except aiomysql.Error as e:
                await conn.rollback()
            finally:
                await cursor.close()
                await self.db_manager.release_connection(conn)

        async def insert_series():
            print("started importing insert_series_gse")

            conn = await self.db_manager.get_write_connection()
            cursor = await conn.cursor()
            try:
                series_data = GEODataHandler.prepare_series_data(file_path=file_path, gse_id=gse_id, platform_id=platform_id)
                await cursor.execute(
                    "INSERT INTO Series (id, platform_id, title, summary, pubmed_id, type, series_contact_email) VALUES (%s, %s, %s, %s, %s, %s, %s) \
                    ON DUPLICATE KEY UPDATE platform_id = VALUES(platform_id), title = VALUES(title), summary = VALUES(summary), \
                    type = VALUES(type), series_contact_email = VALUES(series_contact_email)",
                    (series_data['gse_id'], series_data['platform_id'], series_data['title'], series_data['summary'], series_data['pubmed_id'], series_data['type'], series_data['series_contact_email'])
                )
                await conn.commit()
            except aiomysql.Error as e:
                await conn.rollback()
            finally:
                await cursor.close()
                await self.db_manager.release_connection(conn)

        async def insert_samples_and_sampleseries():
            print("started importing samples")
            selected_gsm_ids = await self.check_sample_id_table(platform_id=platform_id, series_id=gse_id, file_path=file_path, gsm_ids=gsm_ids)
            sample_data = GEODataHandler.prepare_sample_data(file_path)

            if not selected_gsm_ids:
                return

            print("series id", gse_id)
            conn = await self.db_manager.get_write_connection()
            cursor = await conn.cursor()
            try:
                # Insert into Sample table
                for sample in sample_data:
                    if sample['sample_id'] in selected_gsm_ids:
                        await cursor.execute(
                            "INSERT INTO Sample (id, platform_id, title, type, description, sample_contact_email, source_name_ch1, organism_ch1, taxid_ch1, characteristics_ch1, molecule_ch1, extract_protocol_ch1, label_ch1, label_protocol_ch1, hyb_protocol, scan_protocol, data_processing) \
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) \
                            ON DUPLICATE KEY UPDATE platform_id=VALUES(platform_id), title=VALUES(title), type=VALUES(type), description=VALUES(description), sample_contact_email=VALUES(sample_contact_email), source_name_ch1=VALUES(source_name_ch1), organism_ch1=VALUES(organism_ch1), taxid_ch1=VALUES(taxid_ch1), characteristics_ch1=VALUES(characteristics_ch1), molecule_ch1=VALUES(molecule_ch1), extract_protocol_ch1=VALUES(extract_protocol_ch1), label_ch1=VALUES(label_ch1), label_protocol_ch1=VALUES(label_protocol_ch1), hyb_protocol=VALUES(hyb_protocol), scan_protocol=VALUES(scan_protocol), data_processing=VALUES(data_processing)",
                            (sample['sample_id'], sample['platform_id'], sample['title'], sample['type'], sample['description'], sample['sample_contact_email'], sample['source_name_ch1'], sample['organism_ch1'], sample['taxid_ch1'], sample['characteristics_ch1'], sample['molecule_ch1'], sample['extract_protocol_ch1'], sample['label_ch1'], sample['label_protocol_ch1'], sample['hyb_protocol'], sample['scan_protocol'], sample['data_processing'])
                        )
                await conn.commit()
            except aiomysql.Error as e:
                print(f"Error inserting samples: {e}")
                await conn.rollback()
            finally:
                await cursor.close()
                await self.db_manager.release_connection(conn)

            await asyncio.sleep(1)

            conn = await self.db_manager.get_write_connection()
            cursor = await conn.cursor()
            try:
                # Insert into SampleSeries table
                # hier werden dennoch alle samples eingefügt, auch wenn sie nicht in selected_gsm_ids sind
                for sample in sample_data:
                    if sample['sample_id'] in selected_gsm_ids:
                        await cursor.execute(
                            "INSERT INTO SampleSeries (sample_id, series_id) VALUES (%s, %s) \
                            ON DUPLICATE KEY UPDATE sample_id=sample_id",
                            (sample['sample_id'], gse_id)
                        )
                await conn.commit()
            except aiomysql.Error as e:
                print(f"Error inserting sample series: {e}")
                await conn.rollback()
            finally:
                await cursor.close()
                await self.db_manager.release_connection(conn)

        async def insert_gen_expression():
            try:
                # Step 1: Fetch GSM IDs to Importw
                selected_gsm_ids = await self.check_gsm_id_table(file_path, gsm_ids)

                if not selected_gsm_ids:
                    GEODataImport.import_status[import_id]["finished"] = True
                    return

                gsms_to_import = [gsm_id for gsm_id in gsm_ids if gsm_id in selected_gsm_ids]
                parsed_gsms = GEODataHandler.parse_gsm(file_path, gsms_to_import)

                for sample_id, gsm in parsed_gsms.items():
                    await self.update_progress(import_id, sample_id, "inserting raw GSM data...")
                    conn = await self.db_manager.get_write_connection()
                    cursor = await conn.cursor()
                    try:
                        # Clear  sample_id in `MicroarrayMeasurements`
                        await cursor.execute("DELETE FROM MicroarrayMeasurements WHERE sample_id = %s", (sample_id,))
                        
                        gsm_data = []
                        for _, row in gsm.table.iterrows():
                            abs_call = row.get('ABS_CALL')
                            detection_p_value = row.get('DETECTION P-VALUE')

                            # Apply filter logic
                            if filter_p_value:
                                
                                if abs_call == 'P' and detection_p_value and float(detection_p_value) < 0.05:
                                    gsm_data.append((
                                        GEODataHandler.clean_value(row, 'ID_REF'),
                                        GEODataHandler.clean_value(sample_id),
                                        GEODataHandler.clean_value(platform_id),
                                        GEODataHandler.clean_value(row, 'VALUE', is_float=True),
                                        GEODataHandler.clean_value(abs_call),
                                        GEODataHandler.clean_value(detection_p_value, is_float=True)
                                    ))
                            else:
                                # No filter
                                gsm_data.append((
                                    GEODataHandler.clean_value(row, 'ID_REF'),
                                    GEODataHandler.clean_value(sample_id),
                                    GEODataHandler.clean_value(platform_id),
                                    GEODataHandler.clean_value(row, 'VALUE', is_float=True),
                                    GEODataHandler.clean_value(abs_call),
                                    GEODataHandler.clean_value(detection_p_value, is_float=True)
                                ))

                        if not gsm_data:
                            print(f"No valid data to import for sample {sample_id} based on filter criteria.")
                            await self.update_progress(import_id, sample_id, "no valid data")
                            continue

                        # Step 2: Insert Raw Data
                        if gsm_data:
                            await cursor.executemany(
                                """
                                INSERT INTO MicroarrayMeasurements (id_ref, sample_id, platform_id, value, abs_call, detection_p_value)
                                VALUES (%s, %s, %s, %s, %s, %s)
                                """,
                                gsm_data
                            )
                            await conn.commit()
                            print(f"Inserted raw data into MicroarrayMeasurements for sample {sample_id}")

                        # Step 3: Aggregating Data by Gene Symbol, Sample, and Platform
                        await self.update_progress(import_id, sample_id, "aggregating data...")
                        
                        await cursor.execute(
                            """
                            INSERT INTO GenExpression (gene_symbol, sample_id, platform_id, value)
                            SELECT
                                ga.gene_symbol,
                                mm.sample_id,
                                mm.platform_id,
                                AVG(mm.value) AS avg_value
                            FROM
                                MicroarrayMeasurements mm
                            JOIN
                                GeneAnnotations ga ON mm.id_ref = ga.id AND mm.platform_id = ga.platform_id
                            WHERE
                                mm.sample_id = %s
                            GROUP BY
                                mm.sample_id, ga.gene_symbol, mm.platform_id  
                            """,
                            (sample_id,)
                        )
                        await conn.commit()
                        print(f"Aggregated and inserted data into GenExpression for sample {sample_id}")

                        await self.update_progress(import_id, sample_id, "completed")

                    except Exception as e:
                        await conn.rollback()
                        print(f"Error while inserting GenExpression data for sample {sample_id}: {e}")
                        
                        # Deleting the associated Sample data in case of failure
                        await cursor.execute(
                            "DELETE FROM Sample WHERE id = %s",
                            (sample_id,)
                        )
                        await conn.commit()
                        await self.update_progress(import_id, sample_id, "failed")

                    finally:
                        await cursor.close()
                        await self.db_manager.release_connection(conn)

            except Exception as e:
                print("Error while inserting GenExpression data:", e)




        if not await self.check_platform_exists(platform_id):
            await insert_platform()
            await asyncio.sleep(1)
            await insert_gene_annotations()
            await asyncio.sleep(1)
            
        if not await self.check_series_exists(gse_id):
            await insert_series()
            await asyncio.sleep(1)
            
        await insert_samples_and_sampleseries()
        await asyncio.sleep(1)
        
        await insert_gen_expression()
        
        return import_id

    async def get_import_status(self, import_id):
        conn = await self.db_manager.get_read_connection()
        cursor = await conn.cursor()
        try:
            await cursor.execute("SELECT gse_id, finished, progress, imports FROM ImportStatus WHERE import_id = %s", (import_id,))
            result = await cursor.fetchone()
            if result:
                gse_id, finished, progress, imports = result
                return {
                    "gse_id": gse_id,
                    "finished": finished,
                    "progress": progress,
                    "imports": json.loads(imports)
                }
            else:
                return self.import_status_none()
        finally:
            await cursor.close()
            await self.db_manager.release_connection(conn)

    def import_status_none(self):
        return {
            "status": "unknown",
            "message": "No status available for this import ID.",
            "progress": 0,
            "details": {}
        }

    async def get_ongoing_import_id(self, gse_id):
        conn = await self.db_manager.get_read_connection()
        cursor = await conn.cursor()
        try:
            await cursor.execute("SELECT import_id FROM ImportStatus WHERE gse_id = %s AND finished = 0", (gse_id,))
            result = await cursor.fetchone()
            if result:
                return result[0]
            else:
                return None
        finally:
            await cursor.close()
            await self.db_manager.release_connection(conn)

    async def start_import(self, file_path, platform_id, gse_id, gsm_ids=None, import_id=None, filter_p_value=False):
        if not file_path:
            return None

        if import_id is None:
            import_id = str(uuid.uuid4())

        # Pass filter_p_value to the import_from_soft_file method
        asyncio.create_task(self.import_from_soft_file(file_path, platform_id, gse_id, gsm_ids, import_id, filter_p_value))

        await self.insert_import_status_in_db(import_id, gse_id, gsm_ids)
        return import_id

    async def generate_import_id(self):
        return str(uuid.uuid4())

    async def insert_import_status_in_db(self, import_id, gse_id, gsm_ids):
        conn = await self.db_manager.get_write_connection()
        cursor = await conn.cursor()
        try:
            imports = json.dumps({gsm_id: "in progress" for gsm_id in gsm_ids})
            await cursor.execute("""
                INSERT INTO ImportStatus (import_id, gse_id, finished, progress, imports)
                VALUES (%s, %s, %s, %s, %s)
            """, (import_id, gse_id, 0, 1.0, imports))
            await conn.commit()
        finally:
            await cursor.close()
            await self.db_manager.release_connection(conn)

    async def update_import_status_in_db(self, import_id, status_data):
        conn = await self.db_manager.get_write_connection()
        cursor = await conn.cursor()
        try:
            imports = json.dumps(status_data["imports"])
            await cursor.execute("""
                UPDATE ImportStatus
                SET finished = %s, progress = %s, imports = %s
                WHERE import_id = %s
            """, (status_data["finished"], status_data["progress"], imports, import_id))
            await conn.commit()
        finally:
            await cursor.close()
            await self.db_manager.release_connection(conn)
